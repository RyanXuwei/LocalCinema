import os, sys, json, hashlib, mimetypes, threading, subprocess, shutil, time, secrets, webbrowser, queue, sqlite3, random, socket, ipaddress, math
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from contextlib import contextmanager
from conversion_store import ConversionStore,AutoPromoter
from operation_progress import OperationProgress,parse_duration,parse_encode_progress
from playback_storage import playback_directory,relocate_playback,cache_usage,wait_for_conversion,cleanup_moved_copies
from source_groups import SourceGroups,open_group_manager,DEFAULT_GROUP
from source_help import open_source_help
from version import APP_VERSION
from group_access import GroupAccess,visible_payload,may_read
from web_works import WebWorks,WEB_KIND,group_kind
from db_backup import DatabaseBackups,INTERVALS as BACKUP_INTERVALS
from http.cookies import SimpleCookie
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

BASE = Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else BASE
DATA = Path(os.environ.get('LOCALAPPDATA', str(BASE))) / 'LocalCinema'
DATA.mkdir(parents=True, exist_ok=True)
CACHE = DATA / 'posters'
CACHE.mkdir(exist_ok=True)
VIDEO = {'.mp4','.m4v','.webm','.mkv','.kvm','.rm','.rmvb','.avi','.mov','.wmv','.flv','.ts','.m2ts','.mpg','.mpeg'}
PICTURE = {'.jpg','.jpeg','.png','.webp','.bmp'}
def natural(p):
    import re
    return [int(x) if x.isdigit() else x.casefold() for x in re.split(r'(\d+)', str(p))]
def identity(p):
    return hashlib.sha256(str(p.resolve()).casefold().encode()).hexdigest()[:24]

def match_pictures(video, files):
    """Prefer exact stems, then bidirectional substring matches by closeness."""
    name=video.stem.casefold()
    candidates=[p for p in files if p.suffix.lower() in PICTURE and
                (name in p.stem.casefold() or p.stem.casefold() in name)]
    return sorted(candidates,key=lambda p:(p.stem.casefold()!=name,
                  abs(len(p.stem)-len(video.stem)),natural(p.name)))

def lan_addresses():
    addresses=set()
    try:
        for result in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            address=ipaddress.ip_address(result[4][0])
            if not address.is_loopback and not address.is_link_local and not address.is_unspecified:
                addresses.add(str(address))
    except OSError: pass
    preferred=None
    try:
        # UDP connect selects the default route without sending a packet.
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as route:
            route.connect(('192.0.2.1',9))
            preferred=route.getsockname()[0]
    except OSError: pass
    return sorted(addresses,key=lambda address:(address!=preferred,address))

def entry_url(port,access_key):
    addresses=lan_addresses()
    if addresses: return f'http://{addresses[0]}:{port}/?access={access_key}'
    return f'http://127.0.0.1:{port}/'

def default_playback_directory(app_dir,data_dir):
    legacy=Path(data_dir)/'playback'
    return legacy if legacy.is_dir() else Path(app_dir)/'playback'

def window_dimensions(width,height,records=False):
    available_w=max(320,width-48);available_h=max(320,height-48)
    preferred_w,preferred_h=(1280,850) if records else (1160,850)
    return (min(preferred_w,available_w),min(preferred_h,available_h),
            min(860 if records else 800,available_w),min(560,available_h))

def size_window(window,records=False):
    left=top=0;width=window.winfo_screenwidth();height=window.winfo_screenheight()
    if os.name=='nt':
        try:
            import ctypes
            from ctypes import wintypes
            rectangle=wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(48,0,ctypes.byref(rectangle),0):
                left,top=rectangle.left,rectangle.top;width=rectangle.right-left;height=rectangle.bottom-top
        except (AttributeError,OSError):pass
    w,h,min_w,min_h=window_dimensions(width,height,records)
    window.geometry(f'{w}x{h}+{left+(width-w)//2}+{top+(height-h)//2}')
    window.minsize(min_w,min_h)
    return width,height

def cache_video_poster(ffmpeg,video,cache):
    flags=0x08000000 if os.name=='nt' else 0
    try:
        metadata=subprocess.run([ffmpeg,'-nostdin','-hide_banner','-i',str(video)],capture_output=True,timeout=15,creationflags=flags)
        duration=parse_duration(metadata.stderr.decode('utf-8',errors='replace'))
    except (OSError,subprocess.TimeoutExpired):duration=None
    position=duration*.1 if duration else 0
    temporary=cache.with_name(cache.stem+'.'+secrets.token_hex(6)+'.tmp.jpg')
    try:
        result=subprocess.run([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-ss',f'{position:.6f}','-i',str(video),'-frames:v','1','-vf','scale=640:-1','-y',str(temporary)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=45,creationflags=flags)
        if result.returncode!=0 or not temporary.is_file():return False
        from PIL import Image
        with Image.open(temporary) as image:image.verify()
        temporary.replace(cache)
        return True
    except (OSError,ValueError,subprocess.TimeoutExpired):return False
    finally:temporary.unlink(missing_ok=True)

class SingleInstance:
    """OS-owned handles release automatically when the process exits or crashes."""
    def __init__(self,name=None):
        import ctypes
        from ctypes import wintypes
        self.api=ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR]
        self.api.CreateMutexW.restype=wintypes.HANDLE
        self.api.CreateEventW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.BOOL,wintypes.LPCWSTR]
        self.api.CreateEventW.restype=wintypes.HANDLE
        self.api.SetEvent.argtypes=[wintypes.HANDLE]; self.api.SetEvent.restype=wintypes.BOOL
        self.api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        self.api.WaitForSingleObject.restype=wintypes.DWORD
        self.api.CloseHandle.argtypes=[wintypes.HANDLE]; self.api.CloseHandle.restype=wintypes.BOOL
        name=name or 'LocalCinema-'+hashlib.sha256(str(DATA).casefold().encode()).hexdigest()[:24]
        self.event=self.api.CreateEventW(None,False,False,'Local\\'+name+'-show')
        if not self.event: raise ctypes.WinError(ctypes.get_last_error())
        self.mutex=self.api.CreateMutexW(None,False,'Local\\'+name+'-instance')
        error=ctypes.get_last_error()
        if not self.mutex:
            self.api.CloseHandle(self.event); self.event=None
            raise ctypes.WinError(error)
        self.primary=error!=183
        if not self.primary: self.api.SetEvent(self.event)
    def requested_show(self):
        return self.api.WaitForSingleObject(self.event,0)==0
    def close(self):
        for name in ('mutex','event'):
            handle=getattr(self,name,None)
            if handle: self.api.CloseHandle(handle); setattr(self,name,None)
def load_config():
    try: return json.loads((DATA/'config.json').read_text('utf-8'))
    except (OSError, ValueError): return {'roots':[], 'tags':{}, 'categories':[]}
def save_config(config):
    temp = DATA/'config.tmp'
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), 'utf-8')
    temp.replace(DATA/'config.json')

def scan(roots, tags):
    """Both modes collect immediate folders; flat mode also collects root files."""
    flat = {str(Path(r['path']).resolve()).casefold() for r in roots if r['mode']=='flat'}
    found, seen, errors = [], {}, []
    active_group=DEFAULT_GROUP
    def add(source, videos, pictures):
        key = identity(source)
        if key in seen:
            if active_group not in seen[key]['groups']: seen[key]['groups'].append(active_group)
            return
        stamp = max(p.stat().st_mtime for p in videos)
        found.append({'id':key, 'title':source.stem if source.is_file() else source.name,
                      'updated':stamp, 'tags':tags.get(key, []), 'groups':[active_group],
                      'episodes':[{'id':identity(p), 'name':p.stem, 'path':str(p)} for p in sorted(videos,key=natural)],
                      'picture':str(pictures[0]) if pictures else None})
        seen[key]=found[-1]
    for root in roots:
        active_group=root.get('group',DEFAULT_GROUP)
        directory = Path(root['path'])
        try:
            children = sorted(directory.iterdir(),key=natural)
            if root['mode']=='flat':
                files = [p for p in children if p.is_file()]
                for video in files:
                    if video.suffix.lower() in VIDEO:
                        add(video,[video],match_pictures(video,files))
            for folder in children:
                if not folder.is_dir() or str(folder.resolve()).casefold() in flat: continue
                try:
                    files = sorted([p for p in folder.iterdir() if p.is_file()],key=natural)
                    videos = [p for p in files if p.suffix.lower() in VIDEO]
                    if videos: add(folder,videos,[p for p in files if p.suffix.lower() in PICTURE])
                except OSError as e: errors.append(f'{folder}: {e}')
        except OSError as e: errors.append(f'{directory}: {e}')
    return found, errors

class Library:
    def __init__(self, log, db_path=None, config=None, playback_dir=None):
        self.config = load_config() if config is None else config; self.source_groups=SourceGroups(self.config,DATA,BASE/'assets'/'group-icons',save_config); self.group_access=GroupAccess(self.source_groups); self.items=[]; self.media={}; self.pictures={}; self.log=log
        self.lock=threading.RLock(); self.scanning=False; self.token=secrets.token_urlsafe(32); self.access_key=secrets.token_urlsafe(24); self.revision=0
        self.db_path=db_path or DATA/'library.sqlite3'
        with self.db() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS favorites(item_id TEXT PRIMARY KEY, added REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS watches(session TEXT PRIMARY KEY, item_id TEXT NOT NULL, episode_id TEXT NOT NULL,
                    started REAL NOT NULL, updated REAL NOT NULL, position REAL DEFAULT 0, duration REAL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS watches_item ON watches(item_id);
                CREATE TABLE IF NOT EXISTS exposure(item_id TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS keyframes(id TEXT PRIMARY KEY, item_id TEXT NOT NULL,
                    episode_id TEXT NOT NULL, position REAL NOT NULL, title TEXT NOT NULL, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS keyframes_episode ON keyframes(item_id,episode_id,position);
            ''')
            db.execute('INSERT OR IGNORE INTO app_settings(key,value) VALUES (?,?)',('lan_access_key',self.access_key))
            self.access_key=db.execute('SELECT value FROM app_settings WHERE key=?',('lan_access_key',)).fetchone()[0]
        self.conversion_store=ConversionStore(self.db_path)
        self.web_works=WebWorks(self.db,DATA,self.source_groups,on_change=self.refresh_web,log=log)
        self.refresh_web()
        self.backups=DatabaseBackups(self.db_path,Path(self.db_path).parent/'backups',self.config,save_config,log,self.after_restore)
        try:
            import imageio_ffmpeg
            self.ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError: self.ffmpeg=shutil.which('ffmpeg')
        self.playback_dir=Path(playback_dir) if playback_dir else playback_directory(self.db_path,default_playback_directory(APP_DIR,DATA))
        self.cache_migrating=False
        self.compat_media={}; self.conversions={}; self.convert_queue=queue.Queue()
        self.convert_worker=None; self.convert_process=None; self.closing=False
        self.processing_generation=0;self.processing_paused=False;self.processing_stop=threading.Event();self.conversion_idle=threading.Event();self.conversion_idle.set()
        self.background_enabled=bool(self.config.get('background_convert',False))
        self.background_wake=threading.Event(); self.shutdown_event=threading.Event()
        self.background_worker=None; self.scan_generation=0
        self.background_stats={'total':0,'checked':0,'ready':0,'failed':0}
        self.file_progress=OperationProgress()
        self.auto_promoter=AutoPromoter(self.conversion_store,self.rescan,self.log,progress=self.file_progress.update)
    def pause_processing(self):
        with self.lock:
            self.processing_paused=True;self.processing_stop.set();self.scan_generation+=1;self.processing_generation+=1
            self.auto_promoter.set_paused(True);process=self.convert_process
            while True:
                try:self.convert_queue.get_nowait()
                except queue.Empty:break
        if process and process.poll() is None:
            try:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
            except OSError:pass
        self.conversion_idle.wait()
        while self.auto_promoter.busy or self.scanning:time.sleep(.05)
        with self.lock:
            self.conversions={key:job for key,job in self.conversions.items() if job['state'] not in ('queued','converting')}
    def resume_processing(self,wake=True):
        with self.lock:
            if self.closing:return
            self.processing_stop.clear();self.processing_paused=False;self.auto_promoter.set_paused(False)
        if wake:self.wake_background()
    def prepare(self,episode,force=False):
        with self.lock:
            if self.processing_paused:return {'state':'error','message':'服務已停止，請先啟動服務。'}
            if self.cache_migrating: return {'state':'error','message':'正在搬移轉檔快取，請稍後再試。'}
            source=self.media.get(episode)
            if not source or not source.is_file(): return {'state':'error','message':'來源影片不存在，請重新掃描。'}
            if not force and source.suffix.lower() in ('.mp4','.m4v','.webm'):
                return {'state':'ready','url':'/media/'+episode}
            if not self.ffmpeg: return {'state':'error','message':'尚未安裝FFmpeg，請先執行安裝套件.cmd。'}
            stamp=source.stat()
            key=hashlib.sha256(f'compatible-v1|{source.resolve()}|{stamp.st_size}|{stamp.st_mtime_ns}'.encode()).hexdigest()
            target=self.playback_dir/(key+'.mp4')
            if target.is_file() and target.stat().st_size:
                self.compat_media[key]=target
                self.register_conversion(key,source,target)
                return {'state':'ready','url':'/compatible/'+key}
            if self.closing: return {'state':'error','message':'後台正在結束。'}
            if key not in self.conversions:
                self.playback_dir.mkdir(parents=True,exist_ok=True)
                self.conversions[key]={'state':'queued','message':'等待製作相容播放檔；首次播放需等待，原檔不會變更。'}
                self.convert_queue.put((key,source,target))
                if self.convert_worker is None:
                    self.convert_worker=threading.Thread(target=self._convert,daemon=True); self.convert_worker.start()
            return dict(self.conversions[key])
    def cache_maintenance_blocker(self):
        with self.lock:
            if self.closing:return '程式正在退出，請完成退出後重新開啟。'
            if self.cache_migrating:return '已有快取搬移或清理作業，請等待完成。'
            if self.scanning:return '掃描尚未結束，請等待掃描完成。'
            if self.convert_process or any(job['state'] in ('queued','converting') for job in self.conversions.values()):
                return '仍有轉檔或待轉項目，請先停止服務並等待停止完成。'
            if self.auto_promoter.busy:return '目前單筆MP4保存／回收尚未結束，請等待完成。'
            if self.background_enabled and not self.processing_paused:
                return '背景預轉仍可執行，請先停止服務。'
            if self.auto_promoter.enabled and not self.auto_promoter.paused:
                return '自動保留尚未暫停，請先停止服務。'
            return None
    def relocate_playback(self,destination,progress=None):
        with self.lock:
            blocker=self.cache_maintenance_blocker()
            if blocker:raise ValueError(blocker)
            self.cache_migrating=True
        try:
            with self.conversion_store.lock:
                result=relocate_playback(self.playback_dir,destination,self.db_path,progress=progress)
                with self.lock:
                    self.playback_dir=playback_directory(self.db_path,self.playback_dir)
                    self.compat_media={key:self.playback_dir/path.name for key,path in self.compat_media.items()}
            return result
        finally:
            with self.lock: self.cache_migrating=False
    def cleanup_playback(self,progress=None):
        with self.lock:
            blocker=self.cache_maintenance_blocker()
            if blocker:raise ValueError(blocker)
            self.cache_migrating=True
        try:
            moved=cleanup_moved_copies(self.db_path,progress=progress)
            result=self.conversion_store.cleanup_cache(self.playback_dir,legacy=True,progress=progress)
            return {key:result[key]+moved[key] for key in ('removed','bytes','retained')}
        finally:
            with self.lock:self.cache_migrating=False
    def register_conversion(self,key,source,target):
        item_id=episode_id=title=None
        with self.lock:
            for item in self.items:
                for episode in item['episodes']:
                    if str(Path(episode.get('path','')).absolute()).casefold()==str(source.absolute()).casefold():
                        item_id=item['id']; episode_id=episode['id']; title=item['title']; break
                if episode_id: break
        self.conversion_store.register(key,source,target,item_id,episode_id,title)
    def import_conversion_cache(self):
        with self.lock: sources=list(self.media.values())
        for source in sources:
            try:
                stamp=source.stat()
                key=hashlib.sha256(f'compatible-v1|{source.resolve()}|{stamp.st_size}|{stamp.st_mtime_ns}'.encode()).hexdigest()
                target=self.playback_dir/(key+'.mp4')
                if target.is_file() and target.stat().st_size: self.register_conversion(key,source,target)
            except OSError: pass
    def privacy_state(self):
        with self.lock: return {'enabled':bool(self.config.get('privacy_blur',False)), 'revision':int(self.config.get('privacy_revision',0)),'lockOnPageClose':bool(self.config.get('lock_on_page_close',False)),'hideBranding':bool(self.config.get('hide_branding',False))}
    def set_lock_on_page_close(self,enabled):
        with self.lock:
            self.config['lock_on_page_close']=bool(enabled);save_config(self.config)
            if enabled:
                with self.group_access.lock:self.group_access.sessions.clear()
        self.log('關閉最後一個分頁即上鎖：'+('開啟，請重新解鎖頻道。' if enabled else '關閉。'))
    def set_hide_branding(self,enabled):
        with self.lock:
            self.config['hide_branding']=bool(enabled)
            self.config['privacy_revision']=int(self.config.get('privacy_revision',0))+1
            save_config(self.config)
        self.log('首頁已隱藏 BitingBox 與署名字樣。' if enabled else '首頁恢復顯示 BitingBox 與署名字樣。')
    def set_privacy(self,enabled):
        with self.lock:
            self.config['privacy_blur']=bool(enabled)
            self.config['privacy_revision']=int(self.config.get('privacy_revision',0))+1
            save_config(self.config)
        self.log('隱蔽已開啟：網頁影片與預覽套用毛玻璃。' if enabled else '隱蔽已關閉。')
    def page_html(self,page_id=None):
        html=(BASE/'index.html').read_text('utf-8')
        state=self.privacy_state()
        if page_id:html=html.replace('<meta charset=', '<meta name="localcinema-page" content="'+page_id+'"><meta charset=',1)
        if state['hideBranding']:html=html.replace('<title>LocalCinema · by BitingBox Studio</title>','<title>LocalCinema</title>',1)
        classes=' '.join(name for name,on in (('privacy-blur',state['enabled']),('hide-branding',state['hideBranding'])) if on)
        return html.replace('<html lang="zh-Hant">','<html lang="zh-Hant" class="'+classes+'" data-privacy-revision="'+str(state['revision'])+'">',1).encode('utf-8')
    def set_background(self,enabled):
        with self.lock:
            self.background_enabled=bool(enabled)
            self.config['background_convert']=self.background_enabled
            save_config(self.config)
        self.wake_background()
        self.log(('背景預轉已設定，啟動服務後執行。' if self.processing_paused else '背景預先轉檔已開啟。') if enabled else '已暫停背景預先排程；目前轉檔完成後不再新增背景工作。')
    def wake_background(self):
        with self.lock:
            if self.closing or self.processing_paused: return
            if self.background_enabled and self.background_worker is None:
                self.background_worker=threading.Thread(target=self._background_collect,daemon=True)
                self.background_worker.start()
        self.background_wake.set()
    def _background_collect(self):
        while not self.closing:
            self.background_wake.wait(); self.background_wake.clear()
            with self.lock:
                if self.closing: return
                if not self.background_enabled or self.processing_paused: continue
                generation=self.scan_generation
                seen=set(); candidates=[]
                for episode,source in self.media.items():
                    if source.suffix.lower() in ('.mp4','.m4v','.webm'): continue
                    key=str(source.resolve()).casefold()
                    if key not in seen: seen.add(key); candidates.append(episode)
                self.background_stats={'total':len(candidates),'checked':0,'ready':0,'failed':0}
            for episode in candidates:
                while not self.closing:
                    with self.lock:
                        if self.processing_paused or not self.background_enabled or generation!=self.scan_generation: break
                    try: info=self.prepare(episode)
                    except OSError: info={'state':'error'}
                    if info['state'] in ('ready','error'):
                        with self.lock:
                            self.background_stats['checked']+=1
                            self.background_stats['ready' if info['state']=='ready' else 'failed']+=1
                        break
                    if self.shutdown_event.wait(.35): return
                with self.lock:
                    if self.closing: return
                    if self.processing_paused or not self.background_enabled or generation!=self.scan_generation: break
    def conversion_status(self):
        with self.lock:
            states=[job['state'] for job in self.conversions.values()]
            return dict(self.background_stats,enabled=self.background_enabled and not self.processing_paused,
                        queued=states.count('queued'),converting=states.count('converting'),
                        completed=states.count('ready'),errors=states.count('error'),active=next((dict(job) for job in self.conversions.values() if job['state']=='converting'),None))
    def _convert(self):
        while not self.closing:
            job=self.convert_queue.get()
            if job is None: return
            key,source,target=job
            temporary=target.with_suffix('.partial.mp4');reader=None;process=None
            try:
                with self.lock:
                    if self.closing or self.processing_paused:continue
                    self.conversion_idle.clear()
                    self.conversions[key]={'state':'converting','seconds':0,'percent':None,'duration':None}
                try:
                    with self.lock:
                        if self.processing_paused:continue
                        self.convert_process=subprocess.Popen([self.ffmpeg,'-nostdin','-hide_banner','-i',str(source)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=0x08000000 if os.name=='nt' else 0)
                        probe=self.convert_process
                    try:_,metadata=probe.communicate(timeout=15)
                    except subprocess.TimeoutExpired:probe.kill();_,metadata=probe.communicate()
                    duration=parse_duration(metadata.decode('utf-8',errors='replace'))
                except OSError:duration=None
                with self.lock:
                    if self.closing or self.processing_paused:continue
                    self.conversions[key]={'seconds':0,'duration':duration,'percent':None,'state':'converting','message':'正在製作相容播放檔，完成後自動播放；首次轉換可能較久。'}
                    if shutil.disk_usage(self.playback_dir).free<512*1024*1024:
                        raise OSError('快取空間不足，請先清理或搬移快取。')
                    self.convert_process=subprocess.Popen([self.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-progress','pipe:1','-nostats','-i',str(source),'-map','0:v:0','-map','0:a:0?','-sn','-dn','-vf','scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p','-c:v','libx264','-preset','veryfast','-crf','22','-c:a','aac','-b:a','160k','-ac','2','-movflags','+faststart','-threads','2','-y',str(temporary)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',errors='replace',creationflags=0x08000000 if os.name=='nt' else 0)
                    process=self.convert_process
                def read_progress(process=process,job_key=key,job_duration=duration):
                    for line in process.stdout:
                        value=parse_encode_progress(line,job_duration)
                        if value:
                            with self.lock:
                                if self.conversions[job_key]['state']=='converting':self.conversions[job_key].update(value)
                reader=threading.Thread(target=read_progress,daemon=True);reader.start()
                result=wait_for_conversion(process,self.playback_dir,self.processing_stop)
                reader.join(timeout=2)
                if not reader.is_alive():process.stdout.close()
                with self.lock:
                    if self.closing or self.processing_paused:continue
                    if result!=0 or not temporary.is_file() or not temporary.stat().st_size: raise RuntimeError('conversion failed')
                    temporary.replace(target); self.compat_media[key]=target
                    self.conversions[key]={'state':'ready','url':'/compatible/'+key}
                self.register_conversion(key,source,target)
                self.log('相容播放檔製作完成並保留記錄，原始影片未變更。')
            except Exception:
                with self.lock: failed_process=self.convert_process
                if failed_process and failed_process.poll() is None:
                    failed_process.terminate()
                    try:failed_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:failed_process.kill();failed_process.wait(timeout=5)
                with self.lock:
                    if not self.processing_paused and not self.closing:self.conversions[key]={'state':'error','message':'無法轉換此影片；來源可能損壞、受保護或使用不支援的編碼。'}
                if not self.processing_paused and not self.closing:self.log('相容播放檔製作失敗；未變更原始影片。')
            finally:
                if reader:
                    reader.join(timeout=2)
                    if not reader.is_alive() and process.stdout and not process.stdout.closed:process.stdout.close()
                with self.lock: self.convert_process=None
                try: temporary.unlink(missing_ok=True)
                except OSError: pass
                self.conversion_idle.set()
    def shutdown(self):
        self.auto_promoter.close(); self.web_works.close(); self.backups.close()
        with self.lock:
            self.closing=True; process=self.convert_process
        self.shutdown_event.set(); self.processing_stop.set(); self.background_wake.set()
        self.convert_queue.put(None)
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
        if self.convert_worker: self.convert_worker.join(timeout=4)
        if self.background_worker: self.background_worker.join(timeout=2)
    @contextmanager
    def db(self):
        connection=sqlite3.connect(self.db_path,timeout=15)
        try:
            with connection: yield connection
        finally: connection.close()
    def state(self):
        with self.db() as db:
            favorites={r[0] for r in db.execute('SELECT item_id FROM favorites')}
            watches={r[0]:(r[1],r[2]) for r in db.execute('SELECT item_id, COUNT(*), MAX(updated) FROM watches GROUP BY item_id')}
            exposure=dict(db.execute('SELECT item_id,count FROM exposure'))
            progress={}
            for item,ep,pos,duration,updated in db.execute('SELECT item_id,episode_id,position,duration,updated FROM watches ORDER BY updated'):
                progress[item]={'episode':ep,'position':pos,'duration':duration,'updated':updated}
        return favorites,watches,exposure,progress
    def recommend(self, previous=None, group=None, allowed=None):
        with self.lock:
            if not self.items: return None
            _,watches,exposures,_=self.state()
            candidates=[item for item in self.items if (group is None or group in item.get('groups',[DEFAULT_GROUP])) and (allowed is None or allowed.intersection(item.get('groups',[DEFAULT_GROUP])))]
            if not candidates: return None
            # Each recommendation and actual viewing contributes one turn.
            # Uniform random ties avoid deterministic bias; persisted counts survive restarts.
            scores={i['id']:exposures.get(i['id'],0)+watches.get(i['id'],(0,0))[0] for i in candidates}
            minimum=min(scores.values())
            least=[i for i in candidates if scores[i['id']]==minimum]
            choice=random.choice([i for i in least if i['id']!=previous] or least)
            with self.db() as db:
                db.execute('INSERT INTO exposure(item_id,count) VALUES (?,1) ON CONFLICT(item_id) DO UPDATE SET count=count+1',(choice['id'],))
            return choice['id']
    def rescan(self):
        with self.lock:
            if self.scanning or self.cache_migrating or self.processing_paused: return
            self.scanning=True
            roots=list(self.config['roots']); tags=dict(self.config['tags'])
        try:
            items, errors=scan(roots,tags)
            items=self.conversion_store.apply_aliases(items)
            with self.lock:
                for item in items: item['tags']=self.config['tags'].get(item['id'],[])
                self.items=items
                self.media={e['id']:Path(e['path']) for i in items for e in i['episodes']}
                self.pictures={i['id']:Path(i['picture']) for i in items if i['picture']}
                self.refresh_web()
                self.scan_generation+=1
                self.revision+=1
            self.import_conversion_cache()
            self.wake_background()
            self.log(f'掃描完成：{len(items)} 部作品，{len(self.media)} 個影片檔')
            for error in errors: self.log(error)
            for item in items:
                if self.processing_paused or self.closing:break
                if item['picture'] or not self.ffmpeg: continue
                video=Path(item['episodes'][0]['path'])
                cache=CACHE/('frame10-v1-'+identity(video)+'-'+str(video.stat().st_mtime_ns)+'.jpg')
                if not cache.exists():cache_video_poster(self.ffmpeg,video,cache)
                if cache.exists():
                    with self.lock:
                        self.pictures[item['id']]=cache; self.revision+=1
        except Exception as e: self.log(f'掃描／縮圖錯誤：{e}')
        finally: self.scanning=False
    def after_restore(self):
        with self.group_access.lock:self.group_access.sessions.clear()
        self.refresh_web()
        threading.Thread(target=self.rescan,daemon=True).start()
    def refresh_web(self):
        """Web works live beside scanned media; rebuilt without rescanning folders."""
        works=self.web_works.items()
        with self.lock:
            self.items=[item for item in self.items if item.get('kind')!=WEB_KIND]+works
            self.pictures={key:path for key,path in self.pictures.items() if not key.startswith('w') or len(key)!=21}
            self.pictures.update({item['id']:Path(item['picture']) for item in works if item['picture']})
            self.revision+=1
    def web_item(self,work_id):
        with self.lock:return next((item for item in self.items if item['id']==work_id and item.get('kind')==WEB_KIND),None)
    def public(self):
        with self.lock:
            favorites,watches,exposure,progress=self.state()
            return {'items':[{k:v for k,v in i.items() if k not in ('picture','episodes')} | {'episodes':[{'id':e['id'],'name':e['name']} for e in i['episodes']], 'favorite':i['id'] in favorites,'watchCount':watches.get(i['id'],(0,0))[0],'watchedAt':watches.get(i['id'],(0,0))[1], 'progress':progress.get(i['id'])} for i in self.items], 'groups':self.source_groups.public(self.items), 'groupCategories':{g['id']:self.source_groups.tag_catalog(g['id']) for g in self.config['groups']}, 'groupTags':{g['id']:{i['id']:self.source_groups.item_tags(g['id'],i['id']) for i in self.items if g['id'] in i.get('groups',[DEFAULT_GROUP])} for g in self.config['groups']}, 'categories':self.config.get('categories',[]), 'scanning':self.scanning, 'token':self.token, 'revision':self.revision, 'conversion':self.conversion_status(), 'privacy':self.privacy_state()}

def make_handler(lib):
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args): pass
        def end_headers(self):
            if getattr(self,'page_browser_cookie',None):self.send_header('Set-Cookie',f'cinema_pages={self.page_browser_cookie}; HttpOnly; SameSite=Strict; Path=/')
            self.send_header('Cross-Origin-Resource-Policy','same-origin')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Content-Security-Policy',"frame-ancestors 'none'")
            self.send_header('Referrer-Policy','no-referrer')
            super().end_headers()
        def trusted_request(self):
            try:
                if len(self.headers.get_all('Host',[]))!=1: return False
                host=urlparse('//'+self.headers['Host'])
                allowed={'localhost','127.0.0.1',self.connection.getsockname()[0]}
                if host.hostname not in allowed or (host.port or 80)!=self.server.server_port or host.username or host.password or host.path or host.query or host.fragment: return False
                origin=self.headers.get('Origin')
                if origin:
                    site=urlparse(origin)
                    if site.scheme!='http' or site.hostname!=host.hostname or (site.port or 80)!=(host.port or 80) or site.username or site.password or site.path or site.query or site.fragment: return False
                return True
            except (ValueError,OSError): return False
        def authorized(self):
            self.page_browser_cookie=None
            if not self.trusted_request():
                self.reply(403,{'error':'不允許此網站來源或主機名稱。'})
                return False
            if self.client_address[0] in ('127.0.0.1','::1'): return True
            cookie=SimpleCookie()
            try: cookie.load(self.headers.get('Cookie',''))
            except Exception: pass
            saved=cookie.get('cinema_access')
            if saved and secrets.compare_digest(saved.value.encode('utf-8'),lib.access_key.encode('utf-8')): return True
            parsed=urlparse(self.path)
            access=parse_qs(parsed.query).get('access',[''])[0]
            if self.command in ('GET','HEAD') and parsed.path=='/' and secrets.compare_digest(access.encode('utf-8'),lib.access_key.encode('utf-8')):
                self.send_response(303); self.send_header('Location','/')
                self.send_header('Set-Cookie',f'cinema_access={lib.access_key}; Max-Age=31536000; HttpOnly; SameSite=Lax; Path=/')
                self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length','0'); self.end_headers()
                return False
            self.reply(403,{'error':'請使用後台顯示的完整區網存取連結。'})
            return False
        def reply(self,status,data,kind='application/json; charset=utf-8'):
            if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers()
            if self.command!='HEAD': self.wfile.write(data)
        def allowed_groups(self):return lib.group_access.visible(self.headers.get('Cookie',''))
        def work_route(self,action,data,allowed):
            try:
                if action=='add':
                    group=str(data.get('group',''))
                    if group not in allowed:return self.reply(404,{'error':'不存在'})
                    with lib.lock:row=lib.web_works.add(group,data.get('url'),data.get('title',''),data.get('notes',''),bool(data.get('openInTab',False)))
                    lib.refresh_web();return self.reply(200,{'id':row['id']})
                item=lib.web_item(str(data.get('id','')))
                if item is None or not allowed.intersection(item['groups']):return self.reply(404,{'error':'作品不存在'})
                if action=='update':
                    with lib.lock:lib.web_works.update(item['id'],data.get('url'),data.get('title'),data.get('notes'),data.get('openInTab'))
                elif action=='delete':
                    with lib.lock:lib.web_works.delete(item['id'],data.get('confirm'))
                elif action=='check':
                    result=lib.web_works.check_frame(item['id']);lib.refresh_web();return self.reply(200,result)
                elif action=='snapshot' and data.get('now'):
                    if not lib.web_works.capture_now(item['id']):return self.reply(502,{'error':'無法擷取此網址的畫面，請確認網站可開啟。'})
                elif action=='snapshot':lib.web_works.queue_snapshot(item['id'])
                elif action=='snapshot-upload':
                    import base64
                    image=str(data.get('image',''))
                    if not image.startswith('data:image/') or ';base64,' not in image:return self.reply(400,{'error':'快照格式錯誤'})
                    try:raw=base64.b64decode(image.split(';base64,',1)[1],validate=True)
                    except ValueError:return self.reply(400,{'error':'快照格式錯誤'})
                    lib.web_works.store_snapshot(item['id'],raw)
                elif action=='visit':
                    with lib.db() as db:
                        db.execute('INSERT INTO watches VALUES (?,?,?,?,?,?,?) ON CONFLICT(session) DO UPDATE SET updated=excluded.updated',
                                   (str(data.get('session',''))[:100] or secrets.token_hex(12),item['id'],item['id'],time.time(),time.time(),0,0))
                    return self.reply(200,{'ok':True})
                else:return self.reply(404,{'error':'不存在'})
                lib.refresh_web();return self.reply(200,{'ok':True})
            except ValueError as error:return self.reply(400,{'error':str(error)})
        def do_HEAD(self): self.do_GET()
        def do_GET(self):
            if not self.authorized(): return
            route=urlparse(self.path).path
            try:
                if route=='/':
                    page=secrets.token_urlsafe(18);cookie=self.headers.get('Cookie','');browser=lib.group_access.browser_token(cookie)
                    if not lib.group_access.valid_page(browser):
                        browser=secrets.token_urlsafe(24);self.page_browser_cookie=browser;cookie+='; cinema_pages='+browser
                    lib.group_access.touch_page(cookie,page)
                    return self.reply(200,lib.page_html(page),'text/html; charset=utf-8')
                if route=='/api/privacy': return self.reply(200,lib.privacy_state())
                if route.startswith('/group-image/'):
                    if route.rsplit('/',1)[1] not in self.allowed_groups():return self.reply(404,{'error':'不存在'})
                    try: file=lib.source_groups.image(route.rsplit('/',1)[1])
                    except ValueError: return self.reply(404,{'error':'片源群組不存在'})
                    return self.reply(200,file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'image/webp')
                if route.startswith('/assets/'):
                    name=route.removeprefix('/assets/')
                    if name not in ('sumi-background.png','camellia-emblem.png','ui-icons.svg','catalog-pagination.js','localcinema.ico','localcinema-icon.png','playback-modes.js','short-queue.js','interaction-controls.js','bitingbox-studio.png','bitingbox-studio-plaque.svg','studio-layout.css','studio-navigation.js','web-works.js','web-works.css'): return self.reply(404,{'error':'不存在'})
                    return self.reply(200,(BASE/'assets'/name).read_bytes(),mimetypes.guess_type(name)[0] or 'application/octet-stream')
                if route=='/api/library': return self.reply(200,visible_payload(lib,self.allowed_groups()))
                if route.startswith('/media/') or route.startswith('/poster/') or route.startswith('/compatible/'):
                    key=route.rsplit('/',1)[1]
                    if not may_read(lib,self.allowed_groups(),key,episode=not route.startswith('/poster/')):return self.reply(404,{'error':'不存在'})
                    with lib.lock: file=(lib.media if route.startswith('/media/') else lib.compat_media if route.startswith('/compatible/') else lib.pictures).get(key)
                    if not file or not file.is_file(): return self.reply(404,{'error':'找不到檔案'})
                    size=file.stat().st_size; start=0; end=size-1; partial=False
                    header=self.headers.get('Range')
                    if header:
                        try:
                            if not header.startswith('bytes=') or ',' in header: raise ValueError()
                            left,right=header[6:].split('-')
                            if left: start=int(left); end=min(int(right),size-1) if right else size-1
                            else: start=max(0,size-int(right))
                            if start<0 or start>=size or end<start: raise ValueError()
                            partial=True
                        except ValueError:
                            self.send_response(416); self.send_header('Content-Range',f'bytes */{size}'); self.send_header('Content-Length','0'); self.end_headers(); return
                    self.send_response(206 if partial else 200)
                    self.send_header('Content-Type',mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
                    self.send_header('Accept-Ranges','bytes'); self.send_header('Content-Length',str(end-start+1))
                    self.send_header('Cache-Control','private, no-store')
                    if partial: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                    self.end_headers()
                    if self.command=='HEAD': return
                    with file.open('rb') as f:
                        f.seek(start); remaining=end-start+1
                        while remaining:
                            chunk=f.read(min(256*1024,remaining))
                            if not chunk: break
                            self.wfile.write(chunk); remaining-=len(chunk)
                    return
                self.reply(404,{'error':'不存在'})
            except (ConnectionError, BrokenPipeError): pass
            except OSError: self.close_connection=True
        def do_POST(self):
            if not self.authorized(): return
            if self.headers.get('X-Cinema-Token')!=lib.token: return self.reply(403,{'error':'驗證失敗'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                limit=16*1024*1024 if urlparse(self.path).path=='/api/works/snapshot-upload' else 65536
                if not 0<length<=limit: return self.reply(400,{'error':'資料大小錯誤'})
                data=json.loads(self.rfile.read(length)); route=urlparse(self.path).path
                if route=='/api/groups/unlock':
                    with lib.lock:session=lib.group_access.unlock(data.get('password'),self.headers.get('Cookie',''),self.client_address[0],data.get('page'))
                    self.send_response(200);self.send_header('Set-Cookie',f'cinema_groups={session}; HttpOnly; SameSite=Strict; Path=/');self.send_header('Cache-Control','no-store');self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'{}');return
                if route in ('/api/groups/page','/api/groups/page-close'):
                    if route.endswith('page-close'):lib.group_access.close_page(self.headers.get('Cookie',''),data.get('page'))
                    else:lib.group_access.touch_page(self.headers.get('Cookie',''),data.get('page'))
                    return self.reply(200,{'ok':True})
                if route=='/api/groups/lock':
                    lib.group_access.lock_all(self.headers.get('Cookie',''));return self.reply(200,{'ok':True})
                allowed=self.allowed_groups()
                if route in ('/api/category','/api/tags') and data.get('group',DEFAULT_GROUP) not in allowed:return self.reply(404,{'error':'不存在'})
                if data.get('group') and data['group'] not in allowed:return self.reply(404,{'error':'不存在'})
                if data.get('id') and not may_read(lib,allowed,data['id']):return self.reply(404,{'error':'不存在'})
                if data.get('episode') and not may_read(lib,allowed,data['episode'],episode=True):return self.reply(404,{'error':'不存在'})
                if route.startswith('/api/works/'):return self.work_route(route.removeprefix('/api/works/'),data,allowed)
                if route=='/api/prepare': return self.reply(200,lib.prepare(str(data['episode']),bool(data.get('force',False))))
                if route=='/api/recommend': return self.reply(200,{'id':lib.recommend(data.get('previous'),data.get('group'),allowed)})
                if route=='/api/exposure':
                    with lib.lock:
                        if not any(item['id']==data['id'] for item in lib.items): return self.reply(404,{'error':'作品不存在'})
                        with lib.db() as db:
                            db.execute('INSERT INTO exposure(item_id,count) VALUES (?,1) ON CONFLICT(item_id) DO UPDATE SET count=count+1',(data['id'],))
                    return self.reply(200,{'ok':True})
                if route=='/api/keyframes':
                    with lib.lock:
                        item=next((i for i in lib.items if i['id']==data['id']),None)
                        episode=data['episode']
                        if item is None or episode not in [e['id'] for e in item['episodes']]:
                            return self.reply(404,{'error':'影片或集數不存在'})
                        action=data.get('action','list')
                        with lib.db() as db:
                            if action=='add':
                                position=float(data['position'])
                                if not math.isfinite(position) or not 0<=position<=1e9:
                                    return self.reply(400,{'error':'時間格式錯誤'})
                                title=str(data.get('title','')).strip()[:120] or '關鍵幀'
                                db.execute('INSERT INTO keyframes VALUES (?,?,?,?,?,?)',(secrets.token_hex(16),item['id'],episode,position,title,time.time()))
                            elif action in ('rename','delete'):
                                args=(str(data['bookmark']),item['id'],episode)
                                if action=='delete': result=db.execute('DELETE FROM keyframes WHERE id=? AND item_id=? AND episode_id=?',args)
                                else:
                                    title=str(data['title']).strip()[:120] or '關鍵幀'
                                    result=db.execute('UPDATE keyframes SET title=? WHERE id=? AND item_id=? AND episode_id=?',(title,)+args)
                                if result.rowcount==0: return self.reply(404,{'error':'關鍵幀不存在'})
                            elif action!='list': return self.reply(400,{'error':'不支援的操作'})
                            rows=db.execute('SELECT id,position,title FROM keyframes WHERE item_id=? AND episode_id=? ORDER BY position,created,id',(item['id'],episode)).fetchall()
                    return self.reply(200,{'keyframes':[{'id':r[0],'position':r[1],'title':r[2]} for r in rows]})
                if route in ('/api/favorite','/api/watch'):
                    with lib.lock:
                        item=next((i for i in lib.items if i['id']==data['id']),None)
                        if item is None: return self.reply(404,{'error':'作品不存在'})
                        with lib.db() as db:
                            if route=='/api/favorite':
                                if data['favorite']: db.execute('INSERT OR IGNORE INTO favorites VALUES (?,?)',(item['id'],time.time()))
                                else: db.execute('DELETE FROM favorites WHERE item_id=?',(item['id'],))
                            else:
                                ep=data['episode']; session=str(data['session'])[:100]
                                if ep not in [e['id'] for e in item['episodes']]: return self.reply(400,{'error':'集數不存在'})
                                position=max(0,float(data.get('position',0))); duration=max(0,float(data.get('duration',0)))
                                db.execute('INSERT INTO watches VALUES (?,?,?,?,?,?,?) ON CONFLICT(session) DO UPDATE SET updated=excluded.updated,position=excluded.position,duration=excluded.duration WHERE watches.item_id=excluded.item_id AND watches.episode_id=excluded.episode_id', (session,item['id'],ep,time.time(),time.time(),position,duration))
                    return self.reply(200,{'ok':True})
                if route=='/api/tags':
                    with lib.lock:
                        item=next((i for i in lib.items if i['id']==data['id']),None)
                        if item is None: return self.reply(404,{'error':'作品不存在'})
                        tags=list(dict.fromkeys(str(t).strip()[:60] for t in data['tags'] if str(t).strip()))[:50]
                        group=data.get('group',DEFAULT_GROUP)
                        if group not in item.get('groups',[DEFAULT_GROUP]):return self.reply(400,{'error':'影片不在此群組'})
                        lib.source_groups.add_tags(group,tags,item['id'])
                    return self.reply(200,{'ok':True})
                if route=='/api/scan':
                    threading.Thread(target=lib.rescan,daemon=True).start(); return self.reply(200,{'ok':True})
                if route=='/api/category':
                    name=str(data['name']).strip()[:60]
                    if not name: return self.reply(400,{'error':'分類不可空白'})
                    with lib.lock:
                        lib.source_groups.add_tags(data.get('group',DEFAULT_GROUP),[name])
                    return self.reply(200,{'ok':True})
                self.reply(404,{'error':'不存在'})
            except (ValueError,KeyError,TypeError): self.reply(400,{'error':'資料格式錯誤'})
    return Handler

def format_size(size):
    for unit in ('B','KB','MB','GB'):
        if size<1024 or unit=='GB':return f'{size:.0f} {unit}' if unit=='B' else f'{size:.1f} {unit}'
        size/=1024

def build_backup_page(parent,root,lib):
    """Scheduled backups, manual backup and guarded restore of library.sqlite3 and config.json."""
    backups=lib.backups
    ttk.Label(parent,text='資料庫備份',font=('Microsoft JhengHei UI',14)).pack(anchor='w',padx=20,pady=(14,2))
    ttk.Label(parent,text='使用SQLite線上備份API，服務運作中也能安全建立。每份備份包含資料庫（收藏、觀看記錄、關鍵幀、轉檔紀錄、網路作品與備註）與群組／標籤設定。自動備份預設關閉。',wraplength=1000,justify='left').pack(anchor='w',padx=20)
    settings=backups.settings()
    form=ttk.LabelFrame(parent,text='定期備份',padding=12);form.pack(fill='x',padx=20,pady=10)
    enabled=tk.BooleanVar(value=settings['enabled'])
    ttk.Checkbutton(form,text='啟用定期備份',variable=enabled).grid(row=0,column=0,sticky='w',padx=(0,18))
    ttk.Label(form,text='備份頻率').grid(row=0,column=1,sticky='e')
    labels=list(BACKUP_INTERVALS.values());frequency=tk.StringVar(value=BACKUP_INTERVALS[settings['hours']])
    ttk.OptionMenu(form,frequency,frequency.get(),*labels).grid(row=0,column=2,padx=(6,18))
    ttk.Label(form,text='保留天數').grid(row=0,column=3,sticky='e')
    days=tk.StringVar(value=str(settings['days']))
    ttk.Spinbox(form,from_=1,to=3650,textvariable=days,width=6).grid(row=0,column=4,padx=(6,18))
    status=tk.StringVar()
    def save_settings():
        try:
            hours=next(hours for hours,label in BACKUP_INTERVALS.items() if label==frequency.get())
            backups.configure(enabled.get(),hours,int(days.get()));refresh();messagebox.showinfo('備份設定','已儲存備份設定。',parent=root)
        except (ValueError,StopIteration) as error:messagebox.showerror('無法儲存',str(error) or '設定格式錯誤。',parent=root)
    ttk.Button(form,text='儲存備份設定',command=save_settings).grid(row=0,column=5,padx=(0,8))
    ttk.Label(form,textvariable=status).grid(row=1,column=0,columnspan=6,sticky='w',pady=(10,0))
    actions=ttk.Frame(parent);actions.pack(fill='x',padx=20)
    def run_in_background(work,done):
        results=queue.Queue()
        threading.Thread(target=lambda:results.put(_capture(work)),daemon=True).start()
        def finish():
            if results.empty():root.after(150,finish);return
            done(*results.get())
        root.after(150,finish)
    def backup_now():
        button.configure(state='disabled');status.set('正在建立備份…')
        def done(result,error):
            button.configure(state='normal');refresh()
            if error:messagebox.showerror('備份失敗',str(error),parent=root)
            else:lib.log(f'已建立手動備份：{result}');messagebox.showinfo('立即備份',f'已建立備份：\n{result}',parent=root)
        run_in_background(lambda:backups.create('manual'),done)
    button=ttk.Button(actions,text='立即備份',command=backup_now);button.pack(side='left')
    ttk.Button(actions,text='開啟備份資料夾',command=lambda:(backups.folder.mkdir(parents=True,exist_ok=True),os.startfile(backups.folder)) if os.name=='nt' else None).pack(side='left',padx=8)
    ttk.Label(parent,text='可還原的備份',font=('Microsoft JhengHei UI',12)).pack(anchor='w',padx=20,pady=(14,4))
    holder=ttk.Frame(parent);holder.pack(fill='both',expand=True,padx=20)
    table=ttk.Treeview(holder,columns=('time','kind','name','size'),show='headings',height=8,selectmode='browse')
    for column,text,width in (('time','備份時間',170),('kind','類型',90),('name','檔名',480),('size','大小',90)):
        table.heading(column,text=text);table.column(column,width=width,stretch=column=='name')
    bar=ttk.Scrollbar(holder,orient='vertical',command=table.yview);table.configure(yscrollcommand=bar.set)
    bar.pack(side='right',fill='y');table.pack(fill='both',expand=True)
    kinds={'automatic':'自動','manual':'手動','pre-restore':'還原前安全備份'}
    def restore():
        choice=table.selection()
        if not choice:messagebox.showinfo('還原','請先在清單中選取一個備份。',parent=root);return
        name=choice[0]
        dialog=tk.Toplevel(root);dialog.title('還原備份');dialog.configure(bg='#171817');dialog.transient(root)
        ttk.Label(dialog,text='還原會以備份內容取代目前的資料庫與群組設定。\n還原前系統會自動建立目前資料的安全備份。',justify='left').pack(anchor='w',padx=18,pady=(16,8))
        ttk.Label(dialog,text='請輸入備份檔名以確認：').pack(anchor='w',padx=18)
        ttk.Label(dialog,text=name,foreground='#d7c79a').pack(anchor='w',padx=18,pady=4)
        typed=tk.StringVar();entry=ttk.Entry(dialog,textvariable=typed,width=64);entry.pack(fill='x',padx=18)
        include=tk.BooleanVar(value=True)
        ttk.Checkbutton(dialog,text='同時還原群組、標籤與後台設定（config.json）',variable=include).pack(anchor='w',padx=18,pady=8)
        def confirm():
            if typed.get().strip()!=name:messagebox.showerror('檔名不符','輸入的檔名與選取的備份不同。',parent=dialog);return
            dialog.destroy();status.set('正在還原…')
            def done(result,error):
                refresh()
                if error:messagebox.showerror('還原失敗',str(error),parent=root)
                else:messagebox.showinfo('還原完成',f'已還原 {name}。\n還原前的資料已另存：{result}\n網頁重新整理後會看到還原後的內容。',parent=root)
            run_in_background(lambda:backups.restore(name,typed.get().strip(),include.get()),done)
        buttons=ttk.Frame(dialog);buttons.pack(fill='x',padx=18,pady=(4,14))
        ttk.Button(buttons,text='還原',command=confirm).pack(side='right');ttk.Button(buttons,text='取消',command=dialog.destroy).pack(side='right',padx=6)
        dialog.grab_set();entry.focus_set()
    restore_row=ttk.Frame(parent);restore_row.pack(fill='x',padx=20,pady=8)
    ttk.Button(restore_row,text='還原選取的備份',command=restore).pack(side='left')
    ttk.Label(parent,text='注意：備份不含影片、海報與網頁作品快照圖片；還原後缺少的快照可在作品檢視器重新擷取。過期備份依保留天數清理（最新一份一定保留），停用定期備份時不自動刪除。備份存放在：'+str(backups.folder),wraplength=1000,justify='left').pack(anchor='w',padx=20,pady=(0,12))
    def refresh():
        selected=table.selection();table.delete(*table.get_children())
        for entry in backups.list():
            table.insert('','end',iid=entry['name'],values=(time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(entry['time'])),kinds[entry['kind']],entry['name'],format_size(entry['size'])))
        for iid in selected:
            if table.exists(iid):table.selection_set(iid)
        settings=backups.settings();latest=backups.latest()
        last=time.strftime('%Y-%m-%d %H:%M',time.localtime(latest['time'])) if latest else '尚無'
        status.set(('定期備份目前已啟用（'+BACKUP_INTERVALS[settings['hours']]+f"，保留 {settings['days']} 天）" if settings['enabled'] else '定期備份目前已停用')+f'；最近備份：{last}'+(f'；上次錯誤：{backups.last_error}' if backups.last_error else ''))
    def poll():
        try:
            if parent.winfo_exists():refresh()
        except tk.TclError:return
        root.after(30000,poll)
    refresh();root.after(30000,poll)

def _capture(work):
    try:return work(),None
    except Exception as error:return None,error

def render_operation_progress(bar,text,value):
    phase=value['phase'];size=value['size'];done=value['done']
    suffix=f" · 第 {value['index']}/{value['total']} 個" if value['total'] else ''
    if size:
        if str(bar['mode'])!='determinate':bar.stop();bar.configure(mode='determinate')
        percent=min(100,done/size*100);bar['value']=percent
        text.set(f'{phase}{suffix} · 目前檔案 {percent:.1f}% · {done/1024**2:.1f}/{size/1024**2:.1f} MB')
    else:
        if str(bar['mode'])!='indeterminate':bar.configure(mode='indeterminate');bar.start(12)
        text.set(phase+suffix+' · 處理中')

def render_conversion_progress(lib,bar,text):
    active=lib.conversion_status()['active']
    if not active:
        bar.stop();bar.configure(mode='determinate');bar['value']=0;text.set('目前沒有正在轉檔的影片');return
    percent=active.get('percent')
    if percent is None:
        if str(bar['mode'])!='indeterminate':bar.configure(mode='indeterminate');bar.start(12)
        text.set(f"目前影片：已轉 {active.get('seconds',0):.1f} 秒 · 讀取長度或轉檔中")
    else:
        if str(bar['mode'])!='determinate':bar.stop();bar.configure(mode='determinate')
        bar['value']=percent
        text.set(f"目前影片：{percent:.1f}% · {active['seconds']:.1f}/{active['duration']:.1f} 秒")

def build_cache_controls(parent,root,lib,service_running):
    cache_row=ttk.Frame(parent); cache_row.pack(fill='x',padx=20,pady=(8,4))
    cache_text=tk.StringVar(value='轉檔快取目錄：'+str(lib.playback_dir))
    ttk.Label(cache_row,textvariable=cache_text,wraplength=900).pack(anchor='w',fill='x')
    cache_results=queue.Queue();operation=OperationProgress()
    progress_text=tk.StringVar(value='待命')
    progress_label=ttk.Label(parent,textvariable=progress_text,wraplength=900)
    progress_label.pack(fill='x',padx=20,pady=(6,2))
    progress_bar=ttk.Progressbar(parent,maximum=100);progress_bar.pack(fill='x',padx=20,pady=(0,6))
    def poll_progress():
        if not parent.winfo_exists():return
        if getattr(root,'cache_move_busy',False):render_operation_progress(progress_bar,progress_text,operation.snapshot())
        parent.after(150,poll_progress)
    def end_progress(error):
        progress_bar.stop();progress_bar.configure(mode='determinate');progress_bar['value']=0 if error else 100
        progress_text.set('作業未完成；請查看提示' if error else '作業完成')
    poll_progress()
    def choose_cache():
        if service_running() or lib.cache_migrating or getattr(root,'cache_move_busy',False) or getattr(root,'conversion_busy',False):
            messagebox.showinfo('請先停止服務','請停止服務並等候保存作業完成後再搬移快取。',parent=root); return
        blocker=lib.cache_maintenance_blocker()
        if blocker:
            messagebox.showinfo('目前無法搬移',blocker,parent=root);return
        folder=filedialog.askdirectory(title='選擇轉檔快取目錄（搬移既有快取）',parent=root)
        if not folder:return
        operation.update('準備搬移')
        cache_button['state']='disabled'; root.cache_move_busy=True
        cache_text.set('正在搬移與驗證快取，請勿關閉程式…')
        def worker():
            try: cache_results.put((lib.relocate_playback(folder,progress=operation.update),None))
            except Exception as error: cache_results.put((None,str(error)))
        threading.Thread(target=worker,daemon=True).start()
        def finish():
            if cache_results.empty(): root.after(200,finish); return
            result,error=cache_results.get(); root.cache_move_busy=False; cache_button['state']='normal'
            cache_text.set('轉檔快取目錄：'+str(lib.playback_dir));end_progress(error)
            if error:messagebox.showerror('未完成搬移',error,parent=root)
            else:messagebox.showinfo('快取目錄已更新',f"已搬移並驗證 {result['moved']} 個快取。\n舊目錄保留 {result['retained']} 個未能清理的快取。\n後續轉檔將使用新目錄。",parent=root)
        root.after(200,finish)
    cache_button=ttk.Button(cache_row,text='選擇目錄並搬移快取',command=choose_cache); cache_button.pack(anchor='w',pady=(6,0))
    space_row=ttk.Frame(parent);space_row.pack(fill='x',padx=20,pady=4)
    space_text=tk.StringVar(value='快取空間：按「檢查空間」更新')
    ttk.Label(space_row,textvariable=space_text,wraplength=420).pack(side='left',fill='x',expand=True)
    def check_space():
        try:
            usage=cache_usage(lib.playback_dir)
            space_text.set(f"快取 {usage['files']} 個 · {usage['bytes']/1024**3:.2f} GB；磁碟可用 {usage['free']/1024**3:.2f} GB")
        except OSError:space_text.set('目前無法取得快取磁碟空間。')
    def clean_cache():
        if service_running() or getattr(root,'cache_move_busy',False) or getattr(root,'conversion_busy',False):
            messagebox.showinfo('請先停止服務','請停止服務並等候保存或搬移作業完成。',parent=root);return
        operation.update('準備清理')
        root.cache_move_busy=True;clean_button['state']='disabled';cache_button['state']='disabled'
        space_text.set('正在核對已保存的副本；無法確認的快取將保留…')
        result_queue=queue.Queue()
        def worker():
            try:result_queue.put((lib.cleanup_playback(progress=operation.update),None))
            except Exception as error:result_queue.put((None,str(error)))
        threading.Thread(target=worker,daemon=True).start()
        def finish():
            if result_queue.empty():root.after(200,finish);return
            result,error=result_queue.get();root.cache_move_busy=False
            clean_button['state']='normal';cache_button['state']='normal';check_space();end_progress(error)
            if error:messagebox.showerror('清理未完成',error,parent=root)
            else:messagebox.showinfo('安全清理完成',f"已清理 {result['removed']} 個重複快取，釋放 {result['bytes']/1024**3:.2f} GB。\n無法驗證或仍待處理的快取不會刪除。",parent=root)
        root.after(200,finish)
    ttk.Button(space_row,text='檢查空間',command=check_space).pack(side='right',padx=4)
    clean_button=ttk.Button(space_row,text='清理已保存的重複快取',command=clean_cache);clean_button.pack(side='right',padx=4)
    ttk.Label(parent,text='先停止服務並等待停止完成，即可搬移或清理；背景預轉與略過人工審核可保留勾選。僅搬移已完成快取，驗證後才清理舊檔，原始影片不搬移。',style='Sub.TLabel',wraplength=800).pack(anchor='w',padx=20)



def open_conversion_records(root,lib,log,service_running=lambda:False):
    if lib.cache_migrating:
        messagebox.showinfo('正在搬移','請等待快取搬移完成。',parent=root); return
    previous=getattr(root,'conversion_window',None)
    if previous and previous.winfo_exists(): previous.deiconify(); previous.lift(); return
    window=tk.Toplevel(root); root.conversion_window=window
    window.title('轉檔記錄｜保留MP4'); window.configure(bg='#171817')
    size_window(window,records=True)
    notebook=ttk.Notebook(window);notebook.pack(fill='both',expand=True,padx=8,pady=8)
    records_page=ttk.Frame(notebook);storage_page=ttk.Frame(notebook)
    notebook.add(records_page,text='轉檔記錄');notebook.add(storage_page,text='快取與空間')
    ttk.Label(records_page,text='先開啟成品檢查 → 標記已確認 → 保留MP4並回收原檔',font=('Microsoft JhengHei UI',14)).pack(anchor='w',padx=16,pady=12)
    ttk.Label(records_page,text='手動模式只處理選取且已確認的記錄。勾選略過人工審核後，自動處理全部完成項目；先保存、驗證，再回收原檔，不覆蓋同名檔。',wraplength=1040).pack(anchor='w',padx=16)
    build_cache_controls(storage_page,root,lib,service_running)
    encode_text=tk.StringVar();ttk.Label(records_page,textvariable=encode_text).pack(fill='x',padx=16)
    encode_bar=ttk.Progressbar(records_page,maximum=100);encode_bar.pack(fill='x',padx=16,pady=4)
    save_text=tk.StringVar(value='保存作業：待命');ttk.Label(records_page,textvariable=save_text).pack(fill='x',padx=16)
    save_bar=ttk.Progressbar(records_page,maximum=100);save_bar.pack(fill='x',padx=16,pady=4)
    frame=ttk.Frame(records_page); frame.pack(fill='both',expand=True,padx=16,pady=10)
    tree=ttk.Treeview(frame,columns=('status','name','source','output'),show='headings',selectmode='extended')
    for key,label,width in [('status','狀態',125),('name','影片',210),('source','原檔位置',380),('output','成品／保留MP4位置',380)]:
        tree.heading(key,text=label); tree.column(key,width=width,minwidth=80,stretch=False)
    vertical=ttk.Scrollbar(frame,orient='vertical',command=tree.yview); horizontal=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
    tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
    tree.grid(row=0,column=0,sticky='nsew'); vertical.grid(row=0,column=1,sticky='ns'); horizontal.grid(row=1,column=0,sticky='ew')
    frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
    details=tk.Text(records_page,height=4,wrap='word',bg='#1b221d',fg='#d8e5d9',state='disabled'); details.pack(fill='x',padx=16)
    state=tk.StringVar(value='待處理與失敗項目會保留；保存MP4並成功回收原檔後，自動移除該筆記錄。'); ttk.Label(records_page,textvariable=state,wraplength=1040).pack(anchor='w',padx=16,pady=7)
    buttons=ttk.Frame(records_page); buttons.pack(fill='x',padx=16,pady=(0,14))
    rows={}; busy=False; results=queue.Queue()
    auto_mode=tk.BooleanVar(value=lib.auto_promoter.enabled)
    names={'ready':'待人工檢查','confirmed':'已確認','saved':'MP4已保存／待回收','replaced':'僅保留MP4'}
    def selection_changed(event=None):
        selected=[rows[key] for key in tree.selection() if key in rows]
        manual=not busy and not lib.cache_migrating and not lib.auto_promoter.enabled and not lib.auto_promoter.busy
        for button in (review_button,confirm_button): button['state']='normal' if manual else 'disabled'
        remove_button['state']='normal' if selected and manual and all(row['confirmed_at'] and row['status'] in ('confirmed','saved') for row in selected) else 'disabled'
        details.configure(state='normal'); details.delete('1.0','end')
        if len(selected)==1:
            row=selected[0]; details.insert('end','原檔：'+row['source_path']+'\n成品：'+(row['saved_path'] or row['output_path'])+'\n狀態：'+names.get(row['status'],row['status']))
        elif selected: details.insert('end',f'已選取 {len(selected)} 筆，僅會處理這些記錄。')
        details.configure(state='disabled')
    def refresh():
        selected=set(tree.selection()); tree.delete(*tree.get_children()); rows.clear()
        for row in lib.conversion_store.records():
            rows[row['id']]=row
            tree.insert('','end',iid=row['id'],values=(names.get(row['status'],row['status']),Path(row['source_path']).name,row['source_path'],row['saved_path'] or row['output_path']))
        remaining=[key for key in selected if key in rows]
        if remaining: tree.selection_set(remaining)
        selection_changed()
    def review():
        if busy or getattr(root,'service_busy',False) or lib.cache_migrating or lib.auto_promoter.enabled or lib.auto_promoter.busy: return
        selected=tree.selection()
        if len(selected)!=1: messagebox.showinfo('檢查成品','請選取一筆記錄。',parent=window); return
        if lib.privacy_state()['enabled'] and not messagebox.askyesno('開啟外部成品檢查','隱蔽目前已開啟。網頁以外的系統播放器不會套用毛玻璃，將顯示清晰成品。是否開啟？',parent=window): return
        try: os.startfile(str(lib.conversion_store.review_path(selected[0])))
        except Exception as error: messagebox.showerror('無法開啟',str(error),parent=window)
    def run_batch(action):
        nonlocal busy
        selected=list(tree.selection())
        if not selected or busy or getattr(root,'service_busy',False) or lib.cache_migrating or lib.auto_promoter.enabled or lib.auto_promoter.busy: return
        if action=='confirm':
            if not messagebox.askyesno('人工檢查確認',f'你是否已播放檢查這 {len(selected)} 筆成品，確認畫面、聲音與內容沒有問題？\n此操作只標記已確認，不刪除原檔。',parent=window): return
        else:
            if not all(rows[key]['confirmed_at'] and rows[key]['status'] in ('confirmed','saved') for key in selected): return
            description='\n'.join(rows[key]['source_path'] for key in selected[:8])
            if len(selected)>8: description+=f'\n另有 {len(selected)-8} 筆選取項目'
            if not messagebox.askyesno('確認保留MP4並回收原檔',f'將處理選取的 {len(selected)} 筆：\n{description}\n\n先在來源資料夾保存並驗證MP4，再將原檔移到資源回收筒。\n不覆蓋既有檔案；失敗時保留原檔。請先關閉正在播放原檔的裝置。\n是否繼續？',parent=window): return
        busy=True; root.conversion_busy=True; state.set('處理中，請勿移動或修改來源／成品…')
        for button in (review_button,confirm_button,remove_button,refresh_button,auto_check): button['state']='disabled'
        generation=lib.processing_generation
        def worker():
            success=0; errors=[]
            for number,key in enumerate(selected,1):
                if generation!=lib.processing_generation:break
                def progress(phase,index=0,total=0,done=0,size=0):lib.file_progress.update(phase,number,len(selected),done,size)
                progress('確認成品' if action=='confirm' else '準備保存')
                try:
                    if action=='confirm': lib.conversion_store.confirm(key,progress=progress)
                    else: lib.conversion_store.promote(key,progress=progress)
                    success+=1
                except Exception as error: errors.append(Path(rows[key]['source_path']).name+'：'+str(error))
            if action!='confirm' and success: lib.rescan()
            results.put((success,errors))
        threading.Thread(target=worker,daemon=True).start()
    def pump_results():
        nonlocal busy
        if not window.winfo_exists(): return
        render_conversion_progress(lib,encode_bar,encode_text)
        if busy or lib.auto_promoter.busy:render_operation_progress(save_bar,save_text,lib.file_progress.snapshot())
        else:save_bar.stop();save_bar.configure(mode='determinate');save_bar['value']=0;save_text.set('保存作業：待命')
        while not results.empty():
            success,errors=results.get(); busy=False; root.conversion_busy=False
            for button in (review_button,confirm_button,refresh_button,auto_check): button['state']='normal'
            refresh(); state.set(f'完成 {success} 筆；失敗 {len(errors)} 筆。已完成保存與回收的記錄自動移除；其餘保留。')
            log('轉檔記錄操作完成。')
            if errors: messagebox.showwarning('部分項目未完成','\n'.join(errors[:10]),parent=window)
        if lib.auto_promoter.enabled or lib.auto_promoter.busy:
            refresh()
            if lib.auto_promoter.paused:state.set('服務未啟動或已停止；自動保留暫停，啟動服務後恢復。')
            else:state.set(f'自動模式：完成 {lib.auto_promoter.completed} 筆；未完成 {lib.auto_promoter.errors} 筆。關閉此視窗仍持續；取消勾選後停止後續項目。')
        else: selection_changed()
        window.after(500,pump_results)
    review_button=ttk.Button(buttons,text='開啟成品檢查',command=review); review_button.pack(side='left',padx=3)
    confirm_button=ttk.Button(buttons,text='標記已確認',command=lambda:run_batch('confirm')); confirm_button.pack(side='left',padx=3)
    remove_button=ttk.Button(buttons,text='保留MP4並回收原檔',command=lambda:run_batch('promote'),state='disabled'); remove_button.pack(side='left',padx=3)
    refresh_button=ttk.Button(buttons,text='更新記錄',command=refresh); refresh_button.pack(side='left',padx=3)
    def toggle_auto():
        if lib.cache_migrating:
            auto_mode.set(False); return
        lib.auto_promoter.set_enabled(auto_mode.get())
        selection_changed()
        state.set('自動模式已啟用；處理全部既有與新完成項目。' if auto_mode.get() else '已停止後續自動項目；正在保存的單筆會安全完成。')
    auto_check=ttk.Checkbutton(buttons,text='略過人工審核',variable=auto_mode,command=toggle_auto); auto_check.pack(side='left',padx=12)
    tree.bind('<<TreeviewSelect>>',selection_changed)
    def close():
        if busy or getattr(root,'cache_move_busy',False): messagebox.showinfo('仍在處理','請等待目前操作完成，避免中斷保存。',parent=window)
        else: window.destroy()
    window.protocol('WM_DELETE_WINDOW',close); refresh(); pump_results()


def _run(instance):
    if os.name=='nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('LocalCinema.Desktop')
    root=tk.Tk(); root.title(f'LocalCinema v{APP_VERSION}｜本機影片後台 · by BitingBox Studio')
    size_window(root)
    try: root.iconbitmap(default=str(BASE/'assets'/'localcinema.ico'))
    except tk.TclError: pass
    root.configure(bg='#171817'); root.option_add('*Font',('Microsoft JhengHei UI',10))
    style=ttk.Style(root); style.theme_use('clam')
    style.configure('.',background='#171817',foreground='#e5e1d7',fieldbackground='#212321',bordercolor='#41423d',lightcolor='#41423d',darkcolor='#171817')
    style.configure('TButton',background='#2b2d28',padding=(10,8),borderwidth=1)
    style.map('TButton',background=[('active','#46483f')],foreground=[('disabled','#77796f')])
    style.configure('Treeview',background='#20221f',fieldbackground='#20221f',foreground='#e5e1d7',rowheight=29)
    style.configure('Treeview.Heading',background='#30332d',foreground='#bdb8ac',padding=8)
    style.map('Treeview',background=[('selected','#41533e')],foreground=[('selected','#fff9ec')])
    style.configure('Sub.TLabel',foreground='#a4a194')
    style.configure('Source.TNotebook',background='#171817',tabmargins=(2,8,2,0))
    style.configure('Source.TNotebook.Tab',padding=(18,8),background='#292c27',foreground='#bfc2b6',borderwidth=1)
    style.map('Source.TNotebook.Tab',background=[('selected','#4c6447'),('active','#373b31')],foreground=[('selected','#fff3da'),('active','#f1eddf')],padding=[('selected',(18,8))])
    shell=ttk.Frame(root); shell.pack(fill='both',expand=True)
    canvas=tk.Canvas(shell,bg='#171817',highlightthickness=0)
    scrollbar=ttk.Scrollbar(shell,orient='vertical',command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set); scrollbar.pack(side='right',fill='y'); canvas.pack(side='left',fill='both',expand=True)
    content=ttk.Frame(canvas); content_window=canvas.create_window((0,0),window=content,anchor='nw')
    content.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda event:canvas.itemconfigure(content_window,width=event.width))
    def fit_content():
        root.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox('all'))
        canvas.configure(scrollregion=canvas.bbox('all'))
    def scroll_content(event):
        if not isinstance(event.widget,(tk.Text,ttk.Treeview)):
            canvas.yview_scroll(-1 if event.delta>0 else 1,'units')
    root.bind_all('<MouseWheel>',scroll_content,add='+')
    events=queue.Queue(); lib=Library(events.put); server=None; tray=None
    lib.processing_paused=True;lib.processing_stop.set();lib.auto_promoter.set_paused(True)
    lib.auto_promoter.set_enabled(True)
    heading=ttk.Frame(content); heading.pack(fill='x',padx=20,pady=(16,4))
    try:
        from PIL import Image,ImageTk
        root.emblem=ImageTk.PhotoImage(Image.open(BASE/'assets'/'camellia-emblem.png').resize((62,42)))
        ttk.Label(heading,image=root.emblem).pack(side='left',padx=(0,10))
    except ImportError: pass
    ttk.Label(heading,text='映室  /  LOCAL CINEMA',font=('Microsoft JhengHei UI',18)).pack(side='left')
    ttk.Label(content,text='加入多個影片來源，啟動後以瀏覽器觀看；關閉視窗可留在系統列。').pack(anchor='w',padx=20)
    outer_content=content
    backend_pages=ttk.Notebook(outer_content,style='Source.TNotebook'); backend_pages.pack(fill='both',expand=True,padx=12,pady=8)
    sources_page=ttk.Frame(backend_pages); service_page=ttk.Frame(backend_pages); backup_page=ttk.Frame(backend_pages)
    backend_pages.add(sources_page,text='片源與群組');backend_pages.add(service_page,text='服務與轉檔');backend_pages.add(backup_page,text='資料備份')
    build_backup_page(backup_page,root,lib);lib.backups.start()
    content=sources_page
    group_toolbar=ttk.Frame(content);group_toolbar.pack(fill='x',padx=20,pady=(12,0))
    ttk.Label(group_toolbar,text='片源群組',font=('Microsoft JhengHei UI',12)).pack(side='left')
    ttk.Button(group_toolbar,text='＋ 新增／管理片源群組',command=lambda:open_group_manager(root,lib,groups_changed)).pack(side='right')
    source_tabs=ttk.Notebook(content,style='Source.TNotebook'); source_tabs.pack(fill='x',padx=20,pady=12)
    group_trees={}; group_pages={}; group_kinds={}
    active_group_id=DEFAULT_GROUP
    web_signature=[None]
    def groups_changed():
        lib.refresh_web(); refresh()
    def chosen_group():
        selected=source_tabs.select()
        return next((group_id for group_id,page in group_pages.items() if str(page)==selected),DEFAULT_GROUP)
    def chosen_is_web():
        return group_kinds.get(chosen_group())==WEB_KIND
    def current_tree():
        return group_trees.get(chosen_group())
    def works_signature():
        return tuple((row['id'],row['group'],row['url'],row['title']) for row in lib.web_works.rows())
    def build_table(group_id,group,web):
        page=ttk.Frame(source_tabs); group_pages[group_id]=page; group_kinds[group_id]=WEB_KIND if web else 'media'
        if web:
            table=ttk.Treeview(page,columns=('url','title'),show='headings',height=8,selectmode='extended')
            table.heading('url',text='作品網址'); table.heading('title',text='標題')
            table.column('url',width=520); table.column('title',width=220,stretch=False)
            table.bind('<Double-1>',lambda event:edit_work())
        else:
            table=ttk.Treeview(page,columns=('path','mode'),show='headings',height=8,selectmode='extended')
            table.heading('path',text='根目錄'); table.heading('mode',text='資料夾型式')
            table.column('path',width=620); table.column('mode',width=120,stretch=False)
            table.bind('<Button-3>',lambda event,table=table:source_context(event,table))
        bar=ttk.Scrollbar(page,orient='vertical',command=table.yview); table.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y'); table.pack(fill='both',expand=True)
        group_trees[group_id]=table; source_tabs.add(page,text=group['name'])
    def refresh():
        nonlocal active_group_id
        current=chosen_group() if group_pages else active_group_id
        groups=list(lib.config['groups'])
        kinds={group['id']:group_kind(group) for group in groups}
        for group_id in list(group_pages):
            if group_id not in kinds or kinds[group_id]!=group_kinds[group_id]:
                source_tabs.forget(group_pages[group_id]); group_pages.pop(group_id).destroy(); group_trees.pop(group_id); group_kinds.pop(group_id)
        works={}
        for row in lib.web_works.rows():works.setdefault(row['group'],[]).append(row)
        for index,group in enumerate(groups):
            group_id=group['id'];web=kinds[group_id]==WEB_KIND
            if group_id not in group_pages:build_table(group_id,group,web)
            table=group_trees[group_id]; selected=table.selection()
            table.delete(*table.get_children())
            if web:
                rows=works.get(group_id,[])
                for row in rows:table.insert('','end',iid=row['id'],values=(row['url'],row['title']))
                label=f"{group['name']} · 網址 ({len(rows)})"
            else:
                rows=[(n,item) for n,item in enumerate(lib.config['roots']) if item.get('group',DEFAULT_GROUP)==group_id]
                for n,item in rows:
                    table.insert('','end',iid=str(n),values=(item['path'],'平鋪型' if item['mode']=='flat' else '目錄型'))
                label=f"{group['name']} ({len(rows)})"
            for iid in selected:
                if table.exists(iid): table.selection_add(iid)
            source_tabs.insert(index,group_pages[group_id])
            source_tabs.tab(group_pages[group_id],text=label)
        web_signature[0]=works_signature()
        active_group_id=current if current in kinds else DEFAULT_GROUP
        source_tabs.select(group_pages[active_group_id])
        update_controls()
    def add(mode):
        folder=filedialog.askdirectory()
        if folder:
            resolved=str(Path(folder).resolve())
            with lib.lock:
                lib.config['roots']=[r for r in lib.config['roots'] if str(Path(r['path']).resolve()).casefold()!=resolved.casefold()]
                lib.config['roots'].append({'path':resolved,'mode':mode,'group':chosen_group()}); save_config(lib.config)
            refresh()
    def work_dialog(existing=None):
        dialog=tk.Toplevel(root);dialog.title('編輯作品' if existing else '新增作品網址');dialog.configure(bg='#171817');dialog.transient(root)
        url=tk.StringVar(value=existing['url'] if existing else '');title=tk.StringVar(value=existing['title'] if existing else '')
        ttk.Label(dialog,text='作品網址').pack(anchor='w',padx=18,pady=(14,2))
        url_entry=ttk.Entry(dialog,textvariable=url,width=64);url_entry.pack(fill='x',padx=18)
        ttk.Label(dialog,text='標題（選填，留白使用網頁標題）').pack(anchor='w',padx=18,pady=(10,2))
        ttk.Entry(dialog,textvariable=title,width=64).pack(fill='x',padx=18)
        ttk.Label(dialog,text='備註（選填，可多行）').pack(anchor='w',padx=18,pady=(10,2))
        notes=tk.Text(dialog,height=6,width=64,bg='#242d25',fg='#dedfd3',insertbackground='#dedfd3',relief='flat',wrap='word')
        notes.pack(fill='both',expand=True,padx=18);notes.insert('1.0',existing.get('notes','') if existing else '')
        open_in_tab=tk.BooleanVar(value=bool(existing.get('openInTab')) if existing else False)
        ttk.Checkbutton(dialog,text='一律以分頁開啟（不在映室內嵌入，適合需登入或會跳脫外框的網站）',variable=open_in_tab).pack(anchor='w',padx=18,pady=(8,0))
        ttk.Label(dialog,text='新增後會在背景開啟網站 10 秒並擷取快照。',wraplength=460).pack(anchor='w',padx=18,pady=8)
        result={}
        def save():
            try:
                with lib.lock:
                    if existing:lib.web_works.update(existing['id'],url.get(),title.get(),notes.get('1.0','end-1c'),open_in_tab.get())
                    else:lib.web_works.add(chosen_group(),url.get(),title.get(),notes.get('1.0','end-1c'),open_in_tab.get())
                result['ok']=True;dialog.destroy()
            except ValueError as error:messagebox.showerror('無法儲存作品',str(error),parent=dialog)
        buttons=ttk.Frame(dialog);buttons.pack(fill='x',padx=18,pady=(4,14))
        ttk.Button(buttons,text='儲存',command=save).pack(side='right');ttk.Button(buttons,text='取消',command=dialog.destroy).pack(side='right',padx=6)
        dialog.grab_set();url_entry.focus_set();dialog.wait_window()
        if result:groups_changed()
    def add_work():
        if chosen_is_web():work_dialog()
    def edit_work():
        table=current_tree();selected=table.selection() if table else ()
        if not chosen_is_web() or len(selected)!=1:
            if chosen_is_web():messagebox.showinfo('編輯作品','請先選取一個作品網址。',parent=root)
            return
        try:work_dialog(lib.web_works.get(selected[0]))
        except ValueError as error:messagebox.showerror('無法編輯作品',str(error),parent=root)
    def remove():
        table=current_tree()
        selected=table.selection() if table else ()
        if not selected:return
        if chosen_is_web():
            rows=[row for row in lib.web_works.rows(chosen_group()) if row['id'] in selected]
            names='\n'.join('・'+row['title'] for row in rows[:8])+('\n…' if len(rows)>8 else '')
            if not messagebox.askyesno('刪除作品',f'刪除 {len(rows)} 個作品網址？\n{names}\n\n只移除映室中的網址、快照、標籤與最愛，不影響網站本身。',parent=root):return
            if not messagebox.askyesno('再次確認刪除','此操作無法復原。確定要刪除嗎？',icon='warning',parent=root):return
            with lib.lock:
                for row in rows:lib.web_works.delete(row['id'],row['id'])
            groups_changed();return
        with lib.lock:
            for n in sorted(map(int,selected),reverse=True): lib.config['roots'].pop(n)
            save_config(lib.config)
        refresh()
    def assign_group(target,selected):
        if not selected:return
        with lib.lock:lib.source_groups.assign([int(index) for index in selected],target)
        refresh(); events.put('片源群組已更新；請重新掃描套用到網頁片單。')
    def source_context(event,table):
        row=table.identify_row(event.y)
        if not row:return
        if row not in table.selection():table.selection_set(row)
        table.focus(row);table.focus_set()
        selected=tuple(table.selection())
        previous=getattr(root,'source_context_menu',None)
        if previous:previous.destroy()
        menu=tk.Menu(root,tearoff=False,bg='#252821',fg='#e5e1d7',activebackground='#494b3d',activeforeground='#fff3da')
        root.source_context_menu=menu
        targets=tk.Menu(menu,tearoff=False,bg='#252821',fg='#e5e1d7',activebackground='#494b3d',activeforeground='#fff3da')
        for group in [group for group in lib.config['groups'] if group_kind(group)!=WEB_KIND]:
            targets.add_command(label=group['name'],state='disabled' if group['id']==chosen_group() else 'normal',
                                command=lambda target=group['id'],selected=selected:assign_group(target,selected))
        menu.add_cascade(label=f'移動至群組（{len(selected)} 個目錄）',menu=targets)
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:menu.grab_release()
        return 'break'
    controls_holder=ttk.Frame(content); controls_holder.pack(fill='x',padx=20)
    media_controls=ttk.Frame(controls_holder); web_controls=ttk.Frame(controls_holder)
    for label,call in [('新增目錄影片清單',lambda:add('directory')),('新增平鋪影片清單',lambda:add('flat')),('移除選取',remove)]: ttk.Button(media_controls,text=label,command=call).pack(side='left',padx=3)
    for label,call in [('新增作品網址',add_work),('編輯選取',edit_work),('移除選取',remove)]: ttk.Button(web_controls,text=label,command=call).pack(side='left',padx=3)
    source_hint=tk.StringVar()
    ttk.Label(content,textvariable=source_hint,wraplength=850).pack(anchor='w',padx=20,pady=(10,6))
    info_holder=ttk.Frame(content); info_holder.pack(fill='x')
    media_info=ttk.Frame(info_holder)
    guide_row=ttk.Frame(media_info);guide_row.pack(fill='x',padx=20,pady=(0,12))
    for title,description in [
        ('目錄影片清單｜一個資料夾＝一個片單','只收集根目錄下一層資料夾內的影片。\n同夾多支影片合為可選多集；不搜尋更深層。\n根目錄直接放的影片不會收集。'),
        ('平鋪影片清單｜一支影片＝一個片單','根目錄的每支影片，以檔名各建一個片單。\n下一層資料夾按目錄方式收集，可合成多集。\n不搜尋更深層；另設平鋪片源的子夾優先接管。')]:
        card=ttk.LabelFrame(guide_row,text=title,padding=12);card.pack(side='left',fill='both',expand=True,padx=(0,8))
        ttk.Label(card,text=description,wraplength=365,justify='left').pack(anchor='w')
    ttk.Button(media_info,text='查看兩種收集方式的圖解',command=lambda:open_source_help(root,BASE)).pack(anchor='w',padx=20,pady=(0,12))
    web_info=ttk.Frame(info_holder)
    web_card=ttk.LabelFrame(web_info,text='網路作品｜一個網址＝一個作品',padding=12);web_card.pack(fill='x',padx=20,pady=(0,12))
    ttk.Label(web_card,text='新增後會在背景以 Edge／Chrome 開啟網站 10 秒並擷取快照。首頁卡片只顯示快照，放大才載入真實網頁，也可以分頁開啟。\n雙擊網址可編輯標題、網址與備註；刪除需確認兩次，只移除映室中的資料，不影響網站本身。',wraplength=800,justify='left').pack(anchor='w')
    def update_controls(event=None):
        web=chosen_is_web()
        for frame in (media_controls,web_controls,media_info,web_info):frame.pack_forget()
        (web_controls if web else media_controls).pack(side='left')
        (web_info if web else media_info).pack(fill='x')
        source_hint.set('新增、編輯與移除只作用於目前的網路作品群組；首頁同步更新，不需要重新掃描。' if web else '新增與移除只作用於目前群組。目錄列按右鍵可移動群組（支援複選）；變更後到「服務與轉檔」重新掃描。')
    source_tabs.bind('<<NotebookTabChanged>>',update_controls)
    def watch_works():
        try:
            if root.winfo_exists() and works_signature()!=web_signature[0]:refresh()
        except Exception:pass
        root.after(2000,watch_works)
    root.after(2000,watch_works)
    content=service_page
    privacy_row=ttk.Frame(content); privacy_row.pack(fill='x',padx=20,pady=(8,2))
    privacy_var=tk.BooleanVar(value=bool(lib.config.get('privacy_blur',False)))
    ttk.Checkbutton(privacy_row,text='隱蔽（所有影片、封面與預覽加上毛玻璃）',variable=privacy_var,command=lambda:lib.set_privacy(privacy_var.get())).pack(side='left')
    close_lock_var=tk.BooleanVar(value=bool(lib.config.get('lock_on_page_close',False)))
    ttk.Checkbutton(content,text='關閉頁面即上鎖（最後一個分頁關閉時）',variable=close_lock_var,command=lambda:lib.set_lock_on_page_close(close_lock_var.get())).pack(anchor='w',padx=20,pady=4)
    branding_var=tk.BooleanVar(value=bool(lib.config.get('hide_branding',False)))
    ttk.Checkbutton(content,text='隱藏首頁的 BitingBox Studio 與 Ryan Hsu 版權署名',variable=branding_var,command=lambda:lib.set_hide_branding(branding_var.get())).pack(anchor='w',padx=20,pady=4)
    background_row=ttk.Frame(content); background_row.pack(fill='x',padx=20,pady=(8,2))
    background_var=tk.BooleanVar(value=lib.background_enabled)
    def toggle_background():
        if getattr(root,'cache_move_busy',False):
            background_var.set(lib.background_enabled); return
        lib.set_background(background_var.get())
    ttk.Checkbutton(background_row,text='背景預先轉檔（使用CPU與磁碟空間）',variable=background_var,command=toggle_background).pack(side='left')
    ttk.Button(background_row,text='轉檔記錄／人工檢查',command=lambda:open_conversion_records(root,lib,events.put,lambda:server is not None)).pack(side='left',padx=12)
    ttk.Label(content,text='掃描後自動排程非MP4／M4V／WebM影片；每次一支，已完成快取會跳過。取消勾選暫停後續排程。',style='Sub.TLabel',wraplength=800).pack(anchor='w',padx=20)
    conversion_text=tk.StringVar(value='背景預轉尚未排程')
    ttk.Label(content,textvariable=conversion_text,wraplength=800).pack(anchor='w',padx=20,pady=(5,2))
    conversion_progress=ttk.Progressbar(content,mode='determinate',maximum=100)
    conversion_progress.pack(fill='x',padx=20,pady=(0,7))
    active_text=tk.StringVar();ttk.Label(content,textvariable=active_text,wraplength=850).pack(fill='x',padx=20)
    active_bar=ttk.Progressbar(content,maximum=100);active_bar.pack(fill='x',padx=20,pady=(2,7))
    status=tk.StringVar(value='尚未啟動')
    status_link=ttk.Label(content,textvariable=status,takefocus=True)
    status_link.pack(anchor='w',padx=20)
    status_link.bind('<Button-1>',lambda event:open_page() if server else None)
    status_link.bind('<Return>',lambda event:open_page() if server else None)
    lan_frame=ttk.Frame(content); lan_frame.pack(fill='x',padx=20)
    lan_links=[]
    def show_lan():
        lan_links.clear()
        for widget in lan_frame.winfo_children(): widget.destroy()
        if server is None:
            root.after_idle(fit_content); return
        addresses=lan_addresses()
        if not addresses:
            ttk.Label(lan_frame,text='尚未取得區網 IPv4；請確認已連接 Wi-Fi 或網路線。',style='Sub.TLabel').pack(anchor='w')
        for address in addresses:
            url=f'http://{address}:{server.server_port}/?access={lib.access_key}'
            lan_links.append(url)
            row=ttk.LabelFrame(lan_frame,text='手機掃描連線',padding=12); row.pack(fill='x',pady=(8,4))
            import qrcode
            from PIL import ImageTk
            qr=qrcode.QRCode(box_size=3,border=4,error_correction=qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(url); qr.make(fit=True)
            photo=ImageTk.PhotoImage(qr.make_image(fill_color='#152018',back_color='white').convert('RGB'))
            qr_label=ttk.Label(row,image=photo);qr_label.image=photo;qr_label.pack(side='right',padx=(16,0))
            details=ttk.Frame(row);details.pack(side='left',fill='both',expand=True)
            ttk.Label(details,text='區網連線已啟用',font=('Microsoft JhengHei UI',11,'bold')).pack(anchor='w',pady=(2,8))
            label=ttk.Label(details,text=f'區網：{url}',cursor='hand2',foreground='#c7c9a6',font=('Segoe UI',10,'underline'),takefocus=True,wraplength=540)
            label.pack(anchor='w')
            ttk.Label(details,text='手機與電腦請連接相同網路。\n此 QR Code 含入口存取碼，請勿公開分享。',style='Sub.TLabel',wraplength=480).pack(anchor='w',pady=(10,2))
            label.bind('<Button-1>',lambda event,url=url:webbrowser.open(url))
            label.bind('<Return>',lambda event,url=url:webbrowser.open(url))
        root.after_idle(fit_content)
    def start():
        nonlocal server
        if getattr(root,'service_busy',False):return
        if getattr(root,'cache_move_busy',False):
            messagebox.showinfo('正在搬移','請等待快取搬移完成後再啟動服務。',parent=root); return
        if server is None:
            try: server=ThreadingHTTPServer(('0.0.0.0',8765),make_handler(lib))
            except OSError:
                server=ThreadingHTTPServer(('0.0.0.0',0),make_handler(lib))
                events.put('預設連接埠 8765 無法使用，已改用其他可用連接埠；請以畫面顯示連結為準。')
            server.daemon_threads=True
            threading.Thread(target=server.serve_forever,daemon=True).start()
        lib.resume_processing(wake=False);service_button.configure(text='■ 停止服務')
        url=entry_url(server.server_port,lib.access_key); status.set('運行中：'+url)
        status_link.configure(cursor='hand2',foreground='#c7c9a6',font=('Segoe UI',10,'underline'))
        show_lan()
        threading.Thread(target=lib.rescan,daemon=True).start()
    def open_page():
        if getattr(root,'service_busy',False):return
        if server is None: start()
        if server is None: return
        webbrowser.open(entry_url(server.server_port,lib.access_key))
    def stop():
        nonlocal server
        if getattr(root,'service_busy',False):return
        root.service_busy=True;service_button.configure(text='正在停止…',state='disabled')
        status.set('正在停止服務與轉檔；保存／回收中的單筆會安全完成…')
        previous=server;result=queue.Queue()
        def worker():
            try:
                if previous:previous.shutdown();previous.server_close()
                lib.pause_processing()
                while getattr(root,'conversion_busy',False):time.sleep(.05)
                result.put(None)
            except Exception as error:result.put(str(error))
        threading.Thread(target=worker,daemon=True).start()
        def finish():
            nonlocal server
            if result.empty():root.after(100,finish);return
            error=result.get();root.service_busy=False
            if error:
                service_button.configure(text='■ 停止服務',state='normal')
                messagebox.showerror('停止未完成',error,parent=root);return
            server=None;service_button.configure(text='▶ 啟動服務',state='normal')
            status.set('已停止服務與背景轉檔；已完成快取保留')
            status_link.configure(cursor='',foreground='#e5e1d7',font=('Segoe UI',10));show_lan()
        root.after(100,finish)
    def toggle_service():
        if server is None:start()
        else:stop()
    def show(): root.deiconify(); root.state('normal'); root.lift(); root.focus_force()
    def hide():
        if tray:
            messagebox.showinfo('已縮至系統列','程式仍在背景運行，影片服務不會停止。\n\n可從右下角系統列圖示（可能收在隱藏圖示中）開啟後台；\n要完全關閉，請選擇系統列選單中的「結束」，或後台的「結束程式」。',parent=root)
            root.withdraw()
        else: messagebox.showinfo('系統列尚未啟用','請先安裝 pystray 與 Pillow，或使用最小化按鈕。'); root.iconify()
    def quit_app():
        if getattr(root,'service_busy',False) or getattr(root,'conversion_busy',False) or lib.auto_promoter.busy or getattr(root,'cache_move_busy',False):
            messagebox.showinfo('仍在處理','請等待服務停止、保存／回收或搬移作業完成，再結束程式。'); return
        lib.shutdown()
        if tray: tray.stop()
        if server: server.shutdown(); server.server_close()
        root.destroy()
    buttons=ttk.Frame(content); buttons.pack(fill='x',padx=20,pady=10)
    service_button=ttk.Button(buttons,text='▶ 啟動服務',command=toggle_service);service_button.pack(side='left',padx=3)
    for label,call in [('開啟入口頁',open_page),('重新掃描',lambda:threading.Thread(target=lib.rescan,daemon=True).start()),('縮至系統列',hide),('結束程式',quit_app)]: ttk.Button(buttons,text=label,command=call).pack(side='left',padx=3)
    log=tk.Text(content,height=7,bg='#17191f',fg='#d8dee9',state='disabled'); log.pack(fill='both',expand=True,padx=20,pady=(0,15))
    content=outer_content
    backend_pages.bind('<<NotebookTabChanged>>',lambda event:root.after_idle(fit_content))
    studio_row=ttk.Frame(content); studio_row.pack(fill='x',padx=20,pady=(2,14))
    try:
        with Image.open(BASE/'assets'/'bitingbox-studio.png') as studio_image:
            studio_image.thumbnail((190,76),Image.Resampling.LANCZOS)
            root.studio_logo=ImageTk.PhotoImage(studio_image)
        ttk.Label(studio_row,image=root.studio_logo).pack(side='left')
    except (ImportError,OSError,NameError):pass
    ttk.Label(studio_row,text=f'Created by Ryan Hsu. 2026 © Copyright  ·  v{APP_VERSION}',style='Sub.TLabel').pack(side='left',padx=16)

    def pump():
        render_conversion_progress(lib,active_bar,active_text)
        info=lib.conversion_status()
        conversion_text.set(('背景預轉［開啟］' if info['enabled'] else '背景預轉［暫停］')+f"：已檢查 {info['checked']}/{info['total']} · 就緒 {info['ready']} · 排隊 {info['queued']} · 轉換中 {info['converting']} · 本次完成 {info['completed']} · 失敗 {max(info['failed'],info['errors'])}")
        conversion_progress['value']=info['checked']/info['total']*100 if info['total'] else 0
        if instance.requested_show(): show()
        while not events.empty():
            event=events.get()
            if event=='__show': show(); continue
            if event=='__quit': quit_app(); return
            if event=='__open': open_page(); continue
            log.configure(state='normal'); log.insert('end',time.strftime('%H:%M:%S')+' '+event+'\n'); log.see('end'); log.configure(state='disabled')
        root.after(200,pump)
    try:
        import pystray
        from PIL import Image, ImageDraw
        icon=Image.open(BASE/'assets'/'localcinema.ico').convert('RGBA'); icon.thumbnail((64,64))
        tray=pystray.Icon('LocalCinema',icon,'LocalCinema · by BitingBox Studio',pystray.Menu(pystray.MenuItem('顯示後台',lambda:events.put('__show'),default=True),pystray.MenuItem('開啟入口頁',lambda:events.put('__open')),pystray.MenuItem('結束',lambda:events.put('__quit'))))
        threading.Thread(target=tray.run,daemon=True).start()
    except ImportError: events.put('系統列套件尚未安裝，請執行安裝套件.cmd')
    root.protocol('WM_DELETE_WINDOW',hide); refresh(); pump(); root.after_idle(fit_content); root.mainloop()

def main():
    instance=SingleInstance()
    try:
        if instance.primary: _run(instance)
    finally: instance.close()

if __name__=='__main__': main()
