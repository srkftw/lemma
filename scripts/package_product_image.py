#!/usr/bin/env python3
"""Package an audited product ELF and DTB as opaque ROM-installable bytes.

This does not initialize a boot medium or execute update policy. Installation
uses actual UART recovery requests; the Lean ROM validates and publishes them.
"""
import argparse,hashlib,json,struct,zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
IMAGE_MAGIC=0x31474d49414d454c
COMPATIBILITY=0x0007000300010001
SLOT_BYTES=16*1024*1024
CONFIGURATIONS={'lemmasim-silicon-product-notebook','lemmasim-silicon-product-bulk-notebook'}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def pack_elf(elf,dtb,identity):
 if type(identity)!=int or not 0<identity<1<<64:raise ValueError('image ID must be a nonzero UInt64 registry identity')
 if not 40<=len(dtb)<=3072 or dtb[:4]!=b'\xd0\x0d\xfe\xed' or struct.unpack_from('>I',dtb,4)[0]!=len(dtb):raise ValueError('DTB must have its exact bounded FDT length')
 if len(elf)<64 or elf[:7]!=b'\x7fELF\x02\x01\x01':raise ValueError('product ELF must be ELF64 little endian')
 e=struct.unpack_from('<16sHHIQQQIHHHHHH',elf)
 if e[1:4]!=(2,243,1) or e[7]!=0 or e[8]!=64 or e[9]!=56:raise ValueError('product ELF type/ISA/flags differ')
 entry,offset,count=e[4],e[5],e[10]
 if offset>len(elf) or count>(len(elf)-offset)//56:raise ValueError('ELF program header range invalid')
 segments=[]
 for i in range(count):
  kind,flags,start,virtual,physical,files,memory,alignment=struct.unpack_from('<IIQQQQQQ',elf,offset+i*56)
  if kind!=1:continue
  if flags not in (4,5,6) or virtual!=physical or physical%8 or not 0<memory or files>memory or not 0x80000000<=physical<=0x81f00000-memory or start>len(elf)-files or alignment!=4096:raise ValueError('ELF load segment violates product envelope')
  if any(not (physical+memory<=r['destination'] or r['destination']+r['memory_bytes']<=physical) for r in segments):raise ValueError('overlapping ELF load segments')
  segments.append({'destination':physical,'file_bytes':files,'memory_bytes':memory,'bytes':elf[start:start+files]})
 if not 1<=len(segments)<=8 or entry%4 or not 0x80000000<=entry<0x80010000 or not any(r['destination']<=entry and 4<=r['destination']+r['file_bytes']-entry for r in segments):raise ValueError('product entry lacks a valid file-backed segment')
 words=[0]*64;words[:8]=[IMAGE_MAGIC,1,identity,COMPATIBILITY,len(segments),entry,len(dtb),zlib.crc32(dtb)]
 wire=bytearray(4096);wire[512:512+len(dtb)]=dtb
 for i,row in enumerate(segments):
  first=len(wire);raw=row.pop('bytes');row.update(offset=first,crc32=zlib.crc32(raw))
  if len(raw)>SLOT_BYTES-first:raise ValueError('image file payload exceeds boot slot capacity')
  wire.extend(raw);wire.extend(bytes((-len(wire))%512))
  words[8+5*i:13+5*i]=[first,row['file_bytes'],row['memory_bytes'],row['destination'],row['crc32']]
 header=struct.pack('<63Q',*words[:63]);words[63]=zlib.crc32(header)
 wire[:512]=struct.pack('<64Q',*words)
 return bytes(wire),{'entry':entry,'identity':identity,'compatibility':COMPATIBILITY,
  'discovery_bytes':len(dtb),'discovery_crc32':zlib.crc32(dtb),'segments':segments,'sectors':len(wire)//512}
def package(guest,out,identity,source_archive=None):
 if out.exists():raise ValueError('output directory must be unused')
 build=json.loads((guest/'build.json').read_text());audit=json.loads((guest/'audit.json').read_text())
 binding=json.loads((guest/'binding.json').read_text())
 if build.get('status')!='BUILT' or audit.get('status')!='PASS' or build.get('configuration') not in CONFIGURATIONS or audit.get('configuration')!=build['configuration'] or binding.get('profile')!='lemma-silicon-dev/0.7.0':raise ValueError('packaging requires a strictly audited selected product7 guest')
 for name in ('image.elf','platform.dtb'):
  if build.get('artifacts',{}).get(name)!=sha(guest/name):raise ValueError('compiled product artifact identity differs: '+name)
 if audit.get('image_sha256')!=sha(guest/'image.elf'):raise ValueError('product ELF audit identity differs')
 provenance=json.loads((guest/'provenance.json').read_text())
 if build.get('provenance_sha256')!=sha(guest/'provenance.json') or not provenance.get('source_inputs'):
  raise ValueError('Missing exact compiled product source inventory')
 origin=ROOT
 if source_archive is not None:
  source_archive=Path(source_archive).resolve();receipt=json.loads((source_archive.parent/'consumed-source-archive.json').read_text())
  if receipt.get('schema')!='lemma-consumed-guest-source-archive/1' or receipt.get('original_manifest_sha256')!=sha(guest/'provenance.json') or receipt.get('inputs')!=provenance['source_inputs']:
   raise ValueError('Product source archive differs from the complete original provenance')
  origin=source_archive
 for name,digest in provenance['source_inputs'].items():
  p=Path(name)
  if p.is_absolute() or '..' in p.parts or (origin/p).is_symlink() or sha(origin/p)!=digest:
   raise ValueError('Changed or missing compiled product source: '+name)
 wire,layout=pack_elf((guest/'image.elf').read_bytes(),(guest/'platform.dtb').read_bytes(),identity)
 out.mkdir(parents=True);(out/'image.bin').write_bytes(wire)
 receipt={'schema':'lemma-product-image/1','status':'PASS','scope':'opaque compiled image packaging; target installation/boot qualification separate',
  'configuration':build['configuration'],'authentication':'OPEN','anti_rollback':'OPEN','image_sha256':sha(out/'image.bin'),
  'source_validation':{'kind':'explicit-consumed-source-archive' if source_archive else 'current-source','inputs':len(provenance['source_inputs']),
   'archive_manifest_sha256':sha(source_archive.parent/'consumed-source-archive.json') if source_archive else None},
  'inputs':{n:{'path':str((guest/n).resolve()),'sha256':sha(guest/n)} for n in ('image.elf','platform.dtb','build.json','provenance.json','audit.json','binding.json')},**layout}
 (out/'package.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--guest-build',type=Path,required=True);p.add_argument('--source-archive',type=Path);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--image-id',type=lambda x:int(x,0),required=True);a=p.parse_args()
 try:r=package(a.guest_build.resolve(),a.output_dir.resolve(),a.image_id,a.source_archive)
 except (OSError,ValueError,KeyError,struct.error) as e:p.error(str(e))
 print(json.dumps({'status':r['status'],'package':str(a.output_dir/'package.json'),'image':str(a.output_dir/'image.bin')},indent=2))
if __name__=='__main__':main()
