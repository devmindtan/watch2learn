const form = document.querySelector("#lesson-form");
const videoInput = document.querySelector("#video-file");
const subtitleInput = document.querySelector("#subtitle-file");
const workspace = document.querySelector("#workspace");
const video = document.querySelector("#video");
const placeholder = document.querySelector("#audio-placeholder");
const transcript = document.querySelector("#transcript");
const vocabularyList = document.querySelector("#vocabulary-list");
const wordDetail = document.querySelector("#word-detail");
const dictionaryNotice = document.querySelector("#dictionary-notice");
const wordCount = document.querySelector("#word-count");
const formNote = document.querySelector("#form-note");
const pinyinToggle = document.querySelector("#pinyin-toggle");
const cueTemplate = document.querySelector("#cue-template");

let lesson = null;
let videoUrl = null;
const knownWords = new Set(JSON.parse(localStorage.getItem("watch2learn-known") || "[]"));

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function timeLabel(milliseconds) {
  const seconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function seek(milliseconds) {
  if (video.src) {
    video.currentTime = milliseconds / 1000;
    video.play().catch(() => {});
  }
}

function wordById(id) {
  return lesson.vocabulary.find((word) => word.id === id);
}

function saveKnown() {
  localStorage.setItem("watch2learn-known", JSON.stringify([...knownWords]));
}

function showWord(id) {
  const word = wordById(id);
  if (!word) return;
  const occurrence = word.occurrences[0];
  const known = knownWords.has(id);
  wordDetail.className = "word-detail";
  wordDetail.replaceChildren();
  const titleRow = element("div", "word-title-row");
  const title = element("div");
  const heading = element(
    "h3",
    null,
    `${word.word}${word.traditional && word.traditional !== word.word ? ` · ${word.traditional}` : ""}`,
  );
  heading.lang = "zh";
  title.append(heading, element("p", "word-pinyin", word.pinyin));
  const knownButton = element(
    "button",
    `known-button ${known ? "is-known" : ""}`,
    known ? "Đã biết" : "Đánh dấu đã biết",
  );
  knownButton.type = "button";
  titleRow.append(title, knownButton);

  const definitions = word.definitions.length
    ? word.definitions.join("; ")
    : "Chưa có nghĩa offline — hãy cài CC-CEDICT.";
  const context = element("div", "context");
  context.setAttribute("aria-label", "Ngữ cảnh sử dụng");
  if (occurrence.before_text) {
    const before = element("p", "context-neighbor", occurrence.before_text);
    before.lang = "zh";
    context.append(before);
  }
  const current = element("button", "context-current", occurrence.cue_text);
  current.type = "button";
  current.lang = "zh";
  context.append(current);
  if (occurrence.after_text) {
    const after = element("p", "context-neighbor", occurrence.after_text);
    after.lang = "zh";
    context.append(after);
  }

  const occurrenceRow = element("div", "occurrences");
  const occurrenceButtons = element("div");
  for (const item of word.occurrences) {
    const button = element("button", null, timeLabel(item.start_ms));
    button.type = "button";
    button.dataset.time = item.start_ms;
    occurrenceButtons.append(button);
  }
  occurrenceRow.append(
    element("p", null, `${word.occurrence_count} lần xuất hiện`),
    occurrenceButtons,
  );
  wordDetail.append(titleRow, element("p", "definition", definitions), context, occurrenceRow);

  knownButton.addEventListener("click", () => {
    knownWords.has(id) ? knownWords.delete(id) : knownWords.add(id);
    saveKnown();
    showWord(id);
    renderVocabulary();
  });
  current.addEventListener("click", () => seek(occurrence.start_ms));
  wordDetail.querySelectorAll("[data-time]").forEach((button) => {
    button.addEventListener("click", () => seek(Number(button.dataset.time)));
  });
  document.querySelectorAll(".token.is-selected").forEach((token) => token.classList.remove("is-selected"));
  document.querySelectorAll(`[data-word-id="${id}"]`).forEach((token) => token.classList.add("is-selected"));
}

function renderTranscript() {
  transcript.replaceChildren();
  for (const cue of lesson.cues) {
    const row = cueTemplate.content.firstElementChild.cloneNode(true);
    row.dataset.start = cue.start_ms;
    const timeButton = row.querySelector(".cue-time");
    timeButton.textContent = timeLabel(cue.start_ms);
    timeButton.addEventListener("click", () => seek(cue.start_ms));
    const text = row.querySelector(".cue-text");
    for (const segment of cue.segments) {
      if (!segment.vocabulary_id) {
        text.append(segment.text);
        continue;
      }
      const word = wordById(segment.vocabulary_id);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "token";
      button.dataset.wordId = segment.vocabulary_id;
      button.append(
        element("span", "token-pinyin", word?.pinyin || ""),
        element("span", null, segment.text),
      );
      button.addEventListener("click", () => showWord(segment.vocabulary_id));
      text.append(button);
    }
    transcript.append(row);
  }
}

function renderVocabulary() {
  vocabularyList.replaceChildren();
  for (const word of lesson.vocabulary) {
    const item = document.createElement("li");
    const known = knownWords.has(word.id);
    const button = element("button", `word-row ${known ? "is-known" : ""}`);
    button.type = "button";
    button.dataset.wordId = word.id;
    const identity = element("span");
    const hanzi = element("strong", null, word.word);
    hanzi.lang = "zh";
    identity.append(hanzi, element("small", null, word.pinyin));
    button.append(identity, element("span", "frequency", `${word.occurrence_count}×`));
    button.addEventListener("click", () => showWord(word.id));
    item.append(button);
    vocabularyList.append(item);
  }
  wordCount.textContent = `${lesson.vocabulary.length} từ`;
}

function renderLesson() {
  renderTranscript();
  renderVocabulary();
  dictionaryNotice.hidden = lesson.dictionary.loaded;
  dictionaryNotice.textContent = lesson.dictionary.loaded
    ? ""
    : "Chưa tìm thấy CC-CEDICT. Pinyin vẫn hoạt động; nghĩa sẽ hiện sau khi đặt file cedict_ts.u8 vào data/dictionaries/.";
  workspace.hidden = false;
  workspace.scrollIntoView({ behavior: "smooth", block: "start" });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const mediaFile = videoInput.files[0];
  const subtitleFile = subtitleInput.files[0];
  if (!mediaFile) return;
  form.querySelector("button").disabled = true;
  if (videoUrl) URL.revokeObjectURL(videoUrl);
  videoUrl = URL.createObjectURL(mediaFile);
  video.src = videoUrl;
  video.hidden = false;
  placeholder.hidden = true;
  formNote.textContent = subtitleFile
    ? "Đang ghép phụ đề với video trên máy của bạn…"
    : "Đang tách âm thanh và nhận dạng tiếng Trung trên máy. Video dài có thể mất vài phút…";
  try {
    let response;
    if (subtitleFile) {
      response = await fetch("/api/lessons/mandarin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: await subtitleFile.text(),
          filename: subtitleFile.name,
          language: "zh",
        }),
      });
    } else {
      const body = new FormData();
      body.append("video", mediaFile);
      response = await fetch("/api/lessons/mandarin-video", { method: "POST", body });
    }
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Không thể xử lý video.");
    lesson = result;
    renderLesson();
    formNote.textContent = "Bài học đã sẵn sàng. Video và dữ liệu xử lý vẫn ở trên máy này.";
  } catch (error) {
    formNote.textContent = error.message;
  } finally {
    form.querySelector("button").disabled = false;
  }
});

pinyinToggle.addEventListener("change", () => {
  document.body.classList.toggle("hide-pinyin", !pinyinToggle.checked);
});

video.addEventListener("timeupdate", () => {
  const now = video.currentTime * 1000;
  let active = null;
  for (const cue of lesson?.cues || []) {
    if (now >= cue.start_ms && now < cue.end_ms) active = cue.id;
  }
  document.querySelectorAll(".cue-row.is-active").forEach((row) => row.classList.remove("is-active"));
  if (active) document.querySelector(`[data-start="${lesson.cues.find((cue) => cue.id === active).start_ms}"]`)?.classList.add("is-active");
});
