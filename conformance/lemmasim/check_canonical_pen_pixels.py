"""Independent offline full-pixel oracle for a bounded canonical raw stroke.

This never enters a guest or supplies pixels to a controller. Signed Python
integer vectors implement the published integer distance/pressure domain;
production code uses unsigned magnitudes. Both writing-area quantizations are
load-bearing, so a raw screen pixel alone is not the rendered endpoint.
"""
from notebook_pixels import empty_pixels

Q = 1 << 24


def endpoint(sample, width, height):
    raw_x, raw_y = sample[2:4]
    x = (raw_x * Q // 65535) * (width-1) // Q
    screen_y = (raw_y * Q // 65535) * (height-1) // Q
    page_y = max(0, screen_y-160) * Q // (height-161)
    writing_y = 160 + page_y * (height-161) // Q
    normalized_y = (writing_y*Q + height-2) // (height-1)
    return x, normalized_y*(height-1)//Q


def coverage(point, first, last, p0, p1, nominal=512, maximum=4095):
    dx, dy = last[0]-first[0], last[1]-first[1]
    px, py = point[0]-first[0], point[1]-first[1]
    length = dx*dx+dy*dy
    projection = max(0, min(length, dx*px+dy*py))
    # The specified unsigned interpolation floors the magnitude, including
    # decreasing pressure; Python signed // would round that case differently.
    pressure = p0 if not length else (p0 + (p1-p0)*projection//length if p1>=p0
        else p0-(p0-p1)*projection//length)
    radius = (nominal*(maximum+3*pressure)//(4*maximum))//2
    if not length or projection == 0:
        return px*px+py*py <= radius*radius//65536
    if projection == length:
        qx, qy = point[0]-last[0], point[1]-last[1]
        return qx*qx+qy*qy <= radius*radius//65536
    return (dx*py-dy*px)**2 <= radius*radius*length//65536


def expected_stroke(samples, width=1650, height=2200):
    if len(samples) != 3 or any(len(s)!=9 or any(type(v) is not int or not 0<=v<1<<64 for v in s) for s in samples):
        raise ValueError('oracle requires three complete unsigned raw samples')
    if [s[5] for s in samples] != [3,3,2] or any(s[6:8] != (1,0) and s[6:8] != [1,0] for s in samples):
        raise ValueError('oracle scope is two contact samples and their pen-up')
    if (samples[2][2:4] != samples[1][2:4] or samples[2][4]!=0
        or not all(0<=s[4]<=4095 and all(0<=v<=65535 for v in s[2:4]) for s in samples)
        or any(samples[i+1][0]!=samples[i][0]+1 or samples[i+1][1]<=samples[i][1] or samples[i+1][8]!=samples[i][8] for i in range(2))):
        raise ValueError('raw stroke coordinates/pressure outside declared fixture')
    if (width,height)!=(1650,2200):
        raise ValueError('this comparison requires the actual canonical capacity')
    first,last=endpoint(samples[0],width,height),endpoint(samples[1],width,height)
    expected=bytearray(empty_pixels(width,height))
    points=[]
    for y in range(max(160,min(first[1],last[1])-2),min(height,max(first[1],last[1])+3)):
        for x in range(max(0,min(first[0],last[0])-2),min(width,max(first[0],last[0])+3)):
            if coverage((x,y),first,first,samples[0][4],samples[0][4]) or coverage(
                    (x,y),first,last,samples[0][4],samples[1][4]):
                offset=(y*width+x)*3
                expected[offset:offset+3]=bytes(3);points.append([x,y])
    return bytes(expected),points
