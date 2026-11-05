# Verification

Last checked: **4 November 2026**. The local automated suite passes **108 tests**, with two dependency deprecation warnings.

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Automated tests use fixtures and mocked providers where appropriate. They verify execution behavior, not creative quality.

## Automated coverage

| Area | Checks |
| --- | --- |
| Sound plans | Drafts do not generate audio; approval uses the reviewed revision; stale approvals are rejected. |
| Generation | Duration validation, cancellation, recovery, and preservation of a previous playable result after failure. |
| Audio and video | Source-section trimming, cue placement, music-only scoring windows, mixing and original-audio ducking. |
| Personalization | Explicit consent, comparison validation, context separation and deletion of remembered choices. |
| Conversations | Supported actions, request deduplication, interval validation and speech handling. |
| Hosted preview | Root routing, credential handling, visitor isolation, cross-origin write rejection and packaged video range requests without backend access. |

## Recorded integration checks

The following checks were run separately with actual model calls or browser playback. Their captures and generated media stay outside the repository.

- **Reviewed placement:** Muse proposed a sound plan for a synthetic video. Edited music and effect cues were approved, generated and mixed at the reviewed times. Music evaluation excluded gaps and synthesized effects.
- **Recovery:** interrupted generation resumed using an already saved candidate. A failed revision retained the previous playable result.
- **Interval revision:** in a recorded 8–11-second repaint, PCM samples outside the interval matched the selected source exactly. Samples inside the interval changed.
- **Comparison and choice:** switching music preserved the audition position. Listening did not change the selected soundtrack; applying a version was a separate action.
- **Hosted workflow:** a synthetic video was uploaded, planned, approved, rendered into three music candidates and played through the private preview. Another visitor could not access that project.
- **Interface:** browser checks covered narrow and wide layouts, navigation, plan review, playback and export. The latest pass checked 390, 768 and 1440 px widths, preserved page/chat reading positions and played an exported HTML video card offline.

## Reproducing browser checks

Start the local app first. Browser scripts under `scripts/` cover specific interactions; inspect each script's inputs before running it. Checks that accept `--live` can call a paid provider and generate media. They are separate from the default test suite.

Examples include `studio_score_compare_smoke.py`, `video_trim_smoke.py`, `sound_plan_smoke.py` and `studio_recovery_smoke.py`. Some integration scripts require a prepared local project; they are not clean-install unit tests.

## Limits

No controlled user study establishes improved taste, time savings or audiovisual quality. Model preference scores do not measure video fit. Energy-based ducking is not speech detection. Browser sharing depends on the device; native Instagram delivery is not guaranteed. GitHub's native iOS app has not been directly verified.

See the [technical report](../app/static/report/sonvane-technical-report.pdf) for the method and [deployment guide](huggingface-deployment.md) for hosting limits.
