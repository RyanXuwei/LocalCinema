"""Persistent review records and explicit, verified promotion of converted media."""
import os
import sqlite3
import hashlib
import threading
import time
import uuid
import re
from operation_progress import report,tracked_hash
from pathlib import Path
from contextlib import contextmanager


def file_hash(path,progress=None):
    digest=hashlib.sha256()
    size=Path(path).stat().st_size;done=0;last=0
    if progress:progress(0,size)
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block);done+=len(block)
            if progress and time.monotonic()-last>=.15:progress(done,size);last=time.monotonic()
    if progress:progress(done,size)
    return digest.hexdigest()


def recycle_file(path):
    # Explicitly require the modern Windows recycler; never fall back to unlink.
    if os.name!='nt': raise OSError('原檔回收功能僅支援Windows。')
    try:
        from send2trash.win.modern import send2trash
    except ImportError as error:
        raise OSError('請先執行「安裝套件.cmd」安裝安全回收套件，再重試；原檔未刪除。') from error
    send2trash(str(path))


class ConversionStore:
    def __init__(self,db_path):
        self.path=Path(db_path); self.lock=threading.RLock()
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS conversion_records(
                    id TEXT PRIMARY KEY, source_path TEXT NOT NULL, source_size INTEGER NOT NULL,
                    source_mtime INTEGER NOT NULL, output_path TEXT NOT NULL, output_size INTEGER NOT NULL,
                    output_mtime INTEGER NOT NULL, status TEXT NOT NULL, confirmed_at REAL,
                    saved_path TEXT, saved_sha TEXT, item_id TEXT, episode_id TEXT, title TEXT,
                    created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS media_replacements(
                    new_path TEXT PRIMARY KEY, old_path TEXT NOT NULL, item_id TEXT,
                    episode_id TEXT NOT NULL, title TEXT, episode_name TEXT NOT NULL);
            ''')
            db.execute('CREATE TABLE IF NOT EXISTS cache_copies(cache_path TEXT PRIMARY KEY,saved_path TEXT NOT NULL,sha256 TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS cache_moves(old_path TEXT PRIMARY KEY,new_path TEXT NOT NULL,sha256 TEXT NOT NULL)')
            # Completed audit rows are disposable; playback identity aliases remain.
            db.execute("DELETE FROM conversion_records WHERE status='replaced'")
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=20); db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()
    def get(self,key):
        with self.db() as db: row=db.execute('SELECT * FROM conversion_records WHERE id=?',(key,)).fetchone()
        if row is None: raise ValueError('找不到轉檔記錄。')
        return dict(row)
    def records(self):
        with self.db() as db: return [dict(row) for row in db.execute('SELECT * FROM conversion_records ORDER BY updated DESC')]
    def register(self,key,source,output,item_id=None,episode_id=None,title=None):
        source,output=Path(source),Path(output); original=source.stat(); converted=output.stat()
        if converted.st_size<=0: raise ValueError('轉檔成品為空。')
        try: existing=self.get(key)
        except ValueError: existing=None
        if existing and (existing['source_size'],existing['source_mtime'],existing['output_size'],existing['output_mtime'])==(original.st_size,original.st_mtime_ns,converted.st_size,converted.st_mtime_ns) and (not item_id or existing['item_id']==item_id) and (not episode_id or existing['episode_id']==episode_id): return
        with self.lock,self.db() as db:
            old=db.execute('SELECT * FROM conversion_records WHERE id=?',(key,)).fetchone()
            if old and old['status']=='replaced': return
            unchanged=old and (old['source_size'],old['source_mtime'],old['output_size'],old['output_mtime'])==(original.st_size,original.st_mtime_ns,converted.st_size,converted.st_mtime_ns)
            status=old['status'] if unchanged else 'ready'
            confirmed=old['confirmed_at'] if unchanged else None
            now=time.time()
            db.execute('''INSERT INTO conversion_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET source_path=excluded.source_path, source_size=excluded.source_size,
                source_mtime=excluded.source_mtime, output_path=excluded.output_path, output_size=excluded.output_size,
                output_mtime=excluded.output_mtime, status=excluded.status, confirmed_at=excluded.confirmed_at, saved_path=excluded.saved_path, saved_sha=excluded.saved_sha,
                item_id=COALESCE(excluded.item_id,conversion_records.item_id),
                episode_id=COALESCE(excluded.episode_id,conversion_records.episode_id),
                title=COALESCE(excluded.title,conversion_records.title)''',
                (key,str(source.absolute()),original.st_size,original.st_mtime_ns,str(output.absolute()),converted.st_size,
                 converted.st_mtime_ns,status,confirmed,old['saved_path'] if unchanged else None,
                 old['saved_sha'] if unchanged else None,item_id,episode_id,title,old['created'] if old else now,now))
    def review_path(self,key):
        row=self.get(key); path=Path(row['saved_path'] or row['output_path'])
        if not path.is_file(): raise ValueError('成品已不存在，請重新轉檔。')
        return path
    def confirm(self,key,progress=None):
        with self.lock:
            row=self.get(key)
            if row['status']=='replaced': return
            source=Path(row['source_path']); output=self.review_path(key)
            if source.exists() or not row['saved_path']: self.check_source(row,source)
            if row['saved_sha']:
                if tracked_hash(file_hash,output,progress,'確認已保存成品')!=row['saved_sha']: raise ValueError('保留的MP4已變更，請重新檢查。')
            else: self.check_output(row,output)
            with self.db() as db:
                db.execute('UPDATE conversion_records SET status=?,confirmed_at=?,updated=? WHERE id=?',
                           ('saved' if row['saved_path'] else 'confirmed',time.time(),time.time(),key))
    @staticmethod
    def check_source(row,source):
        if not source.is_file() or source.is_symlink(): raise ValueError('原檔不存在或為符號連結；不執行刪除。')
        stamp=source.stat()
        if (stamp.st_size,stamp.st_mtime_ns)!=(row['source_size'],row['source_mtime']):
            raise ValueError('原檔在轉檔後已變更，請重新轉檔確認；不執行刪除。')
    @staticmethod
    def check_output(row,output):
        if not output.is_file() or output.is_symlink(): raise ValueError('轉檔成品不存在或為符號連結。')
        stamp=output.stat()
        if (stamp.st_size,stamp.st_mtime_ns)!=(row['output_size'],row['output_mtime']):
            raise ValueError('成品已變更，請重新轉檔確認；不執行刪除。')
    def promote(self,key,recycler=recycle_file,progress=None):
        with self.lock:
            row=self.get(key)
            if row['status']=='replaced': return Path(row['saved_path'])
            if not row['confirmed_at'] or row['status'] not in ('confirmed','saved'):
                raise ValueError('必須先手動檢查成品並標記「已確認」。')
            source=Path(row['source_path'])
            # A previously saved copy survives a failed recycle operation or a restart.
            if row['saved_path']:
                destination=Path(row['saved_path'])
                if not destination.is_file() or tracked_hash(file_hash,destination,progress,'驗證保存MP4')!=row['saved_sha']:
                    raise ValueError('保留的MP4不存在或已變更，原檔不會刪除。')
            else:
                self.check_source(row,source); output=Path(row['output_path']); self.check_output(row,output)
                destination=source.with_suffix('.mp4')
                if destination.exists(): destination=source.with_name(source.stem+'.converted-'+key[:8]+'.mp4')
                if destination.exists(): raise ValueError('目標MP4已存在；不覆蓋任何既有檔案。')
                temporary=destination.with_name('.'+destination.name+'.'+uuid.uuid4().hex+'.part')
                try:
                    digest=hashlib.sha256()
                    with output.open('rb') as reader,temporary.open('xb') as writer:
                        done=0;size=output.stat().st_size
                        for block in iter(lambda:reader.read(1024*1024),b''):
                            writer.write(block); digest.update(block);done+=len(block)
                            report(progress,'保存MP4',done=done,size=size)
                        writer.flush(); os.fsync(writer.fileno())
                    self.check_source(row,source); self.check_output(row,output)
                    if tracked_hash(file_hash,temporary,progress,'驗證MP4副本')!=digest.hexdigest(): raise ValueError('MP4副本驗證失敗；原檔未刪除。')
                    stamp=source.stat(); os.utime(temporary,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
                    try: os.link(temporary,destination)
                    except OSError:
                        if os.name!='nt': raise
                        os.rename(temporary,destination)  # Windows rename refuses an existing destination.
                    with self.db() as db:
                        db.execute('UPDATE conversion_records SET saved_path=?,saved_sha=?,status=?,updated=? WHERE id=?',
                                   (str(destination),digest.hexdigest(),'saved',time.time(),key))
                    row=self.get(key)
                finally:
                    temporary.unlink(missing_ok=True)
            if destination.is_symlink() or tracked_hash(file_hash,destination,progress,'驗證保存MP4')!=row['saved_sha']:
                raise ValueError('保存的MP4驗證失敗；原檔與快取保留。')
            if source.exists():
                self.check_source(row,source)
                report(progress,'回收原檔')
                recycler(source)
                if source.exists(): raise OSError('原檔仍存在；MP4已保留，未標記為完成。')
            if not destination.is_file() or tracked_hash(file_hash,destination,progress,'驗證保存MP4')!=row['saved_sha']:
                raise ValueError('保存的MP4已變更；快取與記錄保留。')
            episode=row['episode_id'] or hashlib.sha256(str(source.resolve()).casefold().encode()).hexdigest()[:24]
            with self.db() as db:
                db.execute('INSERT OR REPLACE INTO media_replacements VALUES(?,?,?,?,?,?)',
                           (str(destination.resolve()).casefold(),str(source),row['item_id'] or episode,episode,row['title'] or source.stem,source.stem))
                db.execute('INSERT OR REPLACE INTO cache_copies VALUES(?,?,?)',(row['output_path'],str(destination),row['saved_sha']))
                db.execute('DELETE FROM conversion_records WHERE id=?',(key,))
            # Failure to clean a duplicate must never undo successful preservation.
            try:self.cleanup_cache(Path(row['output_path']).parent,only_path=row['output_path'],progress=progress)
            except (OSError,sqlite3.Error,ValueError,RuntimeError):pass
            return destination
    def cleanup_cache(self,directory,legacy=False,only_path=None,progress=None):
        """Delete only generated cache with a second verified, saved copy."""
        report(progress,'盤點重複快取')
        directory=Path(directory).resolve(); freed=count=0; retained=0
        with self.lock:
            with self.db() as db:
                protected={str(Path(value).resolve()).casefold() for row in db.execute('SELECT source_path,output_path,saved_path FROM conversion_records') for value in row if value}
                copies={r[0]:(r[1],r[2]) for r in db.execute('SELECT cache_path,saved_path,sha256 FROM cache_copies')}
                aliases=[Path(r[0]) for r in db.execute('SELECT new_path FROM media_replacements')] if legacy else []
            if legacy and directory.is_dir():
                # Hash only candidates of matching size, and each saved copy once.
                by_size={}
                for saved in aliases:
                    try:
                        if saved.is_file() and not saved.is_symlink():by_size.setdefault(saved.stat().st_size,[]).append(saved)
                    except OSError:pass
                hashes={}
                candidates_list=list(directory.iterdir())
                for index,cache in enumerate(candidates_list,1):
                    report(progress,'比對舊版快取',index,len(candidates_list))
                    if not re.fullmatch(r'[0-9a-fA-F]{64}\.mp4',cache.name) or str(cache) in copies:continue
                    if str(cache.resolve()).casefold() in protected or cache.is_symlink() or not cache.is_file():continue
                    try:
                        candidates=by_size.get(cache.stat().st_size,[])
                        if not candidates:continue
                        digest=tracked_hash(file_hash,cache,progress,'核對快取',index,len(candidates_list))
                        for saved in candidates:
                            if saved not in hashes:hashes[saved]=tracked_hash(file_hash,saved,progress,'核對保存副本',index,len(candidates_list))
                            if hashes[saved]==digest:
                                copies[str(cache)]=(str(saved),digest)
                                with self.db() as db:db.execute('INSERT OR REPLACE INTO cache_copies VALUES(?,?,?)',(str(cache),str(saved),digest))
                                break
                    except OSError:continue
            for index,(name,(saved_name,digest)) in enumerate(copies.items(),1):
                report(progress,'驗證並清理快取',index,len(copies))
                cache=Path(name);saved=Path(saved_name)
                if only_path is not None and str(cache)!=str(only_path):continue
                if cache.parent.resolve()!=directory or not re.fullmatch(r'[0-9a-fA-F]{64}\.mp4',cache.name):continue
                if str(cache.resolve()).casefold() in protected:continue
                try:
                    if not cache.exists():continue
                    if cache.is_symlink() or saved.is_symlink() or cache.resolve()==saved.resolve():continue
                    before=cache.stat()
                    if not saved.is_file() or tracked_hash(file_hash,saved,progress,'複核保存副本',index,len(copies))!=digest or tracked_hash(file_hash,cache,progress,'複核快取',index,len(copies))!=digest:
                        retained+=1;continue
                    after=cache.stat()
                    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):retained+=1;continue
                    cache.unlink();freed+=before.st_size;count+=1
                except OSError:retained+=1
        return {'removed':count,'bytes':freed,'retained':retained}
    def apply_aliases(self,items):
        with self.db() as db: aliases={row['new_path']:dict(row) for row in db.execute('SELECT * FROM media_replacements')}
        for item in items:
            for episode in item['episodes']:
                path=Path(episode['path']); alias=aliases.get(str(path.resolve()).casefold())
                if not alias: continue
                flat_id=hashlib.sha256(str(path.resolve()).casefold().encode()).hexdigest()[:24]
                episode['id']=alias['episode_id']; episode['name']=alias['episode_name']
                if item['id']==flat_id: item['id']=alias['item_id']; item['title']=alias['title']
        return items


class AutoPromoter:
    """Session-only opt-in; failed snapshots wait for explicit retry."""
    def __init__(self,store,on_success,log,recycler=recycle_file,progress=None):
        self.store=store; self.on_success=on_success; self.log=log; self.recycler=recycler;self.progress=progress
        self.lock=threading.RLock(); self.enabled=False; self.busy=False
        self.failed={}; self.stop_event=threading.Event(); self.worker=None
        self.completed=0; self.errors=0
    def set_enabled(self,enabled):
        with self.lock:
            self.enabled=bool(enabled)
            if enabled:
                self.failed.clear(); self.errors=0
                if self.worker is None:
                    self.worker=threading.Thread(target=self.run,daemon=True); self.worker.start()
    def process_pending(self):
        with self.lock:
            if not self.enabled or self.stop_event.is_set():return
        success=0
        for row in self.store.records():
            stamp=tuple(row[k] for k in ('source_size','source_mtime','output_size','output_mtime'))
            with self.lock:
                if not self.enabled or self.stop_event.is_set(): break
                if self.failed.get(row['id'])==stamp: continue
                self.busy=True
            try:
                self.store.confirm(row['id'],progress=self.progress)
                self.store.promote(row['id'],recycler=self.recycler,progress=self.progress)
                success+=1; self.completed+=1
            except Exception:
                self.failed[row['id']]=stamp; self.errors+=1
                self.log('自動保留MP4未完成：項目已保留，請取消勾選後檢查；重新勾選可重試。')
            finally:
                with self.lock: self.busy=False
        if success:
            self.on_success()
            self.log(f'自動保留MP4並回收原檔：完成 {success} 筆。')
    def run(self):
        while not self.stop_event.is_set():
            try: self.process_pending()
            except Exception: self.log('自動保留MP4暫未完成，稍後重新檢查。')
            if self.stop_event.wait(.5): break
    def close(self):
        with self.lock: self.enabled=False; self.stop_event.set()
        if self.worker: self.worker.join()
