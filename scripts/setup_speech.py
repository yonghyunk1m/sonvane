"""Install local CPU speech output in its own Python 3.12 environment."""
import argparse,hashlib,json,subprocess,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/'

def main():
 p=argparse.ArgumentParser();p.add_argument('--python',default='python3.12');args=p.parse_args()
 env=ROOT/'.models/speech-env';models=ROOT/'.models/speech';models.mkdir(parents=True,exist_ok=True)
 if not env.exists():subprocess.run([args.python,'-m','venv',str(env)],check=True)
 python=env/'bin/python'
 subprocess.run([str(python),'-m','pip','install','kokoro-onnx==0.6.1','soundfile==0.14.0'],check=True)
 files={}
 for name in ['kokoro-v1.0.onnx','voices-v1.0.bin']:
  dest=models/name
  if not dest.exists():
   temp=dest.with_suffix(dest.suffix+'.download');urllib.request.urlretrieve(BASE+name,temp);temp.replace(dest)
  files[name]=hashlib.sha256(dest.read_bytes()).hexdigest()
 (models/'provenance.json').write_text(json.dumps({'model':'hexgrad/Kokoro-82M','model_license':'Apache-2.0','runtime':'kokoro-onnx 0.6.1','runtime_license':'MIT','source':BASE,'sha256':files},indent=2))
 subprocess.run([str(python),'-m','pip','check'],check=True)
 print('Local speech output installed.')

if __name__=='__main__':main()
