// Word and sentence study cards, shared by the video screen and the library so
// every place offers the same features. A card works on a "study context":
//   lesson, wordsById, cueIndexById   — the lesson the word/sentence comes from
//   playClip(cueIndex) -> bool         — play the original sentence (false = no video)
//   pause()                            — pause video/clip before narration
//   onChange(wordId?)                  — saved/learned/meaning changed
//   showWord(wordId, occurrenceIndex)  — open (or re-open) a word card
//   openInVideo?(focus)                — library only: jump into the lesson
//   onClose()                          — close the card
import { apiFetch, responseJson } from "./api.js";
import {
  ownMeaning,
  sentenceKey,
  sentenceStatus,
  updateSentence,
  updateWord,
  wordStatus,
} from "./learner.js";
import { openPractice } from "./practice.js";
import { createNarration, speak, stopSpeaking, toneDescription } from "./speech.js";
import { actionButton, button, cleanSenses, element, escapeRegExp, timeLabel } from "./ui.js";

/** The Chinese part of a cue (other-language parts are never read or practised). */
export function chineseText(cue) {
  if (!cue?.segments?.some((segment) => segment.foreign)) return cue?.text || "";
  return cue.segments.filter((segment) => !segment.foreign).map((segment) => segment.text).join("").trim();
}

export function firstMeaning(word) {
  return ownMeaning(word.id) || cleanSenses(word.definitions_vi).senses[0] || "";
}

/** The dictionary sense whose wording appears in this sentence's Vietnamese translation. */
export function contextSense(word, cue) {
  const translation = (cue?.translation_vi || "").normalize("NFC").toLowerCase();
  if (!translation) return null;
  let best = null;
  cleanSenses(word.definitions_vi).senses.forEach((sense, index) => {
    for (const raw of sense.replace(/\([^)]*\)|\[[^\]]*]/g, "").split(/[;,/]/)) {
      const phrase = raw.trim().normalize("NFC").toLowerCase();
      if (phrase.length < 2) continue;
      const pattern = new RegExp(`(^|[^\\p{L}])${escapeRegExp(phrase)}(?=$|[^\\p{L}])`, "u");
      if (pattern.test(translation) && (!best || phrase.length > best.phrase.length)) {
        best = { phrase, text: raw.trim(), index };
      }
    }
  });
  return best;
}

export async function setWordStatus(ctx, wordId, status, cueId) {
  try {
    await updateWord(wordId, { status, lesson_id: ctx.lesson.id, cue_id: cueId });
  } catch (error) {
    window.alert(error.message);
    return;
  }
  ctx.onChange(wordId);
}

function actionRow(label) {
  const row = element("div", "action-row");
  row.dataset.label = label;
  return row;
}

function section(title, ...children) {
  const node = element("section", "word-section");
  node.append(element("h3", null, title), ...children);
  return node;
}

function chinese(tag, className, text) {
  const node = element(tag, className, text);
  node.lang = "zh";
  return node;
}

/** Original sentence when there is video, otherwise read by the Chinese voice. */
function playSentence(ctx, cueIndex, text) {
  if (!ctx.playClip(cueIndex)) speak(text, 0.85);
}

export function renderWordCard(container, ctx, wordId, occurrenceIndex = 0) {
  const word = ctx.wordsById.get(wordId);
  if (!word) return;
  const position = Math.max(0, Math.min(occurrenceIndex, word.occurrences.length - 1));
  const occurrence = word.occurrences[position];
  const cueIndex = ctx.cueIndexById.get(occurrence.cue_id);
  const cue = ctx.lesson.cues[cueIndex];
  const status = wordStatus(wordId);
  const own = ownMeaning(wordId);
  const surface = occurrence.surface || word.word;
  const inContext = contextSense(word, cue);

  const head = element("div", "word-head");
  const identity = element("div");
  const hanzi = element("p", "word-hanzi", word.word);
  hanzi.lang = "zh-Hans";
  if (word.traditional && word.traditional !== word.word) {
    const traditional = element("span", "traditional", word.traditional);
    traditional.lang = "zh-Hant";
    traditional.title = "Phồn thể";
    hanzi.append(traditional);
  }
  identity.append(hanzi, element("p", "word-pinyin", occurrence.pinyin || word.pinyin));
  const close = button("close-button", "×", ctx.onClose);
  close.setAttribute("aria-label", "Đóng");
  head.append(identity, close);

  const listen = actionRow("Nghe");
  listen.append(
    actionButton("listen", "🔊", "Phát âm", () => speak(surface, 0.7)),
    actionButton("listen", "▶", "Câu gốc", () => playSentence(ctx, cueIndex, chineseText(cue) || occurrence.cue_text), {
      title: "Nghe câu chứa từ này trong video",
    }),
  );
  const learn = actionRow("Học");
  learn.append(
    actionButton("lesson", "📖", "Xem chi tiết từ", () => explainWord(explainBox, ctx, word, occurrence, cue, inContext, { speakIt: false })),
    actionButton("lesson", "🗣", "Nghe giảng", () => explainWord(explainBox, ctx, word, occurrence, cue, inContext, { speakIt: true })),
    actionButton("practice", "🎙", "Luyện phát âm", () =>
      openPractice({
        target: surface,
        pinyin: occurrence.pinyin || word.pinyin,
        translation: own || cleanSenses(word.definitions_vi).senses[0] || "",
        kind: "word",
        itemId: status ? wordId : null,
        onScored: () => ctx.onChange(wordId),
      }),
    ),
  );
  const keep = actionRow("Lưu");
  keep.append(
    actionButton("save", status ? "★" : "☆", status ? "Đã lưu" : "Lưu từ", () => !status && setWordStatus(ctx, wordId, "saved", occurrence.cue_id), {
      pressed: Boolean(status),
    }),
    actionButton("learned", "✓", status === "learned" ? "Đã thuộc" : "Đánh dấu thuộc", () =>
      setWordStatus(ctx, wordId, status === "learned" ? "saved" : "learned", occurrence.cue_id),
      { pressed: status === "learned" },
    ),
  );
  if (ctx.openInVideo) {
    keep.append(
      actionButton("video", "🎬", "Xem trong video", () => ctx.openInVideo({ cueId: occurrence.cue_id, wordId })),
    );
  }

  const meaning = element("div");
  if (own) meaning.append(element("p", "own-meaning", `Nghĩa của bạn: ${own}`));
  if (inContext) {
    const highlight = element("p", "context-sense");
    highlight.append("Trong câu này: ", element("strong", null, inContext.text));
    meaning.append(highlight);
  }
  const vietnamese = cleanSenses(word.definitions_vi);
  if (vietnamese.senses.length) {
    const list = element("ol", "senses");
    vietnamese.senses.forEach((sense, index) => list.append(element("li", inContext?.index === index ? "is-context" : "", sense)));
    meaning.append(list);
  } else if (!own) {
    meaning.append(element("p", "sense-note", "Từ điển offline chưa có nghĩa tiếng Việt cho từ này — bạn có thể tự ghi nghĩa bên dưới."));
  }
  vietnamese.notes.forEach((note) => meaning.append(element("p", "sense-note", note)));
  const alternatives = (word.alternatives || []).filter((item) => item.definitions_vi?.length);
  if (alternatives.length) {
    const details = element("details", "more");
    details.append(element("summary", null, `Cách đọc / nghĩa khác (${alternatives.length})`));
    const list = element("ul", "alternatives");
    for (const alternative of alternatives) {
      const item = element("li");
      item.append(element("strong", "alt-pinyin", alternative.pinyin), ` ${alternative.definitions_vi.join("; ")}`);
      list.append(item);
    }
    details.append(list);
    meaning.append(details);
  }

  const context = element("div", "context");
  if (occurrence.before_text) context.append(chinese("p", "context-neighbor", occurrence.before_text));
  const current = chinese("p", "context-current");
  const text = occurrence.cue_text;
  const { start_offset: start, end_offset: end } = occurrence;
  if (Number.isInteger(start) && Number.isInteger(end) && end <= text.length) {
    current.append(text.slice(0, start), element("mark", null, text.slice(start, end)), text.slice(end));
  } else {
    current.textContent = text;
  }
  context.append(current);
  if (cue?.translation_vi) context.append(element("p", "context-translation", cue.translation_vi));
  if (occurrence.after_text) context.append(chinese("p", "context-neighbor", occurrence.after_text));
  const occurrences = element("div", "context-actions");
  if (word.occurrences.length > 8) {
    const previous = button("icon-button", "‹", () => ctx.showWord(wordId, position - 1));
    previous.disabled = position === 0;
    previous.setAttribute("aria-label", "Lần xuất hiện trước");
    const next = button("icon-button", "›", () => ctx.showWord(wordId, position + 1));
    next.disabled = position === word.occurrences.length - 1;
    next.setAttribute("aria-label", "Lần xuất hiện sau");
    occurrences.append(previous, element("span", "occurrence-step", `Lần ${position + 1}/${word.occurrences.length} · ${timeLabel(occurrence.start_ms)}`), next);
  } else if (word.occurrences.length > 1) {
    word.occurrences.forEach((item, index) => {
      const chip = button("occurrence-chip", `${index + 1} · ${timeLabel(item.start_ms)}`, () => ctx.showWord(wordId, index));
      chip.setAttribute("aria-pressed", String(index === position));
      occurrences.append(chip);
    });
  }

  const edit = element("details", "edit-meaning word-section");
  const textarea = element("textarea");
  textarea.value = own;
  textarea.placeholder = "Ví dụ: học (trong câu này nghĩa là “học tập”)";
  textarea.setAttribute("aria-label", "Nghĩa của bạn");
  const save = actionButton("plain", "💾", "Lưu nghĩa", async () => {
    try {
      await updateWord(wordId, {
        status: status || "saved",
        own_meaning: textarea.value.trim(),
        lesson_id: ctx.lesson.id,
        cue_id: occurrence.cue_id,
      });
    } catch (error) {
      window.alert(error.message);
      return;
    }
    ctx.onChange(wordId);
  });
  edit.append(element("summary", null, "Sửa / ghi chú nghĩa của bạn"), textarea, save);

  const explainBox = element("section", "explain-box");
  explainBox.hidden = true;
  container.replaceChildren(
    head,
    element("div", "action-groups", undefined),
    explainBox,
    section("Nghĩa", meaning),
    section(`Trong video · ${word.occurrence_count} lần`, context, occurrences),
    edit,
  );
  container.querySelector(".action-groups").append(listen, learn, keep);
}

/** Read an NDJSON stream from the backend, calling onEvent for each line. */
async function streamEvents(path, body, onEvent) {
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) await responseJson(response);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let newline;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line && onEvent(JSON.parse(line)) === false) {
        reader.cancel();
        return;
      }
    }
    if (done) return;
  }
}

/**
 * A lesson panel. "Xem chi tiết" shows every section to read; "Nghe giảng" is one
 * flowing talk about use only (how and where it is used, an example, a note if
 * any) — reading and meaning are on screen and are not read out. `plan` lists the sections in order; each has
 * a title and either fixed content from verified data (`build(facts)` returns
 * [lines, speech] — empty speech means "shown, not spoken"), `ai: key` filled by
 * the local model (spoken after `say`), or `examples` (only the first is spoken).
 * `optional` sections are hidden when the model leaves them out. Lessons are
 * normally written ahead of time, so they arrive at once from the cache.
 */
export function lessonPanel(box, ctx, { title, request, plan, speakIt }) {
  const run = Symbol("lesson");
  box.run = run;
  const status = element("p", "explain-status");
  const body = element("div", "lesson-sections");
  let narration = null;
  let spokenUpTo = 0;
  const sections = plan.map((item) => {
    const node = element("section", "lesson-section");
    const content = element("div", "lesson-content");
    node.append(element("h4", null, item.title), content);
    if (item.ai || item.examples) content.append(element("p", "sense-note", "AI đang soạn phần này…"));
    body.append(node);
    return { ...item, node, content, ready: false, speech: [] };
  });
  const narrate = () => {
    if (!narration || box.run !== run) return;
    while (spokenUpTo < sections.length && sections[spokenUpTo].ready) {
      const item = sections[spokenUpTo];
      if (item.speech.length) narration.add(item.speech);
      spokenUpTo += 1;
    }
    if (spokenUpTo === sections.length) narration.finish();
  };
  const fill = (item, lines, speech) => {
    item.content.replaceChildren(...lines.map((line) => (line instanceof Node ? line : element("p", null, line))));
    item.speech = speech;
    item.ready = true;
    narrate();
  };
  const intro = (item) => (item.say ? [{ text: item.say, lang: "vi" }] : []);
  const startSpeaking = () => {
    ctx.pause();
    narration = createNarration({
      onError: (error) => {
        if (box.run === run) status.textContent = `Không phát được âm thanh: ${error.message || error}`;
      },
    });
    if (!narration.available) {
      status.textContent = "Chưa có giọng đọc: chạy “pnpm setup:voices” trên máy chủ.";
      return;
    }
    status.textContent = "";
    spokenUpTo = 0;
    narrate();
  };
  const controls = element("div", "action-row");
  controls.append(
    actionButton("lesson", "🗣", "Nghe giảng", startSpeaking, { title: "Nghe giảng cách dùng, liền mạch và ngắn gọn" }),
    actionButton("plain", "⏹", "Dừng", () => stopSpeaking()),
    actionButton("plain", "↻", "Soạn lại", () => {
      if (window.confirm("Nhờ AI soạn lại bài giảng này? Bản cũ sẽ bị thay thế.")) {
        lessonPanel(box, ctx, { title, request: { ...request, refresh: true }, plan, speakIt: false });
      }
    }, { title: "Bài giảng chưa đúng? Nhờ AI soạn lại" }),
  );
  box.replaceChildren(element("h3", null, title), controls, status, body);
  box.hidden = false;
  if (speakIt) startSpeaking();

  streamEvents("/api/explain", request, (event) => {
    if (box.run !== run) return false;
    if (event.type === "facts") {
      plan.forEach((item, index) => item.build && fill(sections[index], ...item.build(event.facts)));
    } else if (event.type === "section") {
      const item = sections.find((candidate) => candidate.ai === event.key);
      if (item) fill(item, [event.text], [...intro(item), { text: event.text }]);
    } else if (event.type === "example") {
      const item = sections.find((candidate) => candidate.examples);
      if (!item) return true;
      const line = element("p", "lesson-example");
      line.append(chinese("span", "lesson-example-zh", event.zh), element("span", "lesson-example-pinyin", ` ${event.pinyin} `), `— ${event.vi}`);
      if (item.ready) item.content.append(line);
      else fill(item, [line], [...intro(item), { text: event.zh, lang: "zh", rate: 0.8 }, { text: `nghĩa là ${event.vi}.`, lang: "vi" }]);
    } else if (event.type === "error") {
      sections.filter((item) => (item.ai || item.examples) && !item.ready).forEach((item) => fill(item, [element("p", "sense-note", event.message)], []));
    } else if (event.type === "done") {
      sections.filter((item) => !item.ready).forEach((item) => {
        if (item.optional) item.node.hidden = true;
        fill(item, item.optional ? [] : [element("p", "sense-note", "AI chưa viết được phần này.")], []);
      });
      body.append(element("p", "ai-label", "Phần cách dùng và ví dụ do AI chạy trên máy của bạn soạn — có thể chưa chính xác."));
    }
    return true;
  }).catch((error) => {
    if (box.run === run) status.textContent = error.message;
  });
}

function tipsSection(subject) {
  return (facts) => [facts.tips.length ? facts.tips : [`${subject} không có âm đặc biệt khó với người Việt.`], []];
}

/** Word details: reading, meaning, pronunciation, where/how it is used, how natives say it, notes. */
export function explainWord(box, ctx, word, occurrence, cue, inContext, { speakIt }) {
  const surface = occurrence.surface || word.word;
  const meaning = ownMeaning(word.id) || cleanSenses(word.definitions_vi).senses.slice(0, 3).join("; ");
  lessonPanel(box, ctx, {
    title: `Chi tiết từ: ${surface}`,
    request: { lesson_id: ctx.lesson.id, word_id: word.id, cue_id: occurrence.cue_id },
    speakIt,
    plan: [
      {
        title: "Đọc thế nào",
        build: (facts) => {
          const lines = [`${surface} đọc là ${facts.syllables.map((item) => item.pinyin).join(" ")}.`];
          facts.syllables.forEach((item) => lines.push(`${item.character} (${item.pinyin}): ${toneDescription(item.pinyin)}.`));
          return [lines, []];
        },
      },
      {
        title: "Nghĩa",
        build: () => {
          const lines = [];
          if (meaning) lines.push(`Nghĩa: ${meaning}.`);
          if (inContext) lines.push(`Trong câu này: ${inContext.text}.`);
          lines.push(chinese("p", "lesson-zh", occurrence.cue_text));
          if (cue?.translation_vi) lines.push(`→ ${cue.translation_vi}`);
          return [lines, []];
        },
      },
      { title: "Lưu ý khi phát âm", build: tipsSection("Từ này") },
      { title: "Dùng thế nào, ở đâu", ai: "cach_dung" },
      { title: "Người bản xứ nói thế nào", examples: true, say: "Chẳng hạn, người bản xứ hay nói," },
      { title: "Lưu ý", ai: "luu_y", optional: true },
    ],
  });
}

/** Sentence details: reading, meaning word by word, pronunciation, structure, when it is said. */
export function explainSentence(box, ctx, cueIndex, { speakIt }) {
  const cue = ctx.lesson.cues[cueIndex];
  if (!cue) return;
  const glossary = cue.segments
    .filter((segment) => segment.vocabulary_id && ctx.wordsById.has(segment.vocabulary_id))
    .map((segment) => ({ text: segment.text, pinyin: segment.pinyin, meaning: firstMeaning(ctx.wordsById.get(segment.vocabulary_id)) }))
    .filter((item) => item.meaning);
  lessonPanel(box, ctx, {
    title: "Chi tiết câu",
    request: { lesson_id: ctx.lesson.id, cue_id: cue.id },
    speakIt,
    plan: [
      {
        title: "Đọc thế nào",
        build: (facts) => [
          [chinese("p", "lesson-zh", chineseText(cue)), facts.syllables.map((item) => item.pinyin).join(" ")],
          [],
        ],
      },
      {
        title: "Nghĩa",
        build: () => [
          [...(cue.translation_vi ? [`Nghĩa: ${cue.translation_vi}`] : []), ...glossary.map((item) => `${item.text} (${item.pinyin || ""}): ${item.meaning}`)],
          [],
        ],
      },
      { title: "Lưu ý khi phát âm", build: tipsSection("Câu này") },
      { title: "Thường nói khi nào, ở đâu", ai: "giao_tiep" },
      { title: "Cấu trúc câu", ai: "cau_truc" },
      { title: "Câu tương tự", examples: true, say: "Một câu tương tự là," },
    ],
  });
}

/** Buttons for studying one sentence: listen, practice, lesson, save/learned. */
export function sentenceActions(ctx, cueIndex, explainBox) {
  const cue = ctx.lesson.cues[cueIndex];
  const status = sentenceStatus(ctx.lesson.id, cue.id);
  const pinyin = cue.segments.map((segment) => segment.pinyin).filter(Boolean).join(" ");
  const setStatus = async (next) => {
    try {
      await updateSentence(ctx.lesson.id, cue.id, next);
    } catch (error) {
      window.alert(error.message);
      return;
    }
    ctx.onChange();
  };
  const listen = actionRow("Nghe");
  listen.append(
    actionButton("listen", "▶", "Câu gốc", () => playSentence(ctx, cueIndex, chineseText(cue)), { title: "Nghe câu này trong video" }),
    actionButton("listen", "🔈", "Đọc chậm", () => speak(chineseText(cue), 0.65)),
  );
  const learn = actionRow("Học");
  learn.append(
    actionButton("lesson", "📖", "Xem chi tiết câu", () => explainSentence(explainBox, ctx, cueIndex, { speakIt: false })),
    actionButton("lesson", "🗣", "Nghe giảng câu", () => explainSentence(explainBox, ctx, cueIndex, { speakIt: true })),
    actionButton("practice", "🎙", "Đọc thử", () =>
      openPractice({
        target: chineseText(cue),
        pinyin,
        translation: cue.translation_vi,
        kind: "sentence",
        itemId: status ? sentenceKey(ctx.lesson.id, cue.id) : null,
        playModel: () => playSentence(ctx, cueIndex, chineseText(cue)),
        onScored: () => ctx.onChange(),
      }),
    ),
  );
  const keep = actionRow("Lưu");
  keep.append(
    actionButton("save", status ? "★" : "☆", status ? "Đã lưu câu" : "Lưu câu", () => !status && setStatus("saved"), { pressed: Boolean(status) }),
    actionButton("learned", "✓", status === "learned" ? "Đã thuộc câu" : "Đánh dấu thuộc", () => setStatus(status === "learned" ? "saved" : "learned"), {
      pressed: status === "learned",
    }),
  );
  if (ctx.openInVideo) keep.append(actionButton("video", "🎬", "Xem trong video", () => ctx.openInVideo({ cueId: cue.id })));
  const groups = element("div", "action-groups");
  groups.append(listen, learn, keep);
  return groups;
}

/** A sentence with clickable words (pinyin above), its translation and study actions. */
export function renderSentenceCard(container, ctx, cueIndex) {
  const cue = ctx.lesson.cues[cueIndex];
  const text = element("p", "now-text");
  text.lang = "zh";
  for (const segment of cue.segments) {
    if (!segment.vocabulary_id || !ctx.wordsById.has(segment.vocabulary_id)) {
      text.append(segment.foreign ? element("span", "foreign-text", segment.text) : segment.text);
      continue;
    }
    const word = ctx.wordsById.get(segment.vocabulary_id);
    const status = wordStatus(segment.vocabulary_id);
    const token = button(`token${status === "learned" ? " is-known" : status === "saved" ? " is-saved" : ""}`, null, () => {
      const index = word.occurrences.findIndex((item) => item.cue_id === cue.id);
      ctx.showWord(segment.vocabulary_id, Math.max(0, index));
    });
    token.dataset.wordId = segment.vocabulary_id;
    token.title = firstMeaning(word);
    token.append(element("span", "token-pinyin", segment.pinyin || word.pinyin), element("span", "token-hanzi", segment.text));
    text.append(token);
  }
  const explainBox = element("section", "explain-box");
  explainBox.hidden = true;
  container.replaceChildren(
    element("p", "card-kicker", `Câu · ${timeLabel(cue.start_ms)}`),
    text,
    element("p", "now-translation", cue.translation_vi || ""),
    sentenceActions(ctx, cueIndex, explainBox),
    explainBox,
  );
}
