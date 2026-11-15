"""Verified, non-recursive relocation of LocalCinema playback cache only."""
import os
import re
import shutil
import sqlite3
import uuid
from pathlib import Path
from contextlib import closing
from conversion_store import file_hash

CACHE_NAME=re.compile(r"[0-9a-f]{64}\.mp4",re.I)

def playback_directory(db_path,default):
    with closing(sqlite3.connect(db_path)) as db:
        row=db.execute("SELECT value FROM app_settings WHERE key='playback_directory'").fetchone()
    return Path(row[0]) if row else Path(default)

def relocate_playback(source,destination,db_path):
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
    for path in files:
        before=path.stat(); target=destination/path.name
        digest=file_hash(path)
        if target.exists():
            if target.is_symlink() or not target.is_file() or target.stat().st_size!=before.st_size or file_hash(target)!=digest:
                raise ValueError('新目錄已有不同內容的同名快取；未覆蓋，舊快取保留。')
        else:
            temporary=destination/('.'+path.name+'.'+uuid.uuid4().hex+'.part')
            try:
                with path.open('rb') as reader,temporary.open('xb') as writer:
                    shutil.copyfileobj(reader,writer,1024*1024); writer.flush(); os.fsync(writer.fileno())
                shutil.copystat(path,temporary)
                if file_hash(temporary)!=digest: raise OSError('快取副本驗證失敗；舊快取保留。')
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
        for path,target,digest,size,mtime in verified:
            stamp=target.stat()
            db.execute('UPDATE conversion_records SET output_path=?,output_size=?,output_mtime=? WHERE output_path=?',
                       (str(target),stamp.st_size,stamp.st_mtime_ns,str(path)))
        db.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES ('playback_directory',?)",(str(destination),))
    retained=0
    for path,target,digest,size,mtime in verified:
        try:
            stamp=path.stat()
            if (stamp.st_size,stamp.st_mtime_ns)!=(size,mtime) or file_hash(target)!=digest: raise OSError('快取已變更')
            path.unlink()  # Verified generated cache copy only; never source media.
        except OSError: retained+=1
    return {'moved':len(verified),'bytes':sum(row[3] for row in verified),'retained':retained}
