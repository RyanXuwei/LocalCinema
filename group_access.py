"""Per-browser hidden-channel access, separate from LAN admission."""
import hashlib,secrets,time,threading,re
from http.cookies import SimpleCookie
class GroupAccess:
    def __init__(self,groups):self.groups=groups;self.sessions={};self.browser_pages={};self.failures={};self.lock=threading.RLock()
    def configure(self,group_id,hidden,password=''):
        group=self.groups.get(group_id)
        if password:
            if not 4<=len(password)<=128:raise ValueError('密碼長度需為4至128字元。')
            salt=secrets.token_hex(16);digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),200000).hex()
            group['password_salt']=salt;group['password_hash']=digest
        if hidden and not group.get('password_hash'):raise ValueError('啟用隱藏前請先設定密碼。')
        group['hidden']=bool(hidden);group['access_revision']=secrets.token_hex(16)
        self.groups.save(self.groups.config)
    def session(self,token):
        session=self.sessions.get(token);now=time.time()
        if session and self.groups.config.get('lock_on_page_close',False):
            pages=self.browser_pages.get(session.get('browser'),session.get('pages',{}))
            session['pages']={page:seen for page,seen in pages.items() if now-seen<=90}
            if session.get('browser'):self.browser_pages[session['browser']]=session['pages']
            if not session['pages']:self.sessions.pop(token,None);return None
        if session and session['expires']<now:self.sessions.pop(token,None);return None
        return session
    def visible(self,cookie):
        with self.lock:
            session=self.session(self.token(cookie));grants=session['grants'] if session else {}
            return {g['id'] for g in self.groups.config['groups'] if not g.get('hidden') or grants.get(g['id'])==g.get('access_revision')}
    @staticmethod
    def valid_page(page):return isinstance(page,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,64}',page))
    @staticmethod
    def browser_token(cookie):
        jar=SimpleCookie()
        try:jar.load(cookie or '');return jar['cinema_pages'].value if 'cinema_pages' in jar else ''
        except Exception:return ''
    def touch_page(self,cookie,page):
        if not self.valid_page(page):raise ValueError('分頁識別格式錯誤。')
        with self.lock:
            session=self.session(self.token(cookie));browser=self.browser_token(cookie);now=time.time()
            if browser:
                pages={key:seen for key,seen in self.browser_pages.get(browser,{}).items() if now-seen<=90}
                pages[page]=now;self.browser_pages[browser]=pages
            if session:
                session.setdefault('pages',{})[page]=now
    def close_page(self,cookie,page):
        if not self.valid_page(page):raise ValueError('分頁識別格式錯誤。')
        with self.lock:
            token=self.token(cookie);session=self.session(token);browser=self.browser_token(cookie)
            pages=self.browser_pages.get(browser,{}) if browser else session.get('pages',{}) if session else {}
            pages.pop(page,None)
            if session and self.groups.config.get('lock_on_page_close',False) and not pages:self.sessions.pop(token,None)
    @staticmethod
    def token(cookie):
        jar=SimpleCookie()
        try:jar.load(cookie or '');return jar['cinema_groups'].value if 'cinema_groups' in jar else ''
        except Exception:return ''
    def unlock(self,password,cookie,peer,page=None):
        if self.groups.config.get('lock_on_page_close',False) and not self.valid_page(page):raise ValueError('請重新整理頁面後再解鎖。')
        if not isinstance(password,str) or len(password)>128:raise ValueError('密碼錯誤。')
        with self.lock:
            now=time.time();attempts=[t for t in self.failures.get(peer,[]) if now-t<60]
            if len(attempts)>=5:raise ValueError('嘗試過於頻繁，請稍候一分鐘再試。')
            matched=[]
            for group in self.groups.config['groups']:
                if not group.get('hidden'):continue
                actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(group['password_salt']),200000).hex()
                if secrets.compare_digest(actual,group['password_hash']):matched.append(group)
            if not matched:
                self.failures[peer]=attempts+[now];raise ValueError('密碼錯誤或沒有可解鎖的頻道。')
            self.failures.pop(peer,None)
            old=self.session(self.token(cookie));self.sessions.pop(self.token(cookie),None)
            grants=dict(old['grants']) if old and old['expires']>now else {}
            grants.update({g['id']:g.get('access_revision') for g in matched})
            self.sessions={k:v for k,v in self.sessions.items() if v['expires']>now}
            browser=self.browser_token(cookie)
            pages=dict(self.browser_pages.get(browser,{})) if browser else dict(old.get('pages',{})) if old and old['expires']>now else {}
            pages={key:seen for key,seen in pages.items() if now-seen<=90}
            if self.valid_page(page):pages[page]=now
            if browser:self.browser_pages[browser]=pages
            token=secrets.token_urlsafe(32);self.sessions[token]={'expires':now+8*3600,'grants':grants,'pages':pages,'browser':browser}
            return token
    def lock_all(self,cookie):
        with self.lock:self.sessions.pop(self.token(cookie),None)

def visible_payload(lib,allowed):
    data=lib.public();data['groups']=[g for g in data['groups'] if g['id'] in allowed]
    data['items']=[dict(i,groups=[g for g in i.get('groups',['default']) if g in allowed],tags=[]) for i in data['items'] if allowed.intersection(i.get('groups',['default']))]
    for key in ('groupCategories','groupTags'):data[key]={g:v for g,v in data[key].items() if g in allowed}
    data['channelsUnlocked']=any(g.get('hidden') and g['id'] in allowed for g in lib.source_groups.config['groups'])
    data['categories']=[]
    return data

def may_read(lib,allowed,key,episode=False):
    return any(allowed.intersection(i.get('groups',['default'])) and (any(e['id']==key for e in i['episodes']) if episode else i['id']==key) for i in lib.items)
