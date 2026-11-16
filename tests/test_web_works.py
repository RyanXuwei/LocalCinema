"""Synthetic web-work fixtures only; no real sites are opened or captured."""
import os,sys,tempfile,unittest,json,threading,http.client,time
from pathlib import Path
from email.message import Message
sys.dont_write_bytecode=True
TEST_HOME=os.environ.get('LOCALAPPDATA') if 'localcinema-tests-' in os.environ.get('LOCALAPPDATA','') else None
if not TEST_HOME:
    HOLDER=tempfile.TemporaryDirectory(prefix='localcinema-tests-');TEST_HOME=HOLDER.name;os.environ['LOCALAPPDATA']=TEST_HOME
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cinema import Library,make_handler,ThreadingHTTPServer
from group_access import visible_payload
from web_works import normalize_url,frame_policy,WEB_KIND

def headers(**values):
    message=Message()
    for key,value in values.items():
        for entry in (value if isinstance(value,list) else [value]):message[key.replace('_','-')]=entry
    return message

class WebWorkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=TEST_HOME);self.root=Path(self.tmp.name);self.captures=[];self.delays=[]
        config={'groups':[{'id':'default','name':'Public'},{'id':'site','name':'Sites','kind':WEB_KIND},{'id':'secret','name':'Secret sites','kind':WEB_KIND}],'roots':[],'tags':{},'categories':[]}
        self.lib=Library(lambda text:None,db_path=self.root/'web.db',config=config)
        works=self.lib.web_works
        works.browser=self.root/'fake-browser.exe'
        def capture(browser,url,target,delay_ms=10000):
            self.delays.append(delay_ms)
            self.captures.append(url);Path(target).parent.mkdir(parents=True,exist_ok=True)
            from PIL import Image
            Image.new('RGB',(32,20),(40,90,60)).save(target,'JPEG');return True
        works.capture=capture;works.probe=lambda url:('blocked' if 'blocked' in url else 'allowed','Synthetic page')
    def tearDown(self):self.lib.shutdown();self.tmp.cleanup()
    def wait_idle(self):
        deadline=time.time()+10
        while self.lib.web_works.pending and time.time()<deadline:time.sleep(.02)
        self.assertFalse(self.lib.web_works.pending);self.lib.refresh_web()
    def test_url_rules(self):
        self.assertEqual(normalize_url('example.test/demo'),'https://example.test/demo')
        self.assertEqual(normalize_url('HTTP://example.test'),'http://example.test/')
        for bad in ('','javascript:alert(1)','file:///C:/x.html','https://user:pw@example.test/','ftp://example.test/','https://exa mple.test/'):
            with self.assertRaises(ValueError,msg=bad):normalize_url(bad)
    def test_frame_policy(self):
        self.assertEqual(frame_policy(headers()),'allowed')
        self.assertEqual(frame_policy(headers(X_Frame_Options='SAMEORIGIN')),'blocked')
        self.assertEqual(frame_policy(headers(Content_Security_Policy="default-src 'self'; frame-ancestors 'self'")),'blocked')
        self.assertEqual(frame_policy(headers(Content_Security_Policy="frame-ancestors *")),'allowed')
        self.assertEqual(frame_policy(headers(Content_Security_Policy=["script-src 'self'","frame-ancestors 'none'"])),'blocked')
    def test_add_snapshot_update_delete(self):
        works=self.lib.web_works
        with self.assertRaises(ValueError):works.add('default','https://example.test/')
        row=works.add('site','https://example.test/a');self.wait_idle()
        item=self.lib.web_item(row['id'])
        self.assertEqual((item['title'],item['frame']),('Synthetic page','allowed'))
        self.assertTrue(Path(self.lib.pictures[row['id']]).is_file());self.assertEqual(self.captures,['https://example.test/a'])
        with self.assertRaises(ValueError):works.add('site','https://example.test/a')
        works.update(row['id'],'https://blocked.example.test/','Kept title');self.wait_idle()
        item=self.lib.web_item(row['id']);self.assertEqual((item['title'],item['frame'],item['url']),('Kept title','blocked','https://blocked.example.test/'))
        snapshot=Path(self.lib.pictures[row['id']])
        self.lib.source_groups.add_tags('site',['demo'],row['id'])
        with self.assertRaises(ValueError):works.delete(row['id'],'')
        self.assertIsNotNone(self.lib.web_item(row['id']))
        works.delete(row['id'],row['id']);self.lib.refresh_web()
        self.assertIsNone(self.lib.web_item(row['id']));self.assertFalse(snapshot.exists())
        self.assertNotIn(row['id'],self.lib.config['group_tags'].get('site',{}))
    def test_retake_now_and_browser_upload(self):
        import io,base64
        from PIL import Image
        works=self.lib.web_works
        row=works.add('site','https://example.test/retake');self.wait_idle()
        first=Path(self.lib.pictures[row['id']])
        self.assertTrue(works.capture_now(row['id']));self.lib.refresh_web()
        self.assertEqual(self.delays[-1],1500);second=Path(self.lib.pictures[row['id']])
        self.assertNotEqual(first,second);self.assertFalse(first.exists())
        buffer=io.BytesIO();Image.new('RGB',(2000,1000),(200,10,10)).save(buffer,'PNG')
        works.store_snapshot(row['id'],buffer.getvalue());self.lib.refresh_web()
        third=Path(self.lib.pictures[row['id']]);self.assertFalse(second.exists())
        with Image.open(third) as image:self.assertEqual(image.size,(1600,800));self.assertEqual(image.getpixel((5,5))[0]>150,True)
        for bad in (b'',b'not an image'):
            with self.assertRaises(ValueError):works.store_snapshot(row['id'],bad)
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.lib));threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            def request(path,data):
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
                connection.request('POST',path,json.dumps(data),{'X-Cinema-Token':self.lib.token})
                response=connection.getresponse();response.read();connection.close();return response.status
            large=io.BytesIO();Image.new('RGB',(1200,700),(10,10,200)).save(large,'JPEG',quality=95)
            image='data:image/jpeg;base64,'+base64.b64encode(large.getvalue()).decode()
            self.assertEqual(request('/api/works/snapshot-upload',{'id':row['id'],'image':image}),200)
            self.assertEqual(request('/api/works/snapshot-upload',{'id':row['id'],'image':'data:text/plain;base64,aGk='}),400)
            self.assertEqual(request('/api/works/snapshot',{'id':row['id'],'now':True}),200)
        finally:server.shutdown();server.server_close()
    def test_notes_and_old_table_migration(self):
        import sqlite3
        from web_works import WebWorks
        works=self.lib.web_works
        row=works.add('site','https://example.test/notes','',' 第一行\r\n第二行  \n\n')
        self.assertEqual(works.get(row['id'])['notes'],' 第一行\n第二行')
        works.update(row['id'],notes='改過');self.assertEqual(works.get(row['id'])['notes'],'改過')
        works.update(row['id'],title='只改標題');self.assertEqual(works.get(row['id'])['notes'],'改過')
        with self.assertRaises(ValueError):works.update(row['id'],notes='x'*5001)
        self.wait_idle();self.assertEqual(self.lib.web_item(row['id'])['notes'],'改過')
        old=self.root/'old.db'
        connection=sqlite3.connect(old)
        with connection:
            connection.execute('''CREATE TABLE web_works(id TEXT PRIMARY KEY, group_id TEXT NOT NULL, url TEXT NOT NULL,
                title TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, snapshot TEXT, snapshot_at REAL,
                frame TEXT NOT NULL DEFAULT 'unknown', title_locked INTEGER NOT NULL DEFAULT 0)''')
            connection.execute("INSERT INTO web_works(id,group_id,url,title,created,updated) VALUES (?,'site','https://example.test/','Old',0,0)",('w'+'0'*20,))
        connection.close()
        from contextlib import contextmanager
        @contextmanager
        def db():
            connection=sqlite3.connect(old)
            try:
                with connection:yield connection
            finally:connection.close()
        migrated=WebWorks(db,self.root,self.lib.source_groups)
        self.assertEqual(migrated.get('w'+'0'*20)['notes'],'')
    def test_inspect_reads_headers_from_real_responses(self):
        import http.server
        from web_works import inspect
        class Site(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                status={'/deny':200,'/csp':200,'/login':403,'/error':500}.get(self.path,200)
                self.send_response(status);self.send_header('Content-Type','text/html; charset=utf-8')
                if self.path in ('/deny','/error'):self.send_header('X-Frame-Options','DENY')
                if self.path=='/csp':self.send_header('Content-Security-Policy',"frame-ancestors 'self' https://trusted.example")
                body=b'<title>Fixture page</title>';self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Site);threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            self.assertEqual(inspect(base+'/ok'),('allowed','','Fixture page'))
            policy,reason,_=inspect(base+'/deny');self.assertEqual(policy,'blocked');self.assertIn('X-Frame-Options: DENY',reason)
            policy,reason,_=inspect(base+'/csp');self.assertEqual(policy,'blocked');self.assertIn('frame-ancestors',reason)
            self.assertEqual(inspect(base+'/error')[0],'blocked')
            policy,reason,_=inspect(base+'/login');self.assertEqual(policy,'unknown');self.assertIn('403',reason)
        finally:server.shutdown();server.server_close()
        policy,reason,_=inspect('http://127.0.0.1:9/unreachable',timeout=2);self.assertEqual(policy,'unknown');self.assertIn('無法連線',reason)
    def test_check_frame_updates_reason(self):
        works=self.lib.web_works;row=works.add('site','https://blocked.example.test/');self.wait_idle()
        works.probe=lambda url:('blocked','','X-Frame-Options: SAMEORIGIN')
        self.assertEqual(works.check_frame(row['id']),{'frame':'blocked','reason':'X-Frame-Options: SAMEORIGIN'})
        self.lib.refresh_web();item=self.lib.web_item(row['id'])
        self.assertEqual((item['frame'],item['frameReason']),('blocked','X-Frame-Options: SAMEORIGIN'));self.assertIsNotNone(item['frameChecked'])
        works.probe=lambda url:(_ for _ in ()).throw(OSError('offline'))
        self.assertEqual(works.check_frame(row['id'])['frame'],'unknown')
    def test_group_kinds(self):
        groups=self.lib.source_groups
        with self.assertRaises(ValueError):groups.assign([0],'site')
        created=groups.create('More sites',WEB_KIND);self.assertEqual(created['kind'],WEB_KIND)
        groups.reorder([created['id'],'secret','site'])
        self.assertEqual([g['id'] for g in self.lib.config['groups']],['default',created['id'],'secret','site'])
        with self.assertRaises(ValueError):groups.reorder(['site','default'])
        public={g['id']:g['kind'] for g in groups.public([])};self.assertEqual(public['default'],'media');self.assertEqual(public['site'],WEB_KIND)
    def test_hidden_web_group_and_http_routes(self):
        works=self.lib.web_works
        public=works.add('site','https://example.test/public');hidden=works.add('secret','https://example.test/private');self.wait_idle()
        self.lib.group_access.configure('secret',True,'web-password')
        payload=visible_payload(self.lib,self.lib.group_access.visible(''))
        self.assertEqual([i['id'] for i in payload['items']],[public['id']])
        self.assertEqual(payload['items'][0]['url'],'https://example.test/public')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.lib));threading.Thread(target=server.serve_forever,daemon=True).start()
        def request(path,data=None,method='POST'):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            connection.request(method,path,json.dumps(data) if data is not None else None,{'X-Cinema-Token':self.lib.token})
            response=connection.getresponse();body=response.read();connection.close();return response.status,body
        try:
            self.assertEqual(request('/poster/'+hidden['id'],method='GET')[0],404)
            self.assertEqual(request('/poster/'+public['id'],method='GET')[0],200)
            self.assertEqual(request('/api/works/delete',{'id':hidden['id'],'confirm':hidden['id']})[0],404)
            self.assertEqual(request('/api/works/add',{'group':'secret','url':'https://example.test/x'})[0],404)
            self.assertEqual(request('/api/works/add',{'group':'default','url':'https://example.test/x'})[0],400)
            status,body=request('/api/works/add',{'group':'site','url':'example.test/new','title':'New'});self.assertEqual(status,200)
            new=json.loads(body)['id'];self.wait_idle()
            self.assertEqual(request('/api/works/delete',{'id':new})[0],400)
            self.assertEqual(request('/api/favorite',{'id':new,'favorite':True})[0],200)
            self.assertEqual(request('/api/works/visit',{'id':new,'session':'s1'})[0],200)
            self.assertEqual(request('/api/tags',{'id':new,'group':'site','tags':['portfolio']})[0],200)
            item=next(i for i in self.lib.public()['items'] if i['id']==new)
            self.assertTrue(item['favorite']);self.assertEqual(item['watchCount'],1)
            self.assertEqual(request('/api/works/delete',{'id':new,'confirm':new})[0],200)
            self.assertIsNone(self.lib.web_item(new))
            self.assertEqual(request('/assets/web-works.js',method='GET')[0],200)
        finally:server.shutdown();server.server_close()

class BrandingTests(unittest.TestCase):
    def test_hide_branding_option(self):
        tmp=tempfile.TemporaryDirectory(dir=TEST_HOME);root=Path(tmp.name)
        lib=Library(lambda text:None,db_path=root/'brand.db',config={'roots':[],'tags':{},'categories':[]})
        try:
            page=lib.page_html().decode();revision=lib.privacy_state()['revision']
            self.assertNotIn('hide-branding',page.split('<head>')[0][:400]);self.assertIn('by BitingBox Studio</title>',page)
            lib.set_hide_branding(True);page=lib.page_html().decode()
            self.assertIn('class="hide-branding"',page);self.assertIn('<title>LocalCinema</title>',page)
            self.assertTrue(lib.privacy_state()['hideBranding']);self.assertGreater(lib.privacy_state()['revision'],revision)
            lib.set_privacy(True);self.assertIn('class="privacy-blur hide-branding"',lib.page_html().decode())
        finally:lib.shutdown();tmp.cleanup()

if __name__=='__main__':unittest.main()
