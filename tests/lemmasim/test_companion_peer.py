"""Actual hosted Lean protocol, durable receipts and raw-adapter regressions.

These are host transport properties, not guest notebook, USB or cold recovery
acceptance. Independent Python frame construction observes Lean output bytes.
"""
import importlib.util
import json
import os
from pathlib import Path
import resource
import select
import signal
import struct
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
MAGIC=0x313030504d434d4c
LOG_MAGIC=0x3130474f4c434d4c
HELPER=ROOT/'sim/companion/os_io.py'

def crc64(data):
    value=0
    for byte in data:
        value^=byte<<56
        for _ in range(8):
            value=((value<<1)^ (0x42f0e1eba9ea3693 if value>>63 else 0))&((1<<64)-1)
    return value

def frame(kind,sequence=0,offset=0,length=0,payload=b'',writer=17,error=0):
    raw=struct.pack('<8Q',MAGIC,1,kind,writer,sequence,offset,length,error)+payload
    return raw+struct.pack('<Q',crc64(raw))

def decode(raw):
    assert len(raw)>=72 and struct.unpack_from('<Q',raw,len(raw)-8)[0]==crc64(raw[:-8])
    fields=struct.unpack_from('<8Q',raw)
    assert fields[0:2]==(MAGIC,1) and fields[2]==3
    assert fields[6]==len(raw)-72
    return fields,raw[64:-8]

def line(process,timeout=12):
    if not select.select([process.stdout],[],[],timeout)[0]:raise AssertionError('bounded hosted response timeout')
    data=process.stdout.readline()
    if not data:raise AssertionError('hosted process exited: '+str(process.poll()))
    return data.decode().strip()

def stop(process):
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=4)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=4)
    for stream in (process.stdin,process.stdout,process.stderr):
        if stream:stream.close()

class CompanionPeerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_temp=tempfile.TemporaryDirectory(prefix='lemma-companion-build-')
        path=os.environ.get('LEMMA_COMPANION_PREPARED')
        if not path:
            output=Path(cls.build_temp.name)/'compiled'
            subprocess.run(['python3',str(ROOT/'scripts/lemmasim_companion.py'),'build','--output-dir',str(output)],cwd=ROOT,check=True,timeout=300,stdout=subprocess.DEVNULL)
            path=output/'prepared.json'
        cls.prepared=json.loads(Path(path).read_text())
        cls.peer=cls.prepared['binaries']['companion-peer']['path']
        cls.client=cls.prepared['binaries']['companion-client']['path']
        spec=importlib.util.spec_from_file_location('companion_build',ROOT/'scripts/lemmasim_companion.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.validate(path)
        cls.adapter=Path(cls.build_temp.name)/'adapter'
        subprocess.run(['g++','-O2','-std=c++17','-Wall','-Wextra','-Werror',str(ROOT/'tests/lemmasim/companion_adapter.cpp'),str(ROOT/'sim/companion/backing_peer.cpp'),str(ROOT/'sim/host/backing_io.cpp'),'-o',str(cls.adapter)],check=True,timeout=90)
    @classmethod
    def tearDownClass(cls):cls.build_temp.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='lemma-companion-')
        self.directory=Path(self.temp.name)/'peer';self.directory.mkdir()
        self.base=self.directory/'base.img'
        with self.base.open('wb') as stream:stream.truncate(268435456)
        self.journal=self.directory/'opaque.log'
        self.journal.write_bytes(struct.pack('<Q',LOG_MAGIC))
        self.socket=Path(self.temp.name)/'peer.sock'
        self.processes=[]
    def tearDown(self):
        for process in reversed(self.processes):stop(process)
        self.temp.cleanup()
    def peer_process(self,helper=HELPER,preexec=None):
        process=subprocess.Popen([self.peer,str(self.directory),str(self.base),'17',str(helper)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,preexec_fn=preexec)
        self.processes.append(process);return process
    def exchange(self,peer,request):
        peer.stdin.write(request.hex().encode()+b'\n');peer.stdin.flush()
        return decode(bytes.fromhex(line(peer)))
    def server(self,drop=0,exit_after=0,helper=HELPER):
        process=subprocess.Popen(['python3',str(ROOT/'sim/companion/server.py'),'--binary',self.peer,'--directory',str(self.directory),'--base',str(self.base),'--writer','17','--helper',str(helper),'--socket',str(self.socket),'--drop-reply',str(drop),'--exit-after-reply',str(exit_after)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
        self.processes.append(process)
        self.assertTrue(line(process).startswith('RAW_PEER_READY '));return process
    def client_process(self):
        process=subprocess.Popen([self.client,str(self.socket),str(Path(self.temp.name)/'client'),'17',str(HELPER)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
        self.processes.append(process)
        self.assertTrue(line(process).startswith('READY 268435456 17 '));return process
    def client_request(self,client,kind,offset=0,length=0,payload=b''):
        client.stdin.write(f'{kind} 8 90 {offset} {length} {payload.hex() or "-"}\n'.encode());client.stdin.flush()
        return line(client)
    def test_independent_vectors_receipts_and_restart(self):
        self.assertEqual(crc64(b'123456789'),0x6c40df5f0b497347)
        peer=self.peer_process();data=bytes((i*13+7)&255 for i in range(512))
        fields,raw=self.exchange(peer,frame(0,length=512));self.assertEqual((fields[7],raw),(0,bytes(512)))
        write=frame(1,1,512,512,data)
        fields,raw=self.exchange(peer,write);self.assertEqual((fields[7],raw),(0,data))
        self.assertEqual(self.journal.stat().st_size,600)
        self.exchange(peer,write);self.assertEqual(self.journal.stat().st_size,600)
        fields,_=self.exchange(peer,frame(1,1,512,512,bytes(512)));self.assertEqual(fields[7],71)
        fields,_=self.exchange(peer,frame(2,3));self.assertEqual(fields[7],71)
        fields,_=self.exchange(peer,frame(2,2));self.assertEqual(fields[7],0)
        self.assertEqual(self.journal.stat().st_size,680)
        stop(peer);peer=self.peer_process()
        fields,raw=self.exchange(peer,frame(0,offset=512,length=512));self.assertEqual((fields[7],raw),(0,data))
        # Exact complete corrupt bytes reject; a truncated tail alone recovers.
        stop(peer)
        with self.journal.open('ab') as stream:stream.write(b'\x48\x00\x00')
        peer=self.peer_process();self.exchange(peer,frame(0,length=512));self.assertEqual(self.journal.stat().st_size,680)
        invalid=bytearray(frame(0,length=512));invalid[-1]^=1
        peer.stdin.write(bytes(invalid).hex().encode()+b'\n');peer.stdin.flush()
        self.assertEqual(line(peer),'error frame CRC')
    def test_lost_ack_both_process_restarts_same_transaction(self):
        server=self.server(drop=2,exit_after=2);client=self.client_process()
        data=bytes((i*7+11)&255 for i in range(512))
        self.assertEqual(self.client_request(client,1,0,512,data),'PENDING')
        self.assertEqual(client.wait(timeout=4),2);server.wait(timeout=4)
        self.assertEqual(self.journal.stat().st_size,600)
        outbox=Path(self.temp.name)/'client/outbox'
        raw=outbox.read_bytes();self.assertEqual(struct.unpack_from('<Q',raw,24)[0],584)
        server=self.server();client=self.client_process()
        self.assertEqual(self.journal.stat().st_size,600)
        raw=outbox.read_bytes();self.assertEqual(struct.unpack_from('<2Q',raw,16),(2,0))
        result=self.client_request(client,0,0,512).split(' ')
        self.assertEqual((result[0:2],bytes.fromhex(result[2])),(['512','0'],data))
        self.assertEqual(self.client_request(client,2),'0 0 -')
        self.assertEqual(self.journal.stat().st_size,680)
    def test_large_frame_bytes_and_independent_bitwise_crc(self):
        # Exercises every input byte and CRC table index over the admitted
        # transfer bound; the observer retains a separate bit-by-bit algorithm.
        data=bytes(range(256))*4096;offset=268435456-len(data)
        with self.base.open('r+b') as base:base.seek(offset);base.write(data)
        peer=self.peer_process()
        fields,raw=self.exchange(peer,frame(0,offset=offset,length=len(data)))
        self.assertEqual((fields[7],raw),(0,data))
        self.assertEqual(self.journal.stat().st_size,8)
    def test_actual_fsync_failure_preserves_observed_bytes(self):
        helper=Path(self.temp.name)/'closed_fd.py'
        helper.write_text('import os,sys,subprocess\nif sys.argv[1]=="sync":\n fd=os.open(sys.argv[2],os.O_RDONLY);os.close(fd);os.fsync(fd)\nelse:\n raise SystemExit(subprocess.call([sys.executable,'+repr(str(HELPER))+']+sys.argv[1:]))\n')
        peer=self.peer_process(helper);data=b'\xa7'*512
        fields,raw=self.exchange(peer,frame(1,1,0,512,data))
        self.assertEqual((fields[7],raw),(5,data));self.assertEqual(self.journal.stat().st_size,600)
        fields,raw=self.exchange(peer,frame(0,length=512));self.assertEqual((fields[7],raw),(0,data))
        stop(peer);peer=self.peer_process()
        fields,raw=self.exchange(peer,frame(1,1,0,512,data));self.assertEqual((fields[7],raw),(0,data))
        self.assertEqual(self.journal.stat().st_size,600)
    def test_actual_partial_append_failure_recovers_tail(self):
        def limit():
            signal.signal(signal.SIGXFSZ,signal.SIG_IGN);resource.setrlimit(resource.RLIMIT_FSIZE,(100,100))
        peer=self.peer_process(preexec=limit)
        fields,raw=self.exchange(peer,frame(1,1,0,512,b'\xcc'*512))
        self.assertEqual((fields[7],raw),(5,b''));self.assertEqual(self.journal.stat().st_size,8)
        fields,raw=self.exchange(peer,frame(0,length=512));self.assertEqual((fields[7],raw),(0,bytes(512)))
    def test_observational_read_does_not_complete_pending_barrier(self):
        helper=Path(self.temp.name)/'closed_fd.py';audit=Path(self.temp.name)/'sync.attempts'
        helper.write_text('import os,sys,subprocess\nif sys.argv[1]=="sync":\n with open('+repr(str(audit))+',"a") as out:out.write("sync\\n")\n fd=os.open(sys.argv[2],os.O_RDONLY);os.close(fd);os.fsync(fd)\nelse:\n raise SystemExit(subprocess.call([sys.executable,'+repr(str(HELPER))+']+sys.argv[1:]))\n')
        self.server(helper=helper);client=self.client_process();data=b'\x89'*512
        result=self.client_request(client,1,0,512,data).split(' ')
        self.assertEqual((result[0:2],bytes.fromhex(result[2])),(['512','5'],data))
        self.assertEqual(audit.read_text(),'sync\n')
        result=self.client_request(client,0,0,512).split(' ')
        self.assertEqual((result[0:2],bytes.fromhex(result[2])),(['512','0'],data))
        self.assertEqual(audit.read_text(),'sync\n')
        raw=(Path(self.temp.name)/'client/outbox').read_bytes()
        self.assertEqual(struct.unpack_from('<Q',raw,24)[0],584)
    def test_cpp_raw_adapter_and_private_replay_rejection(self):
        self.server()
        result=subprocess.run([str(self.adapter),self.client,str(self.socket),str(Path(self.temp.name)/'adapter-client'),'17',str(HELPER)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('PASS',result.stdout)
        self.assertEqual(self.journal.stat().st_size,680)

if __name__=='__main__':unittest.main()
