---
name: watch2learn-ui
description: Design or implement Watch2Learn's responsive video-learning interface, synchronized transcript, Mandarin token interactions, vocabulary selection, progress states, review screens, or visual system. Use only for learner-facing UI and UX; do not use for backend-only pipeline work.
---

# Watch2Learn UI

Read [references/learning-interface.md](references/learning-interface.md) before
creating a new screen or interaction pattern.

## Workflow

1. Name the learning task and primary action before choosing layout or decoration.
2. Design the complete state set: empty, importing, processing, partial result,
   ready, paused/resuming, recoverable error, and unsupported source.
3. Keep video, active cue, selected token, and saved vocabulary synchronized by
   stable IDs and timestamps rather than DOM position.
4. Make Hanzi, pinyin, meaning, context, and saved/known state visually distinct.
5. Support keyboard, touch, reduced motion, zoom, high contrast, and screen readers.
6. Use responsive layout intentionally: side-by-side on wide screens and a clear
   video/transcript/vocabulary priority on narrow screens.
7. Reuse existing tokens/components. Add a component only for repeated behavior.
8. Inspect changed visuals with screenshots and verify critical behavior with
   Playwright when an executable UI exists.

Avoid generic dashboard styling, decorative gradients, dense card grids, flags as
language labels, and color-only learning states. Use proper language tags (`zh`,
`zh-Hans`, `zh-Hant`) and fonts with complete CJK glyph coverage.
