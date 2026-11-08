# Local dictionaries

Place a CC-CEDICT UTF-8 text export at `data/dictionaries/cedict_ts.u8`.
Dictionary dumps are intentionally ignored by Git.

The canonical download page is <https://www.mdbg.net/chinese/dictionary?page=cc-cedict>.
MDBG requires attribution and licenses CC-CEDICT under CC BY-SA 4.0. Its page also
prohibits scripted access, so Watch2Learn does not auto-download the file. Download
it manually, decompress the `.txt.gz`, rename it to `cedict_ts.u8`, and retain the
header/provenance.

Watch2Learn does not modify or redistribute the dictionary. If that changes, the
resulting data and attribution must comply with CC BY-SA 4.0.
