"""Reject fabricated/truncated controller observations and input provenance."""
from pathlib import Path
import copy
import hashlib
import json
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'conformance/silicon'))
from notebook_observations import (fixture,pgm,panel_point_history,
                                   validate_fixture,completed_capture,cold,reset_identity)
from monitor_observations import observe as observe_monitor, READY

class ObservationTests(unittest.TestCase):
    def test_raw_corpus_contains_contact_pressure_and_actual_tool_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            result=fixture(Path(temporary),100000000,50000000)
            self.assertEqual(len(result['raw_samples']),13)
            self.assertEqual([a['button'] for a in result['actions'][1:]],[3,4,7])
            self.assertEqual([r[4] for r in result['raw_samples'][1:7]],
                             [1024,1216,1408,1600,1792,0])

    def test_panel_requires_complete_pixel_corpus(self):
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/'panel';p.write_bytes(b'P5\n512 640\n255\n\xff')
            with self.assertRaisesRegex(ValueError,'length'):pgm(p)

    def test_completion_cannot_replace_controller_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/'events';p.write_text(
                'cycle,event,sequence,x,y,gray\n20,complete,1,0,0,0\n')
            with self.assertRaisesRegex(ValueError,'missing pixels'):panel_point_history(p,100,230)

    def test_later_update_cannot_mutate_accepted_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/'events';p.write_text(
                'cycle,event,sequence,x,y,gray\n20,pixel,1,100,230,0\n'
                '21,pixel,2,101,230,15\n22,complete,2,0,0,0\n')
            with self.assertRaisesRegex(ValueError,'changed before completion'):
                panel_point_history(p,100,230)

    def test_fixture_expectations_cannot_change_without_raw_ingress(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);manifest=fixture(path,100000000,50000000)
            self.assertEqual(len(validate_fixture(manifest,path/'events.txt')),13)
            changed=copy.deepcopy(manifest)
            changed['raw_samples'][1]=list(changed['raw_samples'][1])
            changed['raw_samples'][1][4]+=1
            with self.assertRaisesRegex(ValueError,'encode captured ingress'):
                validate_fixture(changed,path/'events.txt')

    def test_fixture_epoch_and_binding_are_observable_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);manifest=fixture(path,100000000,50000000)
            for field,value in [('profile','lemmasim-virt/0.1.0'),('clock_hz',10000000)]:
                changed=copy.deepcopy(manifest);changed[field]=value
                with self.assertRaisesRegex(ValueError,'fixture binding'):
                    validate_fixture(changed,path/'events.txt')
            changed=copy.deepcopy(manifest)
            changed['raw_samples'][1]=list(changed['raw_samples'][1])
            changed['raw_samples'][1][8]=2
            with self.assertRaisesRegex(ValueError,'sample identity'):
                validate_fixture(changed,path/'events.txt')

    def test_trailing_accepted_update_cannot_be_hidden_by_prior_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/'events';p.write_text(
                'cycle,event,sequence,x,y,gray\n20,pixel,1,100,230,0\n'
                '21,complete,1,0,0,0\n22,pixel,2,100,230,15\n')
            with self.assertRaisesRegex(ValueError,'incomplete accepted update'):
                panel_point_history(p,100,230)

    def test_abort_cannot_cancel_another_accepted_sequence(self):
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/'events';p.write_text(
                'cycle,event,sequence,x,y,gray\n20,pixel,1,100,230,0\n'
                '21,abort,2,0,0,0\n')
            with self.assertRaisesRegex(ValueError,'abort identity'):
                panel_point_history(p,100,230)

    @staticmethod
    def capture(path,**stats_changes):
        stats={'pen_ingress':0,'flushes':0,'media_requests':0,'panel_completed':0,
               'volatile_sectors_discarded':0,'privilege_cycles':[0,0,0,0]}
        stats.update(stats_changes)
        (path/'host-report.json').write_text(json.dumps(stats))
        (path/'uart.bin').write_bytes(b'')
        (path/'panel').write_bytes(b'P5\n512 640\n255\n'+bytes([255])*512*640)
        (path/'panel.events').write_text('cycle,event,sequence,x,y,gray\n')
        result={'status':'STOPPED_BY_PROTOCOL','exit_code':0,'outputs':{
            name:hashlib.sha256((path/name).read_bytes()).hexdigest()
            for name in ('host-report.json','uart.bin','panel','panel.events')}}
        (path/'output.json').write_text(json.dumps(result))
        return result

    def test_timeout_and_empty_inventory_cannot_become_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);result=self.capture(path)
            result.update(status='WALL_TIMEOUT',exit_code=-9)
            (path/'output.json').write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,'declared observation protocol'):
                completed_capture(path)
            result.update(status='STOPPED_BY_PROTOCOL',exit_code=0,outputs={})
            (path/'output.json').write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,'output inventory'):
                completed_capture(path)

    def test_hardware_counts_reject_boolean_and_missing_privileges(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);self.capture(path,flushes=True)
            with self.assertRaisesRegex(ValueError,'hardware count flushes'):
                completed_capture(path)
            self.capture(path,privilege_cycles=[1,2,3])
            with self.assertRaisesRegex(ValueError,'privilege observations'):
                completed_capture(path)

    def test_changed_output_cannot_supply_fresh_hardware_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);self.capture(path)
            (path/'host-report.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'output identity'):
                completed_capture(path)

    def test_consumed_hardware_output_must_be_in_capture_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);result=self.capture(path)
            del result['outputs']['host-report.json']
            (path/'output.json').write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,'output inventory'):
                completed_capture(path)

    def test_cold_reset_identity_requires_retained_medium_and_empty_ram(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);initial=path/'initial.raw';initial.write_bytes(bytes(512))
            retained=path/'retained.raw';retained.write_bytes(bytes(512))
            identity={'transport':'lemma-silicon-events/1','profile':'lemma-silicon-dev/0.1.0',
                'workload':'notebook','reset_cycles':8,'clock_hz':100000000,
                'ram_initialization':'zero external RAM plus exact ELF and DTB loads','inputs':{},
                'initial_medium':{'path':str(initial),'sha256':hashlib.sha256(initial.read_bytes()).hexdigest()}}
            (path/'input.json').write_text(json.dumps(identity))
            reset_identity(path,'notebook',retained)
            for field,value in [('workload','initializer'),('ram_initialization','saved RAM snapshot'),
                                ('inputs',{'events':'previous notebook output'})]:
                changed=copy.deepcopy(identity);changed[field]=value
                (path/'input.json').write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError,'architectural reset identity'):
                    reset_identity(path,'notebook',retained)
            (path/'input.json').write_text(json.dumps(identity))
            retained.write_bytes(b'x'+bytes(511))
            with self.assertRaisesRegex(ValueError,'architectural reset identity'):
                reset_identity(path,'notebook',retained)

    def test_same_capture_cannot_claim_cold_reexecution(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)
            with self.assertRaisesRegex(ValueError,'distinct execution capture'):
                cold(path/'disk',path/'disk',path,path)

    def test_ready_banner_without_monitor_responses_is_not_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);(path/'uart.bin').write_bytes(READY)
            with self.assertRaisesRegex(ValueError,'actual monitor responses'):
                observe_monitor(path)

if __name__=='__main__':unittest.main()
