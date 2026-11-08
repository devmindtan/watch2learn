const $ = (selector) => document.querySelector(selector);

const form = $("#lesson-form");
const videoInput = $("#video-file");
const subtitleInput = $("#subtitle-file");
const dropzone = $("#dropzone");
const videoName = $("#video-name");
const formNote = $("#form-note");
const readiness = $("#readiness");
const progressBox = $("#job-progress");
const progressBar = $("#job-progress-bar");
const progressStage = $("#job-stage");
const progressPercent = $("#job-percent");
const recentList = $("#recent-list");
const recentEmpty = $("#recent-empty");

const library = $("#library");
const workspace = $("#workspace");
const libraryButton = $("#library-button");
const lessonTitle = $("#lesson-title");
const viewToggles = $("#view-toggles");
const pinyinToggle = $("#pinyin-toggle");
const translationToggle = $("#translation-toggle");

const video = $("#video");
const videoMissing = $("#video-missing");
const reattachInput = $("#reattach-file");
const nowIndex = $("#now-index");
const nowTime = $("#now-time");
const nowText = $("#now-text");
const nowTranslation = $("#now-translation");
const prevButton = $("#prev-cue");
const nextButton = $("#next-cue");
const replayButton = $("#replay-cue");
const loopButton = $("#loop-cue");
const speakCueButton = $("#speak-cue");

const wordDetail = $("#word-detail");
const tabs = [$("#tab-transcript"), $("#tab-vocabulary")];
const transcriptPanel = $("#panel-transcript");
const transcript = $("#transcript");
const cueCount = $("#cue-count");
const vocabularyList = $("#vocabulary-list");
const vocabSearch = $("#vocab-search");
const vocabEmpty = $("#vocab-empty");
const wordCount = $("#word-count");
const dictionaryNotice = $("#dictionary-notice");

const state = {
  lesson: null,
  videoUrl: null,
  activeCue: -1,
  selectedWord: null,
  selectedOccurrence: 0,
  loop: false,
  clipEnd: null,
  followTranscript: true,
  filter: "all",
  health: null,
};
let followTimer = null;
const wordsById = new Map();
const cueIndexById = new Map();

/* ---------- Persistence (per-viewer conveniences) ---------- */

function readStore(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

function writeStore(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: keep in-memory state only */
  }
}

const knownWords = new Set(readStore("watch2learn-known", []));
const ownMeanings = readStore("watch2learn-meanings", {});
const preferences = readStore("watch2learn-preferences", { pinyin: true, translation: true });

/* ---------- Helpers ---------- */

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function button(className, text, onClick) {
  const node = element("button", className, text);
  node.type = "button";
  if (onClick) node.addEventListener("click", onClick);
  return node;
}

function timeLabel(milliseconds) {
  const seconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = String(seconds % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

function plain(text) {
  return (text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").toLowerCase();
}

async function responseJson(response) {
  let result = {};
  try {
    result = await response.json();
  } catch {
    /* non-JSON error body */
  }
  if (!response.ok) {
    const detail = Array.isArray(result.detail) ? "Dữ liệu gửi lên không hợp lệ." : result.detail;
    throw new Error(detail || `Yêu cầu không thành công (${response.status}).`);
  }
  return result;
}

const delay = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

/* ---------- Speech (offline browser/OS voices) ---------- */

let chineseVoice = null;
const canSpeak = "speechSynthesis" in window;

function pickVoice() {
  if (!canSpeak) return;
  const voices = speechSynthesis.getVoices();
  chineseVoice =
    voices.find((voice) => /^zh[-_]CN/i.test(voice.lang) && voice.localService) ||
    voices.find((voice) => /^zh[-_]CN/i.test(voice.lang)) ||
    voices.find((voice) => /^(zh|cmn)/i.test(voice.lang)) ||
    null;
  speakCueButton.disabled = !canSpeak;
  speakCueButton.title = chineseVoice
    ? `Đọc chậm bằng giọng máy (${chineseVoice.name})`
    : "Máy chưa có giọng đọc tiếng Trung — dùng “Nghe lại” để nghe giọng gốc trong video.";
}

function speak(text, rate = 0.75) {
  if (!canSpeak || !text) return;
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = chineseVoice?.lang || "zh-CN";
  if (chineseVoice) utterance.voice = chineseVoice;
  utterance.rate = rate;
  speechSynthesis.speak(utterance);
}

if (canSpeak) {
  pickVoice();
  speechSynthesis.addEventListener?.("voiceschanged", pickVoice);
} else {
  speakCueButton.disabled = true;
  speakCueButton.title = "Trình duyệt không hỗ trợ đọc văn bản.";
}

/* ---------- Library ---------- */

const stageLabels = {
  uploaded: "Đã nhận video",
  "probing-video": "Đang đọc cấu trúc video",
  "reading-subtitle": "Đang đọc phụ đề bạn cung cấp",
  "reading-embedded-subtitle": "Đang đọc phụ đề nhúng trong video",
  "extracting-audio": "Đang tách âm thanh",
  "transcribing-mandarin": "Đang nghe và nhận dạng tiếng Trung",
  translating: "Đang dịch sang tiếng Việt",
  "analyzing-vocabulary": "Đang tách từ và tra từ điển",
  complete: "Bài học đã sẵn sàng",
};

const methodLabels = {
  "faster-whisper": "nhận dạng giọng nói",
  "uploaded-subtitle": "phụ đề tải lên",
  "embedded-subtitle": "phụ đề trong video",
};

function setNote(text, isError = false) {
  formNote.textContent = text;
  formNote.classList.toggle("is-error", isError);
}

function showProgress(job) {
  progressBox.hidden = false;
  progressBar.value = job.progress;
  progressBar.textContent = `${job.progress}%`;
  progressStage.textContent = stageLabels[job.stage] || "Đang xử lý trên máy…";
  progressPercent.textContent = `${job.progress}%`;
}

async function waitForJob(initialJob) {
  let job = initialJob;
  while (job.status === "queued" || job.status === "processing") {
    showProgress(job);
    await delay(800);
    job = await responseJson(await fetch(`/api/jobs/${job.id}`));
  }
  showProgress(job);
  if (job.status === "failed") throw new Error(job.error || "Không thể xử lý video này.");
  return job.result;
}

async function loadHealth() {
  try {
    state.health = await responseJson(await fetch("/api/health"));
  } catch {
    state.health = null;
    return;
  }
  const items = [
    ["asr_model_ready", "Nhận dạng giọng nói", "pnpm setup:asr"],
    ["dictionary_loaded", "Từ điển Trung–Anh", "pnpm setup:dictionary"],
    ["vietnamese_dictionary_loaded", "Từ điển Trung–Việt", "pnpm setup:dictionary"],
    ["translation_model_ready", "Dịch câu offline", "pnpm setup:translation"],
  ];
  readiness.replaceChildren(
    ...items.map(([key, label, command]) => {
      const ready = Boolean(state.health[key]);
      const item = element("li", ready ? "" : "is-missing", ready ? label : `${label}: chạy ${command}`);
      return item;
    }),
  );
}

async function loadRecentLessons() {
  try {
    const lessons = await responseJson(await fetch("/api/lessons"));
    recentEmpty.hidden = lessons.length > 0;
    recentList.replaceChildren(
      ...lessons.map((item) => {
        const row = element("li");
        const date = new Date(item.updated_at).toLocaleDateString("vi-VN");
        const method = methodLabels[item.transcript_method] || item.transcript_method || "";
        const open = button("recent-lesson", null, () => openSavedLesson(item.id));
        open.append(
          element("span", null, item.filename),
          element("small", null, `${item.vocabulary_count} từ · ${method} · ${date}`),
        );
        row.append(open);
        return row;
      }),
    );
  } catch (error) {
    recentEmpty.hidden = false;
    recentEmpty.textContent = `Không thể đọc bài học đã lưu: ${error.message}`;
  }
}

async function openSavedLesson(id) {
  try {
    const lesson = await responseJson(await fetch(`/api/lessons/${encodeURIComponent(id)}`));
    setVideoSource(null);
    openLesson({ ...lesson, id });
  } catch (error) {
    setNote(error.message, true);
    showLibrary();
  }
}

function setVideoSource(file) {
  if (state.videoUrl) URL.revokeObjectURL(state.videoUrl);
  state.videoUrl = file ? URL.createObjectURL(file) : null;
  if (state.videoUrl) {
    video.src = state.videoUrl;
  } else {
    video.removeAttribute("src");
    video.load();
  }
  video.hidden = !state.videoUrl;
  videoMissing.hidden = Boolean(state.videoUrl);
}

function showLibrary() {
  video.pause();
  if (canSpeak) speechSynthesis.cancel();
  workspace.hidden = true;
  library.hidden = false;
  libraryButton.hidden = true;
  lessonTitle.hidden = true;
  viewToggles.hidden = true;
  if (location.hash) history.replaceState(null, "", location.pathname);
  document.title = "Watch2Learn · Học tiếng Trung qua video";
  loadRecentLessons();
}

function selectVideoFile(file) {
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  videoInput.files = transfer.files;
  updateVideoName();
}

function updateVideoName() {
  const file = videoInput.files[0];
  videoName.textContent = file ? file.name : "Chọn hoặc kéo thả video tiếng Trung";
  dropzone.classList.toggle("has-file", Boolean(file));
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const mediaFile = videoInput.files[0];
  const subtitleFile = subtitleInput.files[0];
  if (!mediaFile) return;
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  setNote("Đang gửi video tới bộ xử lý trên máy này…");
  showProgress({ progress: 0, stage: "uploaded" });
  try {
    const body = new FormData();
    body.append("video", mediaFile);
    if (subtitleFile) body.append("subtitle", subtitleFile);
    const job = await responseJson(await fetch("/api/lessons/mandarin-video", { method: "POST", body }));
    const lesson = await waitForJob(job);
    setNote("Bài học đã sẵn sàng và được lưu trên máy này.");
    setVideoSource(mediaFile);
    openLesson({ ...lesson, id: lesson.id || job.id });
    progressBox.hidden = true;
  } catch (error) {
    setNote(error.message, true);
    progressBox.hidden = true;
  } finally {
    submit.disabled = false;
  }
});

videoInput.addEventListener("change", updateVideoName);
for (const type of ["dragenter", "dragover"]) {
  dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    dropzone.classList.add("is-dragging");
  });
}
for (const type of ["dragleave", "drop"]) {
  dropzone.addEventListener(type, () => dropzone.classList.remove("is-dragging"));
}
dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  selectVideoFile(event.dataTransfer.files[0]);
});

reattachInput.addEventListener("change", () => {
  const file = reattachInput.files[0];
  if (!file) return;
  setVideoSource(file);
  reattachInput.value = "";
  if (state.activeCue >= 0) video.currentTime = state.lesson.cues[state.activeCue].start_ms / 1000;
});

libraryButton.addEventListener("click", showLibrary);
$(".brand").addEventListener("click", (event) => {
  if (!state.lesson) return;
  event.preventDefault();
  showLibrary();
});

/* ---------- Lesson rendering ---------- */

function openLesson(lesson) {
  state.lesson = lesson;
  state.activeCue = -1;
  state.selectedWord = null;
  state.loop = false;
  state.clipEnd = null;
  wordsById.clear();
  cueIndexById.clear();
  lesson.vocabulary.forEach((word) => wordsById.set(word.id, word));
  lesson.cues.forEach((cue, index) => cueIndexById.set(cue.id, index));

  library.hidden = true;
  workspace.hidden = false;
  libraryButton.hidden = false;
  viewToggles.hidden = false;
  lessonTitle.hidden = false;
  lessonTitle.textContent = lesson.filename || "Bài học";
  document.title = `${lesson.filename || "Bài học"} · Watch2Learn`;
  if (lesson.id) history.replaceState(null, "", `#lesson=${encodeURIComponent(lesson.id)}`);

  loopButton.setAttribute("aria-pressed", "false");
  wordDetail.hidden = true;
  vocabSearch.value = "";
  const missingDictionary = [
    !lesson.dictionary?.loaded && "Trung–Anh (CC-CEDICT)",
    !lesson.vietnamese_dictionary?.loaded && "Trung–Việt (CVDICT)",
  ].filter(Boolean);
  dictionaryNotice.hidden = missingDictionary.length === 0;
  dictionaryNotice.textContent = `Chưa có từ điển offline ${missingDictionary.join(", ")}. Chạy pnpm setup:dictionary rồi mở lại bài học.`;

  renderTranscript();
  renderVocabulary();
  selectTab(0);
  setActiveCue(0, { scroll: false });
  transcriptPanel.scrollTop = 0;
  backfillTranslations();
}

function renderCueText(container, cue, { compact = false } = {}) {
  container.replaceChildren();
  for (const segment of cue.segments) {
    if (!segment.vocabulary_id) {
      container.append(segment.text);
      continue;
    }
    const word = wordsById.get(segment.vocabulary_id);
    const token = button(`token${knownWords.has(segment.vocabulary_id) ? " is-known" : ""}`);
    token.dataset.wordId = segment.vocabulary_id;
    if (segment.vocabulary_id === state.selectedWord) token.classList.add("is-selected");
    const meaning = word ? firstMeaning(word) : "";
    const reading = segment.pinyin || word?.pinyin || "";
    token.setAttribute("aria-label", `${segment.text}, ${reading}${meaning ? `, ${meaning}` : ""}`);
    if (!compact) token.title = meaning;
    token.append(element("span", "token-pinyin", reading), element("span", "token-hanzi", segment.text));
    token.addEventListener("click", (event) => {
      event.stopPropagation();
      const occurrence = word?.occurrences.findIndex((item) => item.cue_id === cue.id) ?? 0;
      showWord(segment.vocabulary_id, Math.max(0, occurrence));
    });
    container.append(token);
  }
}

function translationText(cue) {
  if (cue.translation_vi) return cue.translation_vi;
  if (cue.translation_vi === "") return "";
  return state.health?.translation_model_ready ? "Đang dịch…" : "";
}

function updateTranslationNode(node, cue) {
  node.textContent = translationText(cue);
  node.classList.toggle("is-pending", !cue.translation_vi);
}

function renderTranscript() {
  const cues = state.lesson.cues;
  cueCount.textContent = cues.length;
  transcript.replaceChildren(
    ...cues.map((cue, index) => {
      const row = element("li", "cue-row");
      row.dataset.index = index;
      const time = button("cue-time", timeLabel(cue.start_ms), () => playFromCue(index));
      time.setAttribute("aria-label", `Phát từ ${timeLabel(cue.start_ms)}`);
      const body = element("div");
      const text = element("p", "cue-text");
      text.lang = "zh";
      renderCueText(text, cue, { compact: true });
      const translation = element("p", "cue-translation translation");
      translation.dataset.translationFor = cue.id;
      updateTranslationNode(translation, cue);
      body.append(text, translation);
      row.append(time, body);
      return row;
    }),
  );
}

function firstMeaning(word) {
  const own = ownMeanings[word.id];
  if (own) return own;
  const senses = cleanSenses(word.definitions_vi).senses;
  if (senses.length) return senses[0];
  return cleanSenses(word.definitions).senses[0] || "";
}

function cleanSenses(definitions = []) {
  const senses = [];
  const notes = [];
  for (const definition of definitions) {
    const classifier = definition.match(/^(?:LT|CL):(.*)$/);
    if (classifier) notes.push(`Lượng từ: ${classifier[1].replace(/\[[^\]]*]/g, "").replace(/,/g, ", ")}`);
    else senses.push(definition);
  }
  return { senses, notes };
}

function matchesFilter(word, query) {
  const known = knownWords.has(word.id);
  if (state.filter === "known" && !known) return false;
  if (state.filter === "learning" && known) return false;
  if (!query) return true;
  const haystack = plain(
    [word.word, word.traditional, word.pinyin, word.pinyin_numbered, ...(word.definitions_vi || []), ...word.definitions, ownMeanings[word.id]]
      .filter(Boolean)
      .join(" "),
  );
  return haystack.replace(/\s+/g, "").includes(query.replace(/\s+/g, "")) || haystack.includes(query);
}

function renderVocabulary() {
  const query = plain(vocabSearch.value.trim());
  const words = state.lesson.vocabulary.filter((word) => matchesFilter(word, query));
  const learning = state.lesson.vocabulary.filter((word) => !knownWords.has(word.id)).length;
  wordCount.textContent = `${learning}/${state.lesson.vocabulary.length}`;
  wordCount.title = `${learning} từ đang học trên tổng ${state.lesson.vocabulary.length} từ`;
  vocabEmpty.hidden = words.length > 0;
  vocabularyList.replaceChildren(
    ...words.map((word) => {
      const known = knownWords.has(word.id);
      const item = element("li", known ? "is-known" : "");
      const row = button(`word-row${word.id === state.selectedWord ? " is-selected" : ""}`, null, () => showWord(word.id));
      row.dataset.wordId = word.id;
      const hanzi = element("strong", null, word.word);
      hanzi.lang = "zh";
      const text = element("span", "word-row-text");
      text.append(element("span", "word-row-pinyin", word.pinyin), element("span", "word-row-meaning", firstMeaning(word)));
      row.append(hanzi, text, element("span", "frequency", `${word.occurrence_count}×`));
      const check = button("known-check", "✓", () => toggleKnown(word.id));
      check.setAttribute("aria-pressed", String(known));
      check.setAttribute("aria-label", known ? `Bỏ đánh dấu đã biết ${word.word}` : `Đánh dấu đã biết ${word.word}`);
      item.append(row, check);
      return item;
    }),
  );
}

function toggleKnown(id) {
  knownWords.has(id) ? knownWords.delete(id) : knownWords.add(id);
  writeStore("watch2learn-known", [...knownWords]);
  document.querySelectorAll(`.token[data-word-id="${id}"]`).forEach((token) => token.classList.toggle("is-known", knownWords.has(id)));
  renderVocabulary();
  if (state.selectedWord === id) showWord(id, state.selectedOccurrence, { keepScroll: true });
}

function highlightSelection() {
  document.querySelectorAll(".is-selected[data-word-id]").forEach((node) => node.classList.remove("is-selected"));
  if (state.selectedWord) {
    document.querySelectorAll(`[data-word-id="${state.selectedWord}"]`).forEach((node) => node.classList.add("is-selected"));
  }
}

function section(title, ...children) {
  const node = element("section", "word-section");
  node.append(element("h3", null, title), ...children);
  return node;
}

function showWord(id, occurrenceIndex = 0, { keepScroll = false } = {}) {
  const word = wordsById.get(id);
  if (!word) return;
  const scroll = wordDetail.scrollTop;
  state.selectedWord = id;
  state.selectedOccurrence = Math.min(occurrenceIndex, word.occurrences.length - 1);
  const occurrence = word.occurrences[state.selectedOccurrence];
  const known = knownWords.has(id);

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
  const reading = occurrence.pinyin || word.pinyin;
  identity.append(hanzi, element("p", "word-pinyin", reading));
  const actions = element("div", "word-actions");
  const speakButton = button("control-button", "🔈 Phát âm", () => speak(occurrence.surface || word.word, 0.7));
  speakButton.disabled = !canSpeak;
  speakButton.title = speakCueButton.title.replace("Đọc chậm", "Phát âm");
  const knownButton = button("control-button known-button", known ? "✓ Đã biết" : "Đánh dấu đã biết", () => toggleKnown(id));
  knownButton.setAttribute("aria-pressed", String(known));
  const close = button("close-button", "×", closeWord);
  close.setAttribute("aria-label", "Đóng chi tiết từ");
  actions.append(speakButton, knownButton, close);
  head.append(identity, actions);

  const meaning = element("div");
  if (ownMeanings[id]) meaning.append(element("p", "own-meaning", `Nghĩa của bạn: ${ownMeanings[id]}`));
  const vietnamese = cleanSenses(word.definitions_vi);
  const english = cleanSenses(word.definitions);
  if (vietnamese.senses.length) {
    const list = element("ol", "senses");
    vietnamese.senses.forEach((sense) => list.append(element("li", null, sense)));
    meaning.append(list);
  } else if (!ownMeanings[id]) {
    meaning.append(element("p", "sense-note", "Chưa có nghĩa tiếng Việt trong từ điển offline cho từ này."));
  }
  const notes = vietnamese.notes.length ? vietnamese.notes : english.notes;
  notes.forEach((note) => meaning.append(element("p", "sense-note", note)));
  if (word.alternatives?.length) {
    const details = element("details", "english");
    details.append(element("summary", null, `Cách đọc / nghĩa khác (${word.alternatives.length})`));
    const list = element("ul", "alternatives");
    for (const alternative of word.alternatives) {
      const item = element("li");
      const senses = alternative.definitions_vi?.length ? alternative.definitions_vi : alternative.definitions;
      item.append(element("strong", "alt-pinyin", alternative.pinyin), ` ${senses.join("; ")}`);
      list.append(item);
    }
    details.append(list);
    meaning.append(details);
  }
  if (english.senses.length) {
    const details = element("details", "english");
    details.append(element("summary", null, "Nghĩa tiếng Anh (CC-CEDICT)"), element("p", null, english.senses.join("; ")));
    meaning.append(details);
  }

  const cue = state.lesson.cues[cueIndexById.get(occurrence.cue_id)];
  const context = element("div", "context");
  if (occurrence.before_text) {
    const before = element("p", "context-neighbor", occurrence.before_text);
    before.lang = "zh";
    context.append(before);
  }
  const current = element("p", "context-current");
  current.lang = "zh";
  const text = occurrence.cue_text;
  const { start_offset: start, end_offset: end } = occurrence;
  if (Number.isInteger(start) && Number.isInteger(end) && end <= text.length) {
    current.append(text.slice(0, start), element("mark", null, text.slice(start, end)), text.slice(end));
  } else {
    current.textContent = text;
  }
  context.append(current);
  if (cue) {
    const translation = element("p", "context-translation translation");
    translation.dataset.translationFor = cue.id;
    updateTranslationNode(translation, cue);
    context.append(translation);
  }
  if (occurrence.after_text) {
    const after = element("p", "context-neighbor", occurrence.after_text);
    after.lang = "zh";
    context.append(after);
  }
  const contextActions = element("div", "context-actions");
  const index = cueIndexById.get(occurrence.cue_id);
  contextActions.append(
    button("control-button", "▶ Nghe câu này", () => playClip(index)),
    button("control-button", "🔈 Đọc chậm", () => speak(occurrence.cue_text)),
  );
  if (word.occurrences.length > 1) {
    word.occurrences.forEach((item, position) => {
      const chip = button("occurrence-chip", `${position + 1} · ${timeLabel(item.start_ms)}`, () => showWord(id, position, { keepScroll: true }));
      chip.setAttribute("aria-pressed", String(position === state.selectedOccurrence));
      chip.setAttribute("aria-label", `Lần xuất hiện ${position + 1} tại ${timeLabel(item.start_ms)}`);
      contextActions.append(chip);
    });
  }

  const edit = element("details", "edit-meaning word-section");
  const textarea = element("textarea");
  textarea.value = ownMeanings[id] || "";
  textarea.placeholder = "Ví dụ: học (trong câu này nghĩa là “học tập”)";
  textarea.setAttribute("aria-label", "Nghĩa của bạn");
  const save = button("control-button", "Lưu nghĩa", () => {
    const value = textarea.value.trim();
    if (value) ownMeanings[id] = value;
    else delete ownMeanings[id];
    writeStore("watch2learn-meanings", ownMeanings);
    renderVocabulary();
    showWord(id, state.selectedOccurrence, { keepScroll: true });
  });
  edit.append(element("summary", null, "Sửa / ghi chú nghĩa của bạn"), textarea, save);

  wordDetail.replaceChildren(
    head,
    section("Nghĩa tiếng Việt", meaning),
    section(`Trong video · ${word.occurrence_count} lần`, context, contextActions),
    edit,
  );
  wordDetail.hidden = false;
  wordDetail.scrollTop = keepScroll ? scroll : 0;
  highlightSelection();
}

function closeWord() {
  state.selectedWord = null;
  wordDetail.hidden = true;
  highlightSelection();
}

/* ---------- Playback ---------- */

function hasVideo() {
  return Boolean(state.videoUrl);
}

function setActiveCue(index, { scroll = true } = {}) {
  const cues = state.lesson?.cues || [];
  if (index < 0 || index >= cues.length) return;
  const changed = index !== state.activeCue;
  state.activeCue = index;
  const cue = cues[index];
  nowIndex.textContent = `Câu ${index + 1}/${cues.length}`;
  nowTime.textContent = timeLabel(cue.start_ms);
  prevButton.disabled = index === 0;
  nextButton.disabled = index === cues.length - 1;
  if (!changed && nowText.childElementCount) return;
  renderCueText(nowText, cue);
  nowTranslation.dataset.translationFor = cue.id;
  updateTranslationNode(nowTranslation, cue);
  transcript.querySelector(".cue-row.is-active")?.classList.remove("is-active");
  const row = transcript.children[index];
  row?.classList.add("is-active");
  if (scroll && state.followTranscript && row && !transcriptPanel.hidden) {
    const panelBox = transcriptPanel.getBoundingClientRect();
    const rowBox = row.getBoundingClientRect();
    if (rowBox.top < panelBox.top || rowBox.bottom > panelBox.bottom) {
      transcriptPanel.scrollTop += rowBox.top - panelBox.top - panelBox.height / 3;
    }
  }
}

function seekTo(index) {
  const cue = state.lesson.cues[index];
  setActiveCue(index);
  if (!hasVideo()) return false;
  video.currentTime = cue.start_ms / 1000;
  return true;
}

function playFromCue(index) {
  state.clipEnd = null;
  if (seekTo(index)) video.play().catch(() => {});
}

function playClip(index) {
  if (index === undefined || index < 0) return;
  if (!seekTo(index)) {
    speak(state.lesson.cues[index].text);
    return;
  }
  state.clipEnd = state.loop ? null : state.lesson.cues[index].end_ms;
  video.play().catch(() => {});
}

function stepCue(offset) {
  const target = Math.min(Math.max(state.activeCue + offset, 0), state.lesson.cues.length - 1);
  if (state.loop || !video.paused) playClip(target);
  else seekTo(target);
}

function toggleLoop() {
  state.loop = !state.loop;
  loopButton.setAttribute("aria-pressed", String(state.loop));
  if (state.loop) playClip(state.activeCue);
}

function cueIndexAt(milliseconds) {
  const cues = state.lesson.cues;
  let low = 0;
  let high = cues.length - 1;
  let found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (cues[middle].start_ms <= milliseconds) {
      found = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return found;
}

video.addEventListener("timeupdate", () => {
  if (!state.lesson) return;
  const now = video.currentTime * 1000;
  const active = state.lesson.cues[state.activeCue];
  if (state.loop && active && !video.paused && (now >= active.end_ms || now < active.start_ms - 300)) {
    video.currentTime = active.start_ms / 1000;
    return;
  }
  if (state.clipEnd !== null && now >= state.clipEnd - 80) {
    // Stop just inside the sentence so the active cue does not jump to the next one.
    video.pause();
    video.currentTime = Math.max(active?.start_ms ?? 0, state.clipEnd - 120) / 1000;
    state.clipEnd = null;
    return;
  }
  if (state.loop) return;
  const index = cueIndexAt(now);
  if (index !== -1 && index !== state.activeCue) setActiveCue(index);
});
video.addEventListener("seeking", () => {
  if (!state.loop && state.clipEnd !== null && video.currentTime * 1000 > state.clipEnd) state.clipEnd = null;
});

prevButton.addEventListener("click", () => stepCue(-1));
nextButton.addEventListener("click", () => stepCue(1));
replayButton.addEventListener("click", () => playClip(state.activeCue));
loopButton.addEventListener("click", toggleLoop);
nowTime.addEventListener("click", () => playFromCue(state.activeCue));
speakCueButton.addEventListener("click", () => speak(state.lesson?.cues[state.activeCue]?.text));

function pauseFollowing() {
  state.followTranscript = false;
  window.clearTimeout(followTimer);
  followTimer = window.setTimeout(() => {
    state.followTranscript = true;
  }, 5000);
}
transcriptPanel.addEventListener("wheel", pauseFollowing, { passive: true });
transcriptPanel.addEventListener("touchmove", pauseFollowing, { passive: true });

/* ---------- Translations for lessons saved before offline translation ---------- */

async function backfillTranslations() {
  const lesson = state.lesson;
  if (!state.health?.translation_model_ready) return;
  const missing = lesson.cues.filter((cue) => cue.translation_vi === null || cue.translation_vi === undefined);
  for (let start = 0; start < missing.length; start += 40) {
    const batch = missing.slice(start, start + 40);
    try {
      const result = await responseJson(
        await fetch("/api/translate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ texts: batch.map((cue) => cue.text.slice(0, 500)) }),
        }),
      );
      if (state.lesson !== lesson) return;
      batch.forEach((cue, index) => {
        cue.translation_vi = result.translations[index] ?? "";
        document.querySelectorAll(`[data-translation-for="${cue.id}"]`).forEach((node) => updateTranslationNode(node, cue));
      });
    } catch {
      batch.forEach((cue) => {
        cue.translation_vi = "";
        document.querySelectorAll(`[data-translation-for="${cue.id}"]`).forEach((node) => updateTranslationNode(node, cue));
      });
    }
  }
}

/* ---------- Tabs, filters, toggles, shortcuts ---------- */

function selectTab(index) {
  tabs.forEach((tab, position) => {
    const selected = position === index;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    $(`#${tab.getAttribute("aria-controls")}`).hidden = !selected;
  });
}
tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => selectTab(index));
  tab.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    event.stopPropagation();
    const next = (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    selectTab(next);
    tabs[next].focus();
  });
});

vocabSearch.addEventListener("input", renderVocabulary);
document.querySelectorAll("[data-filter]").forEach((filterButton) => {
  filterButton.addEventListener("click", () => {
    state.filter = filterButton.dataset.filter;
    document.querySelectorAll("[data-filter]").forEach((item) => item.setAttribute("aria-pressed", String(item === filterButton)));
    renderVocabulary();
  });
});

function applyPreferences() {
  pinyinToggle.checked = preferences.pinyin;
  translationToggle.checked = preferences.translation;
  document.body.classList.toggle("hide-pinyin", !preferences.pinyin);
  document.body.classList.toggle("hide-translation", !preferences.translation);
  writeStore("watch2learn-preferences", preferences);
}
pinyinToggle.addEventListener("change", () => {
  preferences.pinyin = pinyinToggle.checked;
  applyPreferences();
});
translationToggle.addEventListener("change", () => {
  preferences.translation = translationToggle.checked;
  applyPreferences();
});

document.addEventListener("keydown", (event) => {
  if (workspace.hidden || event.ctrlKey || event.metaKey || event.altKey) return;
  const target = event.target;
  if (target.closest?.("input, textarea, select, [contenteditable='true'], video")) return;
  const key = event.key.toLowerCase();
  if (key === " " && target.tagName !== "BUTTON" && target.tagName !== "SUMMARY") {
    event.preventDefault();
    if (!hasVideo()) return;
    state.clipEnd = null;
    video.paused ? video.play().catch(() => {}) : video.pause();
  } else if (key === "arrowleft") {
    event.preventDefault();
    stepCue(-1);
  } else if (key === "arrowright") {
    event.preventDefault();
    stepCue(1);
  } else if (key === "r") {
    playClip(state.activeCue);
  } else if (key === "l") {
    toggleLoop();
  } else if (key === "p") {
    pinyinToggle.click();
  } else if (key === "t") {
    translationToggle.click();
  } else if (key === "escape" && !wordDetail.hidden) {
    closeWord();
  }
});

/* ---------- Start ---------- */

applyPreferences();
const healthReady = loadHealth();
loadRecentLessons();
const hashLesson = new URLSearchParams(location.hash.slice(1)).get("lesson");
if (hashLesson) healthReady.then(() => openSavedLesson(hashLesson));
