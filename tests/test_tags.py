"""Synthetic tag catalogs only."""
import sys,unittest
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source_groups import SourceGroups

class TagTests(unittest.TestCase):
    def setUp(self):
        self.saves=0
        config={'groups':[{'id':'default','name':'A'},{'id':'other','name':'B'}],'roots':[],'tags':{},'categories':[],
                'group_categories':{'default':['動作','喜劇','空分類'],'other':['動作']},
                'group_tags':{'default':{'one':['動作','喜劇'],'two':['動作'],'gone':['喜劇']},'other':{'one':['動作']}}}
        def save(config):self.saves+=1
        self.groups=SourceGroups(config,Path('.'),Path('.'),save);self.config=config
    def test_usage_ignores_stale_items(self):
        self.assertEqual(self.groups.tag_usage('default',{'one','two'}),{'動作':2,'喜劇':1})
    def test_prune_only_named_unused_tags(self):
        self.config['group_tags']['default']['one']=['動作']
        removed=self.groups.prune_tags('default',['喜劇','動作'],{'one','two'})
        self.assertEqual(removed,['喜劇'])
        self.assertEqual(self.config['group_categories']['default'],['動作','空分類'])
        self.assertEqual(self.groups.prune_tags('default',['動作'],{'one','two'}),[])
    def test_delete_tag_removes_from_items_in_group_only(self):
        self.assertEqual(self.groups.delete_tag('default','動作'),2)
        self.assertNotIn('動作',self.config['group_categories']['default'])
        self.assertEqual(self.config['group_tags']['default']['one'],['喜劇'])
        self.assertEqual(self.config['group_tags']['other']['one'],['動作'])
        self.assertEqual(self.config['group_categories']['other'],['動作'])

if __name__=='__main__':unittest.main()
