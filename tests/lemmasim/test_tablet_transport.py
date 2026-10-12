"""Independent evdev byte/frame fixtures; no physical-tablet claim."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock
import sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('lemma_tablet',ROOT/'scripts/lemmasim_tablet.py')
tablet=importlib.util.module_from_spec(spec);sys.modules[spec.name]=tablet;spec.loader.exec_module(tablet)


def capabilities(pressure=True):
    axes={0:tablet.Axis(100,1100),1:tablet.Axis(-250,750),26:tablet.Axis(-60,60)}
    if pressure:axes[24]=tablet.Axis(0,8190)
    return tablet.Capabilities('reported pen',axes,frozenset({0x140,0x141,0x14a,0x14b,0x14c,0x149}))


def decoder(pressure=True):
    caps=capabilities(pressure)
    return tablet.Decoder(caps,{key:axis.minimum for key,axis in caps.axes.items()},set())


def event(kind,code,value):return (10,1234,kind,code,value)


class TabletTransport(unittest.TestCase):
    def test_actual_reported_fields_normalize_without_synthetic_or_tilt(self):
        d=decoder()
        corpus=[event(1,0x140,1),event(1,0x14a,1),event(3,0,600),event(3,1,250),
                event(3,24,4095),event(3,26,-30),event(1,0x14c,1),event(0,0,0)]
        for row in corpus:packet=d.feed(row)
        self.assertEqual(packet.words(77),[77,32767,32767,2047,3,1,2])
        self.assertEqual(packet.raw_events,tuple(corpus))
        report=d.capabilities.report()
        self.assertTrue(report['pressure_reported']);self.assertTrue(report['tilt_reported'])
        self.assertEqual(report['tilt_transport'],'UNSUPPORTED_BY_PEN_V1')
        self.assertFalse(packet.flags&4)

    def test_no_pressure_is_explicitly_unavailable_not_invented(self):
        d=decoder(False);d.feed(event(1,0x140,1));d.feed(event(1,0x14a,1));p=d.feed(event(0,0,0))
        self.assertEqual(p.pressure,0);self.assertFalse(d.capabilities.report()['pressure_reported'])
        self.assertEqual(d.capabilities.report()['pressure_when_absent'],'UNAVAILABLE')

    def test_eraser_buttons_contact_release_preserve_reported_state(self):
        d=decoder();d.feed(event(1,0x141,1));d.feed(event(1,0x14a,1));d.feed(event(1,0x149,1))
        self.assertEqual(d.feed(event(0,0,0)).words(2)[4:],[3,2,4])
        d.feed(event(1,0x14a,0));self.assertEqual(d.feed(event(0,0,0)).flags,2)
        d.feed(event(1,0x141,0));self.assertEqual(d.feed(event(0,0,0)).tool,0)

    def test_syn_drop_requires_actual_state_query_and_never_connects_old_frame(self):
        d=decoder();d.feed(event(3,0,1000));loss=d.feed(event(0,3,0))
        self.assertEqual(loss.flags,8);self.assertEqual(loss.reason,'SYN_DROPPED')
        self.assertIsNone(d.feed(event(3,0,300)));self.assertIsNone(d.feed(event(0,0,0)))
        d.resynchronize({0:200,1:-150,24:0,26:0},set())
        self.assertEqual(d.feed(event(0,0,0)).words(10),[10,6553,6553,0,0,0,0])

    def test_missing_capability_bad_axis_and_unbounded_frame_reject(self):
        with self.assertRaises(ValueError):tablet.Capabilities('pointer',{0:tablet.Axis(0,10),1:tablet.Axis(0,10)},frozenset({0x14a}))
        with self.assertRaises(ValueError):tablet.Axis(10,10)
        d=decoder();d.feed(event(3,0,1101))
        with self.assertRaises(ValueError):d.feed(event(0,0,0))
        self.assertEqual(d.loss('bad-frame').flags,8)
        d=decoder()
        for _ in range(128):d.feed(event(3,26,0))
        with self.assertRaises(ValueError):d.feed(event(3,26,0))
        with self.assertRaises(ValueError):d.last_packet.words(True)

    def test_real_byte_pipe_partial_record_eof_and_bounded_teardown(self):
        readfd,writefd=os.pipe()
        try:
            rows=[event(1,0x140,1),event(1,0x14a,1),event(3,0,600),event(3,1,250),event(3,24,4095),event(0,0,0)]
            data=b''.join(tablet.INPUT_EVENT.pack(*row) for row in rows)
            os.write(writefd,data[:10]);packets=[]
            with tempfile.TemporaryDirectory() as tmp, mock.patch.object(tablet.os,'open',return_value=readfd), \
                 mock.patch.object(tablet,'probe',return_value=capabilities()), \
                 mock.patch.object(tablet,'current_state',return_value=({0:100,1:-250,24:0,26:0},set())):
                bridge=tablet.TabletBridge('/selected/tablet',packets.append,Path(tmp)/'raw.jsonl')
                report=bridge.start();os.write(writefd,data[10:]);os.close(writefd);writefd=-1
                bridge._thread.join(2);bridge.close();readfd=-1
                self.assertFalse(bridge.alive);self.assertIsNone(bridge.error)
                self.assertEqual(packets[0].words(500),[500,32767,32767,2047,3,1,0])
                self.assertEqual(packets[1].flags,8);self.assertEqual(packets[1].reason,'device-disconnect')
                captured=[json.loads(row) for row in (Path(tmp)/'raw.jsonl').read_text().splitlines()]
                self.assertEqual(captured[0]['kind'],'capabilities');self.assertEqual(len(captured),3)
        finally:
            if readfd>=0:os.close(readfd)
            if writefd>=0:os.close(writefd)

    def test_session_sink_uses_observed_virtual_time_and_only_literal_pen(self):
        calls=[]
        def rpc(directory,value,timeout):
            calls.append((directory,value,timeout))
            return {'machine':{'ticks':0x100000005,'cycle':999,'virtual_ns':9984}} if value['action']=='clock' else {}
        tablet.session_sink(Path('/session'),rpc)(tablet.Packet(17,23,99,3,1,2))
        self.assertEqual(calls,[(Path('/session'),{'action':'clock','source':'tablet'},2),
            (Path('/session'),{'action':'inject','kind':'pen',
             'words':[0x100000005,17,23,99,3,1,2],'source':'tablet'},2)])

    def test_clock_failure_and_invalid_ticks_do_not_admit_tablet_sample(self):
        for clock in (TimeoutError('Clock unavailable'),{'machine':{'ticks':True}},
                      {'machine':{'ticks':1<<64}}):
            calls=[]
            def rpc(directory,value,timeout):
                calls.append(value)
                if isinstance(clock,Exception):raise clock
                return clock
            with self.subTest(clock=clock),self.assertRaises((TimeoutError,ValueError)):
                tablet.session_sink(Path('/session'),rpc)(tablet.Packet(17,23,99,3,1,2))
            self.assertEqual(calls,[{'action':'clock','source':'tablet'}])

    def test_cli_sigterm_stops_real_input_pipe_and_records_explicit_loss(self):
        # Kernel capability queries are a fixture; actual pipe bytes, process,
        # signal and teardown are exercised. This is not a tablet hardware test.
        readfd,writefd=os.pipe()
        child=None
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);admitted=tmp/'admitted.jsonl';raw=tmp/'raw.jsonl'
            code='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import lemmasim_tablet as tablet,lemmasim_session as session
caps=tablet.Capabilities('fixture pen',{0:tablet.Axis(0,1000),1:tablet.Axis(0,1000),24:tablet.Axis(0,4095)},frozenset({0x140,0x14a}))
tablet.probe=lambda fd:caps
tablet.current_state=lambda fd,c:({0:0,1:0,24:0},set())
admission_path=Path(sys.argv[2])
def rpc(directory,value,timeout):
    with admission_path.open('a') as output:output.write(json.dumps(value)+'\\n')
    return {'machine':{'ticks':987}} if value['action']=='clock' else {}
session.request=rpc
sys.argv=['tablet','--device',sys.argv[3],'--session-dir',sys.argv[4],'--record',sys.argv[5]]
tablet.main()
'''
            try:
                child=subprocess.Popen([sys.executable,'-c',code,str(ROOT/'scripts'),str(admitted),
                    f'/proc/self/fd/{readfd}',str(tmp/'session'),str(raw)],pass_fds=(readfd,),
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                rows=[event(1,0x140,1),event(1,0x14a,1),event(3,0,500),event(3,1,250),
                      event(3,24,1000),event(0,0,0)]
                os.write(writefd,b''.join(tablet.INPUT_EVENT.pack(*row) for row in rows))
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    if admitted.exists() and len(admitted.read_text().splitlines())>=2:break
                    if child.poll() is not None:break
                    time.sleep(0.01)
                if child.poll() is not None:
                    _,stderr=child.communicate(timeout=3)
                    self.fail('Adapter failed before signal: '+stderr)
                self.assertTrue(admitted.exists(),'No literal event admitted')
                child.terminate();stdout,stderr=child.communicate(timeout=3)
                self.assertEqual(child.returncode,0,stderr)
                calls=[json.loads(row) for row in admitted.read_text().splitlines()]
                injections=[row for row in calls if row['action']=='inject']
                self.assertEqual(injections[0],{'action':'inject','kind':'pen',
                    'words':[987,32767,16383,1000,3,1,0],'source':'tablet'})
                self.assertEqual(injections[1]['words'],[987,32767,16383,0,8,0,0])
                self.assertEqual(len(calls),4)
                captured=[json.loads(row) for row in raw.read_text().splitlines()]
                self.assertEqual(captured[-1]['reason'],'adapter-cancel')
                self.assertEqual(captured[-1]['flags'],8)
                self.assertIn('fixture pen',stdout)
            finally:
                if child is not None and child.poll() is None:
                    child.kill();child.communicate(timeout=3)
                if child is not None:
                    child.stdout.close();child.stderr.close()
                os.close(readfd);os.close(writefd)


if __name__=='__main__':unittest.main()
