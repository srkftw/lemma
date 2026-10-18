"""Companion speech codecs. PCM is data for the guest, never host playback.
Recognition is an inspectable proposal distinct from the original raw waveform.
"""
import hashlib,io,json,shutil,struct,subprocess,wave
from pathlib import Path

def synthesize(text,executable=None,rate=48000):
    executable=Path(executable) if executable else Path(shutil.which('espeak-ng') or '/nonexistent/espeak-ng')
    if not executable.is_file():raise ValueError('espeak-ng unavailable; pass --espeak with an admitted executable')
    if rate not in (16000,22050,48000) or not text or len(text)>2048:raise ValueError('speech format/range')
    result=subprocess.run([str(executable),'--stdout','-v','en-us','-s','155',text],capture_output=True,timeout=30,check=True)
    with wave.open(io.BytesIO(result.stdout),'rb') as w:
        if w.getnchannels()!=1 or w.getsampwidth()!=2:raise ValueError('unexpected synthesizer PCM')
        source_rate=w.getframerate();source=w.readframes(w.getnframes())
    samples=struct.unpack('<'+'h'*(len(source)//2),source)
    output=[]
    for i in range(len(samples)*rate//source_rate):
        index,frac=divmod(i*source_rate,rate)
        output.append((samples[index]*(rate-frac)+samples[min(index+1,len(samples)-1)]*frac)//rate)
    pcm=struct.pack('<'+'h'*len(output),*output)
    version=subprocess.check_output([str(executable),'--version'],text=True).splitlines()[0]
    return pcm,{'schema':'lemma-companion-pcm/1','origin':'SYNTHETIC','format':'S16_LE','channels':1,
        'rate':rate,'frames':len(output),'sha256':hashlib.sha256(pcm).hexdigest(),'synthesizer':version,
        'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
        'transformation':{'name':'linear-rational-resampling/1','source_rate':source_rate,'target_rate':rate},
        'delivery':'GENERATED_ONLY_NO_HOST_PLAYBACK','physical_audibility':'UNVERIFIED'}

def recognize(wav_path,executable,model_directory,grammar=None):
    """Real open PocketSphinx file adapter; no canned transcript fallback.
    The host ingress must retain original capture clock/consent outside this
    routine. Resampling is explicit: caller supplies16kHz monoS16 WAV.
    """
    path=Path(wav_path);model=Path(model_directory);executable=Path(executable)
    with wave.open(str(path),'rb') as w:
        if (w.getnchannels(),w.getsampwidth(),w.getframerate())!=(1,2,16000):raise ValueError('ASR requires declared 16kHz monoS16 transformation')
    required=[model/'en-us',model/'en-us.lm.bin',model/'cmudict-en-us.dict']
    if not executable.is_file() or not all(p.exists() for p in required):raise ValueError('open ASR executable/model unavailable')
    command=[str(executable),'-hmm',str(required[0]),'-lm',str(required[1]),'-dict',str(required[2]),'single',str(path)]
    if grammar is not None:
        command=command[:3]+command[5:-2]+['-jsgf',str(Path(grammar))]+command[-2:]
    result=subprocess.run(command,capture_output=True,text=True,timeout=120,check=True)
    events=[json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if not events or any(not isinstance(e,dict) or not isinstance(e.get('t'),str) for e in events):raise ValueError('ASR output schema')
    text=' '.join(event['t'] for event in events)
    if not text or len(text)>4096:raise ValueError('ASR empty/malformed transcript')
    identities={str(p.relative_to(model)):hashlib.sha256(p.read_bytes()).hexdigest() for p in model.rglob('*') if p.is_file()}
    return {'schema':'lemma-recognition-proposal/1','raw_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'text':text,'recognition_events':events,'corrections':[],'authority':'NONE_PROPOSAL_REQUIRES_STUDENT_CONFIRMATION',
        'adapter':'pocketsphinx-file/1','executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),'model_files':identities,'command':command,
        'grammar_sha256':None if grammar is None else hashlib.sha256(Path(grammar).read_bytes()).hexdigest(),
        'grammar_scope':'unrestricted-language-model' if grammar is None else 'bounded-mathematics-question-vocabulary/1',
        'accuracy':'UNQUALIFIED'}


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=['synthesize','recognize'])
    p.add_argument('--text');p.add_argument('--input',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--executable',type=Path,required=True);p.add_argument('--model-directory',type=Path)
    p.add_argument('--grammar',type=Path);p.add_argument('--rate',type=int,default=16000)
    a=p.parse_args()
    if a.operation=='synthesize':
        if not a.text or not a.output or a.output.exists():p.error('text and unused output WAV required')
        pcm,receipt=synthesize(a.text,a.executable,a.rate)
        with wave.open(str(a.output),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(a.rate);w.writeframes(pcm)
        receipt['wav_sha256']=hashlib.sha256(a.output.read_bytes()).hexdigest()
    else:
        if not a.input or not a.model_directory:p.error('input WAV and explicit model directory required')
        receipt=recognize(a.input,a.executable,a.model_directory,a.grammar)
    print(json.dumps(receipt,sort_keys=True))
if __name__=='__main__':main()
