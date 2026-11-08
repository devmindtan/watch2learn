# Mandarin pipeline reference

## Canonical stages

1. Parse subtitle cues into original text and `[start_ms, end_ms)`.
2. Remove presentation markup while retaining an original payload for audit.
3. Detect script and normalize punctuation/spacing without flattening Hanzi.
4. Segment with Jieba plus a project dictionary; keep cue and character offsets.
5. Look up CC-CEDICT by exact, simplified, and traditional forms.
6. Select readings/senses using available context; preserve alternatives.
7. Consolidate lexemes and attach each timestamped surface occurrence.
8. Filter punctuation, names/noise, and learner-known words without deleting data.
9. Rank by repetition, useful frequency/level data, confidence, and context quality.

## Minimum test cases

- compounds that would be wrong if split character-by-character;
- polyphonic characters in distinct contexts;
- erhua, neutral tone, numbers, names, and mixed Latin/Hanzi text;
- simplified and traditional variants resolving to the same lexeme when valid;
- adjacent subtitle cues and repeated words retaining distinct timestamps;
- ASR uncertainty and learner correction surviving a reprocessing run.

HSK and frequency data need separately documented sources and licenses. Do not
hard-code a scraped list whose provenance is unknown.
