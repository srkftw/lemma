# SPDX-License-Identifier: Apache-2.0
"""Observer-only malformed literal CSV tests; no RTL execution claim."""
from pathlib import Path
import csv, hashlib, json, sys, tempfile, unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'conformance/silicon'))
import notebook_observations as oracle

class BarrierObservationTests(unittest.TestCase):
    def rows(self):
        # Literal external WRITE, failed FLUSH, RTL status+used DMA, guest ACK.
        return [
          [10,'media-write',1,9,'0x40','0x0','0x0','0x0',0,8,15,8,1,0,0],
          [20,'media-flush',0,9,'0x0','0x0','0x0','0x0',1,8,15,8,1,0,0],
          [21,'dma',1,0,'0x82000800','0x1','0x1','0xff',0,10,15,8,1,0,1],
          [24,'dma',1,1,'0x82000102','0x1','0x1','0x0',0,13,15,8,1,0,1],
          [40,'mmio',1,2,'0x10001064','0x100000001','0x1','0x0',0,0,15,8,1,1,1]]

    def check(self,rows,omitted=0):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'block.csv'
            with path.open('w',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(oracle.FIELDS);writer.writerows(rows)
            return oracle.failed_barrier(path,{'block_rows':len(rows),'block_omitted':omitted})

    def test_literal_failed_barrier_and_completion(self):
        observed=self.check(self.rows())
        self.assertEqual(observed['failed_flush_cycle'],20)
        self.assertEqual(observed['ioerr_dma_cycle'],21)
        self.assertEqual(observed['used_index_cycle'],24)
        self.assertEqual(observed['irq_ack_cycle'],40)

    def test_successful_flush_cannot_substitute(self):
        rows=self.rows();rows[1][8]=0
        with self.assertRaisesRegex(ValueError,'failed medium barrier'):self.check(rows)

    def test_failed_barrier_without_ioerr_status_rejected(self):
        rows=self.rows();del rows[2]
        with self.assertRaisesRegex(ValueError,'IOERR status-byte'):self.check(rows)

    def test_status_without_used_publication_rejected(self):
        rows=self.rows();del rows[3]
        with self.assertRaisesRegex(ValueError,'used-index'):self.check(rows)

    def test_unconsumed_interrupt_rejected(self):
        rows=self.rows();del rows[4]
        with self.assertRaisesRegex(ValueError,'acknowledge'):self.check(rows)

    def test_unrelated_dma_error_rejected(self):
        rows=self.rows();rows[2][8]=1
        with self.assertRaisesRegex(ValueError,'unrelated transport error'):self.check(rows)

    def test_omitted_trace_cannot_hide_required_history(self):
        with self.assertRaisesRegex(ValueError,'omissions'):self.check(self.rows(),omitted=1)

    def test_incomplete_row_rejected(self):
        rows=self.rows();rows[2].pop()
        with self.assertRaisesRegex(ValueError,'malformed block'):self.check(rows)


class FailedFlushObservationTests(unittest.TestCase):
    """Synthetic host observations; existing Store decoding remains independent."""
    @staticmethod
    def row(tag,value,object):
        return ('K1 '+' '.join(f'{n:016x}' for n in (tag,value,1,1,object))+'\n').encode()

    def fixture(self,path):
        capture=path/'capture';capture.mkdir()
        before=path/'acknowledged.raw';before.write_bytes(b'A'*512)
        failed=path/'failed.raw';failed.write_bytes(before.read_bytes())
        initial=capture/'initial-medium.raw';initial.write_bytes(before.read_bytes())
        samples=[(10,1,20000,40000,0,2,1,0),
                 (20,2,20000,41000,1024,3,1,0),(30,3,21000,41000,1216,3,1,0),
                 (40,4,22000,41000,1408,3,1,0),(50,5,23000,41000,1600,3,1,0),
                 (60,6,24000,41000,1792,3,1,0),(70,7,24000,41000,0,2,1,0)]
        raw=capture/'input.events'
        raw.write_text(''.join(str(r[0])+' pen '+' '.join(map(str,r[1:]))+'\n' for r in samples))
        ident=lambda p:{'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        identity={'transport':'lemma-silicon-events/1','profile':'lemma-silicon-dev/0.1.0',
                  'workload':'notebook','reset_cycles':8,'clock_hz':100000000,
                  'ram_initialization':'zero external RAM plus exact ELF and DTB loads',
                  'inputs':{'events':ident(raw)},'initial_medium':ident(initial),
                  'options':{'fail_flush':1,'block_trace':True}}
        (capture/'input.json').write_text(json.dumps(identity))
        stats={'pen_ingress':7,'pen_accepted':7,'flushes':1,'media_requests':2,
               'panel_completed':2,'volatile_sectors_discarded':1,
               'privilege_cycles':[10,20,0,3],'timer_traps':1,'block_rows':5,'block_omitted':0}
        (capture/'host-report.json').write_text(json.dumps(stats))
        (capture/'uart.bin').write_bytes(self.row(0x423,7,0x10007)+self.row(0x424,227,0x10007))
        with (capture/'block.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(oracle.FIELDS)
            writer.writerows(BarrierObservationTests().rows())
        pixels=bytearray([255])*(512*640)
        # Independently authored literal five-row letters for the FAILED label.
        letters=[['111','100','110','100','100'],['010','101','111','101','101'],
                 ['111','010','010','010','111'],['100','100','100','100','111'],
                 ['111','100','110','100','111'],['110','101','101','101','110']]
        for index,letter in enumerate(letters):
            for y in range(15):
                for x in range(9):
                    if letter[y//3][x//3]=='1':pixels[(132+y)*512+24+index*12+x]=0
        (capture/'panel').write_bytes(b'P5\n512 640\n255\n'+pixels)
        (capture/'panel.events').write_text('cycle,event,sequence,x,y,gray\n'
            '10,pixel,1,0,0,15\n11,complete,1,0,0,0\n'
            '30,pixel,2,24,132,0\n31,complete,2,0,0,0\n')
        self.inventory(capture)
        return before,failed,capture

    @staticmethod
    def inventory(capture):
        outputs={name:hashlib.sha256((capture/name).read_bytes()).hexdigest()
                 for name in ('uart.bin','host-report.json','panel','panel.events','block.csv')}
        (capture/'output.json').write_text(json.dumps({'status':'STOPPED_BY_PROTOCOL',
                                                     'exit_code':0,'outputs':outputs}))

    def observe(self,files):
        # Store decoding is covered by its separate raw-record oracle corpus;
        # these fixtures isolate the newly required failure observations.
        with mock.patch.object(oracle,'committed_bytes',return_value=b'literal prior acknowledged records'), \
             mock.patch.object(oracle,'recover',return_value=(None,6,{})):
            return oracle.failed_flush(*files)

    def test_literal_failed_flush_provenance_and_guest_ioerr(self):
        with tempfile.TemporaryDirectory() as temporary:
            result=self.observe(self.fixture(Path(temporary)))
            self.assertEqual(result['status'],'PASS')
            self.assertEqual(result['new_raw_samples'],7)
            self.assertEqual(result['barrier']['failed_flush_cycle'],20)

    def test_failure_without_reset_identity_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            files=self.fixture(Path(temporary));(files[2]/'input.json').unlink()
            with self.assertRaises(OSError):self.observe(files)

    def test_failure_without_declared_first_barrier_fault_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            files=self.fixture(Path(temporary));capture=files[2]
            identity=json.loads((capture/'input.json').read_text());identity['options']['fail_flush']=2
            (capture/'input.json').write_text(json.dumps(identity))
            with self.assertRaisesRegex(ValueError,'first FLUSH failure'):self.observe(files)

    def test_saved_cannot_replace_failed_append(self):
        with tempfile.TemporaryDirectory() as temporary:
            files=self.fixture(Path(temporary));capture=files[2]
            (capture/'uart.bin').write_bytes(self.row(0x423,7,0x10007)+self.row(0x421,7,0x10007))
            self.inventory(capture)
            with self.assertRaisesRegex(ValueError,'transportFailed without Saved'):self.observe(files)

    def test_unrelated_guest_error_cannot_supply_medium_barrier_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            files=self.fixture(Path(temporary));capture=files[2]
            (capture/'uart.bin').write_bytes(self.row(0x423,7,0x10007)+self.row(0x424,228,0x10007))
            self.inventory(capture)
            with self.assertRaisesRegex(ValueError,'transportFailed without Saved'):self.observe(files)

    def test_no_user_execution_or_missing_sample_rejected(self):
        for changes in ({'privilege_cycles':[0,20,0,3]},{'pen_accepted':6}):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as temporary:
                files=self.fixture(Path(temporary));capture=files[2]
                stats=json.loads((capture/'host-report.json').read_text());stats.update(changes)
                (capture/'host-report.json').write_text(json.dumps(stats));self.inventory(capture)
                with self.assertRaisesRegex(ValueError,'genuine S/U'):self.observe(files)

    def test_unacknowledged_stable_write_before_first_failed_flush_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            files=self.fixture(Path(temporary));files[1].write_bytes(b'B'*512)
            with self.assertRaisesRegex(ValueError,'acknowledged medium bytes'):self.observe(files)

    def test_pending_pixels_cannot_supply_completed_failed_label(self):
        with tempfile.TemporaryDirectory() as temporary:
            files=self.fixture(Path(temporary));capture=files[2]
            (capture/'panel').write_bytes(b'P5\n512 640\n255\n'+bytes([255])*(512*640));self.inventory(capture)
            with self.assertRaisesRegex(ValueError,'show guest FAILED'):self.observe(files)

    def test_failed_label_cannot_hide_trailing_accepted_pixel_stream(self):
        with tempfile.TemporaryDirectory() as temporary:
            files=self.fixture(Path(temporary));capture=files[2]
            with (capture/'panel.events').open('a') as stream:stream.write('32,pixel,3,0,0,15\n')
            self.inventory(capture)
            with self.assertRaisesRegex(ValueError,'incomplete accepted update'):self.observe(files)

    def cold_fixtures(self,path,trailing=False):
        before_path=path/'before';before_path.mkdir()
        after_path=path/'after';after_path.mkdir()
        before,_,prior=self.fixture(before_path)
        _,after,capture=self.fixture(after_path)
        identity=json.loads((capture/'input.json').read_text());identity['inputs']={}
        identity['options']['fail_flush']=None
        (capture/'input.events').unlink()
        (capture/'input.json').write_text(json.dumps(identity))
        stats=json.loads((capture/'host-report.json').read_text())
        stats.update(pen_ingress=0,pen_accepted=0,flushes=0,volatile_sectors_discarded=0)
        (capture/'host-report.json').write_text(json.dumps(stats))
        for directory in (prior,capture):
            (directory/'panel').write_bytes(b'P5\n512 640\n255\n'+bytes([255])*(512*640))
            (directory/'panel.events').write_text('cycle,event,sequence,x,y,gray\n'
                '10,pixel,1,0,0,15\n11,complete,1,0,0,0\n'
                '30,pixel,2,24,132,15\n31,complete,2,0,0,0\n')
            (directory/'uart.bin').write_bytes(self.row(0x420,(640<<32)|512,1))
        if trailing:
            with (capture/'panel.events').open('a') as stream:stream.write('32,pixel,3,0,0,15\n')
        self.inventory(prior);self.inventory(capture)
        return before,after,prior,capture

    def test_cold_exact_payload_and_optical_equality_requires_completed_stream(self):
        with tempfile.TemporaryDirectory() as temporary:
            files=self.cold_fixtures(Path(temporary))
            with mock.patch.object(oracle,'committed_bytes',return_value=b'literal acknowledged records'):
                self.assertEqual(oracle.cold(*files)['status'],'PASS')

    def test_cold_optical_equality_cannot_hide_trailing_accepted_stream(self):
        with tempfile.TemporaryDirectory() as temporary:
            files=self.cold_fixtures(Path(temporary),trailing=True)
            with mock.patch.object(oracle,'committed_bytes',return_value=b'literal acknowledged records'):
                with self.assertRaisesRegex(ValueError,'incomplete accepted update'):oracle.cold(*files)


if __name__=='__main__':unittest.main()
