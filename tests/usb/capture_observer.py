#!/usr/bin/env python3
"""Sensitivity checks for the offline USB wire observer, using a retained tape.
Changed tape copies are observer fixtures, never claimed as machine executions.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from check_guest_usb_link import decode_capture
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True);a=p.parse_args()
 out=a.work_dir.resolve();out.mkdir(parents=True,exist_ok=False);original=a.capture.resolve();text=original.read_text()
 observed=decode_capture(original);assert observed['wire_version']=='LMUSBRW1'
 v2=text.replace('LMUSBRW1 ','LMUSBRW2 ',1).replace('USBHOST/1 PACKET_BYTES_DEV','USBHOST/2 PACKET_BYTES_DEV',1)
 (out/'shape-v2.raw').write_text(v2);new=decode_capture(out/'shape-v2.raw')
 assert new['requests']==observed['requests'] and new['transactions']==observed['transactions']
 mutations={'wrong-v2-handshake':v2.replace('USBHOST/2 PACKET_BYTES_DEV','USBHOST/1 PACKET_BYTES_DEV',1),
   'undeclared-wire-version':v2.replace('LMUSBRW2 ','LMUSBRW3 ',1),
   'bad-runtime-identity':v2.replace(observed['runtime_identity'],'g'*64,1),
   'unrecorded-send-success':v2.replace(' SENT\n',' LOST\n',1)}
 for name,tape in mutations.items():
  assert tape!=v2;f=out/(name+'.raw');f.write_text(tape)
  try:decode_capture(f)
  except ValueError:continue
  raise ValueError('Observer admitted mutation: '+name)
 r={'status':'PASS','scope':__doc__,'retained_capture':{'path':str(original),'sha256':sha(original)},'observer_sha256':sha(ROOT/'scripts/check_guest_usb_link.py'),'fixture_sha256':sha(__file__),'rejected':list(mutations),'shape_v2_is_not_an_execution':True}
 (out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
