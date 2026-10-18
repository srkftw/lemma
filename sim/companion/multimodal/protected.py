"""Host-only independent RFC8439 oracle and development protected packet peer.
The maintained target implements its own scalar/Action AEAD. This reference uses
Python arbitrary integers for Poly1305, giving an independent arithmetic oracle.
No private key is emitted in receipts. A live simulator uses host OS entropy;
that boundary does not qualify a physical entropy source or deployed security.
"""
import hashlib,hmac,json,os,stat,struct
from pathlib import Path

MAX_SEQUENCE=(1<<64)-2
HEADER=struct.Struct('<16Q')

class Rejected(ValueError):pass

def chacha_block(key,nonce,counter):
    if len(key)!=32 or len(nonce)!=12 or not 0<=counter<1<<32:raise Rejected('cipher format')
    state=list(struct.unpack('<4I',b'expand 32-byte k'))+list(struct.unpack('<8I',key))+[counter]+list(struct.unpack('<3I',nonce))
    x=state[:]
    def rotate(v,n):return ((v<<n)|(v>>(32-n)))&0xffffffff
    def quarter(a,b,c,d):
        x[a]=(x[a]+x[b])&0xffffffff;x[d]=rotate(x[d]^x[a],16)
        x[c]=(x[c]+x[d])&0xffffffff;x[b]=rotate(x[b]^x[c],12)
        x[a]=(x[a]+x[b])&0xffffffff;x[d]=rotate(x[d]^x[a],8)
        x[c]=(x[c]+x[d])&0xffffffff;x[b]=rotate(x[b]^x[c],7)
    for _ in range(10):
        for q in ((0,4,8,12),(1,5,9,13),(2,6,10,14),(3,7,11,15),(0,5,10,15),(1,6,11,12),(2,7,8,13),(3,4,9,14)):quarter(*q)
    return struct.pack('<16I',*((a+b)&0xffffffff for a,b in zip(x,state)))

def poly1305(key,message):
    if len(key)!=32:raise Rejected('one-time-key format')
    r=int.from_bytes(key[:16],'little')&0x0ffffffc0ffffffc0ffffffc0fffffff
    a=0
    for i in range(0,len(message),16):a=((a+int.from_bytes(message[i:i+16]+b'\1','little'))*r)%((1<<130)-5)
    return ((a+int.from_bytes(key[16:],'little'))% (1<<128)).to_bytes(16,'little')

def xor_stream(key,nonce,message):
    return bytes(value^chacha_block(key,nonce,1+i//64)[i%64] for i,value in enumerate(message))

def tag_for(key,nonce,aad,ciphertext):
    mac_data=aad+b'\0'*((-len(aad))%16)+ciphertext+b'\0'*((-len(ciphertext))%16)+struct.pack('<QQ',len(aad),len(ciphertext))
    return poly1305(chacha_block(key,nonce,0)[:32],mac_data)

def seal(key,nonce,aad,plaintext):
    if len(aad)>256 or len(plaintext)>4096:raise Rejected('bounded AEAD length')
    ciphertext=xor_stream(key,nonce,plaintext)
    return ciphertext+tag_for(key,nonce,aad,ciphertext)

def open_packet(key,nonce,aad,sealed):
    if len(aad)>256 or not 16<=len(sealed)<=4112:raise Rejected('bounded AEAD length')
    ciphertext,tag=sealed[:-16],sealed[-16:]
    if not hmac.compare_digest(tag,tag_for(key,nonce,aad,ciphertext)):raise Rejected('authentication failed')
    return xor_stream(key,nonce,ciphertext)

def hkdf(salt,key,info):
    prk=hmac.digest(salt,key,'sha256')
    return hmac.digest(prk,info+b'\1','sha256')

def owner_key(path):
    p=Path(path);s=p.stat()
    if s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)&0o077 or not stat.S_ISREG(s.st_mode):raise Rejected('owner key must be an owner-only regular file')
    key=p.read_bytes()
    if len(key)!=32:raise Rejected('owner key must contain exactly32binary bytes')
    return key

class Session:
    """One authenticated-hello exchange, then strict bounded packets.
    No snapshot API deliberately serializes live session credentials. Each
    reconnect constructs a new instance with fresh hello randomness on both
    ends, key derivation and grants; caller owns persistent completed-action
    frontiers separately from transport receipt.
    """
    def __init__(self,key,role,boot,capture,external,document_revision,durable_frontier,development=False,random_bytes=None):
        if len(key)!=32 or role not in ('tablet','companion') or min(boot,capture,external)<=0:raise Rejected('session context')
        if random_bytes is not None and not development:raise Rejected('deterministic entropy requires explicit synthetic development')
        self.key=key;self.role=role;self.context=(boot,capture,external,document_revision,durable_frontier)
        self.development=development;self.random=os.urandom(32) if random_bytes is None else random_bytes
        if len(self.random)!=32:raise Rejected('fresh nonce length')
        self.hello={"schema":"lemma-protected-hello/1","role":role,"boot":boot,"capture":capture,"external":external,
            "revision":document_revision,"durable_frontier":durable_frontier,"random":self.random.hex(),"development":development}
        self.send_key=None;self.receive_key=None;self.tx=0;self.rx=0;self.tx_stream=[0]*32;self.rx_stream=[0]*32;self.queues=[[],[],[],[]]
    def offer(self):
        data=json.dumps(self.hello,sort_keys=True,separators=(',',':')).encode()
        return {'hello':self.hello,'tag':hmac.digest(self.key,b'lemma-hello/1\0'+data,'sha256').hex()}
    def accept(self,offer):
        peer=offer['hello'];data=json.dumps(peer,sort_keys=True,separators=(',',':')).encode()
        if not hmac.compare_digest(bytes.fromhex(offer['tag']),hmac.digest(self.key,b'lemma-hello/1\0'+data,'sha256')):raise Rejected('owner endpoint authentication failed')
        if peer.get('schema')!='lemma-protected-hello/1' or peer.get('role')==self.role or peer.get('role') not in ('tablet','companion') or peer.get('development')!=self.development:raise Rejected('hello identity')
        if tuple(peer[k] for k in ('boot','capture','external','revision','durable_frontier'))!=self.context:raise Rejected('reconnect binding mismatch')
        if len(bytes.fromhex(peer['random']))!=32 or peer['random']==self.random.hex():raise Rejected('peer nonce')
        tablet=self.hello if self.role=='tablet' else peer
        companion=peer if self.role=='tablet' else self.hello
        transcript=json.dumps([tablet,companion],sort_keys=True,separators=(',',':')).encode()
        salt=hashlib.sha256(transcript).digest()
        t2c=hkdf(salt,self.key,b'lemma-protected/1 tablet-to-companion\0'+salt)
        c2t=hkdf(salt,self.key,b'lemma-protected/1 companion-to-tablet\0'+salt)
        self.send_key,self.receive_key=(t2c,c2t) if self.role=='tablet' else (c2t,t2c)
        self.transcript_sha256=salt.hex()
    def enqueue(self,channel,stream,consent,clock,start,end,payload,archive_granted=False):
        if self.send_key is None:raise Rejected('no authenticated session')
        if channel not in range(4) or stream not in range(32) or len(payload)>4096 or min(consent,clock)<=0 or end<start:raise Rejected('packet format')
        if channel==3 and not archive_granted:raise Rejected('archive grant absent')
        #8per channel, fixed128KiB aggregate payload ceiling. Safety/control
        #queue is independent from bulk; no global camera FIFO blocks it.
        if len(self.queues[channel])==8:raise Rejected('priority channel full')
        self.queues[channel].append((stream,consent,clock,start,end,bytes(payload)))
    def next_packet(self):
        if self.send_key is None:raise Rejected('no authenticated session')
        channel=next((i for i,q in enumerate(self.queues) if q),None)
        if channel is None:return None
        stream,consent,clock,start,end,payload=self.queues[channel][0]
        if self.tx==MAX_SEQUENCE or self.tx_stream[stream]==MAX_SEQUENCE:raise Rejected('sequence exhausted; rekey required')
        self.queues[channel].pop(0);self.tx+=1;self.tx_stream[stream]+=1
        boot,capture,external,revision,durable=self.context
        header=HEADER.pack(1,boot,capture,external,stream,channel,self.tx,self.tx_stream[stream],clock,start,end,consent,len(payload),revision,durable,0)
        nonce=struct.pack('<IQ',1 if self.role=='tablet' else 2,self.tx)
        return header+seal(self.send_key,nonce,header,payload)
    def receive(self,frame,current_consent,archive_granted=False):
        if self.receive_key is None:raise Rejected('no authenticated session')
        if not HEADER.size+16<=len(frame)<=HEADER.size+4112:raise Rejected('frame length')
        fields=HEADER.unpack_from(frame);version,boot,capture,external,stream,channel,seq,stream_seq,clock,start,end,consent,length,revision,durable,reserved=fields
        #Use only bounded counter for nonce before authentication. No header
        #field affects grants, queues or acknowledgements until authentication.
        nonce=struct.pack('<IQ',2 if self.role=='tablet' else 1,seq)
        plaintext=open_packet(self.receive_key,nonce,frame[:HEADER.size],frame[HEADER.size:])
        if version!=1 or reserved or (boot,capture,external,revision,durable)!=self.context:raise Rejected('authenticated incompatible/stale header')
        if stream not in range(32) or channel not in range(4) or seq!=self.rx+1 or stream_seq!=self.rx_stream[stream]+1 or seq>MAX_SEQUENCE:raise Rejected('replayed/gapped/exhausted sequence')
        #Authenticated transport sequence is consumed even when the current
        #guest grant has revoked the payload. Unrelated streams can continue.
        self.rx=seq;self.rx_stream[stream]=stream_seq
        if consent!=current_consent or consent==0:raise Rejected('revoked queued permission')
        if channel==3 and not archive_granted:raise Rejected('archive permission absent')
        if length!=len(plaintext) or not clock or end<start:raise Rejected('authenticated malformed payload')
        self.rx=seq;self.rx_stream[stream]=stream_seq
        return {'stream':stream,'channel':channel,'payload':plaintext,'capture':[start,end],'source_clock':clock,
            'acknowledgement':'AUTHENTICATED_TRANSPORT_RECEIPT_ONLY','durable_frontier':durable}
    def cancel_queued(self,stream=None):
        if stream is not None and stream not in range(32):raise Rejected('cancel stream')
        cancelled=0
        for channel in range(4):
            before=len(self.queues[channel])
            self.queues[channel]=[item for item in self.queues[channel] if stream is not None and item[0]!=stream]
            cancelled+=before-len(self.queues[channel])
        return {'cancelled_queued_packets':cancelled,'already_emitted_unchanged':True}
    def receipt(self):
        return {'schema':'lemma-protected-session-receipt/1','role':self.role,'context':self.context,
            'transcript_sha256':getattr(self,'transcript_sha256',None),'development_only':self.development,
            'entropy_boundary':'HOST_OS_SIMULATOR_ONLY','physical_entropy':'UNQUALIFIED','production_security':'UNVERIFIED',
            'tx':self.tx,'rx':self.rx,'queued_by_priority':[len(q) for q in self.queues]}
