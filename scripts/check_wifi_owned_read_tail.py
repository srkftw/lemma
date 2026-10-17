#!/usr/bin/env python3
"""Qualify the source-bound remaining56-byte Common12 READ tail in private forks.

The original2M failure stays failed. This separate1M/120 phase verifies exact
repeat, final-CRC corruption and real hardware timeout, never a broad3M pass.
"""
import argparse,json,sys,time,re,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_wifi_owned_read import Owner,observe_ram,validate_inputs,validate_resume,write,require,file_sha
parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
for name in ('native-build','target-capture','rom-bundle','peer-prepared','pending-observation','tail-checkpoint','tail-inspect','original-prefix-result','reference-success','work-dir'):
 parser.add_argument('--'+name,type=Path,required=True)
args=parser.parse_args();root=Path(__file__).resolve().parents[1];out=args.work_dir.resolve()
if not out.is_relative_to(root/'build/silicon') or out.exists():parser.error('unused build/silicon subdirectory required')
out.mkdir();__import__('shutil').copyfile(__file__,out/'runner.py');started=time.monotonic();result={'status':'FAIL','scope':'threeprospective1M/120tailforks fromretained14M; exactrepeat,corruptfinalCRC,withheldremaining; original2MFAILunchanged'}
owners=[]
try:
 binary,identity,target,rom,peer,helper=validate_inputs(args.native_build.resolve(),args.target_capture.resolve(),args.rom_bundle.resolve(),args.peer_prepared.resolve(),out)
 initial=validate_resume(args.pending_observation.resolve(),target,rom,identity)
 parent=args.tail_checkpoint.resolve();original=file_sha(parent);ram,uart=observe_ram(parent,identity);prefixstate=json.load(open(args.tail_inspect.resolve()));reply=bytes.fromhex(initial['reply_hex']);payload=bytes((i*29+7)%256 for i in range(512))
 require(json.loads(args.original_prefix_result.read_text())['status']=='FAIL','original strict prefix is not preserved FAIL')
 original_plan=json.loads((parent.parent/'plan.json').read_text())
 require(original_plan['start']==initial['cycle'] and original_plan['delta']==2000000 and original_plan['end']==14282160,'tail is not the exact original2M boundary')
 require(prefixstate['cycle']==14282160 and ram['context'][1:4]==[2,72,528] and ram['context'][6:8]==[0,0] and ram['context_record'][0:3]==[1,4,1] and ram['owned']==2 and ram['terminal']==0,'notretained528byteboundary')
 require(bytes.fromhex(ram['reply_hex'])[:528]==reply[:528] and prefixstate['wifi']['chip']['rx_packets']==prefixstate['wifi']['peer']['tx_packets']==33,'prefix differs')
 write(out/'plan.json',{'schema':'lemma-owned-read-tail-variants/1','parent_checkpoint':str(parent),'parent_sha256':original,'start':14282160,'end':15282160,'delta_perfork':1000000,'host_seconds_perfork':120,'modes':['exact-repeat','corrupt-final-crc','withheld-remaining'],'source_work_bounds':{'remaining_fragments':[16,16,16,8],'crc_words':72,'crc_byte_steps':576,'crc_bit_steps':4608,'result_copy_words':64,'loss':'realRTL RXwatchdog8192/controllerfault; nohostfaultfabrication'},'original2Mstatus':'FAIL','original_result_sha256':file_sha(args.original_prefix_result.resolve()),'observer_sha256':file_sha(out/'runner.py'),'no_prefix_reinjection':True,'no_state_mask':True,'no_cancel_or_reclaim_claim':'Block API has no qualified cancel/reclaim; failures must retain owned/pinned quarantine','scope':result['scope']})
 runs={}
 for mode in ('exact-repeat','corrupt-final-crc','withheld-remaining'):
  owner=Owner(binary,out/mode,cut=parent,bound=120);owners.append(owner);state=owner.call('inspect');require(state['cycle']==14282160 and state['isolated_medium'] is True,'notprivateexactfork')
  data=bytearray(reply)
  if mode=='corrupt-final-crc':data[-1]^=1
  cursor=528;packets=[];inflight=False
  try:
   while state['cycle']<15282160:
    chip=state['wifi']['chip'];external=state['wifi']['peer'];require(not state['finished'],'guestterminated')
    if mode!='withheld-remaining':require(not chip['fault'] and not external['fault'],'unexpectedradiofault')
    if inflight and not external['tx_active'] and external['tx_packets']==33+len(packets):inflight=False
    if mode!='withheld-remaining' and chip['rx_active'] and chip['rx_packets']==33+len(packets) and not chip['head_valid'] and not inflight and cursor<len(data):
     n=min(16,len(data)-cursor);part=data[cursor:cursor+n];owner.pio(state['cycle'],[(24,n),(32,127),*[(256+i*8,b) for i,b in enumerate(part)],(56,1)])
     packets.append({'offset':cursor,'length':n,'cycle':state['cycle'],'bytes':part.hex()});cursor+=n;inflight=True
    terminal=bool(re.search(b'K1 000000000000049[6f] ',(owner.directory/'uart.bin').read_bytes()))
    state=owner.call('run '+str(15282160-state['cycle'] if terminal else min(128,15282160-state['cycle'])))
   final=owner.snapshot('complete-final');r,full_uart=observe_ram(final,identity);write(owner.directory/'final-ram.json',r);write(owner.directory/'final-inspect.json',state);write(owner.directory/'response-fragments.json',packets);(owner.directory/'authoritative-uart.bin').write_bytes(full_uart)
   if mode=='exact-repeat':
    require(cursor==584 and r['terminal']==1 and r['owned']==0 and r['all_owner_pin_zero'] and bytes.fromhex(r['result_hex'])==payload,'validrepeat failed')
    prior=json.load(open(args.reference_success.resolve()));require(prior['status']=='PASS_GENUINE_OWNED_READ_TAIL' and file_sha(Path(prior['full_checkpoint']))==prior['full_checkpoint_sha256'] and file_sha(final)==prior['full_checkpoint_sha256'] and final.stat().st_size==prior['full_checkpoint_bytes'],'unmasked entire checkpoint repeat differs')
    require(full_uart==(args.reference_success.resolve().parent/'authoritative-uart.bin').read_bytes(),'complete authoritativeUART differs')
   else:
    require(r['terminal']==2 and r['owned']==2 and r['context_record'][0:3]==[1,4,1] and r['packet_record'][0:3]==[1,4,0] and r['context'][9]==0 and re.search(b'K1 000000000000049f ',full_uart) and not re.search(b'K1 0000000000000494 ',full_uart),'failedreply published or lost ownership')
    if mode=='corrupt-final-crc':require(cursor==584 and r['context'][3]==584 and r['context'][6]==217 and state['wifi']['chip']['fault']==0 and state['wifi']['chip']['rx_packets']==37,'CRCcorruption notguestquarantine')
    else:require(cursor==528 and not packets and r['context'][3]==528 and r['context'][6]==4 and state['wifi']['chip']['fault']==4 and state['wifi']['chip']['events']==4 and state['wifi']['chip']['rx_packets']==33,'withheldreply notrealwatchdog quarantine')
   require(file_sha(parent)==original,'parent mutated')
   runs[mode]={'status':'PASS_OBSERVED_'+mode.upper().replace('-','_'),'end':state['cycle'],'checkpoint':str(final),'checkpoint_sha256':file_sha(final),'checkpoint_bytes':final.stat().st_size,'phase_seconds':time.monotonic()-owner.started,'context':r['context'],'owned':r['owned'],'context_pin':r['context_record'][2],'new_packets':len(packets),'actual_chip_fault':state['wifi']['chip']['fault'],'scope':result['scope']};write(owner.directory/'result.json',runs[mode])
  finally:owner.close()
 result.update(status='PASS_GENUINE_READ_TAIL_EXACT_CRC_LOSS',runs=runs,original2Mstatus='FAIL')
except BaseException as error:result['error']=repr(error);raise
finally:
 for owner in owners:
  if owner.process.poll() is None:owner.close()
 result['wall_seconds']=time.monotonic()-started;write(out/'result.json',result)
print(result['status'],result['wall_seconds'])
