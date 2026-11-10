// Library screen: saved videos, words and sentences (all stored on the backend).
import { apiFetch, apiJson, apiUrl, responseJson } from "./api.js";
import { removeSentence, removeWord, updateSentence, updateWord } from "./learner.js";
import { openPractice } from "./practice.js";
import { speak, stopSpeaking } from "./speech.js";
import { renderSentenceCard, renderWordCard } from "./study.js";
import { $, actionButton, button, element, plain, timeLabel } from "./ui.js";

const tabs = [...document.querySelectorAll("[data-library-tab]")];
const videoGrid = $("#video-grid");
const videosEmpty = $("#videos-empty");
const lists = {
  words: { list: $("#words-list"), empty: $("#words-empty"), search: $("#words-search"), status: "saved" },
  sentences: {
    list: $("#sentences-list"),
    empty: $("#sentences-empty"),
    search: $("#sentences-search"),
    status: "saved",
  },
  dictionary: { list: $("#dictionary-list"), empty: $("#dictionary-empty"), search: $("#dictionary-search"), status: null },
};
const methodLabels = {
  "faster-whisper": "máy tự nghe",
  "uploaded-subtitle": "phụ đề tải lên",
  "embedded-subtitle": "phụ đề trong video",
  "youtube-subtitle": "phụ đề YouTube",
};
let handlers = {};
let current = "videos";
const cache = { words: [], sentences: [], dictionary: [] };
const rowRenderers = { words: wordRow, sentences: sentenceRow, dictionary: dictionaryRow };

export function initLibrary(options) {
  handlers = options;
  tabs.forEach((tab) => tab.addEventListener("click", () => showLibraryTab(tab.dataset.libraryTab)));
  for (const [kind, view] of Object.entries(lists)) {
    view.search.addEventListener("input", () => render(kind));
    document.querySelectorAll(`[data-${kind}-status]`).forEach((filter) => {
      filter.addEventListener("click", () => {
        view.status = filter.dataset[`${kind}Status`];
        document
          .querySelectorAll(`[data-${kind}-status]`)
          .forEach((item) => item.setAttribute("aria-pressed", String(item === filter)));
        load(kind);
      });
    });
  }
}

export function showLibraryTab(name) {
  current = name;
  tabs.forEach((tab) => {
    const selected = tab.dataset.libraryTab === name;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    $(`#library-${tab.dataset.libraryTab}`).hidden = !selected;
  });
  $("#library-study").hidden = name === "videos";
  closeStudy();
  refreshLibrary();
}

export function refreshLibrary() {
  if (current === "videos") loadVideos();
  else load(current);
  loadCounts();
}

async function loadCounts() {
  try {
    const [words, sentences, dictionary] = await Promise.all([
      apiJson("/api/library/words"),
      apiJson("/api/library/sentences"),
      apiJson("/api/dictionary?limit=0"),
    ]);
    $("#count-words").textContent = words.length || "";
    $("#count-sentences").textContent = sentences.length || "";
    $("#count-dictionary").textContent = dictionary.total || "";
  } catch {
    /* counts are decorative */
  }
}

export async function loadVideos() {
  try {
    const lessons = await apiJson("/api/lessons");
    $("#count-videos").textContent = lessons.length || "";
    videosEmpty.hidden = lessons.length > 0;
    videoGrid.replaceChildren(...lessons.map(videoCard));
  } catch (error) {
    videosEmpty.hidden = false;
    videosEmpty.textContent = `Không thể đọc kho video: ${error.message}`;
  }
}

function videoCard(item) {
  const card = element("li", "video-card");
  const open = button("video-open", null, () => handlers.openLesson(item.id));
  const thumb = element("span", "video-thumb");
  if (item.thumbnail_url) {
    const image = element("img");
    image.alt = "";
    image.loading = "lazy";
    image.src = apiUrl(item.thumbnail_url);
    image.addEventListener("error", () => image.remove());
    thumb.append(image);
  }
  thumb.append(element("span", "video-thumb-fallback", "文"));
  const progress = item.vocabulary_count ? Math.round((item.learned_count / item.vocabulary_count) * 100) : 0;
  const bar = element("span", "video-progress");
  bar.style.setProperty("--progress", `${progress}%`);
  bar.title = `Đã thuộc ${item.learned_count}/${item.vocabulary_count} từ`;
  const badges = element("span", "badges");
  if (item.source_kind === "youtube") badges.append(element("span", "badge", "YouTube"));
  if (item.has_media) badges.append(element("span", "badge badge-saved", "Đã lưu video"));
  const prepared = preparedLabel(item.prepared);
  if (prepared) badges.append(prepared);
  open.append(
    thumb,
    element("span", "video-title", item.filename),
    element(
      "span",
      "video-meta",
      `${item.learned_count}/${item.vocabulary_count} từ đã thuộc · ${methodLabels[item.transcript_method] || ""}`,
    ),
    bar,
    badges,
  );
  const remove = actionButton("danger", "🗑", null, async () => {
    if (!window.confirm(`Xoá bài học “${item.filename}” và video đã lưu của nó?`)) return;
    try {
      await responseJson(await apiFetch(`/api/lessons/${item.id}`, { method: "DELETE" }));
    } catch (error) {
      window.alert(error.message);
    }
    loadVideos();
  });
  remove.title = `Xoá bài học ${item.filename}`;
  remove.setAttribute("aria-label", remove.title);
  card.append(open, remove);
  return card;
}

/** Progress of the AI lessons written ahead of time for this video. */
function preparedLabel(prepared) {
  if (!prepared?.total) return null;
  const { done, total, state, reason } = prepared;
  if (state === "complete" || done >= total) return element("span", "badge badge-saved", "Bài giảng sẵn sàng");
  const badge = element("span", "badge", `Đang soạn bài giảng ${done}/${total}`);
  if (reason) badge.title = reason;
  if (state === "waiting" || state === "paused" || state === "error") badge.textContent += ` · ${reason || "tạm dừng"}`;
  return badge;
}

async function load(kind) {
  const view = lists[kind];
  const query = view.status ? `?status=${view.status}` : "";
  try {
    if (kind === "dictionary") {
      const result = await apiJson("/api/dictionary");
      cache.dictionary = result.entries;
      const ready = result.entries.filter((entry) => entry.has_lesson).length;
      $("#dictionary-summary").textContent =
        `${result.total} từ đã gặp trong các video · ${ready} từ đã có bài giảng. Mỗi từ chỉ soạn một lần, video sau có từ đó dùng lại ngay.`;
    } else {
      cache[kind] = await apiJson(`/api/library/${kind}${query}`);
    }
  } catch (error) {
    view.empty.hidden = false;
    view.empty.textContent = error.message;
    return;
  }
  render(kind);
}

function render(kind) {
  const view = lists[kind];
  const query = plain(view.search.value.trim());
  const rows = cache[kind].filter((row) => {
    if (!query) return true;
    const text = kind === "words"
      ? [row.word, row.pinyin, row.meaning, row.own_meaning, row.sentence]
      : kind === "dictionary"
        ? [row.word, row.traditional, row.pinyin, ...(row.meanings || [])]
        : [row.text, row.pinyin, row.translation];
    return plain(text.filter(Boolean).join(" ")).includes(query);
  });
  view.empty.hidden = rows.length > 0;
  view.empty.textContent = cache[kind].length
    ? "Không có mục nào khớp."
    : kind === "words"
      ? "Chưa có từ nào. Trong bài học, bấm vào một từ rồi chọn “Lưu” hoặc “Đã thuộc”."
      : kind === "dictionary"
        ? "Từ điển còn trống. Import một video, mọi từ trong đó sẽ được thêm vào đây."
        : "Chưa có câu nào. Trong bài học, bấm “Lưu câu” ở khung câu đang học.";
  view.list.replaceChildren(...rows.map(rowRenderers[kind]));
  markSelection();
  const first = rows.find((row) => row.lesson_exists || row.lesson_id);
  if (wideScreen.matches && !selection && first) {
    openStudy(kind === "sentences" ? sentenceTarget(first) : studyTarget(first), { focus: false });
  }
}

const studyTarget = (row) => ({ lessonId: row.lesson_id, cueId: row.cue_id, wordId: row.word_id });
const sentenceTarget = (row) => ({ lessonId: row.lesson_id, cueId: row.cue_id });
const keyOf = ({ lessonId, cueId, wordId }) => (wordId ? `w:${wordId}` : `s:${lessonId}/${cueId}`);

function markSelection() {
  document.querySelectorAll(".library-item[data-key]").forEach((item) => {
    const selected = item.dataset.key === selection;
    item.classList.toggle("is-selected", selected);
    if (selected) item.setAttribute("aria-current", "true");
    else item.removeAttribute("aria-current");
  });
}

function scoreBadge(row) {
  if (row.best_score === null || row.best_score === undefined) return null;
  return element("span", "badge badge-score", `Phát âm tốt nhất ${row.best_score}%`);
}

function stop(event) {
  event.stopPropagation();
}

/** Quick actions on a row; the row itself opens the full study card. */
function quickActions(...buttons) {
  const actions = element("div", "library-actions");
  buttons.filter(Boolean).forEach((item) => {
    item.addEventListener("click", stop);
    actions.append(item);
  });
  return actions;
}

function openableRow(onOpen, target) {
  const item = element("li", "library-item");
  item.dataset.key = keyOf(target);
  item.tabIndex = 0;
  item.addEventListener("click", onOpen);
  item.addEventListener("keydown", (event) => {
    if (event.target === item && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      onOpen();
    }
  });
  return item;
}

function wordRow(row) {
  const open = () => openStudy(studyTarget(row));
  const item = row.lesson_exists ? openableRow(open, studyTarget(row)) : element("li", "library-item");
  const main = element("div", "library-item-main");
  const hanzi = element("strong", "library-hanzi", row.word);
  hanzi.lang = "zh";
  const head = element("div", "library-item-head");
  head.append(hanzi, element("span", "library-pinyin", row.pinyin || ""));
  main.append(head, element("p", "library-meaning", row.own_meaning || row.meaning || "—"));
  if (row.sentence) {
    const sentence = element("p", "library-sentence", row.sentence);
    sentence.lang = "zh";
    sentence.title = row.sentence_translation || "";
    main.append(sentence);
  }
  const badges = element("div", "badges");
  const score = scoreBadge(row);
  if (score) badges.append(score);
  if (!row.lesson_exists) badges.append(element("span", "badge", "Bài học đã bị xoá"));
  main.append(badges);
  const learned = row.status === "learned";
  item.append(
    main,
    quickActions(
      actionButton("listen", "🔊", null, () => speak(row.word, 0.7), { title: `Phát âm ${row.word}` }),
      !row.lesson_exists &&
        actionButton("practice", "🎙", null, () =>
          openPractice({
            target: row.word,
            pinyin: row.pinyin,
            translation: row.own_meaning || row.meaning,
            kind: "word",
            itemId: row.word_id,
            onScored: () => load("words"),
          }),
        { title: "Luyện phát âm" }),
      actionButton("learned", "✓", null, async () => {
        await updateWord(row.word_id, { status: learned ? "saved" : "learned" });
        load("words");
        loadCounts();
      }, { pressed: learned, title: learned ? "Đã thuộc — bấm để học lại" : "Đánh dấu đã thuộc" }),
      actionButton("danger", "🗑", null, async () => {
        await removeWord(row.word_id);
        load("words");
        loadCounts();
      }, { title: `Xoá ${row.word} khỏi kho` }),
    ),
  );
  return item;
}

/** A global dictionary entry; opens in the newest video that contains the word. */
function dictionaryRow(row) {
  const target = { lessonId: row.lesson_id, wordId: row.word_id };
  const item = row.lesson_id ? openableRow(() => openStudy(target), target) : element("li", "library-item");
  const main = element("div", "library-item-main");
  const hanzi = element("strong", "library-hanzi", row.word);
  hanzi.lang = "zh";
  const head = element("div", "library-item-head");
  head.append(hanzi, element("span", "library-pinyin", row.pinyin || ""));
  main.append(head, element("p", "library-meaning", row.meaning || "Chưa có nghĩa tiếng Việt"));
  const badges = element("div", "badges");
  badges.append(element("span", "badge", row.video_count ? `${row.video_count} video` : "Video đã bị xoá"));
  badges.append(
    row.has_lesson ? element("span", "badge badge-saved", "Có bài giảng") : element("span", "badge", "Chưa soạn bài giảng"),
  );
  main.append(badges);
  item.append(
    main,
    quickActions(
      actionButton("listen", "🔊", null, () => speak(row.word, 0.7), { title: `Phát âm ${row.word}` }),
      row.lesson_id &&
        actionButton("save", "☆", null, async () => {
          try {
            await updateWord(row.word_id, { status: "saved", lesson_id: row.lesson_id });
          } catch (error) {
            window.alert(error.message);
            return;
          }
          loadCounts();
        }, { title: `Lưu ${row.word} vào từ vựng đang học` }),
    ),
  );
  return item;
}

function sentenceRow(row) {
  const open = () => openStudy(sentenceTarget(row));
  const item = row.lesson_exists ? openableRow(open, sentenceTarget(row)) : element("li", "library-item");
  const main = element("div", "library-item-main");
  const text = element("p", "library-sentence-text", row.text);
  text.lang = "zh";
  main.append(text, element("p", "library-pinyin", row.pinyin || ""));
  if (row.translation) main.append(element("p", "library-translation", row.translation));
  const badges = element("div", "badges");
  badges.append(element("span", "badge", timeLabel(row.start_ms)));
  const score = scoreBadge(row);
  if (score) badges.append(score);
  main.append(badges);
  const learned = row.status === "learned";
  item.append(
    main,
    quickActions(
      actionButton("listen", "🔊", null, () => speak(row.text, 0.75), { title: "Nghe câu" }),
      actionButton("learned", "✓", null, async () => {
        await updateSentence(row.lesson_id, row.cue_id, learned ? "saved" : "learned");
        load("sentences");
      }, { pressed: learned, title: learned ? "Đã thuộc — bấm để học lại" : "Đánh dấu đã thuộc" }),
      actionButton("danger", "🗑", null, async () => {
        await removeSentence(row.lesson_id, row.cue_id);
        load("sentences");
        loadCounts();
      }, { title: "Xoá câu khỏi kho" }),
    ),
  );
  return item;
}

/* ---------- Study pane: the same cards as the video screen ---------- */

// Wide screens: list on the left, a roomy study pane on the right (first item is
// opened automatically). Narrow screens: the pane opens full screen on a tap.
const wideScreen = window.matchMedia("(min-width: 1001px)");
const pane = $("#study-pane");
const paneBody = $("#study-body");
const placeholder = $("#study-placeholder");
const paneVideo = $("#study-video");
const paneNote = $("#study-video-note");
const paneSentence = $("#study-sentence");
const paneWord = $("#study-word");
const lessonCache = new Map();
let paneState = null;
let selection = null;
let clipEnd = null;

paneVideo.addEventListener("timeupdate", () => {
  if (clipEnd !== null && paneVideo.currentTime * 1000 >= clipEnd - 80) {
    paneVideo.pause();
    clipEnd = null;
  }
});
$("#study-close").addEventListener("click", () => closeStudy());
pane.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !wideScreen.matches) closeStudy();
});

function closeStudy() {
  stopSpeaking();
  paneVideo.pause();
  paneState = null;
  selection = null;
  pane.classList.remove("is-open");
  document.body.classList.remove("study-open");
  paneBody.hidden = true;
  placeholder.hidden = false;
  $("#study-title").textContent = "Chọn một mục để học";
  markSelection();
}

async function lessonFor(lessonId) {
  if (!lessonCache.has(lessonId)) lessonCache.set(lessonId, apiJson(`/api/lessons/${lessonId}`));
  try {
    return await lessonCache.get(lessonId);
  } catch (error) {
    lessonCache.delete(lessonId);
    throw error;
  }
}

function paneContext(lesson, wordsById, cueIndexById) {
  return {
    lesson,
    wordsById,
    cueIndexById,
    playClip: (index) => {
      if (!lesson.media?.available) return false;
      const cue = lesson.cues[index];
      clipEnd = cue.end_ms;
      paneVideo.currentTime = cue.start_ms / 1000;
      paneVideo.play().catch(() => {});
      return true;
    },
    pause: () => paneVideo.pause(),
    onChange: () => {
      renderPane();
      if (current !== "videos") load(current);
      loadCounts();
    },
    showWord: (wordId, index) => {
      paneState.wordId = wordId;
      paneState.occurrence = index;
      const cueId = wordsById.get(wordId)?.occurrences[index]?.cue_id;
      if (cueId) paneState.cueId = cueId;
      renderPane();
      paneWord.scrollIntoView({ block: "nearest", behavior: "smooth" });
    },
    openInVideo: (focus) => {
      closeStudy();
      handlers.openLesson(lesson.id, focus);
    },
    onClose: () => {
      paneState.wordId = null;
      renderPane();
    },
  };
}

function renderPane() {
  if (!paneState) return;
  const { lesson, wordsById, cueIndexById } = paneState;
  const ctx = paneContext(lesson, wordsById, cueIndexById);
  const cueIndex = cueIndexById.get(paneState.cueId) ?? 0;
  renderSentenceCard(paneSentence, ctx, cueIndex);
  paneWord.hidden = !paneState.wordId;
  paneBody.classList.toggle("has-word", Boolean(paneState.wordId));
  if (paneState.wordId) renderWordCard(paneWord, ctx, paneState.wordId, paneState.occurrence || 0);
}

/** Open a saved word or sentence with every study feature, without leaving the library. */
export async function openStudy(target, { focus = true } = {}) {
  const { lessonId, cueId, wordId } = target;
  selection = keyOf(target);
  markSelection();
  let lesson;
  try {
    lesson = await lessonFor(lessonId);
  } catch (error) {
    window.alert(error.message);
    return;
  }
  if (selection !== keyOf(target)) return; // another row was chosen meanwhile
  stopSpeaking();
  const wordsById = new Map(lesson.vocabulary.map((word) => [word.id, word]));
  const cueIndexById = new Map(lesson.cues.map((cue, index) => [cue.id, index]));
  const occurrence = wordId ? Math.max(0, wordsById.get(wordId)?.occurrences.findIndex((item) => item.cue_id === cueId) ?? 0) : 0;
  const shownCue = cueId || wordsById.get(wordId)?.occurrences[occurrence]?.cue_id;
  paneState = { lesson, wordsById, cueIndexById, cueId: shownCue, wordId, occurrence };
  $("#study-title").textContent = lesson.filename || "Bài học";
  if (lesson.media?.available) {
    const source = apiUrl(lesson.media.url);
    if (paneVideo.dataset.lesson !== lesson.id) {
      paneVideo.src = source;
      paneVideo.dataset.lesson = lesson.id;
    }
    paneVideo.hidden = false;
    paneNote.hidden = true;
  } else {
    paneVideo.hidden = true;
    paneNote.hidden = false;
    paneNote.textContent =
      "Video chưa được tải về máy nên “Câu gốc” sẽ đọc bằng giọng máy. Bấm 🎬 để xem đúng đoạn này trên YouTube.";
  }
  placeholder.hidden = true;
  paneBody.hidden = false;
  renderPane();
  pane.scrollTop = 0;
  if (!wideScreen.matches) {
    pane.classList.add("is-open");
    document.body.classList.add("study-open");
  }
  if (focus) pane.focus({ preventScroll: wideScreen.matches });
}
