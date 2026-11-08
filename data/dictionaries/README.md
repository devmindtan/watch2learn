# Local dictionaries

Run `pnpm setup:dictionary` (included in `pnpm setup`) to install the pinned
CC-CEDICT snapshot at `data/dictionaries/cedict_ts.u8` and the pinned CVDICT
Chinese-Vietnamese snapshot at `data/dictionaries/cvdict.u8`. Dictionary dumps are intentionally ignored by
Git.

The canonical download page is <https://www.mdbg.net/chinese/dictionary?page=cc-cedict>.
MDBG requires attribution and licenses CC-CEDICT under CC BY-SA 4.0. Its page also
prohibits scripted access, so Watch2Learn downloads an unmodified, checksummed
snapshot from the documented `oxalis-ink/cc-cedict` GitHub redistribution mirror.

See [ATTRIBUTION.md](ATTRIBUTION.md) for the pinned snapshot, source, license and
required credit.
