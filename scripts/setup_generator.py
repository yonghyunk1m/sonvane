"""Install the pinned local music generator, isolated from the web app.

Requires Python 3.12 and an NVIDIA GPU compatible with CUDA 12.8 wheels.
Downloads several GB into ignored .models/. Does not read API credentials.
"""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_REV = 'ca1e85fe9430179831e6bc6be790c332190a3866'
MODEL_REV = '19671f406d603126926c1b7e2adc169acbcade22'


def run(*args):
    subprocess.run([str(a) for a in args], check=True, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default='python3.12', help='Python 3.12 executable')
    args = parser.parse_args()
    runtime = ROOT / '.models/ace-step-runtime'
    env = ROOT / '.models/generator-env'
    runtime.parent.mkdir(exist_ok=True)
    if not runtime.exists():
        run('git', 'clone', 'https://github.com/ace-step/ACE-Step-1.5.git', runtime)
    # Refuse to change an existing checkout with a different revision or local edits.
    current = subprocess.check_output(['git', '-C', str(runtime), 'rev-parse', 'HEAD'], text=True).strip()
    if current != RUNTIME_REV:
        dirty = subprocess.check_output(['git', '-C', str(runtime), 'status', '--porcelain'], text=True)
        if dirty:
            raise SystemExit('Generator checkout has local edits. Preserve them before changing versions.')
        run('git', '-C', runtime, 'fetch', 'origin', RUNTIME_REV)
        run('git', '-C', runtime, 'checkout', '--detach', RUNTIME_REV)
    if not env.exists():
        run(args.python, '-m', 'venv', env)
    python = env / 'bin/python'
    run(python, '-c', 'import sys; assert sys.version_info[:2] == (3, 12), "Use Python 3.12"')
    run(python, '-m', 'pip', 'install', 'torch==2.10.0', 'torchvision==0.25.0', 'torchaudio==2.10.0', '--index-url', 'https://download.pytorch.org/whl/cu128')
    run(python, '-m', 'pip', 'install', '-r', ROOT/'scripts/generator-requirements.txt')
    checkpoint = runtime / 'checkpoints'
    run(python, '-c', 'from huggingface_hub import snapshot_download; import sys; snapshot_download(repo_id="ACE-Step/Ace-Step1.5", revision=sys.argv[1], local_dir=sys.argv[2], allow_patterns=["acestep-v15-turbo/*", "vae/*", "Qwen3-Embedding-0.6B/*", "README.md", "config.json", "LICENSE*"])', MODEL_REV, checkpoint)
    (checkpoint/'sonvane-provenance.json').write_text(json.dumps({'repo':'ACE-Step/Ace-Step1.5', 'revision':MODEL_REV, 'runtime_revision':RUNTIME_REV, 'license':'MIT', 'mode':'DiT-only; Muse supplies the caption'}, indent=2))
    run(python, '-m', 'pip', 'check')
    print('Generator installed. Start the web app and open /studio/.')


if __name__ == '__main__':
    main()
