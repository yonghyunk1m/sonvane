"""Download public A1 and CLAP weights into ignored .models/, not into Git."""
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1] / '.models'
root.mkdir(exist_ok=True)
files = {
    'A1_clap_audio_only.pt': 'https://huggingface.co/TuneJury/tunejury/resolve/main/A1_clap_audio_only.pt',
    'A1_clap_audio_only.json': 'https://raw.githubusercontent.com/yonghyunk1m/TuneJury/main/checkpoints/input_ablation/A1_clap_audio_only.json',
    'music_audioset_epoch_15_esc_90.14.pt': 'https://huggingface.co/lukewys/laion_clap/resolve/main/music_audioset_epoch_15_esc_90.14.pt',
}
for name, url in files.items():
    target = root / name
    if target.exists():
        print('Present:', name)
        continue
    temporary = root / (name + '.part')
    print('Downloading:', name, flush=True)
    urllib.request.urlretrieve(url, temporary)
    temporary.replace(target)
    print('Ready:', name, target.stat().st_size, 'bytes', flush=True)
