#!/usr/bin/env python3
"""Owner-side opaque image authoring with the PUBLIC DEVELOPMENT KEY00..1f.
This writes a tag file, never a live boot medium, guest RAM or an auth flag.
The Lean ROM independently checks actual loaded bytes before handoff.
"""
import argparse,hashlib,hmac,json,struct,zlib
from pathlib import Path
KEY_ID=0x4445560000000001
DOMAIN=0x31544855414d454c
TAG_MAGIC=0x31474154414d454c
COMPATIBILITY=0x000a000300010001
def tag(image,slot):
 if type(slot)!=int or slot not in (0,1) or not 4096<=len(image)<=16*1024*1024 or len(image)%512:raise ValueError('bounded complete image/slot required')
 w=struct.unpack_from('<64Q',image)
 if w[0]!=0x31474d49414d454c or w[1]!=1 or w[2]==0 or w[3]!=COMPATIBILITY or not 1<=w[4]<=8 or w[63]!=zlib.crc32(image[:504]):raise ValueError('invalid Product10 header')
 if not 40<=w[6]<=3072:raise ValueError('invalid discovery span')
 stream=hmac.new(bytes(range(32)),digestmod=hashlib.sha256);stream.update(struct.pack('<4Q',DOMAIN,1,KEY_ID,slot));stream.update(image[:512]);stream.update(image[512:512+w[6]])
 if zlib.crc32(image[512:512+w[6]])!=w[7]:raise ValueError('discovery checksum differs')
 spans=[]
 for i in range(w[4]):
  offset,files,memory,destination,crc=w[8+i*5:13+i*5]
  if offset%512 or offset<4096 or files>memory or memory==0 or offset>len(image)-files or not 0x80000000<=destination<=0x81f00000-memory or destination%8:raise ValueError('invalid file/RAM span')
  if any(not(destination+memory<=a or a+n<=destination) for a,n in spans):raise ValueError('overlapping image destinations')
  spans.append((destination,memory));data=image[offset:offset+files]
  if zlib.crc32(data)!=crc:raise ValueError('segment checksum differs')
  stream.update(data)
 mac=stream.digest();wire=bytearray(512);struct.pack_into('<6Q',wire,0,TAG_MAGIC,1,slot,w[2],COMPATIBILITY,KEY_ID);wire[48:80]=mac;struct.pack_into('<Q',wire,504,zlib.crc32(wire[:504]));return bytes(wire)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--public-development-key',action='store_true',required=True);p.add_argument('--image',type=Path,required=True);p.add_argument('--slot',type=int,choices=[0,1],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 try:
  data=tag(a.image.read_bytes(),a.slot);a.output.parent.mkdir(parents=True,exist_ok=True)
  with a.output.open('xb') as f:f.write(data)
 except (OSError,ValueError,struct.error) as e:p.error(str(e))
 print(json.dumps({'tag':str(a.output.resolve()),'slot':a.slot,'sha256':hashlib.sha256(data).hexdigest(),'scope':'PUBLIC DEVELOPMENT KEY; authoring only, target validation not implied'},indent=2))
if __name__=='__main__':main()
