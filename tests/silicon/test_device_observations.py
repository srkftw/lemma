# SPDX-License-Identifier: Apache-2.0
"""Literal offline fixtures test rejection; they are never execution evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'conformance/silicon'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from device_observations import fixture,raw_events,observe

class DeviceObservations(unittest.TestCase):
    @staticmethod
    def write_json(path,value):
        path.write_text(json.dumps(value))
    @staticmethod
    def ident(path):
        return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    @classmethod
    def capture(cls,path):
        # Synthetic captured bytes for this checker unit test, never a PASS run.
        (path/'input.events').write_bytes(raw_events())
        initial=path/'initial.raw';initial.write_bytes(bytes(512))
        image=path/'image';image.write_bytes(b'checker fixture image')
        audit=path/'audit';cls.write_json(audit,{'status':'PASS','configuration':'lemmasim-silicon-devices',
            'stage':'supervisor','image_sha256':cls.ident(image)['sha256']})
        artifact=path/'artifact';artifact.write_bytes(b'checker fixture artifact')
        identity={'schema_version':1,'transport':'lemma-silicon-events/1','profile':'lemma-silicon-dev/0.1.0',
            'workload':'devices','reset_cycles':8,'clock_hz':100000000,
            'ram_initialization':'zero external RAM plus exact ELF and DTB loads',
            'inputs':{'events':cls.ident(path/'input.events')},'initial_medium':cls.ident(initial),
            'prepared':{'profile':'lemma-silicon-dev/0.1.0','workloads':{'devices':{
                'image':cls.ident(image),'audit':cls.ident(audit)}},
                **{key:cls.ident(artifact) for key in ('binary','rom','rom_audit','rtl_build')}}}
        cls.write_json(path/'input.json',identity)
        rows=[(0x40e,1,171,4,6),(0x40f,1,2,2,3),(0x400,0x80480000,1024,4,0),
            (0x406,1,0x8000000000000009,0x80480000,0x1000000),
            (0x401,1,0,0,0),(0x401,5,0,0,0),(0x404,1000,4,1024,0),
            (0x406,13,0x8000000000000009,0x80480000,0x1000004),
            (0x402,257,20000,22000,0),(0x402,258,21000,23000,0)]
        cls.write_uart(path,rows)
        stats={'pen_ingress':303,'pen_accepted':258,'flushes':1,'media_requests':2,
            'panel_completed':0,'panel_aborted':1,'volatile_sectors_discarded':0,
            'privilege_cycles':[10,10,0,10],'timer_traps':1,'traps':4,
            'finished':False,'explicit_observer_stop':True}
        cls.write_json(path/'host-report.json',stats)
        (path/'panel').write_bytes(b'P5\n512 640\n255\n'+bytes([255])*512*640)
        (path/'panel.events').write_text('cycle,event,sequence,x,y,gray\n100,abort,1,0,0,0\n')
        cls.publish(path)
        return identity,rows,stats
    @classmethod
    def write_uart(cls,path,rows):
        (path/'uart.bin').write_bytes(''.join('K1 '+' '.join(f'{n:016x}' for n in row)+'\n' for row in rows).encode())
    @classmethod
    def publish(cls,path):
        cls.write_json(path/'output.json',{'status':'STOPPED_BY_PROTOCOL','exit_code':0,'outputs':{
            name:cls.ident(path/name)['sha256'] for name in ('uart.bin','host-report.json','panel','panel.events')}})
    def test_literal_fixture_matches_retained_external_corpus(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);result=fixture(path)
            self.assertEqual(len((path/'events.txt').read_text().splitlines()),303)
            self.assertEqual(result['events_sha256'],'9e19572938fc049cb6fe49fd7927c271c9c7568779b4d01de89bd1f9a616f0c2')
    def test_complete_literal_checker_fixture_and_missing_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);_,rows,_=self.capture(path)
            self.assertEqual(observe(path)['raw_events'],303)
            for drop in (0,1):
                changed=rows[:drop]+rows[drop+1:];self.write_uart(path,changed);self.publish(path)
                with self.assertRaisesRegex(ValueError,'probe observations'):observe(path)
    def test_read_flush_cannot_be_replaced_by_banner_or_zero_dma(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);_,rows,stats=self.capture(path)
            self.write_uart(path,[row for row in rows if row[0]!=0x401]);self.publish(path)
            with self.assertRaisesRegex(ValueError,'block read/FLUSH'):observe(path)
            self.write_uart(path,rows);stats['flushes']=0;self.write_json(path/'host-report.json',stats);self.publish(path)
            with self.assertRaisesRegex(ValueError,'DMA/FLUSH'):observe(path)
    def test_sequence_substitution_and_missing_user_irq_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);_,rows,_=self.capture(path)
            changed=rows[:-1]+[(0x402,1,21000,23000,0)]
            self.write_uart(path,changed);self.publish(path)
            with self.assertRaisesRegex(ValueError,'raw sequence'):observe(path)
            changed=[row for row in rows if not(row[0]==0x406 and row[1]==13)]
            self.write_uart(path,changed);self.publish(path)
            with self.assertRaisesRegex(ValueError,'block/pen SEIP'):observe(path)
    def test_wrong_pc_zero_user_or_boolean_hardware_count_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);_,rows,stats=self.capture(path)
            changed=copy.deepcopy(rows);changed[3]=(*changed[3][:-1],0x80200000)
            self.write_uart(path,changed);self.publish(path)
            with self.assertRaisesRegex(ValueError,'isolated User PC'):observe(path)
            self.write_uart(path,rows);stats['privilege_cycles'][0]=0
            self.write_json(path/'host-report.json',stats);self.publish(path)
            with self.assertRaisesRegex(ValueError,'M/S/U'):observe(path)
            stats['privilege_cycles'][0]=10;stats['pen_accepted']=True
            self.write_json(path/'host-report.json',stats);self.publish(path)
            with self.assertRaisesRegex(ValueError,'pen_accepted'):observe(path)
    def test_raw_event_tamper_and_failed_image_audit_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);identity,_,_=self.capture(path)
            (path/'input.events').write_bytes(raw_events().replace(b'1800',b'1700'))
            identity['inputs']['events']=self.ident(path/'input.events');self.write_json(path/'input.json',identity)
            with self.assertRaisesRegex(ValueError,'303 raw external events'):observe(path)
            (path/'input.events').write_bytes(raw_events());identity['inputs']['events']=self.ident(path/'input.events')
            audit=path/'audit';report=json.loads(audit.read_text());report['status']='FAIL';self.write_json(audit,report)
            identity['prepared']['workloads']['devices']['audit']=self.ident(audit);self.write_json(path/'input.json',identity)
            with self.assertRaisesRegex(ValueError,'strict PASS audit'):observe(path)
    def test_timeout_cannot_become_an_observed_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);self.capture(path)
            result=json.loads((path/'output.json').read_text());result.update(status='WALL_TIMEOUT',exit_code=-9)
            self.write_json(path/'output.json',result)
            with self.assertRaisesRegex(ValueError,'observation protocol'):observe(path)
    def test_reset_must_abort_the_actual_accepted_controller_sequence(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);self.capture(path)
            for line in ('100,abort,2,0,0,0\n','100,complete,1,0,0,0\n',''):
                (path/'panel.events').write_text('cycle,event,sequence,x,y,gray\n'+line);self.publish(path)
                with self.assertRaisesRegex(ValueError,'controller'):observe(path)

if __name__=='__main__':unittest.main(verbosity=2)
