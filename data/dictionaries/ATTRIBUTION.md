# CC-CEDICT attribution

Watch2Learn uses an unmodified CC-CEDICT snapshot for Chinese-English meanings,
pinyin, and simplified/traditional mappings.

- Source project: [MDBG CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict)
- Redistribution mirror: [oxalis-ink/cc-cedict](https://github.com/oxalis-ink/cc-cedict)
- Snapshot: `1.0+20261007032622`
- License: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- Credit: MDBG and the CC-CEDICT editors and contributors; based on CEDICT by
  Paul Andrew Denisowski.

## CVDICT attribution

Watch2Learn uses an unmodified CVDICT snapshot for Chinese-Vietnamese meanings.

- Source project: [ph0ngp/CVDICT](https://github.com/ph0ngp/CVDICT)
- Snapshot: commit `c379d909e308343a247e51619f7839a2060a271c` (version 1.0.1)
- License: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- Credit: Phong Phan; based on CC-CEDICT. Its meanings were machine-translated
  from CC-CEDICT and manually reviewed, so occasional errors are possible.

The downloaded dictionaries are not committed to Git. `pnpm setup` retrieves the
pinned, unmodified snapshot and verifies its SHA-256 digest.
