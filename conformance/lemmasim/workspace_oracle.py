"""Independent passive course-workspace and envelope2 byte observer.

Only reports exported bytes. Never supplies a document, guest result, recovery
choice or persistence receipt. The package and Doc8 observers stay independent
of the maintained guest codecs and checking services.
"""
import struct,hashlib
from course_package import decode
from math_oracle import inspect as inspect_math
RAW_MAGIC=0x3153574b504d454c
PACKED_MAGIC=0x3243574b504d454c

def decode_envelope(payload):
 if len(payload)<32:raise ValueError('short workspace header')
 magic,version,raw_bytes,stored_bytes=struct.unpack_from('<4Q',payload)
 if magic==RAW_MAGIC:
  if len(payload)!=3712:raise ValueError('raw workspace exact size')
  return payload,1
 if (magic,version,raw_bytes)!=(PACKED_MAGIC,2,3712):raise ValueError('workspace envelope magic/version/raw size')
 if stored_bytes!=len(payload) or not 96<=len(payload)<=3808 or len(payload)%8:raise ValueError('workspace envelope exact size')
 bits=int.from_bytes(payload[32:96],'little')
 if bits>>464 or bits.bit_count()!=(len(payload)-96)//8:raise ValueError('workspace envelope bitmap bound/population')
 result=bytearray(3712);cursor=96
 for i in range(464):
  if bits&(1<<i):
   word=payload[cursor:cursor+8]
   if word==bytes(8):raise ValueError('workspace envelope noncanonical zero')
   result[i*8:i*8+8]=word;cursor+=8
 if cursor!=len(payload):raise ValueError('workspace envelope suffix')
 return bytes(result),2


def observe_raw(payload,namespace,object_id,packages):
 def require(condition,message):
  if not condition:raise ValueError(message)
 require(len(payload)==3712,'exactactualWorkspace3712required')
 words=struct.unpack('<464Q',payload);magic,version,length,ns,page,inner,mask,reserved=words[:8]
 require((magic,version,length,ns,inner,reserved)==(0x3153574b504d454c,1,3712,namespace,2496,0) and 1<=page<=64 and object_id==0x504b000000000000|page and 0<=mask<512,'actualWorkspaceheader/namespace/object/mask differs')
 document=inspect_math(payload[64:2560],namespace,0x8000+page)
 require(document['format']=='lemma-mathematical-submission/8','actualWorkspaceinnerDoc8required')
 admitted={}
 for raw in packages:
  course=decode(raw);key=(course['identity'],course['edition'],course['crc32'])
  require(key not in admitted,'duplicateindependentpackageidentity')
  admitted[key]=(raw,course)
 def binding(slot,known):
  row=struct.unpack('<16Q',slot)
  if not known:
   require(row==(0,)*16,'Unknown packageprovenance mustremainallzero')
   return {'origin':'Unknown'}
  tag,v,identity,edition,crc,node,anchor,kind,goal,checker,domain,assumptions,budget,source_span,rights_span,revision=row
  require((tag,v)==(0x31444e494253434c,1) and (identity,edition,crc) in admitted,'knownprovenance has noactualimmutablepublisherbytes')
  raw,course=admitted[identity,edition,crc];require(1<=node<=len(course['nodes']),'actualselectednode absent')
  entry=struct.unpack_from('<24Q',raw,128+(node-1)*192)
  header=struct.unpack_from('<16Q',raw)
  require(row[5:13]==(entry[0],entry[8],entry[1],entry[2],entry[3],entry[4],entry[5],entry[9]) and anchor==node and kind==3 and goal in (1,2),'actualbinding node/originalgoal/checker/domain/assumptions/resource differs')
  require((source_span,rights_span)==(header[13],header[15]) and 1<=revision<=0x7fffffffffffffff,'actualsource/rights/revisionanchor differs')
  return {'origin':'InstalledPackage','identity':identity,'edition':edition,'crc32':crc,'node':node,'revision':revision,'goal':goal,'checker':checker,'domain':domain,'assumptions':assumptions,'budget':budget,'source_anchor':course['source_anchor'],'edition_anchor':course['edition_anchor'],'rights_anchor':course['rights_anchor'],'package_sha256':hashlib.sha256(raw).hexdigest(),'node_source_anchor':course['nodes'][node-1]['source_anchor']}
 current=binding(payload[2560:2688],bool(mask&256));histories=[]
 for i in range(8):
  bound=binding(payload[2688+i*128:2816+i*128],bool(mask&(1<<i)))
  if bound['origin']!='Unknown':
   require(i<document['attempts'],'knownunused attempt is notprovenance')
   attempt=document['history'][i]
   require((bound['revision'],bound['goal'],bound['domain'],bound['assumptions'],bound['budget'])==(attempt['revision'],attempt['goal'],attempt['goal'],0,attempt['budget']),'knownbinding notactualimmutableattempt')
  histories.append(bound)
 if current['origin']!='Unknown':require(current['revision']<=document['revision'],'currentselection fromfuture revision')
 applicable=(current['origin']!='Unknown' and (current['revision'],current['goal'],current['domain'],current['assumptions'],current['budget'])==(document['revision'],document['goal'],document['goal'],0,document['budget']))
 return {'format':'lemma-course-workspace/1','namespace':namespace,'page':page,'payload_sha256':hashlib.sha256(payload).hexdigest(),'document':document,'current':current,'applicable_package_selection':applicable,'history':histories,'mask':mask}


def observe(payload,namespace,object_id,packages):
 raw,version=decode_envelope(payload)
 result=observe_raw(raw,namespace,object_id,packages)
 result.update(storage_format='lemma-course-workspace-envelope/2' if version==2 else 'lemma-course-workspace/1',
               encoded_bytes=len(payload),encoded_sha256=hashlib.sha256(payload).hexdigest(),
               decoded_sha256=hashlib.sha256(raw).hexdigest())
 return result
