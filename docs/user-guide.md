# Sonvane user and developer guide

[Back to the project](../README.md)

## Run locally

Requires Python 3.12, Git, and enough storage for model downloads. The current generator setup requires an NVIDIA GPU compatible with its CUDA 12.8 wheels. CPU scoring is supported; the complete music-generation setup is not a static website.

```bash
git clone https://github.com/yonghyunk1m/sonvane.git
cd sonvane
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Set `MODEL_API_KEY` in your local `.env`. The repository is currently private, so cloning requires repository access until release. Never put the API key in frontend code.

Download the evaluation models and install the isolated generator (both download several GB):

```bash
.venv/bin/python scripts/download_models.py
.venv/bin/python scripts/setup_generator.py --python python3.12
bash scripts/run.sh
```

Open the local app shown in the startup log, then choose **Studio**. The development server accepts local access only. Use an SSH tunnel for your own remote development machine; configure its hostname privately.

Optional local read-aloud setup:

```bash
.venv/bin/python scripts/setup_speech.py --python python3.12
```

| Page | Purpose |
| --- | --- |
| `/demo/` | Overview, interactive audiovisual work and pipeline |
| `/studio/` | Upload, sound-plan review, generation, comparison, revision and export |
| `/report/` | Technical report with scope and evaluation limitations |
| `/workbench/` | Earlier music-evaluation workflow; different from Studio |

## Repository guide

- `app/`: API, validation, orchestration, scoring, personalization and browser UI.
- `scripts/`: model setup, local execution, verification and presentation builds.
- `tests/`: automated checks with explicit test fixtures.
- `docs/`: setup guides, verification, release history and credits.
- `docs/THIRD_PARTY.md`: model, font, library and artwork provenance.
- `.data/`, `.models/`, `.env`, `artifacts/`: local-only data, models, credentials and review outputs; excluded from Git.

Presentation builders may require private source footage in ignored `artifacts/`; it is not part of a fresh source checkout. Reproducing the application does not require those private demo captures. Original source code is licensed under MIT; separate asset and upstream terms are documented in `docs/THIRD_PARTY.md`. The repository remains private until the owner authorizes publication.

## Create a soundtrack

1. **Choose a video**, or drop it on the welcome panel. MP4/MOV sources may be up to 10 minutes / 250 MB. Selecting a valid video automatically uploads the working section and sends one Muse request; no prompt or context selection is required.
2. Read **Your video** (Muse's observation of the sampled scene) and its recommended music/effect placements. Music has not been generated yet. Short clips use their full length; longer videos initially use the **first 30 seconds**, with that scope shown explicitly. This is not whole-video analysis.
3. Click **Create my soundtrack** to approve and generate three music variations. Effects-only plans use **Apply this plan**. Generation uses the approved prompts without an additional Muse request.
4. Optional: open **Adjust timing or sound** to edit cues, preview effects and save changes. **Change section** reuses the original browser File when available and waits for an explicit analysis action after trimming. After reloading, reselect the original video to change its section. This creates a new clip project while retaining the prior project.
5. Play the recommended mix and **Download video**. Other audio/record exports and alternate versions are in **Other downloads** and **Compare other versions**. **Change the music** exposes further revision controls.
6. **Add a preference** and **Ask Muse or refine your request** are optional. **Advanced options → Ask Muse for a new plan** explicitly requests a fresh paid proposal. Automatic analysis is not repeated on reload, duplicate media events, or failure; failures offer an explicit retry.
7. The mix controls below the video apply the existing music without generation or a Meta request. **Lower music under original audio** reduces music when the retained original sound is louder, then restores it as the original becomes quieter. This follows audio energy, not speech detection. It is available only when **Keep original audio** is enabled and the source has audio. Explicitly remembered text and A/B comparisons retain their previous memory semantics.
8. Saved projects, unsent messages and cue edits restore in the same browser. Up to four generation attempts remain allowed per project. Previous tracks preserve their approved placement snapshots.

Reviewed plans allow up to three non-overlapping music sections (each at least three seconds) and five effects (each 0.1–5 seconds), with at most eight cues total. Effects may overlap music. Supported effects are **whoosh, chime, impact, click, and riser**, generated with deterministic local DSP; the effect description records intent, while the selected type/duration/gain controls the sound. This is not arbitrary text-to-SFX or realistic Foley generation. Gaps contain no added music; retained original audio follows the mix settings. Effects-only and original-only plans use no music model or music scores. Their output is available through **Sound design**; musical plans offer both raw **Music** and mixed **Music + effects** downloads.

Suggestions are approximate: 12 sampled frames are not frame-level event tracking. The user should review timing and sound quality. The current editable plan and each generated track's immutable approved snapshot are stored separately. Stale approval versions are rejected before generation. Saved cue pieces and completed variations are reused after Stop/Resume. Music generation internally requests at least ten seconds per cue and trims to its approved length; the system does not establish coherent musical transitions between independently generated cues.

**Quick full-clip soundtrack** retains the earlier one-click workflow (four frames → three full-clip music briefs). Once a sound plan exists, use review and approval instead. Chat can explain plans, mix existing audio, or repaint within an approved music interval; it cannot silently approve or rewrite cue placements.

Muse Spark 1.3 handles frame-only planning. Videos with audio use Muse Spark 1.2, following Meta's current audio-understanding guidance. Plans use a strict JSON schema; failures are visible and never replaced with synthetic music. Paid requests are not retried automatically. **Stop generation** retains a validated plan, completed candidates, and completed scores. **Resume saved work** continues that checkpoint without a new Meta call or another round. An already-sent planning request may still finish and incur usage after Stop. If planning never produced a valid plan, a new generation attempt is needed. Changing the saved direction invalidates the unfinished plan. A failed revision preserves the previous playable selection. Network polling reconnects using read requests only.

The 3–30 second working length is an application constraint for bounded three-candidate generation, evaluation, and rendering; it is not a claim about the maximum length supported by the underlying models. The server accurately seeks and re-encodes the selected video and original audio together. Only that clip is sent onward for planning and receives a soundtrack. Preview/downloads contain the selected section, not the entire source with partial music. Selection timestamps and the original duration are retained in the project and decision record. The original file on your device stays unchanged; the temporary full upload is removed after processing. No Meta request is needed to trim.

Revisions use the selected candidate's prompt, measured scores, recent feedback, and matching remembered instructions. Whole-track revisions regenerate the music. **Change only a section** uses ACE-Step repainting for a 1+ second interval in a 10–30 second track; the application splices it into the original PCM audio with crossfades inside the interval. Samples outside the interval remain unchanged. This is not isolated instrument-stem editing.

## Talk with Muse

After analysis, **Plan with Muse** is visible below the recommendation. Once a soundtrack exists, **Refine with Muse** appears below the result. The same interface can create/revise music, adjust an existing mix, select a named candidate, explain measured evidence, edit an interval, or manage explicitly permitted memories. Real execution results are displayed separately from Muse's proposed action. Conversation state persists with the project. Request IDs prevent replaying the same paid turn after an uncertain response.

With the audio-sharing checkbox enabled, a conversation includes the selected track's first ten seconds (or original video audio before music exists), labeled separately from sampled frames. Muse Spark 1.2 handles these audio-bearing conversations. Disable the option to send text, scores, and frames only.

**Record voice** captures up to 30 seconds in the browser, converts it to mono 16 kHz WAV, and asks Muse to transcribe it. Review the transcription before sending; recording alone does not execute an action. Microphone audio is processed in memory; submitted transcript text persists in the project. Microphone permission is granted by the browser. This is a turn-based voice interface, not continuous full-duplex audio.

**Read aloud** strips Markdown syntax from the visible reply and synthesizes it locally with Kokoro on CPU. The cached WAV includes word timings derived from the model’s phoneme durations. The transcript highlights the current word and follows it within its own scroll area; clicking a word (or focusing it and pressing Enter) starts reading there. Arrow keys move between words. Reply Markdown is rendered with local markdown-it, with raw HTML and remote image loading disabled. Starting a video cancels pending narration, so a late voice response cannot interrupt it. A newly completed soundtrack also leaves a currently playing original video in place until the user chooses the mix. Starting a recording or sending a new message interrupts playback. It is not an official Meta voice and does not clone the user. Install the isolated speech environment on a fresh machine:

```bash
python scripts/setup_speech.py --python python3.12
```

This downloads the Kokoro v1.0 ONNX model and voices into ignored `.models/speech/`, with file hashes recorded locally. The runtime is pinned to `kokoro-onnx==0.6.1`; no separate paid speech API is used.

## What learns, and what is measured

Text directions are saved instructions for Muse. **Explicit listening comparisons train a separate, regularized Bradley–Terry linear model over frozen CLAP features.** Its contribution starts small and adjusts future candidate ranking in matching contexts; general preferences also apply across contexts. Deleting an example removes it from future fits. No TuneJury or generation-model weights are fine-tuned, and downloading a track is not treated as a preference vote.

The studio evaluates non-overlapping, balanced windows of at most ten seconds across each generated track and averages the A1 scores and audio embeddings. A1 is an unbounded aggregate preference signal; CLAP similarity is approximate prompt relevance. The base utility is `0.65 * sigmoid(A1) + 0.35 * (CLAP similarity + 1) / 2`, plus a bounded learned residual. These weights are a prototype heuristic, not calibrated probabilities or validated measures of video fit. The record includes the baseline and personalized order, windows, prompts, seeds, and model revisions.

The earlier `/workbench/` retains its original behavior: 2–12 uploaded clips, only the first ten seconds scored, heuristic selection with observed votes, and a measured-data Meta tool loop. That workflow does not train a persistent personal model and sends no raw audio to Meta. Do not conflate these two interfaces.

MIT licensing of ACE-Step does **not** guarantee third-party rights clearance for generated music. The workflow is not a copyright checker.

## Budget and local data

Muse requests use your own Meta API key and its available credits or billing. See [Meta’s pricing](https://dev.meta.ai/docs/pricing-rate-limits). Sonvane does not silently switch to another provider when credits or the application budget run out. Previously generated music remains available; new Muse requests require available quota.

The app defaults to a **$5 reserved budget and 40 Meta requests**. Studio planning, conversation, and voice transcription each reserve $0.25 before a request; workbench tool-loop requests reserve $0.10 each, at most four per planner run. Failed or uncertain requests keep their reservation. Studio requests cap the encoded payload at 3 MB; quick planning uses at most 3,000 output tokens; cue planning and conversation/transcription use at most 4,000. A conversational generation request can use two calls: action interpretation and music planning. No automatic paid retries or paid search are used. Local generation has no per-generation API charge, but uses your compute. These controls are app-local, not an account-wide billing cap. The configured budget cannot exceed $150. Fresh installations use the $5/40 defaults in `.env.example`; operators must set their own budget.

Reported cost uses token usage and the current pricing assumptions of $1.25/M input and $4.25/M output tokens, checked 2026-11-03. Reservation and reported usage are different figures.

Videos, generated music, frame samples, private provider responses, preferences, and the ledger are stored in ignored `.data/`; model files in `.models/`. `.env`, `.cache/`, and `artifacts/` are ignored. Profiles are local browser identifiers, **not authentication**. The app is bound to loopback and is not a hosted multi-user service.

## Verification and presentation

```bash
.venv/bin/python -m pytest -q
# Optional browser checks (requires Playwright + Chromium):
.venv/bin/python scripts/browser_smoke.py
# Paid, real generation and Meta calls; opt in explicitly:
.venv/bin/python scripts/studio_smoke.py --live
# One paid planning request; tests interruption, saved-candidate reuse, and recovery:
.venv/bin/python scripts/studio_recovery_smoke.py --live
# Local browser upload/trimming checks; generation intercepted, no paid calls:
PYTHONPATH=. .venv/bin/python scripts/video_trim_smoke.py

# Seven paid requests; full conversation, real speech input, and a section edit:
.venv/bin/python scripts/conversation_smoke.py --live
```

See [verification](studio-verification.md) and the [technical report](../app/static/report/sonvane-technical-report.pdf). Automated tests use synthetic fixtures and scripted choices. They establish execution behavior, not musical quality, human satisfaction or personalization accuracy. The GitHub repository remains private; the Protected Hugging Face Space exposes the running demo through its direct app URL.

The Overview’s abstract particle sculpture is an interactive artwork, separate from Studio’s generated music. Drag to rotate or Shift-drag to roll; motion continues during interaction, and nearby particles respond to the pointer. Turn sound on to hear the musical sketch, trace the curve to emphasize different frequencies, and rotate it to shift stereo position. Camera volume control is optional and processes frames in the browser.

In Studio, TuneJury’s score cards play the music immediately. Switching versions preserves the audition position; **Use in my video** applies the chosen version separately. Cards compare the selected version’s generation round. Other rounds remain under **Saved generations**, with their audio and selection controls. Re-running an unchanged, already-generated sound plan is labeled **Make 3 more versions**.

## Share a finished video

Choose **Share** beside **Save video**. Sonvane prepares the selected rendered mix, then offers:

- **Share to an app** opens the device share sheet when file sharing is supported. Available destinations depend on the browser, device and installed apps; Instagram is not guaranteed to appear.
- **Save MP4** downloads the mixed video for upload in your social app.
- **Save video card** downloads one HTML file containing the video and audio. Send the file and open it in a browser; it requires no Sonvane server or login. Some messaging apps only offer a download for HTML attachments.

The card includes the chosen track name and video. It does not include private server addresses, conversation history, API keys or a project access link. Nothing is posted automatically.

File sharing follows the [Web Share API](https://www.w3.org/TR/web-share/); restricted embedded browsers can fall back to downloads.
