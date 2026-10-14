"""Separate closed artifact authority for the privileged Common12 READ client.

The original Common295 corpus is unchanged. This opt-in corpus comes from its
own genuine source/tool-bound export. Independent framing/pin/CRC-order checks
complement exact pre/post bodies; neither is a compiler correctness proof.
"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from core0_common import Core0Error
from paper_next import canonical

CONFIGURATION='lemmasim-silicon-wifi-common-read-probe'
FUNCTION_COUNT=327
PREFIX='Lemma.Radio.WiFi.Block.'

def _semantics(ir,rows):
 from audit_kernel import _ir_definition_body,validate_checked_call_gate
 def body(source):
  row=rows.get(source)
  if row is None:raise Core0Error('owned READ semantic owner missing: '+source)
  return _ir_definition_body(ir,row['symbol'])
 def symbol(source):return rows[source]['symbol']
 fragment=body(PREFIX+'fragmentLength')
 if not re.search(r'icmp ult i64 %arg0, %arg1',fragment) or not re.search(r'sub i64 %arg1, %arg0',fragment) or not re.search(r'icmp ult i64 %[-\w.]+, 16',fragment):
  raise Core0Error('owned READ fragment lost exact unsigned16-byte bound')
 shape=body(PREFIX+'replyShape')
 for pattern in (r'icmp eq i64 %arg0, 512',r'icmp eq i64 %arg0, 0',r'icmp ule i64 %arg1, 4095'):
  if not re.search(pattern,shape):raise Core0Error('owned READ success/error shape differs')
 for owner,checked,protected in [
  ('beginRead','Lemma.Kernel.Memory.Frames.pin',PREFIX+'publishRequest'),
  ('send','Lemma.Radio.WiFi.Queue.enqueue','Lemma.Radio.WiFi.Queue.kick'),
  ('finishTX','Lemma.Radio.WiFi.Queue.complete','Lemma.Radio.WiFi.Controller.acknowledge'),
  ('validate','Lemma.Kernel.Memory.Frames.release','Lemma.Kernel.Memory.Frames.unpin')]:
  validate_checked_call_gate(body(PREFIX+owner),symbol(checked),symbol(protected))
 crc=body('Lemma.USB.BlockProtocol.crcStep')
 if '4823603603198064275' not in crc:raise Core0Error('owned READ CRC64 polynomial differs')
 word=body('Lemma.USB.BlockProtocol.crcWord')
 if len(re.findall(r'call i64 @'+re.escape(symbol('Lemma.USB.BlockProtocol.crcByte'))+r'\(',word))!=8:
  raise Core0Error('owned READ CRC word is not eight little-endian byte steps')
 for shift in (8,16,24,32,40,48,56):
  masks=re.findall(r'(%[-\w.]+) = and i64 '+str(shift)+r', 63\b',word)
  if len(masks)!=1 or len(re.findall(r'lshr i64 %arg1, '+re.escape(masks[0])+r'\b',word))!=1:
   raise Core0Error('owned READ CRC byte order differs')
 return {'request_bytes':72,'success_reply_bytes':584,'error_reply_bytes':72,
         'payload_bytes':512,'fragment_max':16,'context_pin':'retained until complete validated result',
         'delivery_is_completion':False,'read_is_durable_commit':False}

def validate(ir,unit,*,optimized):
 from wifi_common import _new,body_normalized,literal_aliases
 rows={canonical(r['source']):r for r in unit.get('functions',[])}
 if unit.get('configuration')!=CONFIGURATION or unit.get('role')!='kernel':
  if any(_new(s) for s in rows):raise Core0Error('owned READ declarations escape exact kernel selection')
  return None
 authority_path=Path(__file__).resolve().parents[1]/'tooling/wifi-owned-read-authority.json'
 if not authority_path.is_file():raise Core0Error('owned READ genuine authority is not yet qualified')
 authority=json.loads(authority_path.read_text())
 wanted=authority.get('functions',{})
 if (authority.get('schema')!='lemma-common-owned-read-authority/1' or
     authority.get('configuration')!=CONFIGURATION or authority.get('contract_version')!='core0-kernel-v0.8' or
     authority.get('function_count')!=FUNCTION_COUNT or len(wanted)!=FUNCTION_COUNT or
     unit.get('contract_version')!='core0-kernel-v0.8' or len(rows)!=len(unit['functions']) or set(rows)!=set(wanted)):
  raise Core0Error('owned READ complete selected Kernel8 corpus differs')
 if any(s.startswith(('Lemma.Boot.Product','Lemma.Platform.LemmaSim.BootHealth','Lemma.Kernel.Process.')) or s.endswith(('.initProduct','.prepareManagedProduct','.configureProduct')) for s in rows):
  raise Core0Error('owned READ acquired NV/User task authority')
 semantic=_semantics(ir,rows) if not optimized else None
 aliases=literal_aliases(ir,unit) if optimized else {}
 names={r['symbol']:s for s,r in rows.items()};observed={}
 for source,want in wanted.items():
  row=rows[source]
  if (row['args'],row['effects'])!=(want['args'],want['effects']):raise Core0Error('owned READ signature/effect differs: '+source)
  digest=hashlib.sha256(body_normalized(ir,row,names,aliases).encode()).hexdigest()
  if digest!=want['post' if optimized else 'pre']:raise Core0Error('owned READ complete checked body differs: '+source)
  observed[source]=digest
 return {'contract_version':'lemma-common-owned-read-artifact-authority/1','configuration':CONFIGURATION,
         'binding':12,'complete_bodies':observed,'phase':'post' if optimized else 'pre',
         'semantics':semantic,'scope':'closed privileged opaque READ512; actual samples/peer/ownership require separate observation'}
