"""Per-browser hidden-channel access, separate from LAN admission."""
import hashlib,secrets,time,threading
from http.cookies import SimpleCookie
class GroupAccess:
    def __init__(self,groups):self.groups=groups;self.sessions={};self.failures={};self.lock=threading.RLock()
    def configure(self,group_id,hidden,password=''):
        group=self.groups.get(group_id)
        if password:
            if not 4<=len(password)<=128:raise ValueError('密碼長度需為4至128字元。')
            salt=secrets.token_hex(16);digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),200000).hex()
            group['password_salt']=salt;group['password_hash']=digest
        if hidden and not group.get('password_hash'):raise ValueError('啟用隱藏前請先設定密碼。')
        group['hidden']=bool(hidden);group['access_revision']=secrets.token_hex(16)
        self.groups.save(self.groups.config)
    def visible(self,cookie):
        token=self.token(cookie)
        with self.lock:
            session=self.sessions.get(token)
            if session and session['expires']<time.time():self.sessions.pop(token,None);session=None
            grants=session['grants'] if session else {}
            return {g['id'] for g in self.groups.config['groups'] if not g.get('hidden') or grants.get(g['id'])==g.get('access_revision')}
    @staticmethod
    def token(cookie):
        jar=SimpleCookie()
        try:jar.load(cookie or '');return jar['cinema_groups'].value if 'cinema_groups' in jar else ''
        except Exception:return ''
    def unlock(self,password,cookie,peer):
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
            old=self.sessions.pop(self.token(cookie),None)
            grants=dict(old['grants']) if old and old['expires']>now else {}
            grants.update({g['id']:g.get('access_revision') for g in matched})
            self.sessions={k:v for k,v in self.sessions.items() if v['expires']>now}
            token=secrets.token_urlsafe(32);self.sessions[token]={'expires':now+8*3600,'grants':grants}
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
