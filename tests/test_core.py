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
    def test_entry_url_prefers_lan_and_falls_back(self):
        from unittest.mock import patch,MagicMock
        from cinema import entry_url,lan_addresses
        with patch('cinema.lan_addresses',return_value=['192.0.2.20','198.51.100.10']):
            self.assertEqual(entry_url(9123,'synthetic-key'),'http://192.0.2.20:9123/?access=synthetic-key')
        with patch('cinema.lan_addresses',return_value=[]):
            self.assertEqual(entry_url(9123,'synthetic-key'),'http://127.0.0.1:9123/')
        answers=[(2,1,6,'',(address,0)) for address in ['198.51.100.10','192.0.2.20','127.0.0.1','169.254.1.2']]
        route=MagicMock();route.__enter__.return_value.getsockname.return_value=('192.0.2.20',12345)
        with patch('cinema.socket.getaddrinfo',return_value=answers),patch('cinema.socket.socket',return_value=route):
            self.assertEqual(lan_addresses(),['192.0.2.20','198.51.100.10'])
        with patch('cinema.socket.getaddrinfo',side_effect=OSError),patch('cinema.socket.socket',side_effect=OSError):
            self.assertEqual(lan_addresses(),[])
    def test_playback_directory_move_and_restart(self):
        from playback_storage import playback_directory
        source=self.root/'cache-old';source.mkdir();target=self.root/'cache-new'
        key='a'*64;cache=source/(key+'.mp4');cache.write_bytes(b'synthetic converted bytes')
        original=self.root/'synthetic.flv';original.write_bytes(b'synthetic original')
        lib=Library(lambda text:None,db_path=self.root/'move.db',config={'roots':[],'tags':{},'categories':[]},playback_dir=source)
        lib.conversion_store.register(key,original,cache,'item','episode','Fixture')
        lib.conversion_store.confirm(key);before=lib.conversion_store.get(key)
        lib.compat_media[key]=cache
        (source/'unrelated.txt').write_text('leave unchanged')
        (source/('b'*64+'.partial.mp4')).write_bytes(b'partial')
        try:
            report=lib.relocate_playback(target)
            self.assertEqual(report['moved'],1);self.assertFalse(cache.exists())
            moved=target/cache.name;self.assertEqual(moved.read_bytes(),b'synthetic converted bytes')
            self.assertTrue(original.exists());self.assertTrue((source/'unrelated.txt').exists())
            self.assertTrue((source/('b'*64+'.partial.mp4')).exists())
            after=lib.conversion_store.get(key)
            self.assertEqual(after['output_path'],str(moved));self.assertEqual(after['status'],'confirmed')
            self.assertEqual(after['confirmed_at'],before['confirmed_at'])
            self.assertEqual(after['item_id'],'item');self.assertEqual(after['episode_id'],'episode')
            self.assertEqual(lib.compat_media[key],moved)
            self.assertEqual(playback_directory(lib.db_path,source),target)
            self.assertEqual(lib.conversion_store.review_path(key),moved)
        finally:lib.shutdown()
        restarted=Library(lambda text:None,db_path=self.root/'move.db',config={'roots':[],'tags':{},'categories':[]})
        try:self.assertEqual(restarted.playback_dir,target)
        finally:restarted.shutdown()
    def test_playback_move_conflicts_and_busy_keep_old(self):
        from playback_storage import playback_directory
        source=self.root/'old';source.mkdir();target=self.root/'new';target.mkdir()
        name='c'*64+'.mp4';(source/name).write_bytes(b'cache');(target/name).write_bytes(b'conflict')
        lib=Library(lambda text:None,db_path=self.root/'conflict.db',config={'roots':[],'tags':{},'categories':[]},playback_dir=source)
        try:
            with self.assertRaises(ValueError):lib.relocate_playback(target)
            self.assertEqual((source/name).read_bytes(),b'cache');self.assertEqual((target/name).read_bytes(),b'conflict')
            self.assertEqual(playback_directory(lib.db_path,source),source)
            with self.assertRaises(ValueError):lib.relocate_playback(source/'nested')
            lib.background_enabled=True
            with self.assertRaises(ValueError):lib.relocate_playback(target)
            lib.background_enabled=False
            (target/name).write_bytes(b'cache')
            self.assertEqual(lib.relocate_playback(target)['moved'],1)
            self.assertFalse((source/name).exists())
        finally:lib.shutdown()
    def test_playback_move_failed_commit_preserves_cache(self):
        from playback_storage import relocate_playback
        import sqlite3
        source=self.root/'old';source.mkdir();target=self.root/'new';name='d'*64+'.mp4'
        (source/name).write_bytes(b'cache')
        # Deliberately missing schema: copying succeeds, database commit cannot.
        with self.assertRaises(sqlite3.OperationalError):relocate_playback(source,target,self.root/'missing-schema.db')
        self.assertEqual((source/name).read_bytes(),b'cache')
        self.assertEqual((target/name).read_bytes(),b'cache')
    def test_default_cache_location_and_window_bounds(self):
        from cinema import default_playback_directory,window_dimensions
        app=self.root/'app';data=self.root/'data';data.mkdir()
        self.assertEqual(default_playback_directory(app,data),app/'playback')
        (data/'playback').mkdir()
        self.assertEqual(default_playback_directory(app,data),data/'playback')
        self.assertEqual(window_dimensions(1920,1040)[:2],(1160,850))
        self.assertEqual(window_dimensions(1920,1040,True)[:2],(1280,850))
        for width,height in [(1366,728),(1024,720),(800,600)]:
            w,h,min_w,min_h=window_dimensions(width,height,True)
            self.assertLessEqual(w,width-48);self.assertLessEqual(h,height-48)
            self.assertLessEqual(min_w,w);self.assertLessEqual(min_h,h)
    def test_stopped_service_can_move_with_preferences_checked(self):
        old=self.root/'old';old.mkdir();new=self.root/'new';name='6'*64+'.mp4';(old/name).write_bytes(b'completed cache')
        lib=Library(lambda text:None,db_path=self.root/'stopped-move.db',config={'roots':[],'tags':{},'categories':[],'background_convert':True},playback_dir=old)
        lib.auto_promoter.enabled=True
        try:
            lib.pause_processing()
            self.assertTrue(lib.background_enabled);self.assertTrue(lib.auto_promoter.enabled)
            self.assertIsNone(lib.cache_maintenance_blocker())
            self.assertEqual(lib.relocate_playback(new)['moved'],1)
            self.assertEqual((new/name).read_bytes(),b'completed cache')
            self.assertEqual(lib.cleanup_playback()['removed'],0)
            self.assertTrue(lib.background_enabled);self.assertTrue(lib.auto_promoter.enabled)
            lib.scanning=True
            self.assertIn('掃描',lib.cache_maintenance_blocker())
            with self.assertRaises(ValueError):lib.relocate_playback(self.root/'another')
            lib.scanning=False;lib.auto_promoter.busy=True
            self.assertIn('保存',lib.cache_maintenance_blocker())
            with self.assertRaises(ValueError):lib.cleanup_playback()
            lib.auto_promoter.busy=False
        finally:
            lib.scanning=False;lib.auto_promoter.busy=False;lib.shutdown()
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
    def test_auto_promote_opt_in_existing_and_new(self):
        from conversion_store import AutoPromoter
        store=ConversionStore(self.root/'auto.db'); rescans=[]; recycled=[]
        def recycler(path):
            recycled.append(path);path.rename(path.with_suffix('.recycled'))
        auto=AutoPromoter(store,lambda:rescans.append(True),lambda text:None,recycler)
        def fixture(key):
            source=self.root/(key+'.flv');source.write_bytes(b'original')
            output=self.root/(key+'-cache.mp4');output.write_bytes(b'converted')
            store.register(key,source,output,'item-'+key,'episode-'+key,key)
            return source
        source=fixture('one');collision=source.with_suffix('.mp4');collision.write_bytes(b'existing')
        auto.process_pending();self.assertTrue(source.exists());self.assertEqual(recycled,[])
        # Drive the same worker step deterministically without launching a thread.
        auto.enabled=True;auto.process_pending()
        self.assertFalse(source.exists());self.assertEqual(collision.read_bytes(),b'existing')
        saved=self.root/'one.converted-one.mp4';self.assertEqual(saved.read_bytes(),b'converted')
        source=fixture('two');auto.process_pending();self.assertFalse(source.exists())
        self.assertEqual(store.records(),[]);self.assertEqual(auto.completed,2)
        with store.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM media_replacements').fetchone()[0],2)
        auto.set_enabled(False);source=fixture('three');auto.process_pending();self.assertTrue(source.exists())
        auto.close()
    def test_auto_promote_failure_waits_for_retry(self):
        from conversion_store import AutoPromoter
        store=ConversionStore(self.root/'auto-fail.db')
        source=self.root/'source.flv';source.write_bytes(b'original')
        output=self.root/'cache.mp4';output.write_bytes(b'converted');store.register('job',source,output)
        attempts=[]
        def recycler(path):attempts.append(path);raise OSError('synthetic failure')
        auto=AutoPromoter(store,lambda:None,lambda text:None,recycler)
        auto.enabled=True;auto.process_pending();auto.process_pending()
        self.assertEqual(len(attempts),1);self.assertTrue(source.exists())
        self.assertEqual(store.get('job')['status'],'saved')
        auto.recycler=lambda path:path.rename(self.root/'recycled.flv')
        auto.failed.clear();auto.process_pending()
        self.assertFalse(source.exists());self.assertEqual(store.records(),[]);auto.close()
    def test_auto_promote_disable_finishes_only_current(self):
        from conversion_store import AutoPromoter
        store=ConversionStore(self.root/'auto-stop.db')
        for key in ['one','two']:
            source=self.root/(key+'.flv');source.write_bytes(b'original')
            output=self.root/(key+'.cache.mp4');output.write_bytes(b'converted');store.register(key,source,output)
        def recycler(path):
            auto.set_enabled(False);path.rename(path.with_suffix('.recycled'))
        auto=AutoPromoter(store,lambda:None,lambda text:None,recycler)
        auto.enabled=True;auto.process_pending()
        self.assertEqual(auto.completed,1);self.assertEqual(len(store.records()),1);auto.close()
    def test_promote_releases_only_verified_generated_cache(self):
        store=ConversionStore(self.root/'release.db');cache_dir=self.root/'playback';cache_dir.mkdir()
        cache=cache_dir/('f'*64+'.mp4');cache.write_bytes(b'converted bytes')
        source=self.root/'source.flv';source.write_bytes(b'original bytes')
        store.register('f'*64,source,cache,'item','episode','Fixture');store.confirm('f'*64)
        saved=store.promote('f'*64,recycler=lambda path:path.rename(self.root/'recycled.flv'))
        self.assertEqual(saved.read_bytes(),b'converted bytes');self.assertFalse(cache.exists())
        with store.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM media_replacements').fetchone()[0],1)
    def test_cache_cleanup_retains_damaged_saved_and_untracked_files(self):
        from conversion_store import file_hash
        store=ConversionStore(self.root/'clean.db');folder=self.root/'cache';folder.mkdir()
        cache=folder/('a'*64+'.mp4');cache.write_bytes(b'complete')
        saved=self.root/'saved.mp4';saved.write_bytes(b'complete');digest=file_hash(saved)
        with store.db() as db:db.execute('INSERT INTO cache_copies VALUES(?,?,?)',(str(cache),str(saved),digest))
        saved.write_bytes(b'corrupted')
        self.assertEqual(store.cleanup_cache(folder)['removed'],0);self.assertTrue(cache.exists())
        saved.write_bytes(b'complete')
        source=self.root/'pending.flv';source.write_bytes(b'original');store.register('pending',source,cache)
        self.assertEqual(store.cleanup_cache(folder)['removed'],0);self.assertTrue(cache.exists())
        with store.db() as db:db.execute('DELETE FROM conversion_records')
        unmapped=folder/('b'*64+'.mp4');unmapped.write_bytes(b'only copy')
        self.assertEqual(store.cleanup_cache(folder)['removed'],1)
        self.assertTrue(unmapped.exists());self.assertEqual(saved.read_bytes(),b'complete')
    def test_legacy_completed_cache_cleanup(self):
        store=ConversionStore(self.root/'legacy.db');folder=self.root/'cache';folder.mkdir()
        cache=folder/('c'*64+'.mp4');cache.write_bytes(b'matching saved copy')
        saved=self.root/'saved.mp4';saved.write_bytes(cache.read_bytes())
        with store.db() as db:db.execute('INSERT INTO media_replacements VALUES(?,?,?,?,?,?)',(str(saved),str(self.root/'old.flv'),'item','episode','Fixture','Episode'))
        self.assertEqual(store.cleanup_cache(folder,legacy=True)['removed'],1)
        self.assertFalse(cache.exists());self.assertTrue(saved.exists())
        with store.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM media_replacements').fetchone()[0],1)
    def test_recovery_when_recycle_completed_before_interruption(self):
        store=ConversionStore(self.root/'recovery.db')
        source=self.root/'source.flv';source.write_bytes(b'original')
        cache=self.root/('d'*64+'.mp4');cache.write_bytes(b'converted')
        store.register('recover',source,cache);store.confirm('recover')
        def interrupted(path):path.rename(self.root/'recycled.flv');raise OSError('synthetic interruption after recycle')
        with self.assertRaises(OSError):store.promote('recover',recycler=interrupted)
        self.assertTrue(cache.exists());self.assertEqual(store.get('recover')['status'],'saved')
        store.confirm('recover');saved=store.promote('recover',recycler=lambda path:self.fail('must not recycle twice'))
        self.assertTrue(saved.exists());self.assertFalse(cache.exists());self.assertEqual(store.records(),[])
    def test_move_journal_retains_old_until_reverified(self):
        from unittest.mock import patch
        from playback_storage import cleanup_moved_copies
        old=self.root/'old';old.mkdir();new=self.root/'new';name='e'*64+'.mp4';(old/name).write_bytes(b'good')
        lib=Library(lambda text:None,db_path=self.root/'journal.db',config={'roots':[],'tags':{},'categories':[]},playback_dir=old)
        try:
            with patch('playback_storage.cleanup_moved_copies',return_value={'retained':1}):lib.relocate_playback(new)
            self.assertTrue((old/name).exists());(new/name).write_bytes(b'bad!')
            self.assertEqual(cleanup_moved_copies(lib.db_path)['removed'],0);self.assertTrue((old/name).exists())
            (new/name).write_bytes(b'good')
            self.assertEqual(cleanup_moved_copies(lib.db_path)['removed'],1)
            self.assertFalse((old/name).exists());self.assertEqual((new/name).read_bytes(),b'good')
        finally:lib.shutdown()
    def test_move_second_verification_failure_keeps_old_setting(self):
        from unittest.mock import patch
        from conversion_store import file_hash
        from playback_storage import playback_directory
        old=self.root/'old';old.mkdir();new=self.root/'new';name='9'*64+'.mp4';(old/name).write_bytes(b'good')
        lib=Library(lambda text:None,db_path=self.root/'verify.db',config={'roots':[],'tags':{},'categories':[]},playback_dir=old)
        try:
            def digest(path):return 'wrong' if Path(path)==new/name else file_hash(path)
            with patch('playback_storage.file_hash',side_effect=digest):
                with self.assertRaises(OSError):lib.relocate_playback(new)
            self.assertTrue((old/name).exists());self.assertEqual(playback_directory(lib.db_path,old),old)
        finally:lib.shutdown()
    def test_low_space_stops_conversion_without_touching_files(self):
        from unittest.mock import Mock,patch
        from types import SimpleNamespace
        from playback_storage import wait_for_conversion
        process=Mock();process.poll.return_value=None
        with patch('playback_storage.shutil.disk_usage',return_value=SimpleNamespace(free=1)):
            with self.assertRaises(OSError):wait_for_conversion(process,self.root,Mock())
        process.terminate.assert_called_once();process.wait.assert_called_once_with(timeout=5)
    def test_progress_reports_verified_move_and_cleanup(self):
        from operation_progress import OperationProgress
        state=OperationProgress();events=[]
        def progress(*args):state.update(*args);events.append(state.snapshot())
        old=self.root/'old';old.mkdir();new=self.root/'new';name='8'*64+'.mp4'
        (old/name).write_bytes(b'synthetic'*300000)
        lib=Library(lambda text:None,db_path=self.root/'progress.db',config={'roots':[],'tags':{},'categories':[]},playback_dir=old)
        try:lib.relocate_playback(new,progress=progress)
        finally:lib.shutdown()
        self.assertTrue(any(e['phase']=='複製快取' and e['done']==e['size']>0 for e in events))
        self.assertTrue(any(e['phase']=='提交前複核副本' for e in events))
        self.assertTrue(any(e['phase']=='清理前複核新檔' for e in events))
        self.assertTrue(all(0<=e['done']<=e['size'] for e in events))
    def test_real_synthetic_encoding_progress(self):
        import subprocess,time
        from unittest.mock import patch
        from operation_progress import parse_encode_progress,parse_duration
        lib=Library(lambda text:None,db_path=self.root/'encode.db',config={'roots':[],'tags':{},'categories':[]},playback_dir=self.root/'cache')
        if not lib.ffmpeg:lib.shutdown();self.skipTest('FFmpeg unavailable')
        source=self.root/'synthetic.avi'
        try:
            run=subprocess.run([lib.ffmpeg,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=blue:s=160x90:r=12','-t','2','-c:v','mpeg4',str(source)],capture_output=True,timeout=15,creationflags=0x08000000 if os.name=='nt' else 0)
            self.assertEqual(run.returncode,0)
            lib.media={'episode':source}
            with patch('cinema.parse_encode_progress',wraps=parse_encode_progress) as parsed:
                lib.prepare('episode',force=True);end=time.monotonic()+15
                while time.monotonic()<end:
                    with lib.lock:states=[job['state'] for job in lib.conversions.values()]
                    if states and states[0] in ('ready','error'):break
                    time.sleep(.03)
                self.assertEqual(states,['ready']);self.assertGreater(parsed.call_count,0)
            self.assertIsNone(lib.conversion_status()['active'])
            self.assertEqual(parse_duration('Duration: 00:01:30.50'),90.5)
            self.assertIsNone(parse_duration('Duration: N/A'))
            self.assertIsNone(parse_encode_progress('out_time_us=N/A',10))
            self.assertEqual(parse_encode_progress('out_time_us=5000000',10)['percent'],50)
            self.assertLess(parse_encode_progress('out_time_us=12000000',10)['percent'],100)
            self.assertIsNone(parse_encode_progress('out_time_us=1000000',None)['percent'])
        finally:lib.shutdown()
    def test_stop_active_encoding_and_resume(self):
        import subprocess,time
        lib=Library(lambda text:None,db_path=self.root/'stop.db',config={'roots':[],'tags':{},'categories':[]},playback_dir=self.root/'cache')
        if not lib.ffmpeg:lib.shutdown();self.skipTest('FFmpeg unavailable')
        source=self.root/'synthetic.avi'
        try:
            run=subprocess.run([lib.ffmpeg,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=blue:s=640x360:r=24','-t','30','-c:v','mpeg4',str(source)],capture_output=True,timeout=20,creationflags=0x08000000 if os.name=='nt' else 0)
            self.assertEqual(run.returncode,0);before=source.read_bytes();lib.media={'episode':source}
            lib.prepare('episode',force=True);end=time.monotonic()+10
            while time.monotonic()<end:
                with lib.lock:active=lib.convert_process
                if active and active.stdout is not None:break
                time.sleep(.01)
            self.assertIsNotNone(active);self.assertIsNotNone(active.stdout)
            ready_cache=lib.playback_dir/('1'*64+'.mp4');ready_cache.write_bytes(b'completed cache fixture')
            lib.pause_processing()
            self.assertIsNotNone(active.poll());self.assertTrue(lib.conversion_idle.is_set())
            self.assertIsNone(lib.convert_process);self.assertFalse(list(lib.playback_dir.glob('*.partial.mp4')))
            self.assertEqual(source.read_bytes(),before);self.assertEqual(ready_cache.read_bytes(),b'completed cache fixture')
            self.assertEqual(lib.conversion_status()['queued'],0);self.assertEqual(lib.conversion_status()['converting'],0)
            self.assertEqual(lib.prepare('episode',force=True)['state'],'error')
            lib.resume_processing();lib.prepare('episode',force=True);end=time.monotonic()+20
            while time.monotonic()<end:
                with lib.lock:states=[job['state'] for job in lib.conversions.values()]
                if states and states[0] in ('ready','error'):break
                time.sleep(.03)
            self.assertEqual(states,['ready']);self.assertEqual(source.read_bytes(),before)
        finally:lib.shutdown()
    def test_paused_automation_keeps_preference_and_items(self):
        from conversion_store import AutoPromoter
        store=ConversionStore(self.root/'paused.db');source=self.root/'source.flv';source.write_bytes(b'original')
        cache=self.root/'cache.mp4';cache.write_bytes(b'converted');store.register('job',source,cache)
        auto=AutoPromoter(store,lambda:None,lambda text:None,lambda path:path.rename(self.root/'recycled.flv'))
        auto.enabled=True;auto.set_paused(True);auto.process_pending()
        self.assertTrue(auto.enabled);self.assertTrue(source.exists());self.assertEqual(len(store.records()),1)
        auto.set_paused(False);auto.process_pending();self.assertFalse(source.exists());auto.close()
    def test_recycle_failure_is_retryable(self):
        store=ConversionStore(self.root/'test.db');source=self.root/'test.flv';output=self.root/'cache.mp4'
        source.write_bytes(b'original');output.write_bytes(b'converted');store.register('job',source,output);store.confirm('job')
        def failure(path):raise OSError('fixture recycling failure')
        with self.assertRaises(OSError):store.promote('job',recycler=failure)
        self.assertTrue(source.is_file());self.assertEqual(store.get('job')['status'],'saved')
        self.assertTrue(Path(store.get('job')['saved_path']).is_file())

if __name__=='__main__':unittest.main()
