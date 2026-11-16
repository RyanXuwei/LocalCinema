"""Synthetic databases only; never touches the real LocalCinema data."""
import os,sys,tempfile,unittest,json,sqlite3,time
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db_backup import DatabaseBackups,parse,stamp

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='localcinema-backup-');self.root=Path(self.tmp.name)
        self.db=self.root/'library.sqlite3';self.saved=[];self.restored=[]
        with self.connect() as connection:
            connection.execute('PRAGMA journal_mode=WAL');connection.execute('CREATE TABLE favorites(item_id TEXT PRIMARY KEY, added REAL)')
            connection.execute("INSERT INTO favorites VALUES ('original',1)")
        self.config={'groups':[{'id':'default','name':'Original'}],'roots':[]}
        self.backups=DatabaseBackups(self.db,self.root/'backups',self.config,lambda config:self.saved.append(json.dumps(config)),on_restore=lambda:self.restored.append(True))
    def tearDown(self):self.backups.close();self.tmp.cleanup()
    def connect(self):
        connection=sqlite3.connect(self.db)
        class Closing:
            def __enter__(s):return connection.__enter__()
            def __exit__(s,*exc):connection.__exit__(*exc);connection.close()
        return Closing()
    def favorites(self):
        with self.connect() as connection:return [row[0] for row in connection.execute('SELECT item_id FROM favorites ORDER BY item_id')]
    def test_names_and_defaults(self):
        self.assertEqual(self.backups.settings(),{'enabled':False,'hours':24,'days':7})
        name=f'library-{stamp(0)}-manual.sqlite3';self.assertEqual(parse(name),(0.0,'manual'))
        for bad in ('library-x-manual.sqlite3','../library-19700101T000000000000Z-manual.sqlite3','library-19700101T000000000000Z-other.sqlite3'):
            self.assertIsNone(parse(bad))
        self.assertFalse(self.backups.due())
        with self.assertRaises(ValueError):self.backups.configure(True,5,7)
        with self.assertRaises(ValueError):self.backups.configure(True,24,0)
    def test_backup_restore_with_safety_copy_and_confirmation(self):
        name=self.backups.create('manual')
        with self.connect() as connection:connection.execute("INSERT INTO favorites VALUES ('later',2)")
        self.config['groups'][0]['name']='Changed'
        with self.assertRaises(ValueError):self.backups.restore(name,'wrong-name')
        self.assertEqual(self.favorites(),['later','original'])
        safety=self.backups.restore(name,name)
        self.assertEqual(self.favorites(),['original']);self.assertEqual(self.config['groups'][0]['name'],'Original');self.assertEqual(self.restored,[True])
        self.assertEqual(parse(safety)[1],'pre-restore')
        self.backups.restore(safety,safety,include_config=False)
        self.assertEqual(self.favorites(),['later','original']);self.assertEqual(self.config['groups'][0]['name'],'Original')
        with self.assertRaises(ValueError):self.backups.restore('../x.sqlite3','../x.sqlite3')
    def test_schedule_and_retention(self):
        self.backups.configure(True,24,7);self.assertTrue(self.backups.due())
        first=self.backups.tick();self.assertIsNotNone(first);self.assertFalse(self.backups.due())
        self.assertTrue(self.backups.due(time.time()+25*3600))
        folder=self.root/'backups'
        for days in (10,9,1):
            old=f'library-{stamp(time.time()-days*86400)}-automatic.sqlite3';(folder/old).write_bytes((folder/first).read_bytes())
        removed=self.backups.prune()
        self.assertEqual(len(removed),2);self.assertEqual(len(self.backups.list()),2)
        self.backups.configure(False,24,7);self.assertIsNone(self.backups.tick())
        only=self.root/'solo';only.mkdir()
        lonely=DatabaseBackups(self.db,only,{'backup_retention_days':1},lambda c:None)
        (only/f'library-{stamp(time.time()-30*86400)}-manual.sqlite3').write_bytes((folder/first).read_bytes())
        self.assertEqual(lonely.prune(),[]);self.assertEqual(len(lonely.list()),1)

if __name__=='__main__':unittest.main()
