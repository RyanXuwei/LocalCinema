"""Scheduled and manual backups of the library database and its config, with guarded restore."""
import json,re,sqlite3,threading,time
from datetime import datetime,timezone
from pathlib import Path

NAME=re.compile(r'library-(\d{8}T\d{12}Z)-(automatic|manual|pre-restore)\.sqlite3')
INTERVALS={1:'每小時',6:'每 6 小時',24:'每天',168:'每週'}

def stamp(now=None):
    return datetime.fromtimestamp(now if now is not None else time.time(),timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')

def parse(name):
    match=NAME.fullmatch(name or '')
    if not match:return None
    moment=datetime.strptime(match.group(1),'%Y%m%dT%H%M%S%fZ').replace(tzinfo=timezone.utc)
    return moment.timestamp(),match.group(2)

def copy_database(source,target):
    """SQLite online backup: consistent even while other connections write."""
    source_connection=sqlite3.connect(source,timeout=15);target_connection=sqlite3.connect(target,timeout=15)
    try:
        source_connection.backup(target_connection)
        result=target_connection.execute('PRAGMA integrity_check').fetchone()[0]
        if result!='ok':raise ValueError('備份檔完整性檢查失敗：'+str(result))
    finally:target_connection.close();source_connection.close()

class DatabaseBackups:
    def __init__(self,db_path,folder,config,save,log=lambda text:None,on_restore=lambda:None,config_path=None):
        self.db_path=Path(db_path);self.folder=Path(folder);self.config=config;self.save=save;self.log=log
        self.on_restore=on_restore;self.config_path=Path(config_path) if config_path else None
        self.lock=threading.RLock();self.stop=threading.Event();self.worker=None;self.last_error=''
    # settings
    def settings(self):
        hours=int(self.config.get('backup_interval_hours',24));days=int(self.config.get('backup_retention_days',7))
        return {'enabled':bool(self.config.get('backup_enabled',False)),'hours':hours if hours in INTERVALS else 24,'days':max(1,min(3650,days))}
    def configure(self,enabled,hours,days):
        hours=int(hours);days=int(days)
        if hours not in INTERVALS:raise ValueError('備份頻率不正確。')
        if not 1<=days<=3650:raise ValueError('保留天數需為 1 至 3650 天。')
        with self.lock:
            self.config['backup_enabled']=bool(enabled);self.config['backup_interval_hours']=hours;self.config['backup_retention_days']=days
            self.save(self.config)
        self.log('定期備份已'+('啟用：'+INTERVALS[hours]+f'，保留 {days} 天。' if enabled else '停用。'))
    # files
    def list(self):
        if not self.folder.is_dir():return []
        result=[]
        for path in self.folder.iterdir():
            info=parse(path.name)
            if info and path.is_file():
                result.append({'name':path.name,'time':info[0],'kind':info[1],'size':path.stat().st_size,
                               'config':self.config_copy(path).is_file()})
        return sorted(result,key=lambda entry:entry['time'],reverse=True)
    def config_copy(self,path):
        return Path(path).with_suffix('.config.json')
    def latest(self):
        entries=[entry for entry in self.list() if entry['kind']!='pre-restore']
        return entries[0] if entries else None
    def create(self,kind='manual'):
        if kind not in ('automatic','manual','pre-restore'):raise ValueError('備份類型錯誤。')
        with self.lock:
            self.folder.mkdir(parents=True,exist_ok=True)
            name=f'library-{stamp()}-{kind}.sqlite3';target=self.folder/name;temporary=self.folder/(name+'.partial')
            try:
                copy_database(self.db_path,temporary);temporary.replace(target)
                (self.folder/(name.removesuffix('.sqlite3')+'.config.json')).write_text(json.dumps(self.config,ensure_ascii=False,indent=2),'utf-8')
            finally:temporary.unlink(missing_ok=True)
            self.last_error=''
            return name
    def prune(self,now=None):
        """Delete backups older than the retention period; the newest backup always stays."""
        days=self.settings()['days'];cutoff=(now or time.time())-days*86400;removed=[]
        entries=self.list()
        for entry in entries[1:]:
            if entry['time']<cutoff:
                path=self.folder/entry['name']
                path.unlink(missing_ok=True);self.config_copy(path).unlink(missing_ok=True);removed.append(entry['name'])
        return removed
    def restore(self,name,confirm,include_config=True):
        if confirm!=name:raise ValueError('請輸入完整的備份檔名以確認還原。')
        if not parse(name):raise ValueError('備份檔名格式錯誤。')
        source=self.folder/name
        if not source.is_file():raise ValueError('找不到這個備份檔。')
        with self.lock:
            check=sqlite3.connect(source)
            try:
                if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('備份檔已損壞，無法還原。')
            finally:check.close()
            safety=self.create('pre-restore')
            copy_database(source,self.db_path)
            config_file=self.config_copy(source)
            if include_config and config_file.is_file():
                restored=json.loads(config_file.read_text('utf-8'))
                if not isinstance(restored,dict) or not isinstance(restored.get('groups'),list):raise ValueError('備份的設定檔格式錯誤。')
                for key in ('backup_enabled','backup_interval_hours','backup_retention_days'):
                    if key in self.config:restored[key]=self.config[key]
                self.config.clear();self.config.update(restored);self.save(self.config)
        self.log(f'已從 {name} 還原；還原前的資料保存在 {safety}。')
        self.on_restore()
        return safety
    # schedule
    def due(self,now=None):
        settings=self.settings()
        if not settings['enabled']:return False
        latest=next((entry for entry in self.list() if entry['kind']=='automatic'),None)
        return latest is None or (now or time.time())-latest['time']>=settings['hours']*3600
    def tick(self,now=None):
        if not self.due(now):return None
        try:
            name=self.create('automatic');removed=self.prune(now)
            self.log(f'定期備份完成：{name}'+(f'，清理 {len(removed)} 個過期備份' if removed else ''))
            return name
        except Exception as error:
            self.last_error=str(error);self.log(f'定期備份失敗：{error}');return None
    def start(self,interval=60):
        if self.worker and self.worker.is_alive():return
        def run():
            self.tick()
            while not self.stop.wait(interval):self.tick()
        self.worker=threading.Thread(target=run,daemon=True,name='database-backups');self.worker.start()
    def close(self):self.stop.set()
