"""Synthetic fixtures only. Never import cinema before isolating LOCALAPPDATA."""
import os,sys,tempfile,unittest,json
from pathlib import Path
sys.dont_write_bytecode=True
TEST_HOME=tempfile.TemporaryDirectory(prefix='localcinema-tests-')
os.environ['LOCALAPPDATA']=TEST_HOME.name
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cinema import scan,Library
from conversion_store import ConversionStore
from group_access import GroupAccess,visible_payload,may_read
from source_groups import SourceGroups

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=TEST_HOME.name);self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def groups(self):
        config={'groups':[{'id':'default','name':'Public'},{'id':'hidden','name':'Private'}],'roots':[],'tags':{},'categories':[]}
        return SourceGroups(config,self.root,Path(__file__).resolve().parents[1]/'assets/group-icons',lambda config:None)
    def test_scanner_depth_modes_and_override(self):
        root=self.root/'media'
        for name in ['Series/1.mp4','Series/2.mkv','Series/deep/ignored.mp4','Single.flv']:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'synthetic')
        directory=[{'path':str(root),'mode':'directory'}]
        items,errors=scan(directory,{})
        self.assertFalse(errors);self.assertEqual([(i['title'],len(i['episodes'])) for i in items],[('Series',2)])
        items,_=scan([{'path':str(root),'mode':'flat'}],{})
        self.assertEqual({i['title'] for i in items},{'Single','Series'})
        items,_=scan(directory+[{'path':str(root/'Series'),'mode':'flat'}],{})
        self.assertEqual({i['title'] for i in items},{'1','2','deep'})
    def test_group_tags_and_order(self):
        groups=self.groups();groups.add_tags('default',['A'],'same');groups.add_tags('hidden',['B'],'same')
        self.assertEqual(groups.item_tags('default','same'),['A']);self.assertEqual(groups.item_tags('hidden','same'),['B'])
        groups.reorder(['hidden','default']);self.assertEqual(groups.config['groups'][0]['id'],'hidden')
        with self.assertRaises(ValueError):groups.reorder(['hidden','hidden'])
        self.assertEqual(groups.config['groups'][0]['id'],'hidden')
    def test_channel_unlock_revoke_and_rate_limit(self):
        groups=self.groups();access=GroupAccess(groups);access.configure('hidden',True,'test-only-password')
        self.assertNotIn('test-only-password',json.dumps(groups.config))
        self.assertEqual(access.visible(''),{'default'})
        token=access.unlock('test-only-password','','peer');cookie='cinema_groups='+token
        self.assertEqual(access.visible(cookie),{'default','hidden'});self.assertEqual(access.visible(''),{'default'})
        access.configure('hidden',True,'changed-test-password');self.assertEqual(access.visible(cookie),{'default'})
        token=access.unlock('changed-test-password','','peer');access.lock_all('cinema_groups='+token)
        self.assertEqual(access.visible('cinema_groups='+token),{'default'})
        for _ in range(5):
            with self.assertRaises(ValueError):access.unlock('incorrect','','limited-peer')
        with self.assertRaises(ValueError):access.unlock('changed-test-password','','limited-peer')
    def test_replacement_preserves_library_identity_and_history(self):
        for mode in ('flat','directory'):
            media=self.root/mode;folder=media if mode=='flat' else media/'Series';folder.mkdir(parents=True)
            source=folder/'Episode.flv';source.write_bytes(b'synthetic source');output=self.root/(mode+'.mp4');output.write_bytes(b'converted fixture')
            lib=Library(lambda text:None,db_path=self.root/(mode+'.db'),config={'roots':[{'path':str(media),'mode':mode}],'tags':{},'categories':[]})
            try:
                lib.ffmpeg=None;lib.rescan();item=lib.items[0];iid=item['id'];eid=item['episodes'][0]['id']
                lib.source_groups.add_tags('default',['A'],iid)
                with lib.db() as db:
                    db.execute('INSERT INTO favorites VALUES (?,?)',(iid,1))
                    db.execute('INSERT INTO watches VALUES (?,?,?,?,?,?,?)',('s',iid,eid,1,2,30,100))
                    db.execute('INSERT INTO keyframes VALUES (?,?,?,?,?,?)',('f',iid,eid,20,'test',1))
                store=lib.conversion_store;store.register('job',source,output,iid,eid,item['title']);store.confirm('job')
                saved=store.promote('job',recycler=lambda path:path.rename(self.root/(mode+'-recycled.flv')))
                self.assertEqual(store.records(),[]);self.assertTrue(saved.is_file());lib.rescan();after=lib.public()['items'][0]
                self.assertEqual(after['id'],iid);self.assertEqual(after['episodes'][0]['id'],eid);self.assertEqual(after['title'],item['title'])
                self.assertTrue(after['favorite']);self.assertEqual(after['progress']['position'],30)
                self.assertEqual(lib.source_groups.item_tags('default',iid),['A'])
                with lib.db() as db:self.assertEqual(db.execute('SELECT episode_id FROM keyframes').fetchone()[0],eid)
                self.assertEqual(ConversionStore(lib.db_path).records(),[])
            finally:lib.shutdown()
    def test_hidden_channels_http_boundary(self):
        import threading,http.client
        from cinema import make_handler,ThreadingHTTPServer
        lib=Library(lambda text:None,db_path=self.root/'http.db',config=self.groups().config)
        media=self.root/'fixture.mp4';media.write_bytes(b'test media')
        lib.items=[{'id':'item','title':'Hidden fixture','groups':['hidden'],'tags':[],'updated':0,'picture':None,'episodes':[{'id':'episode','name':'One','path':str(media)}]}]
        lib.media={'episode':media};lib.group_access.configure('hidden',True,'test-http-password')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(lib));threading.Thread(target=server.serve_forever,daemon=True).start()
        def request(method,path,data=None,cookie=''):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            connection.request(method,path,json.dumps(data) if data is not None else None,{'X-Cinema-Token':lib.token,'Cookie':cookie})
            response=connection.getresponse();result=(response.status,dict(response.getheaders()),response.read());connection.close();return result
        try:
            data=json.loads(request('GET','/api/library')[2]);self.assertEqual(data['items'],[])
            self.assertNotIn('Hidden fixture',json.dumps(data));self.assertEqual(request('GET','/media/episode')[0],404)
            self.assertEqual(request('POST','/api/prepare',{'episode':'episode'})[0],404)
            status,headers,_=request('POST','/api/groups/unlock',{'password':'test-http-password'});self.assertEqual(status,200)
            cookie=headers['Set-Cookie'].split(';')[0]
            self.assertEqual(request('GET','/media/episode',cookie=cookie)[0],200)
            self.assertEqual(len(json.loads(request('GET','/api/library',cookie=cookie)[2])['items']),1)
            self.assertEqual(json.loads(request('GET','/api/library')[2])['items'],[])
            request('POST','/api/groups/lock',{},cookie);self.assertEqual(request('GET','/media/episode',cookie=cookie)[0],404)
        finally:server.shutdown();server.server_close();lib.shutdown()
    def test_lan_entry_from_scanner(self):
        import threading,http.client
        from cinema import make_handler,ThreadingHTTPServer
        lib=Library(lambda text:None,db_path=self.root/'lan.db',config=self.groups().config)
        class RemoteHandler(make_handler(lib)):
            def setup(self):
                super().setup()
                self.client_address=('192.0.2.20',self.client_address[1])
        server=ThreadingHTTPServer(('127.0.0.1',0),RemoteHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        def request(path,cookie='',origin=None):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            headers={'Cookie':cookie}
            if origin: headers['Origin']=origin
            connection.request('GET',path,headers=headers)
            response=connection.getresponse(); result=(response.status,dict(response.getheaders()),response.read())
            connection.close();return result
        try:
            self.assertEqual(request('/')[0],403)
            self.assertEqual(request('/?access=wrong')[0],403)
            status,headers,_=request('/?access='+lib.access_key)
            self.assertEqual(status,303);self.assertEqual(headers['Location'],'/')
            self.assertIn('SameSite=Lax',headers['Set-Cookie'])
            self.assertIn('HttpOnly',headers['Set-Cookie'])
            cookie=headers['Set-Cookie'].split(';')[0]
            self.assertEqual(request('/',cookie)[0],200)
            self.assertEqual(request('/api/library',cookie)[0],200)
            status,headers,body=request('/assets/bitingbox-studio-plaque.svg',cookie)
            self.assertEqual(status,200);self.assertIn('image/svg+xml',headers['Content-Type'])
            self.assertEqual(body,(Path(__file__).resolve().parents[1]/'assets/bitingbox-studio-plaque.svg').read_bytes())
            self.assertEqual(request('/api/library')[0],403)
            self.assertEqual(request('/?access='+lib.access_key,origin='http://untrusted.invalid')[0],403)
        finally:server.shutdown();server.server_close();lib.shutdown()
    def test_recycle_failure_is_retryable(self):
        store=ConversionStore(self.root/'test.db');source=self.root/'test.flv';output=self.root/'cache.mp4'
        source.write_bytes(b'original');output.write_bytes(b'converted');store.register('job',source,output);store.confirm('job')
        def failure(path):raise OSError('fixture recycling failure')
        with self.assertRaises(OSError):store.promote('job',recycler=failure)
        self.assertTrue(source.is_file());self.assertEqual(store.get('job')['status'],'saved')
        self.assertTrue(Path(store.get('job')['saved_path']).is_file())

if __name__=='__main__':unittest.main()
