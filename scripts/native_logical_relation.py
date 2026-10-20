import hashlib,struct
VERSION='lemma-native-logical-observation-relation/2'
def compare_machine(left,right):
 marker=b'\x05timer\x00\x00\x00\x00\x00\x00\x00\x02';assert left.count(marker)==right.count(marker)==1
 at=left.index(marker)+len(marker);assert right.index(marker)+len(marker)==at
 assert len(left)==len(right) and left[:at]==right[:at] and left[at+24:]==right[at+24:]
 assert left[at+8:at+16]==right[at+8:at+16]==bytes(8)
 assert left[at+24:at+38]==right[at+24:at+38]==b'\x05\x0ctimer/icount'
 mm=b'lemma-paper-pen/1/multimodal-v1';assert left.count(b'\x05'+bytes([len(mm)])+mm+b'\0\0\0\1')==1
 return {'version':VERSION,'raw_equal':left==right,'bytes':len(left),'host_fields':[{'name':name,'offset':offset,'left':struct.unpack_from('>q',left,offset)[0],'right':struct.unpack_from('>q',right,offset)[0]} for name,offset in [('timer.cpu_ticks_offset',at),('timer.cpu_clock_offset',at+16)]],'all_other_bytes_equal':True}
def compare_logical(left,right,left_machine,right_machine):
 for data,machine in [(left,left_machine),(right,right_machine)]:
  assert data[:8]==b'LMTLB02\0' and struct.unpack_from('<Q',data,8)[0]==2
  length=struct.unpack_from('<Q',data,16)[0];assert data[24:24+length]==b'lemma-silicon-fast-softtlb/0.2.0'
  assert hashlib.sha256(data[:-32]).digest()==data[-32:] and data[24+length:24+length+32]==hashlib.sha256(machine).digest()
 cut=24+struct.unpack_from('<Q',left,16)[0]
 assert len(left)==len(right) and left[:cut]==right[:cut] and left[cut+32:-32]==right[cut+32:-32]
 return {'version':VERSION,'bytes':len(left),'all_translation_and_witness_payload_equal':True,'file_binding_and_integrity_checked':True}
