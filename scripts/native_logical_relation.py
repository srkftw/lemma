import hashlib,struct
VERSION='lemma-native-logical-observation-relation/2'
def multimodal_payload(data):
 """Pure observer of the pinned v1 subsection, never an admission parser.

 Field order is the complete maintained lemma_multimodal_checkpoint.inc.c
 schema. Full VMState comparison below still checks every serialized byte.
 """
 name=b'lemma-paper-pen/1/multimodal-v1';marker=b'\x05'+bytes([len(name)])+name+b'\0\0\0\1'
 assert data.count(marker)==1
 at=data.index(marker)+len(marker)
 def words(count):
  nonlocal at
  values=struct.unpack_from('>'+str(count)+'Q',data,at);at+=count*8;return values
 model_names='tick mask inhibit link pending pcm_valid pcm_data pcm_position pcm_tick dma_stream dma_index dma_active dma_cancel'.split()
 record_names='data capture available quality sequence epoch config selector'.split()
 stream_names='state error epoch sequence gain period exposure selector consent calibration lease quiet consent_floor config next capture available latched_quality latched_reference dma_addr dma_words dma_status consumed submitted start input reference latched history'.split()
 model=dict(zip(model_names,words(13)));model['dma_record']=dict(zip(record_names,words(8)));model['streams']=[]
 for identifier in range(9):
  stream={'id':identifier,**dict(zip(stream_names,words(29)))}
  stream['fifo']=[dict(zip(record_names,words(8))) for _ in range(16)]
  stream.update(zip(('head','count','converting','source_quality'),words(4)));model['streams'].append(stream)
 model['timer_expires_ns']=struct.unpack_from('>q',data,at)[0]
 return model
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
