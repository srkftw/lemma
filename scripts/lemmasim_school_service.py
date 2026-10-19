#!/usr/bin/env python3
"""Bounded external school bytes for an ordinary live machine.

Network work never runs on the machine owner thread. Only that thread admits
completed opaque packages through the modeled UART. School policy and guest
documents remain in Lean. Credentials/live peers are not checkpoint state.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import os
from pathlib import Path
import re
import stat
import struct
import zlib
import time
import urllib.parse
import urllib.request
import uuid

from lemmasim_tutor import ask_context, uart_path
from lemmasim_course import frame,selection_frame


def school_capability(data):
    result=None
    for row in re.finditer(rb'(?:^|\n)K1 0000000000000731 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?(?=\n)',data):
        version,chunks,size,selection=(int(x,16) for x in row.groups())
        if (version,chunks) not in ((1,8),(2,512)) or size!=262144 or selection!=2:
            raise ValueError('unsupported guest school capability tuple')
        result={'version':version,'maximumChunks':chunks,'maximumBytes':size,'selection':selection}
    return result


def submission_stream(data):
    """Copy one complete committed guest byte stream; never interpret its work."""
    if not isinstance(data,bytes) or len(data)>16*1048576:
        raise ValueError('guest submission observation exceeds16MiB')
    current=None;complete=None
    rows=re.finditer(rb'(?:^|\n)K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?(?=\n)',data)
    for row in rows:
        tag,a,b,c,d=(int(x,16) for x in row.groups())
        if tag==0x72e:
            if a>>48!=0x5351 or b==0 or not 256<=c<=262144 or d not in (1,2):
                raise ValueError('malformed guest submission stream start')
            current={'queue':a,'commit':b,'total':c,'bytes':bytearray()}
        elif tag==0x72f and current is not None:
            offset=b&((1<<48)-1);count=b>>48
            if a!=current['queue'] or not 1<=count<=16 or offset!=len(current['bytes']) or count>current['total']-offset:
                raise ValueError('guest submission stream is missing, reordered or mixed')
            current['bytes'].extend(struct.pack('<2Q',c,d)[:count])
        elif tag==0x730 and current is not None:
            if (a,b,c,d)!=(current['queue'],current['commit'],current['total'],0) or len(current['bytes'])!=c:
                raise ValueError('guest submission stream ended before its exact committed bytes')
            complete=current;current=None
    if current is not None:raise ValueError('guest submission is still streaming; keep writing or retry after completion')
    if complete is None:raise ValueError('tap SEND on the guest paper to commit and stream work first')
    return complete


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('school service refuses redirects')


class SchoolService:
    def __init__(self, session):
        self.session=session; self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='lemma-school-io')
        self.connection=None; self.binding=None; self.epoch=0; self.jobs={}; self.partial=False
        self.review=None

    def invalidate(self):
        self.epoch+=1; self.connection=None; self.binding=None;self.review=None
        for job in self.jobs.values():
            if job.get('future') is not None: job['future'].cancel()

    def close(self):
        self.invalidate(); self.pool.shutdown(wait=False,cancel_futures=True)

    def context(self):
        metadata=json.loads((self.session.directory/'session.json').read_text())
        if metadata['identity']!=self.session.machine.identity:
            raise ValueError('school service machine identity differs')
        return ask_context(uart_path(self.session.directory,metadata).read_bytes())

    def connect(self, path):
        path=Path(path); info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode & 0o077 or info.st_size>4096:
            raise ValueError('choose an owned private regular pairing file of at most4096 bytes')
        credential=json.loads(path.read_text())
        if credential.get('schema')!='lemma-school-credential/1' or not re.fullmatch('[a-f0-9]{64}',credential.get('token','')):
            raise ValueError('unsupported school credential')
        url=urllib.parse.urlsplit(credential.get('endpoint',''))
        if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost','::1') or url.path!='/v1/client' or url.username or url.password or url.query or url.fragment:
            raise ValueError('school service requires an explicit loopback /v1/client endpoint')
        self.invalidate(); self.connection=(url.geturl(),credential['token'])

    @staticmethod
    def exchange(connection, command):
        url,token=connection
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        request=urllib.request.Request(url,data=json.dumps(command,separators=(',',':')).encode(),
            headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
        deadline=time.monotonic()+30
        with opener.open(request,timeout=5) as response:
            parts=[];size=0
            while True:
                if time.monotonic()>deadline:raise ValueError('school response exceeded original30s bound')
                chunk=response.read(65536)
                if not chunk:break
                size+=len(chunk)
                if size>1048576:raise ValueError('school response exceeded1MiB bound')
                parts.append(chunk)
        reply=json.loads(b''.join(parts))
        if reply.get('ok') is not True or not isinstance(reply.get('result'),dict):
            raise ValueError('Lean school rejected: '+str(reply.get('error','missing result')))
        return reply['result']

    def dispatch(self, value):
        operation=value.get('operation')
        if operation=='observation':
            metadata=json.loads((self.session.directory/'session.json').read_text())
            data=uart_path(self.session.directory,metadata).read_bytes()
            records={};queue=None
            for row in re.finditer(rb'(?:^|\n)K1 (000000000000(?:04b1|04b9|0727|072e|0732|0733|0734)) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?(?=\n)',data):
                key,*words=(int(x,16) for x in row.groups());records[hex(key)]=words
                if key==0x72e:queue={'state':'pending','queue':str(words[0]),'localQueueCommit':str(words[1]),'bytes':words[2]}
                elif key==0x732:queue={'state':'failed','code':words[0]}
                elif key in (0x733,0x734):
                    a,b,c,d=words
                    if not ((d==2 and b==0) or (d==3 and b>0)):raise ValueError('malformed terminal guest queue report')
                    queue={'state':'cancelled' if d==2 else 'acknowledged','queue':str(a),'schoolCommit':str(b),'observedFrontier':str(c),
                           'observation':'new-pointer-commit' if key==0x733 else 'restored-pointer-read'}
            return {'authority':'complete compiled-guest console records','records':records,'outgoingQueue':queue,'capability':school_capability(data)}
        if operation=='poll':
            self.pump();job=self.jobs.get(value.get('id'))
            if job is None:raise ValueError('school request absent')
            return {k:v for k,v in job.items() if k not in ('future','epoch','stream')}
        if operation=='disconnect':
            self.invalidate();return {'status':'disconnected','scope':'live external admission cleared; saved guest work retained'}
        if operation=='sample':
            encoded=value.get('hex','')
            if not isinstance(encoded,str) or len(encoded)!=8398 or not re.fullmatch('[a-f0-9]+',encoded):
                raise ValueError('the account-free sample requires its maintained compiled package')
            payload=bytes.fromhex(encoded)
            if hashlib.sha256(payload).hexdigest()!='3f1900b5ede7a4197086dc6cb30176e66fb75ac24aaee68f8cabcf689bb1093e':
                raise ValueError('sample differs from the admitted source-grounded local package')
            result={'package_hex':encoded,'sample':True};self.admit(result)
            return {k:v for k,v in result.items() if k!='package_hex'}
        if operation=='connect':self.connect(value['credential'])
        if self.connection is None:raise ValueError('connect using a private school pairing file first')
        mutations=('install','review','join','help','submit','cancel')
        if operation=='cancel':
            self.epoch+=1
            for pending in self.jobs.values():
                if pending.get('future') is not None:pending['future'].cancel()
        elif operation in mutations and any(j.get('status')=='pending' and j.get('operation') in mutations for j in self.jobs.values()):
            raise ValueError('a school transfer is pending; cancel it or wait before changing its publication/context')
        if len([j for j in self.jobs.values() if j.get('status')=='pending' and j.get('epoch')==self.epoch])>=2:
            raise ValueError('school I/O backpressure: two bounded requests pending')
        if operation in ('connect','catalogue'):
            command={'op':'course-catalogue','limit':20,'after':value.get('after',0)}
        elif operation=='submit':
            metadata=json.loads((self.session.directory/'session.json').read_text())
            stream=submission_stream(uart_path(self.session.directory,metadata).read_bytes())
            command={'op':'guest-submit','hex':bytes(stream['bytes']).hex()}
        elif operation=='reviews':command={'op':'reviews','limit':20,'after':value.get('after',0)}
        elif operation=='review':
            command={'op':'review-open','id':value['id']}
        elif operation=='feedback':command={'op':'feedback','limit':20,'after':value.get('after',0)}
        elif operation=='install':
            self.review=None
            course,revision=value.get('course'),value.get('revision')
            if type(course) is not int or not 1<=course<=65535 or type(revision) is not int or not 1<=revision<=0xffffffff:
                raise ValueError('select a bounded publication identity and edition')
            command={'op':'client-course','course':course,'revision':revision}
        elif operation=='join':
            ask=self.context();binding=f"native-{ask['session']}-{ask['source']}-{ask['edition']}"
            command={'op':'join','course':ask['source'],'revision':ask['edition'],'session':binding,
                     'guestSession':ask['session'],'lifetimeMs':3600000,'ask':ask,**({'reviewId':self.review} if self.review else {})}
        elif operation=='help':
            if self.binding is None:raise ValueError('bind the current guest ASK first')
            ask=self.context();command={'op':'assist','session':self.binding,'course':ask['source'],'revision':ask['edition'],'ask':ask}
        elif operation=='cancel':
            if self.binding is None:raise ValueError('no school session is bound')
            command={'op':'cancel-session','session':self.binding};self.binding=None
        else:raise ValueError('unsupported ordinary school operation')
        id=uuid.uuid4().hex
        # Completed observations are bounded diagnostics, never a durable queue.
        for old in list(self.jobs):
            if len(self.jobs)<64:break
            if self.jobs[old]['status']!='pending':del self.jobs[old]
        self.jobs[id]={'id':id,'status':'pending','operation':operation,'epoch':self.epoch,
                      **({'binding':binding} if operation=='join' else {}),
                      **({'review':value['id']} if operation=='review' else {}),
                      **({'stream':stream} if operation=='submit' else {}),
                      'future':self.pool.submit(self.exchange,self.connection,command)}
        return {'id':id,'status':'pending','operation':operation}

    def admit_acknowledgement(self,result,stream):
        if result.get('queueObject')!=stream['queue'] or result.get('envelopeCRC32')!=zlib.crc32(stream['bytes']):
            raise ValueError('school commit acknowledgement differs from the exact guest byte stream')
        commit=result.get('commitSequence')
        if type(commit) is not int or not 1<=commit<(1<<63):raise ValueError('school returned no bounded durable commit identity')
        packet=struct.pack('<8Q',0x31504b43414d454c,3,10,stream['queue'],commit,0,stream['commit'],result['envelopeCRC32'])
        state=self.session.machine.call('inspect');cycle=state['cycle']
        ingress=state.get('devices',{}).get('uart_ingress',{})
        if not ingress.get('enabled') or len(packet)>65536-ingress.get('pending',65536):raise ValueError('school acknowledged work; guest acknowledgement input is busy; retry same submission')
        self.admit_packet(packet,state)
        result['guestAcknowledgement']='exact school commit bytes admitted to guest UART; durable queue acknowledgement is separate'

    def admit(self, result):
        encoded=result.get('package_hex')
        if encoded is None:return
        if self.partial:raise ValueError('partial school transfer requires cold reopen before retry')
        if not isinstance(encoded,str) or not 256<=len(encoded)<=65536 or not re.fullmatch('(?:[a-f0-9]{2})+',encoded):
            raise ValueError('school returned invalid bounded package bytes')
        payload=bytes.fromhex(encoded)
        import struct
        identity,edition=struct.unpack_from('<2Q',payload,24);crc=struct.unpack_from('<Q',payload,80)[0]
        transaction=uuid.uuid4().int%(2**63-2)+1
        packet=frame(1,identity,edition,len(payload),transaction,crc)+payload
        # Only the versioned guest advertises the v2 selected-publication path.
        if school_capability(uart_path(self.session.directory,json.loads((self.session.directory/'session.json').read_text())).read_bytes()) is not None:
            packet+=selection_frame(identity,edition,transaction+1,crc,result.get('node',0))
        session=self.session;session.ensure_capture_certain()
        state=session.machine.call('inspect');cycle=state['cycle']
        ingress=state.get('devices',{}).get('uart_ingress',{})
        if not ingress.get('enabled') or len(packet)>65536-ingress.get('pending',65536):
            raise ValueError('guest UART backpressure; retry after guest drains input')
        self.admit_packet(packet,state)
        result['transport']={'contract':'lemma-school-native-service/1','bytes':len(payload),'transaction':transaction,'byte_interval_ns':100000,
                             'receipt':'UART input admitted; guest install, JOIN and visible delivery remain separate'}

    def admit_packet(self,packet,state):
        session=self.session;cycle=state['cycle']
        # Fast cycle is 10 ns. A paced controller has one stable-merged event
        # per byte; legacy backends receive one byte per admitted event.
        paced=state.get('devices',{}).get('uart_ingress',{}).get('paced') is True
        width=1024 if paced else 1
        admitted=0
        try:
            for offset in range(0,len(packet),width):
                chunk=packet[offset:offset+width].hex()
                when=cycle+offset*10000
                value={'action':'inject','kind':'uart','cycle':when,'hex':chunk}
                if paced:value['byte_interval_ns']=100000
                command=f'inject {when} uart-paced 100000 {chunk}' if paced else f'inject {when} uart {chunk}'
                session.external(value,state,command)
                admitted+=len(chunk)//2
        except BaseException:
            self.partial=admitted>0;raise

    def pump(self):
        for job in self.jobs.values():
            future=job.get('future')
            if job['status']!='pending' or future is None or not future.done():continue
            try:
                if job['epoch']!=self.epoch:raise ValueError('external school epoch changed; reconnect explicitly')
                result=future.result()
                if job['operation']=='submit':self.admit_acknowledgement(result,job['stream'])
                else:self.admit(result)
                if job['operation']=='join':self.binding=job['binding']
                if job['operation']=='review':self.review=job['review']
                job.update(status='completed',result={k:v for k,v in result.items() if k!='package_hex'})
            except Exception as error:job.update(status='failed',error=str(error))
            job.pop('future',None);job.pop('stream',None)
