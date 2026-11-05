# Licenses, credits and model provenance

Sonvane’s original source code and documentation are licensed under the [MIT License](../LICENSE). Bundled third-party code, fonts, model artifacts and their notices retain their respective licenses. The MIT grant does not cover Sonvane’s brand marks, character illustrations, source video or music media; no additional reuse permission for those assets is granted here. See [selected artwork credits](character-art.md).

Music-generation and music-evaluation model weights and credentials are not distributed in this repository. The bundled browser face detector is documented below.

## TuneJury A1

- Paper: https://arxiv.org/abs/2606.17006
- Original project: https://github.com/yonghyunk1m/TuneJury
- Checkpoint: https://huggingface.co/TuneJury/tunejury/blob/main/A1_clap_audio_only.pt
- Configuration: https://github.com/yonghyunk1m/TuneJury/blob/main/checkpoints/input_ablation/A1_clap_audio_only.json
- Model card identifies the A1 checkpoint as **Apache-2.0**. The primary CLAP+MERT checkpoint is **CC-BY-NC 4.0** and is not used here.

The small inference adapter in `app/audio.py` reconstructs the published A1 head architecture (512 input; hidden widths 1024, 512, 256, 128; Linear/BatchNorm/ReLU/Dropout blocks). We acknowledge the public `tunejury/model.py` implementation as its architectural source. No new reward model is trained.

## LAION-CLAP-Music

- Code: https://github.com/LAION-AI/CLAP
- Weight source: https://huggingface.co/lukewys/laion_clap
- Encoder: `music_audioset_epoch_15_esc_90.14.pt`, HTSAT-base, fusion disabled.

The downloader fetches original artifacts from their hosts. Weights are not bundled in source. Applicable upstream notices and licenses remain with those distributions. Verify license conditions before redistributing artifacts or making a commercial release.

## Test audio

The optional local test clips are generated from sinusoidal notes by this application's code. They are intentionally labeled synthetic tests. They are not paper results or examples of high-quality generated music.

## Meta API

The app is a client of Meta Model API using Standard Muse Spark and documented Chat Completions tool calls. No Meta model weights are distributed. API terms and pricing apply independently.

## Interface assets and typography

Sonvane's paired-S marks are original vector artwork. The selected creator illustrations and existing TuneJury character are documented in [artwork credits](character-art.md). Artwork, names and logos are not relicensed under the application's software license.

**Inter** is distributed under the SIL Open Font License; its notice is retained in `app/static/assets/inter-OFL.txt`. Source: https://github.com/google/fonts/tree/main/ofl/inter. Fonts are served locally.

The Overview's Canvas sculpture and browser-synthesized musical sketches are original interactive artwork. They are separate from Studio's generated soundtracks and are not Meta outputs or TuneJury measurements. MediaPipe notices are recorded below.

Video processing uses `imageio-ffmpeg`. FFmpeg binaries, private recordings, discarded design concepts and production captures are not bundled in this repository.

## ACE-Step 1.5 generation and studio personalization

- Runtime: https://github.com/ace-step/ACE-Step-1.5 — MIT; pinned commit `ca1e85fe9430179831e6bc6be790c332190a3866`.
- Model: https://huggingface.co/ACE-Step/Ace-Step1.5 — MIT; pinned revision `19671f406d603126926c1b7e2adc169acbcade22`.
- Downloaded components: `acestep-v15-turbo`, `vae`, and `Qwen3-Embedding-0.6B`. Upstream files and notices remain with those distributions; weights and upstream source are not committed here.
- Generation runs in an isolated Python 3.12 process, DiT-only, with eight inference steps. Meta supplies the caption. No separate ACE language model is loaded.
- The studio trains an application-local pairwise linear residual on frozen CLAP features. TuneJury, CLAP, and ACE-Step weights remain unchanged.
- Model licensing does not certify that generated outputs are free of third-party claims.

The studio uses Muse Spark 1.3 for frame-only requests and 1.2 when audio is included, following https://dev.meta.ai/docs/video-understanding (checked 2026-11-03). Unlike the earlier workbench planner, studio planning sends sampled video frames and original audio to Meta. Strict output follows https://dev.meta.ai/docs/structured-output.

## Voice input and spoken replies

Recorded microphone speech is transcribed with Muse Spark 1.2 through its documented audio input: https://dev.meta.ai/docs/video-understanding. The user reviews the transcript before sending it as a chat message. Recorded audio is not a cloned voice or a voice-model training sample.

Spoken replies use **Kokoro-82M v1.0**, Apache-2.0 weights: https://huggingface.co/hexgrad/Kokoro-82M. The isolated CPU runtime is **kokoro-onnx 0.6.1**, MIT: https://github.com/thewh1teagle/kokoro-onnx. The ONNX export and voice pack are downloaded from its `model-files-v1.1` release, with SHA-256 values saved in the ignored local provenance manifest. Upstream phonemizer/eSpeak dependencies retain their separate licenses. Models, voice packs, and synthesized recordings are not bundled in the source repository.

The selected stock voice is `af_heart`. It is neither an official Meta/Muse voice nor an imitation of the user. Local test speech was synthesized from an original scripted sentence using the installed Flite voice before the Kokoro path was added; it remains an explicitly synthetic fixture, not the user's voice recording or a human study.

## Section editing

ACE-Step's existing `repaint` task is used with an explicit source-audio time mask. The application additionally restores original PCM outside the selected interval and blends boundaries inside that interval. This application code is not a new audio-editing foundation model or an isolated-stem editor. Source documentation: https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/INFERENCE.md.

## Optional face-distance interaction

The Overview uses MediaPipe Tasks Vision 0.10.32 and the BlazeFace short-range face detector for opt-in camera distance control. The original package license and artifact hashes are retained in `app/static/assets/mediapipe/`. Sources: [MediaPipe package](https://www.npmjs.com/package/@mediapipe/tasks-vision) and [face detection model documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/face_detector). Camera frames are processed in the browser; this feature does not send the camera stream to Muse or the hosted backend.

## Demo film narration

The English demo-film narration uses the stock **Ryan** voice from [Qwen3-TTS-12Hz-1.7B-CustomVoice](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice), whose model card specifies Apache-2.0. It was synthesized locally in a separate production environment. It is not a clone or imitation of Yonghyun Kim. This production voice is separate from the application’s Kokoro spoken replies. Model weights and production recordings are not included in the source repository.
