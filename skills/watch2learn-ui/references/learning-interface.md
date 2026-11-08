# Learning interface principles

## Primary workspace

- Video remains visible while the learner follows the active transcript cue.
- Clicking a cue seeks the video; clicking a token opens details without losing
  playback position.
- Active cue highlighting is calm and stable. Avoid continuous auto-scroll that
  fights manual reading; pause following after the learner scrolls away.
- Pinyin is optional and can be hidden globally or revealed per token.
- A token detail shows Hanzi, pinyin, concise meanings, the original sentence,
  timestamp replay, known/save actions, and alternate analysis when uncertain.

## Accessibility and typography

- Use semantic buttons and lists; expose playback time and processing progress.
- Target at least WCAG AA contrast and a 44px touch target where practical.
- Do not encode known/new/uncertain state with color alone.
- Preserve text selection and browser zoom. Avoid tiny ruby text as the only pinyin
  representation; provide an accessible textual equivalent.
- Prefer system/Noto CJK fallbacks rather than downloading a commercial font.

## Responsive behavior

- Wide: video plus transcript as the main split; vocabulary panel is secondary.
- Narrow: video first, active transcript next, vocabulary details in a sheet or
  routed view with an obvious return path.
- Never require hover for definitions or core controls.
