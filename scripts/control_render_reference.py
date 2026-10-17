from pathlib import Path
import sys,json,argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));from lemmasim_readonly import FONT_ROWS
p=argparse.ArgumentParser(description='Independent scalar test-only course-control pixels; no machine adapter')
p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();base=a.output_dir.resolve()
if base.exists() or not base.is_relative_to(ROOT/'build'):p.error('unused ignored output required')
base.mkdir(parents=True)
cases=[(1650,2200,0x123456789abc,0xfedcba987654,0x307,0x0123456789abcdef,2|(3<<8)|(99<<16)),(1651,1000,0xffffffffffff,0,0xb10,0xffffffffffffffff,0),(1663,900,0,0x10001,1,0x8000000000000000,1|(1<<8)|(8<<16)),(416,760,0x10001,0x20003,0x101,1,1|(255<<8)|(255<<16))]
for number,(w,h,requested,shown,pos,revision,ctx)in enumerate(cases):
 lines=[list(s)for s in ['NODE+   ROLE+   PAGE+   USE     ','IDENT+  EDIT+   LOAD    RESET   ','SOURCE  EDITION RIGHTS  TITLE   ','REQ I0000 E00000000 N00 R00     ','READ I0000 E00000000            ','REV 0000000000000000 D0 A0 B00  ']]
 # First authored row uses32 cells. Trailing spaces are all white.
 lines[0]+= [' ']*(32-len(lines[0]));assert all(len(row)==32 for row in lines)
 for row,start,value,digits in [(3,5,requested&65535,4),(3,11,requested>>16,8),(4,6,shown&65535,4),(4,12,shown>>16,8),(5,4,revision,16)]:lines[row][start:start+digits]=f'{value:0{digits}X}'[-digits:]
 for row,a,b,value in [(3,21,22,pos&255),(3,25,26,pos>>8),(5,28,29,(ctx>>16)&255)]:lines[row][a]=chr(48+value//10);lines[row][b]=chr(48+value%10)
 lines[5][22]=chr(48+(ctx&255));lines[5][25]=chr(48+((ctx>>8)&255))
 stride=(w+1)//2;image=bytearray([0xa5])*(stride*h)
 for y in range(120):
  line=lines[y//20]
  for x in range(384):
   ch=line[x//12];bits=('0'*15 if ch==' ' else FONT_ROWS.get(ch,FONT_ROWS['O']));v=0 if x%12<9 and y%20<15 and bits[(y%20//3)*3+x%12//3]=='1'else 15;addr=(640+y)*stride+(24+x)//2
   if (24+x)%2==0:image[addr]=(image[addr]&15)|(v<<4)
   else:image[addr]=(image[addr]&240)|v
 (base/f'case{number}.expected').write_bytes(image)
(base/'cases.json').write_text(json.dumps(cases)+'\n');print('independent authored scalar-reference fixtures',len(cases))
