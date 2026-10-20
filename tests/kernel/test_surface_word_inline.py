"""Host failures for the closed two-callback optimization catalog.

Real selected pre/post LLVM tests live in the source-bound qualification driver;
these tests exercise malformed metadata, never fabricate a compiler program.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from core0_common import Core0Error
from surface_word_inline import catalog, removed_symbols, CALLBACKS, CALLERS, ARGS, EFFECTS, FIELD, VERSION, POLICY
from package_closure_deployment import CONFIGURATIONS, NOTEBOOK_ROOT, SOFTWARE_DEPLOYMENT


def fixture():
    rows = [{'source': NOTEBOOK_ROOT, 'symbol': 'root', 'args': ['u64'], 'effects': []}]
    rows += [{'source': s, 'symbol': 'word'+str(i), 'args': ARGS, 'effects': EFFECTS} for i,s in enumerate(CALLBACKS)]
    rows += [{'source': s, 'symbol': 'caller'+str(i), 'args': ['u64']*4 if i==0 else ARGS, 'effects': EFFECTS} for i,s in enumerate(CALLERS)]
    rows += [{'source': '_private.Lemma.Ink.Surface.0.Lemma.Ink.Surface.gatherWord', 'symbol':'gather', 'args':['u64'], 'effects':['checked-access','virtual-read']}]
    return {'configuration': CONFIGURATIONS[0], 'role':'user', 'contract_version':'core0-user-v0.2',
            'schema_version':2, 'artifact_category':'development-user-unit',
            'managed_policy':'lemma-notebook-arithmetic-v1', 'software_deployment':deepcopy(SOFTWARE_DEPLOYMENT),
            'image_key':'notebook','image_id':2,'boot_role':'notebook', 'functions':rows,
            'roots':[{'source':NOTEBOOK_ROOT,'symbol':'root','id':1,'args':['u64']}],
            FIELD:{'contract_version':VERSION,'policy':POLICY,'callbacks':[
                {'source':s,'symbol':'word'+str(i),'args':ARGS,'effects':EFFECTS,'caller':CALLERS[i],'budget':64,'count':64}
                for i,s in enumerate(CALLBACKS)]}}


class SurfaceWordInlineCatalog(unittest.TestCase):
    def test_closed_pair_only(self):
        for cfg in CONFIGURATIONS:
            u=fixture();u['configuration']=cfg
            self.assertEqual(removed_symbols(u),{'word0','word1'})
        u=fixture();u.pop(FIELD)
        self.assertIsNone(catalog(u));self.assertEqual(removed_symbols(u),set())
    def test_exact_multimodal_pair_keeps_original_callback_catalog(self):
        from multimodal_deployment import LEGACY_CONFIGURATIONS as names,SOFTWARE_DEPLOYMENT as software,NOTEBOOK_ROOT as root
        for cfg in names:
            u=fixture();u.update(configuration=cfg,software_deployment=deepcopy(software))
            u['roots'][0]['source']=root;u['functions'][0]['source']=root
            self.assertEqual(removed_symbols(u),{'word0','word1'})
            for key,value in [('configuration',cfg+'-unknown'),('software_deployment',SOFTWARE_DEPLOYMENT),
                              ('image_key','arithmetic'),('image_id',3)]:
                changed=deepcopy(u);changed[key]=value
                with self.subTest(cfg=cfg,key=key),self.assertRaises(Core0Error):catalog(changed)
    def test_school_catalog_requires_selected_software_and_school_root(self):
        from school_deployment import software_deployment_for
        for cfg in ('lemmasim-silicon-school-notebook','lemmasim-silicon-school-initialize',
                    'lemmasim-silicon-integrated-school-notebook',
                    'lemmasim-silicon-integrated-pcm-school-notebook'):
            u=fixture();u.update(configuration=cfg,software_deployment=software_deployment_for(cfg))
            root='Lemma.Applications.Notebook.mainMultimodalSchool'
            u['roots'][0]['source']=root;u['functions'][0]['source']=root
            self.assertEqual(removed_symbols(u),{'word0','word1'})
            for change in ('legacy-root','legacy-software','wrong-image','unknown-configuration'):
                changed=deepcopy(u)
                if change=='legacy-root':
                    changed['roots'][0]['source']='Lemma.Applications.Notebook.mainMultimodal'
                    changed['functions'][0]['source']='Lemma.Applications.Notebook.mainMultimodal'
                elif change=='legacy-software':changed['software_deployment']=SOFTWARE_DEPLOYMENT
                elif change=='wrong-image':changed['image_id']=3
                else:changed['configuration']=cfg+'-unknown'
                with self.subTest(cfg=cfg,change=change),self.assertRaises(Core0Error):catalog(changed)
    def test_wrong_identity(self):
        for key,value in [('configuration','lemmasim-silicon-array-bulk-notebook'),('role','kernel'),
                          ('contract_version','core0-user-v0.7'),('schema_version',2.0),('schema_version',True),
                          ('image_id',2.0),('image_id',True),('image_key','arithmetic'),('boot_role','initialize')]:
            with self.subTest(key=key,value=value):
                u=fixture();u[key]=value
                with self.assertRaises(Core0Error):catalog(u)
    def test_malformed_maps(self):
        for value in [None, [], 4, True]:
            with self.subTest(value=value),self.assertRaises(Core0Error):catalog(value)
        for key,value in [('roots',[None]),('roots',[[]]),('roots',{}),('functions',[[]]),('functions',[{'source':[]}]),
                          (FIELD,None),(FIELD,[]),(FIELD,{'contract_version':VERSION})]:
            u=fixture();u[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(Core0Error):catalog(u)
    def test_root_and_source_binding(self):
        for key,value in [('id',True),('id',1.0),('source','Lemma.Applications.Notebook.mainClosureBulk'),
                          ('symbol','word0'),('args',[])]:
            u=fixture();u['roots'][0][key]=value
            with self.subTest(key=key),self.assertRaises(Core0Error):catalog(u)
        u=fixture();u['functions'].append(deepcopy(u['functions'][1]))
        with self.assertRaises(Core0Error):catalog(u)
    def test_no_partial_or_broader_catalog(self):
        for key,value in [('budget',63),('count',65),('count',64.0),('args',['u64']*7),('effects',[]),
                          ('source','Lemma.User.Memory.read64'),('symbol','root'),('caller',NOTEBOOK_ROOT)]:
            u=fixture();u[FIELD]['callbacks'][0][key]=value
            with self.subTest(key=key),self.assertRaises(Core0Error):catalog(u)
        for callbacks in [[],fixture()[FIELD]['callbacks'][:1],fixture()[FIELD]['callbacks']*2,[None,None]]:
            u=fixture();u[FIELD]['callbacks']=callbacks
            with self.assertRaises(Core0Error):catalog(u)
        u=fixture();u[FIELD]['extra']=True
        with self.assertRaises(Core0Error):catalog(u)
