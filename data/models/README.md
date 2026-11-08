# Local speech models

Run `pnpm setup:asr` once to download the MIT-licensed
`Systran/faster-whisper-small` model into `data/models/faster-whisper-small/`.
The model is multilingual, runs locally, and is ignored by Git. The bootstrap is
explicit because model weights are large and must never be downloaded silently
from a learner action.

Override the model location with `WATCH2LEARN_WHISPER_MODEL=/absolute/path`.
