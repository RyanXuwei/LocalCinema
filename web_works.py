"""HTML works: website URLs kept in web-kind groups, shown as snapshots until opened."""
import os,re,secrets,shutil,subprocess,tempfile,threading,time,queue
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
from urllib.request import Request,urlopen

WEB_KIND='web'
MEDIA_KIND='media'
SNAPSHOT_DELAY_MS=10000
IMMEDIATE_DELAY_MS=1500
UPLOAD_LIMIT=12*1024*1024
SNAPSHOT_SIZE=(1280,800)
ID_PATTERN=re.compile(r'w[0-9a-f]{20}')

def group_kind(group):
    return WEB_KIND if group.get('kind')==WEB_KIND else MEDIA_KIND

def normalize_url(value):
    """Only absolute http(s) addresses; credentials in URLs are refused."""
    text=str(value or '').strip()
    if not text:raise ValueError('請輸入作品網址。')
    if len(text)>2048:raise ValueError('網址過長。')
    if '://' not in text:text='https://'+text
    try:parts=urlsplit(text)
    except ValueError:raise ValueError('網址格式錯誤。')
    if parts.scheme.lower() not in ('http','https'):raise ValueError('只支援 http 或 https 網址。')
    if not parts.hostname:raise ValueError('網址缺少網站名稱。')
    if parts.username or parts.password:raise ValueError('網址不可包含帳號或密碼。')
    if any(ord(c)<33 for c in text):raise ValueError('網址不可包含空白或控制字元。')
    try:parts.port
    except ValueError:raise ValueError('網址的連接埠錯誤。')
    return urlunsplit((parts.scheme.lower(),parts.netloc,parts.path or '/',parts.query,parts.fragment))

def clean_title(value,url=''):
    title=re.sub(r'\s+',' ',str(value or '')).strip()[:120]
    return title or (urlsplit(url).hostname or '網頁作品')

def clean_notes(value):
    text=str(value or '').replace('\r\n','\n').replace('\r','\n')
    text='\n'.join(line.rstrip() for line in text.split('\n')).strip('\n')
    if len(text)>5000:raise ValueError('備註最多 5000 字。')
    return text

def frame_policy(headers):
    """'blocked' when the site forbids being framed by another origin, else 'allowed'."""
    options=(headers.get('X-Frame-Options') or '').strip().lower()
    if options in ('deny','sameorigin') or options.startswith('allow-from'):return 'blocked'
    policies=headers.get_all('Content-Security-Policy') if hasattr(headers,'get_all') else [headers.get('Content-Security-Policy')]
    for policy in policies or []:
        if not policy:continue
        for directive in str(policy).split(';'):
            parts=directive.strip().split()
            if parts and parts[0].lower()=='frame-ancestors':
                sources=[source.lower() for source in parts[1:]]
                if '*' not in sources:return 'blocked'
    return 'allowed'

def probe(url,timeout=10):
    """Read response headers and the page title without running scripts."""
    request=Request(url,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) LocalCinemaSnapshot/2.0','Accept':'text/html,*/*;q=0.8'})
    with urlopen(request,timeout=timeout) as response:
        policy=frame_policy(response.headers)
        title=''
        if 'html' in (response.headers.get('Content-Type') or '').lower():
            body=response.read(262144).decode(response.headers.get_content_charset() or 'utf-8',errors='replace')
            match=re.search(r'<title[^>]*>(.*?)</title>',body,re.I|re.S)
            if match:
                import html
                title=html.unescape(match.group(1))
        return policy,clean_title(title,url) if title else ''

def find_browser():
    candidates=[]
    for variable in ('PROGRAMFILES(X86)','PROGRAMFILES','LOCALAPPDATA'):
        base=os.environ.get(variable)
        if base:
            candidates+= [Path(base)/'Microsoft/Edge/Application/msedge.exe',Path(base)/'Google/Chrome/Application/chrome.exe']
    for name in ('msedge','chrome','chromium','google-chrome'):
        found=shutil.which(name)
        if found:candidates.append(Path(found))
    return next((path for path in candidates if path.is_file()),None)

def capture_snapshot(browser,url,target,delay_ms=SNAPSHOT_DELAY_MS,size=SNAPSHOT_SIZE):
    """Headless Edge/Chrome in a throwaway profile; page time runs 10 s before the screenshot."""
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    flags=0x08000000 if os.name=='nt' else 0
    with tempfile.TemporaryDirectory(prefix='localcinema-snapshot-') as work:
        raw=Path(work)/'shot.png'
        command=[str(browser),'--headless=new','--disable-gpu','--hide-scrollbars','--mute-audio','--no-first-run',
                 '--no-default-browser-check','--disable-extensions','--disable-sync','--incognito',
                 f'--user-data-dir={Path(work)/"profile"}',f'--window-size={size[0]},{size[1]}',
                 f'--virtual-time-budget={int(delay_ms)}',f'--screenshot={raw}',url]
        try:subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=max(60,delay_ms/1000+50),creationflags=flags)
        except (OSError,subprocess.TimeoutExpired):return False
        if not raw.is_file():return False
        from PIL import Image
        temporary=target.with_name(target.stem+'.'+secrets.token_hex(6)+'.tmp.jpg')
        try:
            with Image.open(raw) as image:image.convert('RGB').save(temporary,'JPEG',quality=86)
            temporary.replace(target);return True
        except (OSError,ValueError):return False
        finally:temporary.unlink(missing_ok=True)

class WebWorks:
    def __init__(self,db,data_dir,groups,on_change=lambda:None,log=lambda text:None,browser=None,capture=capture_snapshot,probe=probe):
        self.db=db;self.folder=Path(data_dir)/'web-snapshots';self.groups=groups;self.on_change=on_change;self.log=log
        self.browser=browser;self.capture=capture;self.probe=probe
        self.jobs=queue.Queue();self.pending=set();self.lock=threading.RLock();self.worker=None;self.closing=False
        with self.db() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS web_works(id TEXT PRIMARY KEY, group_id TEXT NOT NULL, url TEXT NOT NULL,
                title TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, snapshot TEXT, snapshot_at REAL,
                frame TEXT NOT NULL DEFAULT 'unknown', title_locked INTEGER NOT NULL DEFAULT 0)''')
            connection.execute('CREATE INDEX IF NOT EXISTS web_works_group ON web_works(group_id)')
            columns={row[1] for row in connection.execute('PRAGMA table_info(web_works)')}
            if 'notes' not in columns:connection.execute("ALTER TABLE web_works ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
    def web_group(self,group_id):
        group=self.groups.get(group_id)
        if group_kind(group)!=WEB_KIND:raise ValueError('此群組不是作品群組。')
        return group
    def rows(self,group_id=None):
        with self.db() as connection:
            query='SELECT id,group_id,url,title,created,updated,snapshot,snapshot_at,frame,notes FROM web_works'
            rows=connection.execute(query+(' WHERE group_id=?' if group_id else '')+' ORDER BY created,id',(group_id,) if group_id else ()).fetchall()
        return [dict(zip(('id','group','url','title','created','updated','snapshot','snapshotAt','frame','notes'),row)) for row in rows]
    def get(self,work_id):
        if not isinstance(work_id,str) or not ID_PATTERN.fullmatch(work_id):raise ValueError('作品不存在。')
        found=[row for row in self.rows() if row['id']==work_id]
        if not found:raise ValueError('作品不存在。')
        return found[0]
    def snapshot_path(self,row):
        name=row.get('snapshot')
        if name and Path(name).name==name and name.endswith('.jpg'):
            path=self.folder/name
            if path.is_file():return path
        return None
    def items(self):
        valid={group['id'] for group in self.groups.config['groups'] if group_kind(group)==WEB_KIND}
        result=[]
        for row in self.rows():
            if row['group'] not in valid:continue
            result.append({'id':row['id'],'kind':WEB_KIND,'title':row['title'],'url':row['url'],'updated':row['updated'],
                           'tags':[],'groups':[row['group']],'episodes':[],'frame':row['frame'],'snapshotAt':row['snapshotAt'],
                           'snapshotPending':row['id'] in self.pending,'notes':row['notes'] or '','picture':str(self.snapshot_path(row) or '') or None})
        return result
    def add(self,group_id,url,title='',notes=''):
        self.web_group(group_id);url=normalize_url(url);notes=clean_notes(notes);now=time.time()
        if any(row['url']==url for row in self.rows(group_id)):raise ValueError('此群組已有相同網址。')
        work_id='w'+secrets.token_hex(10);locked=bool(str(title or '').strip())
        with self.db() as connection:
            connection.execute('INSERT INTO web_works(id,group_id,url,title,created,updated,title_locked,notes) VALUES (?,?,?,?,?,?,?,?)',
                               (work_id,group_id,url,clean_title(title,url),now,now,int(locked),notes))
        self.queue_snapshot(work_id);return self.get(work_id)
    def update(self,work_id,url=None,title=None,notes=None):
        row=self.get(work_id);new_url=normalize_url(url) if url is not None else row['url']
        if new_url!=row['url'] and any(other['url']==new_url for other in self.rows(row['group'])):raise ValueError('此群組已有相同網址。')
        new_title=clean_title(title,new_url) if title is not None else row['title']
        new_notes=clean_notes(notes) if notes is not None else row['notes'] or ''
        with self.db() as connection:
            connection.execute('UPDATE web_works SET notes=? WHERE id=?',(new_notes,work_id))
            connection.execute('UPDATE web_works SET url=?,title=?,updated=?,title_locked=CASE WHEN ? THEN 1 ELSE title_locked END'+(",frame='unknown'" if new_url!=row['url'] else '')+' WHERE id=?',
                               (new_url,new_title,time.time(),title is not None,work_id))
        if new_url!=row['url']:self.queue_snapshot(work_id)
        return self.get(work_id)
    def delete(self,work_id,confirm):
        row=self.get(work_id)
        if confirm!=work_id:raise ValueError('刪除需要再次確認。')
        with self.db() as connection:
            connection.execute('DELETE FROM web_works WHERE id=?',(work_id,))
            for table in ('favorites','exposure','watches'):connection.execute(f'DELETE FROM {table} WHERE item_id=?',(work_id,))
        path=self.snapshot_path(row)
        if path:path.unlink(missing_ok=True)
        tags=self.groups.config.get('group_tags',{}).get(row['group'],{})
        if tags.pop(work_id,None) is not None:self.groups.save(self.groups.config)
        return row
    def delete_group_works(self,group_id):
        for row in self.rows(group_id):self.delete(row['id'],row['id'])
    def queue_snapshot(self,work_id):
        with self.lock:
            if self.closing or work_id in self.pending:return
            self.pending.add(work_id);self.jobs.put(work_id)
            if not self.worker or not self.worker.is_alive():
                self.worker=threading.Thread(target=self._run,daemon=True,name='web-snapshots');self.worker.start()
    def close(self):
        with self.lock:self.closing=True
        self.jobs.put(None)
    def _run(self):
        while True:
            work_id=self.jobs.get()
            if work_id is None or self.closing:return
            try:self.refresh_snapshot(work_id)
            except Exception as error:self.log(f'作品快照錯誤：{error}')
            finally:
                with self.lock:self.pending.discard(work_id)
                self.on_change()
    def capture_now(self,work_id):
        """Synchronous recapture with only a short settle time, for the viewer's retake button."""
        with self.lock:
            if work_id in self.pending:raise ValueError('快照正在擷取中，請稍候。')
            self.pending.add(work_id)
        try:return self.refresh_snapshot(work_id,IMMEDIATE_DELAY_MS)
        finally:
            with self.lock:self.pending.discard(work_id)
            self.on_change()
    def store_snapshot(self,work_id,data):
        """Save an image the browser captured from the viewer as this work's preview."""
        row=self.get(work_id)
        if not isinstance(data,(bytes,bytearray)) or not 0<len(data)<=UPLOAD_LIMIT:raise ValueError('快照圖片大小錯誤。')
        from PIL import Image
        import io
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('JPEG','PNG','WEBP'):raise ValueError('快照圖片格式錯誤。')
                if image.width*image.height>40000000 or image.width<16 or image.height<16:raise ValueError('快照圖片尺寸錯誤。')
                image=image.convert('RGB')
                if image.width>1600:image=image.resize((1600,round(image.height*1600/image.width)))
                self.folder.mkdir(parents=True,exist_ok=True)
                name=work_id+'-'+secrets.token_hex(4)+'.jpg';temporary=self.folder/(name+'.tmp')
                image.save(temporary,'JPEG',quality=88);temporary.replace(self.folder/name)
        except (OSError,Image.DecompressionBombError) as error:raise ValueError('無法讀取快照圖片。') from error
        with self.db() as connection:
            connection.execute('UPDATE web_works SET snapshot=?,snapshot_at=? WHERE id=?',(name,time.time(),work_id))
        old=self.snapshot_path(row)
        if old and old.name!=name:old.unlink(missing_ok=True)
        self.on_change();return True
    def refresh_snapshot(self,work_id,delay_ms=SNAPSHOT_DELAY_MS):
        try:row=self.get(work_id)
        except ValueError:return False
        policy='unknown';title=''
        try:policy,title=self.probe(row['url'])
        except Exception as error:self.log(f'作品網址無法讀取標頭：{error}')
        browser=self.browser or find_browser();name=work_id+'-'+secrets.token_hex(4)+'.jpg';captured=False
        if browser:captured=bool(self.capture(browser,row['url'],self.folder/name,delay_ms=delay_ms))
        else:self.log('找不到 Edge 或 Chrome，無法擷取作品快照。')
        try:current=self.get(work_id)
        except ValueError:
            (self.folder/name).unlink(missing_ok=True);return False
        if current['url']!=row['url']:
            (self.folder/name).unlink(missing_ok=True);return False
        with self.db() as connection:
            connection.execute('UPDATE web_works SET frame=? WHERE id=?',(policy,work_id))
            if title:connection.execute('UPDATE web_works SET title=? WHERE id=? AND title_locked=0',(title,work_id))
            if captured:connection.execute('UPDATE web_works SET snapshot=?,snapshot_at=? WHERE id=?',(name,time.time(),work_id))
        if captured:
            old=self.snapshot_path(current)
            if old and old.name!=name:old.unlink(missing_ok=True)
        return captured
