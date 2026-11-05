from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from . import store

MODEL_LABEL = "TuneJury A1 · CLAP audio-only"
MODEL_VERSION = "a1-clap-audio-only:first10s:seed0:v1"
MODELS = store.ROOT / ".models"
SCORER_LOCK = threading.RLock()
_scorer = None


def inspect_audio(path: Path) -> dict:
    info = sf.info(path)
    duration = info.frames / info.samplerate if info.samplerate else 0
    if not 1 <= duration <= 180 or info.channels not in (1, 2):
        raise ValueError("Use mono or stereo audio between 1 and 180 seconds.")
    if info.samplerate > 96000 or info.samplerate < 8000:
        raise ValueError("Use a sample rate between 8 and 96 kHz.")
    wav, sr = sf.read(path, dtype="float32", always_2d=True)
    if not np.isfinite(wav).all():
        raise ValueError("The audio contains invalid samples.")
    mono = wav.mean(axis=1)
    chunks = np.array_split(mono, 120)
    wave = [round(float(np.max(np.abs(x))), 4) if len(x) else 0 for x in chunks]
    rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
    return {"duration": round(duration, 3), "sample_rate": sr, "channels": info.channels,
            "waveform": wave, "rms_dbfs": round(20 * np.log10(max(rms, 1e-8)), 2),
            "clipped_fraction": round(float(np.mean(np.abs(wav) >= 0.999)), 6),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class A1Scorer:
    def __init__(self):
        import os
        import torch
        import torch.nn as nn
        import laion_clap

        self.torch = torch
        self.device = os.getenv("TUNEJURY_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
        head_path = MODELS / "A1_clap_audio_only.pt"
        clap_path = MODELS / "music_audioset_epoch_15_esc_90.14.pt"
        if not head_path.exists() or not clap_path.exists():
            raise ValueError("Model files are missing. Run scripts/download_models.py first.")
        # Architecture matches the published TuneJury head (see docs/THIRD_PARTY.md).
        layers = []
        previous = 512
        for width in [1024, 512, 256, 128]:
            layers.extend([nn.Linear(previous, width), nn.BatchNorm1d(width), nn.ReLU(), nn.Dropout(0.5)])
            previous = width
        layers.append(nn.Linear(previous, 1))
        self.head = nn.Sequential(*layers)
        state = torch.load(head_path, map_location="cpu", weights_only=True)
        state = state.get("state_dict", state)
        self.head.load_state_dict({k.removeprefix("net."): v for k, v in state.items()})
        self.head.to(self.device).eval()
        self.clap = laion_clap.CLAP_Module(enable_fusion=False, amodel="HTSAT-base", device=self.device)
        self.clap.load_ckpt(ckpt=str(clap_path))
        self.clap.to(self.device).eval()

    def extract(self, path: Path) -> dict:
        import math
        torch = self.torch
        wav, sr = sf.read(path, dtype="float32", always_2d=True, frames=sf.info(path).samplerate * 10)
        mono = wav.mean(axis=1)
        divisor = math.gcd(sr, 48000)
        mono = resample_poly(mono, 48000 // divisor, sr // divisor).astype(np.float32)
        torch.manual_seed(0)
        np.random.seed(0)
        with torch.inference_mode():
            emb = self.clap.get_audio_embedding_from_data(x=mono[None, :], use_tensor=False)[0]
            value = float(self.head(torch.tensor(emb, device=self.device).unsqueeze(0)).item())
        if not np.isfinite(value):
            raise ValueError("TuneJury returned a non-finite score")
        return {"score": value, "embedding": np.asarray(emb).tolist(), "model": MODEL_LABEL,
                "window": [0, round(min(10, len(wav) / sr), 3)]}

    def text(self, query: str) -> list[float]:
        with self.torch.inference_mode():
            return self.clap.get_text_embedding([query], use_tensor=False)[0].tolist()


def scorer() -> A1Scorer:
    global _scorer
    if _scorer is None:
        _scorer = A1Scorer()
    return _scorer


def score_path(path: Path, digest: str) -> dict:
    key = f"{MODEL_VERSION}:{digest}"
    cached = store.cache_get(key)
    if cached:
        return {**cached, "cached": True}
    with SCORER_LOCK:
        result = scorer().extract(path)
    store.cache_set(key, result)
    return {**result, "cached": False}


def cosine(a, b) -> float:
    a, b = np.asarray(a), np.asarray(b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 1e-12 else 0.0


def apply_alignment(session: dict, query: str):
    if not query.strip():
        for track in session["tracks"]:
            track["alignment"] = None
        return
    with SCORER_LOCK:
        text_emb = scorer().text(query)
    for track in session["tracks"]:
        track["alignment"] = cosine(track["embedding"], text_emb) if track.get("embedding") else None
