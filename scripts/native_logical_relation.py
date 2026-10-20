import hashlib,re,struct
VERSION='lemma-native-logical-observation-relation/2'
MM2_VERSION='lemma-native-MM2-logical-observation-relation/3'
def multimodal_section(data,expected_abi=None):
 candidates=list(re.finditer(rb'\x05(.)lemma-paper-pen/1/multimodal-v([0-9]+)(.{4})',data,re.DOTALL))
 assert len(candidates)==1,'missing, duplicate or mixed multimodal subsection'
 section=candidates[0];length,number,version=section.groups();abi=int(number)
 name=b'lemma-paper-pen/1/multimodal-v'+number
 assert abi in (1,2) and length[0]==len(name) and struct.unpack('>I',version)[0]==abi,'incompatible multimodal subsection ABI/version'
 assert expected_abi is None or abi==expected_abi,'multimodal controller ABI differs'
 return abi,section.end()
def multimodal_payload(data,expected_abi=None):
 """Pure observer of the pinned ABI1/ABI2 subsection, never an admission parser.

 Field order is the complete maintained lemma_multimodal_checkpoint.inc.c
 schema. Full VMState comparison below still checks every serialized byte.
 """
 abi,at=multimodal_section(data,expected_abi)
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
 if abi==2:
  model['controller_abi']=2
  names='base capacity producer fetch end eof enabled status owner_epoch owner_consent owner_config submitted_base consumed_base gaps bus_kind bus_addr bus_data bus_samples bus_cancel turn'.split()
  model['ring']=dict(zip(names,words(20)))
 model['timer_expires_ns']=struct.unpack_from('>q',data,at)[0]
 return model
def compare_machine(left,right):
 marker=b'\x05timer\x00\x00\x00\x00\x00\x00\x00\x02';assert left.count(marker)==right.count(marker)==1
 at=left.index(marker)+len(marker);assert right.index(marker)+len(marker)==at
 assert len(left)==len(right) and left[:at]==right[:at] and left[at+24:]==right[at+24:]
 assert left[at+8:at+16]==right[at+8:at+16]==bytes(8)
 assert left[at+24:at+38]==right[at+24:at+38]==b'\x05\x0ctimer/icount'
 abi,_=multimodal_section(left)
 multimodal_payload(left,abi);multimodal_payload(right,abi)
 return {'version':MM2_VERSION if abi==2 else VERSION,'raw_equal':left==right,'bytes':len(left),'host_fields':[{'name':name,'offset':offset,'left':struct.unpack_from('>q',left,offset)[0],'right':struct.unpack_from('>q',right,offset)[0]} for name,offset in [('timer.cpu_ticks_offset',at),('timer.cpu_clock_offset',at+16)]],'all_other_bytes_equal':True}
def compare_logical(left,right,left_machine,right_machine):
 for data,machine in [(left,left_machine),(right,right_machine)]:
  assert data[:8]==b'LMTLB02\0' and struct.unpack_from('<Q',data,8)[0]==2
  length=struct.unpack_from('<Q',data,16)[0];assert data[24:24+length]==b'lemma-silicon-fast-softtlb/0.2.0'
  assert hashlib.sha256(data[:-32]).digest()==data[-32:] and data[24+length:24+length+32]==hashlib.sha256(machine).digest()
 cut=24+struct.unpack_from('<Q',left,16)[0]
 assert len(left)==len(right) and left[:cut]==right[:cut] and left[cut+32:-32]==right[cut+32:-32]
 abi,_=multimodal_section(left_machine)
 multimodal_payload(left_machine,abi);multimodal_payload(right_machine,abi)
 return {'version':MM2_VERSION if abi==2 else VERSION,'bytes':len(left),'all_translation_and_witness_payload_equal':True,'file_binding_and_integrity_checked':True}
