#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Literal Power-v2/QEMU reset/clock/RAM boundaries. No guest CPU claim."""
import argparse,hashlib,json,sys,time
from pathlib import Path
from check_power_controller import Probe,POWER,PEN,HARDWARE,digest

def require(v,message):
 if not v:raise ValueError(message)
def main():
 p=argparse.ArgumentParser();p.add_argument('--qemu',type=Path,required=True);p.add_argument('--dtb',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.mkdir();start=time.monotonic();medium=out/'medium.raw'
 with medium.open('xb') as f:f.truncate(256*1024*1024)
 r={'status':'FAIL','scope':__doc__,'qemu_sha256':digest(a.qemu),'dtb_sha256':digest(a.dtb),'observer_sha256':digest(__file__)};m=fork=None
 def settled():
  for _ in range(200):
   s=m.state()
   if not s['system_reset_pending']:return s
   time.sleep(.001)
  raise TimeoutError('internal reset request did not settle within declared200ms observer bound')
 try:
  m=Probe(a.qemu,a.dtb,out,medium);r['argv']=m.argv
  require(m.read(POWER+8)==2,'wrong version')
  m.step(80);require(not settled()['domain_reset'],'cold reset qualification differs')
  # Pinned virt constructs ACLINT only under TCG. Qtest has no MTIMER:
  # actual guest qualification, rather than an unmapped zero, checks its phase.
  tree=m.qmp.execute('human-monitor-command',{'command-line':'info mtree'})
  require('aclint-mtimer' not in tree,'qtest timer scope changed; update explicit fixture')
  r['timer_scope']='qtest has no ACLINT; real TCG guest separately checks MTIME phase'
  r['memory_tree']=tree
  m.write(0x80480000,0x1122334455667788)
  m.write(POWER+96,8);require(m.state()['write_pending'],'MMIO publication skipped next clock edge')
  m.step(10);m.write(POWER+104,1);m.step(10)
  armed=m.state();require(armed['watchdog_remaining']==8 and armed['watchdog_armed'],'watchdog arm differs')
  m.step(70);require(m.state()['watchdog_remaining']==1,'watchdog expired early')
  m.write(POWER+104,2);m.step(10);require(m.state()['watchdog_remaining']==8,'valid terminal heartbeat did not win')
  m.step(80);expiry=settled();require(expiry['reset_cause']==4 and expiry['reset_remaining']==8 and expiry['domain_reset'],'watchdog reset differs')
  require(m.read(0x80480000)==0x1122334455667788,'watchdog lost retained RAM')
  m.step(70);held=settled();require(held['reset_remaining']==1 and held['domain_reset'],'reset hold too short')
  # A held domain with no pending host reset is serializable, retaining its
  # clock/timer/raw inputs. This assertion does not close the QEMU cache hole.
  m.qmp.execute('stop');checkpoint=out/'held.chk';m.save(checkpoint)
  before=m.state();checkpoint_ns=m.now();m.qmp.execute('cont');m.step(10);end=settled()
  require(not end['domain_reset'] and end['reset_epoch']==1,'reset hold too long')
  forkdir=out/'fork';forkdir.mkdir();private=forkdir/'medium.raw'
  with private.open('xb') as f:f.truncate(256*1024*1024)
  fork=Probe(a.qemu,a.dtb,forkdir,private);fork.step(checkpoint_ns);fork.qmp.execute('stop')
  fork.qmp.execute('lemma-load-machine',{'filename':str(checkpoint)})
  require(fork.state()==before,'held-domain scalar state changed on restore')
  fork.qmp.execute('cont');fork.step(10)
  require(fork.state()==end,'held-domain accepted next edge changed on restore')
  require(fork.read(0x80480000)==0x1122334455667788,'held-domain restored RAM differs')
  r['held_suffix']={'before':before,'after':end,'snapshot_bytes':checkpoint.stat().st_size}
  # Brownout wins simultaneous power-good loss and timeout; actual RAM is
  # erased, pending raw pen is discarded, future raw supply/wake retained.
  now=m.now();m.inject('external-supply',f'{now+10} 2 0');m.inject('external-supply',f'{now+10} 3 1')
  m.inject('external-button',f'{now+30} 1');m.step(10);loss=settled()
  require(loss['reset_cause']==5 and loss['reset_epoch']==2,'supply precedence differs')
  require(m.read(0x80480000)==0,'supply loss did not erase actual RAM')
  m.step(20);require(settled()['button_level']==1,'future raw button lost on reset')
  m.step(100);require(settled()['reset_epoch']==2 and settled()['reset_remaining']==8,'held unsafe repeated loss')
  now=m.now();m.inject('external-supply',f'{now+10} 3 0');m.step(10)
  require(settled()['reset_cause']==6 and settled()['reset_epoch']==2,'unsafe cause changed epoch')
  now=m.now();m.inject('external-supply',f'{now+10} 2 1');m.step(10)
  require(settled()['reset_remaining']==7,'first safe edge not counted')
  m.step(60);require(settled()['reset_remaining']==1,'safe qualification too short')
  m.step(10);require(not settled()['domain_reset'],'safe qualification too long')
  require(m.devices()['pen']['resync'],'pen requires explicit postreset resynchronization')
  r['supply_loss']=loss;r['final']=settled();r['status']='PASS'
 except BaseException as e:r['error']=str(e);raise
 finally:
  for obj in (fork,m):
   if obj:
    (obj.directory/'wire.json').write_text(json.dumps(obj.wire,indent=2)+'\n');obj.close()
  r['host_seconds']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({'status':r['status'],'host_seconds':r['host_seconds']}))
if __name__=='__main__':main()
