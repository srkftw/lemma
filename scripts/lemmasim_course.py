#!/usr/bin/env python3
"""Raw local-owner course commands for the actual guest installer.

The adapter copies a package artifact and the fixed command frame into modeled
UART input. It does not install a Store object, inspect a journal, recover a
document, check mathematics or acknowledge persistence. Guest outcomes appear
in the session UART. A command admission is not an Installed receipt.
"""
from __future__ import annotations
import hashlib,json,struct
from pathlib import Path
from lemmasim_session import request,bounded
from course_deployment import CONFIGURATIONS as LEGACY_CONFIGURATIONS
from course_await_deployment import CONFIGURATIONS as AWAIT_CONFIGURATIONS
from package_closure_deployment import CONFIGURATIONS as PACKAGE_CONFIGURATIONS
from package_companion_deployment import ALL_CONFIGURATIONS as USB_PACKAGE_CONFIGURATIONS
CANONICAL_CONFIGURATIONS=LEGACY_CONFIGURATIONS+AWAIT_CONFIGURATIONS+PACKAGE_CONFIGURATIONS
CONFIGURATIONS=CANONICAL_CONFIGURATIONS+USB_PACKAGE_CONFIGURATIONS
MAGIC=0x31504b43414d454c

def frame(operation,identity,edition,count,transaction,crc):
    bounded(operation,1,3,'Course operation'); bounded(identity,1,65535,'Package identity')
    bounded(edition,1,0xffffffff,'Package edition'); bounded(crc,0,0xffffffff,'Package CRC32')
    if operation==1:
        bounded(count,128,32768,'Package bytes'); bounded(transaction,1,(1<<63)-1,'Install transaction')
    elif operation==2:
        if count!=0:raise ValueError('Load has no payload')
        bounded(transaction,0,15,'Course node ordinal')
    else:
        if count!=0:raise ValueError('Delete probe has no payload')
        bounded(transaction,1,(1<<63)-1,'Delete transaction')
    return struct.pack('<8Q',MAGIC,1,operation,identity,edition,count,transaction,crc)

def send(args):
    directory=args.session_dir.resolve(); metadata=json.loads((directory/'session.json').read_text())
    if metadata.get('schema')!='lemmasim-live/1' or metadata.get('mode') not in ('developer','laboratory') or metadata.get('backend')!='rtl':
        raise ValueError('Course command requires a canonical RTL Developer/Laboratory session')
    identity=metadata.get('identity',{})
    if identity.get('profile') not in ('lemma-silicon-dev/0.3.0','lemma-silicon-dev/0.13.0'):
        raise ValueError('Course command requires an exact admitted course hardware profile')
    argv=metadata.get('argv',[])
    if argv.count('--image')!=1:raise ValueError('Course session lacks an exact guest image')
    image=Path(argv[argv.index('--image')+1]); build=json.loads((image.parent/'build.json').read_text())
    configuration=build.get('configuration')
    expected_profile=('lemma-silicon-dev/0.13.0' if configuration in USB_PACKAGE_CONFIGURATIONS else
                      'lemma-silicon-dev/0.3.0' if configuration in CANONICAL_CONFIGURATIONS else None)
    if expected_profile is None or identity.get('profile')!=expected_profile or hashlib.sha256(image.read_bytes()).hexdigest()!=identity.get('guest'):
        raise ValueError('Course command requires the exact audited course guest deployment')
    operation={'course-install':1,'course-load':2,'course-delete-probe':3}[args.command]
    payload=b''
    if operation==1:
        path=args.package.resolve()
        if path.stat().st_size>32768:raise ValueError('Package exceeds raw command bound')
        payload=path.read_bytes()
        if len(payload)<128:raise ValueError('Package is shorter than its header')
        # These are untrusted declared fields. The guest checks shape, exact
        # identity/edition, complete CRC and immutable publication authority.
        identity,edition=struct.unpack_from('<2Q',payload,24)
        crc=struct.unpack_from('<Q',payload,80)[0]; transaction=args.transaction
    else:
        identity,edition,crc=args.identity,args.edition,args.crc
        transaction=args.node if operation==2 else args.transaction
    packet=frame(operation,identity,edition,len(payload),transaction,crc)+payload
    chunks=[]
    for offset in range(0,len(packet),4096):
        value={'action':'inject','kind':'uart','hex':packet[offset:offset+4096].hex()}
        if args.cycle is not None:value['cycle']=args.cycle
        result=request(directory,value,timeout=120)
        chunks.append({'offset':offset,'bytes':min(4096,len(packet)-offset),'boundary':result})
    return {'status':'RAW_COMMAND_ADMITTED','operation':operation,'identity':identity,'edition':edition,
            'bytes':len(payload),'expected_crc32':crc,'transaction_or_node':transaction,'chunks':chunks,
            'receipt':'No persistence receipt from adapter; read actual guest K1/4b1 outcome in session UART'}
