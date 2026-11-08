# 20-repo-generate-video assessment

Reviewed locally on 2026-11-08. This sibling repository remains reference-only;
Watch2Learn does not import or depend on it.

## Useful patterns

- Execute FFmpeg with an argument array and `-nostdin` rather than interpolating a
  shell command.
- Keep media inspection read-only by default and refuse accidental input overwrite.
- Isolate deterministic parsing/analysis functions and test them with synthetic
  data rather than large committed media fixtures.
- Silence detection can later help identify ASR chunk boundaries, but should not
  split inside subtitle cues or become the source of transcript timing truth.

## Not reused

- `scripts/shared/media_probe.py` points directly at Remotion's Linux compositor
  binary and parses human-readable FFmpeg stderr. Watch2Learn needs cross-platform
  binary discovery and machine-readable `ffprobe` JSON.
- Shot detection, contact sheets, YouTube loudness normalization, music energy,
  Remotion rendering, voice generation, and production-management workflows do not
  serve the first vocabulary-learning slice.
- No code or assets were copied. If sharing becomes desirable later, extract a
  separately licensed package with its own tests instead of cross-repo imports.

## Watch2Learn adaptation

Create a small media adapter that discovers the repo-local/system FFmpeg pair,
probes streams with `ffprobe -of json`, extracts mono 16 kHz PCM without shell
interpolation, writes to a caller-owned job directory, and never overwrites an
existing output. Add silence/chunk analysis only when local ASR is implemented.
