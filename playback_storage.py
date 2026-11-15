"""Verified, non-recursive relocation of LocalCinema playback cache only."""
import os
import re
import shutil
import sqlite3
import uuid
import subprocess
from pathlib import Path
from contextlib import closing
from conversion_store import file_hash
from operation_progress import report,tracked_hash

CACHE_NAME=re.compile(r"[0-9a-f]{64}\.mp4",re.I)

def playback_directory(db_path,default):
    with closing(sqlite3.connect(db_path)) as db:
        row=db.execute("SELECT value FROM app_settings WHERE key='playback_directory'").fetchone()
    return Path(row[0]) if row else Path(default)

def relocate_playback(source,destination,db_path,progress=None):
    report(progress,'盤點快取')
    source=Path(source).absolute(); destination=Path(destination).absolute()
    if source.is_symlink() or destination.is_symlink():
        raise ValueError('快取目錄不可為符號連結。')
    source=source.resolve(); destination=destination.resolve()
    if source==destination: return {'moved':0,'bytes':0,'retained':0}
    if source in destination.parents or destination in source.parents:
        raise ValueError('新舊目錄不可互相包含。')
    destination.mkdir(parents=True,exist_ok=True)
    files=[]
    if source.exists():
        for path in source.iterdir():
            if CACHE_NAME.fullmatch(path.name):
                if path.is_symlink() or not path.is_file(): raise ValueError('快取項目不是一般檔案。')
                files.append(path)
    # No recursive search and no arbitrary media-file migration.
    sizes=sum(path.stat().st_size for path in files if not (destination/path.name).exists())
    if shutil.disk_usage(destination).free<sizes:
        raise OSError('新目錄空間不足；舊快取未移除。')
    verified=[]
    for index,path in enumerate(files,1):
        before=path.stat(); target=destination/path.name
        digest=tracked_hash(file_hash,path,progress,'核對來源',index,len(files))
        if target.exists():
            if target.is_symlink() or not target.is_file() or target.stat().st_size!=before.st_size or tracked_hash(file_hash,target,progress,'驗證既有副本',index,len(files))!=digest:
                raise ValueError('新目錄已有不同內容的同名快取；未覆蓋，舊快取保留。')
        else:
            temporary=destination/('.'+path.name+'.'+uuid.uuid4().hex+'.part')
            try:
                with path.open('rb') as reader,temporary.open('xb') as writer:
                    done=0
                    while True:
                        block=reader.read(1024*1024)
                        if not block:break
                        writer.write(block);done+=len(block);report(progress,'複製快取',index,len(files),done,before.st_size)
                    writer.flush(); os.fsync(writer.fileno())
                shutil.copystat(path,temporary)
                if tracked_hash(file_hash,temporary,progress,'驗證新副本',index,len(files))!=digest: raise OSError('快取副本驗證失敗；舊快取保留。')
                # Both paths are on destination's filesystem. Never overwrite.
                try: os.link(temporary,target)
                except OSError:
                    if os.name!='nt': raise
                    os.rename(temporary,target)
            finally: temporary.unlink(missing_ok=True)
        after=path.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise OSError('搬移期間快取已變更；舊快取保留。')
        verified.append((path,target,digest,before.st_size,before.st_mtime_ns))
    # Commit paths and directory together; other library and identity data stay untouched.
    with closing(sqlite3.connect(db_path,timeout=20)) as db,db:
        for index,(path,target,digest,size,mtime) in enumerate(verified,1):
            if tracked_hash(file_hash,path,progress,'提交前複核來源',index,len(verified))!=digest or tracked_hash(file_hash,target,progress,'提交前複核副本',index,len(verified))!=digest:
                raise OSError('搬移提交前二次驗證失敗；舊快取保留。')
            stamp=target.stat()
            db.execute('UPDATE conversion_records SET output_path=?,output_size=?,output_mtime=? WHERE output_path=?',
                       (str(target),stamp.st_size,stamp.st_mtime_ns,str(path)))
            db.execute('UPDATE cache_copies SET cache_path=? WHERE cache_path=?',(str(target),str(path)))
            db.execute('INSERT OR REPLACE INTO cache_moves VALUES(?,?,?)',(str(path),str(target),digest))
        db.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES ('playback_directory',?)",(str(destination),))
    cleanup=cleanup_moved_copies(db_path,progress=progress)
    return {'moved':len(verified),'bytes':sum(row[3] for row in verified),'retained':cleanup['retained']}


def cleanup_moved_copies(db_path,progress=None):
    removed=freed=retained=0
    with closing(sqlite3.connect(db_path,timeout=20)) as db:
        rows=list(db.execute('SELECT old_path,new_path,sha256 FROM cache_moves'))
        protected={str(Path(value).resolve()).casefold() for row in db.execute('SELECT source_path,output_path,saved_path FROM conversion_records') for value in row if value}
    for index,(old_name,new_name,digest) in enumerate(rows,1):
        report(progress,'核對搬移後舊檔',index,len(rows))
        old=Path(old_name);new=Path(new_name)
        if str(old.resolve()).casefold() in protected:retained+=1;continue
        try:
            if not CACHE_NAME.fullmatch(old.name) or old.name!=new.name or old.resolve()==new.resolve():retained+=1;continue
            if old.is_symlink() or new.is_symlink():retained+=1;continue
            if old.exists():
                before=old.stat()
                if not new.is_file() or tracked_hash(file_hash,old,progress,'清理前複核舊檔',index,len(rows))!=digest or tracked_hash(file_hash,new,progress,'清理前複核新檔',index,len(rows))!=digest:retained+=1;continue
                after=old.stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):retained+=1;continue
                old.unlink();removed+=1;freed+=before.st_size
            with closing(sqlite3.connect(db_path,timeout=20)) as db,db:
                db.execute('DELETE FROM cache_moves WHERE old_path=?',(old_name,))
        except (OSError,sqlite3.Error):retained+=1
    return {'removed':removed,'bytes':freed,'retained':retained}



def cache_usage(directory):
    directory=Path(directory);total=count=0
    if directory.is_dir():
        for path in directory.iterdir():
            if CACHE_NAME.fullmatch(path.name) and not path.is_symlink() and path.is_file():
                try:total+=path.stat().st_size;count+=1
                except OSError:pass
    parent=directory
    while not parent.exists() and parent!=parent.parent:parent=parent.parent
    return {'bytes':total,'files':count,'free':shutil.disk_usage(parent).free}

def wait_for_conversion(process,directory,stop_event,min_free=256*1024*1024):
    def stop():
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    while process.poll() is None:
        try:free=shutil.disk_usage(directory).free
        except OSError:
            stop();raise
        if free<min_free:
            stop()
            raise OSError('快取磁碟空間不足，已停止轉檔並保留原檔。')
        if stop_event.wait(1):return process.wait()
    return process.returncode
