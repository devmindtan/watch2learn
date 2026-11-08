# Local speech models

Run `pnpm setup:asr` once to download the MIT-licensed
`Systran/faster-whisper-small` model into `data/models/faster-whisper-small/`.
The model is multilingual, runs locally, and is ignored by Git. The bootstrap is
explicit because model weights are large and must never be downloaded silently
from a learner action.

Override the model location with `WATCH2LEARN_WHISPER_MODEL=/absolute/path`.

# Local translation model

Run `pnpm setup:translation` once to download the Apache-2.0
`Helsinki-NLP/opus-mt-zh-vi` model (CTranslate2 int8 conversion, about 83 MB) into
`data/models/opus-mt-zh-vi/`. Every file is pinned to a revision and verified by
SHA-256. Without it, lessons still build; cue translations are simply empty.

Override the location with `WATCH2LEARN_TRANSLATION_MODEL=/absolute/path`.

# Local voices

Run `pnpm setup:voices` to download the Piper voices `zh_CN-chaowen-medium`
(dataset CC0) and `vi_VN-vais1000-medium` (VAIS-1000, CC BY 4.0) into
`data/models/piper/`, pinned to a revision and verified by SHA-256. They read
words, sentences and explanations aloud in any browser.
