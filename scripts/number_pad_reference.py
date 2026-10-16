"""Independent passive/test-only number pad1 pixels. Never supplies machine pixels."""
from pathlib import Path
import argparse
from lemmasim_readonly import FONT_ROWS

def reference(width,height=760,limited=False):
    lines=[list(' '*32) for _ in range(10)]
    header='LIMIT 99' if limited else 'TYPE0-99'
    lines[0][:8]=header
    for row,values in ((2,'123'),(4,'456'),(6,'789')):
        for column,value in zip((4,15,26),values):lines[row][column]=value
    lines[8][3:6]='CLR';lines[8][15]='0';lines[8][24:28]='BACK'
    stride=(width+1)//2;image=bytearray([0xa5])*(stride*height)
    for y in range(200):
        for x in range(384):
            ch=lines[y//20][x//12]
            bits='0'*15 if ch==' ' else FONT_ROWS.get(ch,FONT_ROWS['O'])
            black=x%12<9 and y%20<15 and bits[(y%20//3)*3+x%12//3]=='1'
            value=0 if black else 15
            addr=(160+y)*stride+(448+x)//2
            if x%2:image[addr]=(image[addr]&240)|value
            else:image[addr]=(image[addr]&15)|(value<<4)
    return bytes(image)

def pad_matches(path,limited):
    from check_notebook_workflow import visible_pixels
    width,height,rgb=visible_pixels(Path(path))
    if width!=1650 or height!=2200:return False
    expected=reference(width,760,limited);stride=(width+1)//2
    for y in range(160,360):
        packed=expected[y*stride+224:y*stride+416]
        gray=bytes(v for b in packed for v in ((b>>4)*17,(b&15)*17))
        row=b''.join(bytes((v,v,v))for v in gray)
        if rgb[(y*width+448)*3:(y*width+832)*3]!=row:return False
    return True

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();base=a.output_dir.resolve();root=Path(__file__).resolve().parents[1]
    if base.exists()or not base.is_relative_to(root/'build'):p.error('unused ignored output required')
    base.mkdir(parents=True)
    for number,width in enumerate((1650,1651,832)):
        (base/f'case{number}.expected').write_bytes(reference(width,limited=number==1))
    print('NUMBER_PAD_SCALAR_REFERENCE:3 authored geometries')
if __name__=='__main__':main()
