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
const progressBox = document.querySelector("#job-progress");
const progressBar = document.querySelector("#job-progress-bar");
const progressStage = document.querySelector("#job-stage");
const progressPercent = document.querySelector("#job-percent");
const recentList = document.querySelector("#recent-list");
const recentEmpty = document.querySelector("#recent-empty");

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

const stageLabels = {
  uploaded: "Đã tải video vào bộ xử lý local",
  "probing-video": "Đang đọc cấu trúc video",
  "reading-subtitle": "Đang đọc phụ đề bạn cung cấp",
  "reading-embedded-subtitle": "Đang đọc phụ đề nhúng trong video",
  "extracting-audio": "Đang tách giọng nói khỏi video",
  "transcribing-mandarin": "Đang nhận dạng tiếng Trung",
  "analyzing-vocabulary": "Đang tạo từ vựng và ngữ cảnh",
  complete: "Bài học đã sẵn sàng",
};

function showProgress(job) {
  progressBox.hidden = false;
  progressBar.value = job.progress;
  progressBar.textContent = `${job.progress}%`;
  progressStage.textContent = stageLabels[job.stage] || "Đang xử lý trên máy…";
  progressPercent.textContent = `${job.progress}%`;
}

async function responseJson(response) {
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "Yêu cầu không thành công.");
  return result;
}

function delay(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function waitForJob(initialJob) {
  let job = initialJob;
  while (job.status === "queued" || job.status === "processing") {
    showProgress(job);
    await delay(800);
    job = await responseJson(await fetch(`/api/jobs/${job.id}`));
  }
  showProgress(job);
  if (job.status === "failed") {
    throw new Error(job.error || "Không thể xử lý video này.");
  }
  return job.result;
}

async function loadRecentLessons() {
  try {
    const lessons = await responseJson(await fetch("/api/lessons"));
    recentList.replaceChildren();
    recentEmpty.hidden = lessons.length > 0;
    for (const item of lessons) {
      const row = document.createElement("li");
      const button = element("button", "recent-lesson");
      button.type = "button";
      button.append(
        element("span", null, item.filename),
        element("small", null, `${item.vocabulary_count} từ · ${item.transcript_method}`),
      );
      button.addEventListener("click", async () => {
        try {
          lesson = await responseJson(await fetch(`/api/lessons/${item.id}`));
          if (videoUrl) URL.revokeObjectURL(videoUrl);
          videoUrl = null;
          video.removeAttribute("src");
          video.load();
          video.hidden = true;
          placeholder.textContent =
            "Bài học đã lưu. Chọn lại video gốc nếu bạn muốn phát đúng khoảnh khắc.";
          placeholder.hidden = false;
          renderLesson();
        } catch (error) {
          formNote.textContent = error.message;
        }
      });
      row.append(button);
      recentList.append(row);
    }
  } catch (error) {
    recentEmpty.textContent = `Không thể đọc bài học đã lưu: ${error.message}`;
  }
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
    : "Từ điển offline chưa sẵn sàng. Chạy pnpm setup để cài dữ liệu CC-CEDICT miễn phí.";
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
  formNote.textContent = "Đang tải video vào bộ xử lý local…";
  progressBox.hidden = false;
  try {
    const body = new FormData();
    body.append("video", mediaFile);
    if (subtitleFile) body.append("subtitle", subtitleFile);
    const job = await responseJson(
      await fetch("/api/lessons/mandarin-video", { method: "POST", body }),
    );
    lesson = await waitForJob(job);
    renderLesson();
    await loadRecentLessons();
    formNote.textContent = "Bài học đã sẵn sàng và được tự động lưu trên máy này.";
  } catch (error) {
    formNote.textContent = error.message;
    progressBox.hidden = true;
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

loadRecentLessons();
