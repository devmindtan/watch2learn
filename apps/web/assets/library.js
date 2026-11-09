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
};
const methodLabels = {
  "faster-whisper": "máy tự nghe",
  "uploaded-subtitle": "phụ đề tải lên",
  "embedded-subtitle": "phụ đề trong video",
  "youtube-subtitle": "phụ đề YouTube",
};
let handlers = {};
let current = "videos";
const cache = { words: [], sentences: [] };

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
  refreshLibrary();
}

export function refreshLibrary() {
  if (current === "videos") loadVideos();
  else load(current);
  loadCounts();
}

async function loadCounts() {
  try {
    const [words, sentences] = await Promise.all([
      apiJson("/api/library/words"),
      apiJson("/api/library/sentences"),
    ]);
    $("#count-words").textContent = words.length || "";
    $("#count-sentences").textContent = sentences.length || "";
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

async function load(kind) {
  const view = lists[kind];
  const query = view.status ? `?status=${view.status}` : "";
  try {
    cache[kind] = await apiJson(`/api/library/${kind}${query}`);
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
      : [row.text, row.pinyin, row.translation];
    return plain(text.filter(Boolean).join(" ")).includes(query);
  });
  view.empty.hidden = rows.length > 0;
  view.empty.textContent = cache[kind].length
    ? "Không có mục nào khớp."
    : kind === "words"
      ? "Chưa có từ nào. Trong bài học, bấm vào một từ rồi chọn “Lưu” hoặc “Đã thuộc”."
      : "Chưa có câu nào. Trong bài học, bấm “Lưu câu” ở khung câu đang học.";
  view.list.replaceChildren(...rows.map(kind === "words" ? wordRow : sentenceRow));
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

function openableRow(onOpen) {
  const item = element("li", "library-item");
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
  const open = () => openStudy({ lessonId: row.lesson_id, cueId: row.cue_id, wordId: row.word_id });
  const item = row.lesson_exists ? openableRow(open) : element("li", "library-item");
  const main = element("div", "library-item-main");
  const hanzi = element("strong", "library-hanzi", row.word);
  hanzi.lang = "zh";
  const head = element("div", "library-item-head");
  head.append(hanzi, element("span", "library-pinyin", row.pinyin || ""));
  main.append(head, element("p", "library-meaning", row.own_meaning || row.meaning || "—"));
  if (row.sentence) {
    const sentence = element("p", "library-sentence", row.sentence);
    sentence.lang = "zh";
    main.append(sentence);
    if (row.sentence_translation) main.append(element("p", "library-translation", row.sentence_translation));
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
      row.lesson_exists &&
        actionButton("video", "🎬", null, () => handlers.openLesson(row.lesson_id, { cueId: row.cue_id, wordId: row.word_id }), {
          title: "Xem trong video",
        }),
      actionButton("learned", "✓", learned ? "Đã thuộc" : "Thuộc", async () => {
        await updateWord(row.word_id, { status: learned ? "saved" : "learned" });
        load("words");
        loadCounts();
      }, { pressed: learned }),
      actionButton("danger", "🗑", null, async () => {
        await removeWord(row.word_id);
        load("words");
        loadCounts();
      }, { title: `Xoá ${row.word} khỏi kho` }),
    ),
  );
  return item;
}

function sentenceRow(row) {
  const open = () => openStudy({ lessonId: row.lesson_id, cueId: row.cue_id });
  const item = row.lesson_exists ? openableRow(open) : element("li", "library-item");
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
      actionButton("practice", "🎙", null, () =>
        openPractice({
          target: row.text,
          pinyin: row.pinyin,
          translation: row.translation,
          kind: "sentence",
          itemId: row.sentence_id,
          onScored: () => load("sentences"),
        }),
      { title: "Đọc thử câu" }),
      row.lesson_exists &&
        actionButton("video", "🎬", null, () => handlers.openLesson(row.lesson_id, { cueId: row.cue_id }), { title: "Xem trong video" }),
      actionButton("learned", "✓", learned ? "Đã thuộc" : "Thuộc", async () => {
        await updateSentence(row.lesson_id, row.cue_id, learned ? "saved" : "learned");
        load("sentences");
      }, { pressed: learned }),
      actionButton("danger", "🗑", null, async () => {
        await removeSentence(row.lesson_id, row.cue_id);
        load("sentences");
        loadCounts();
      }, { title: "Xoá câu khỏi kho" }),
    ),
  );
  return item;
}

/* ---------- Study drawer: the same cards as the video screen ---------- */

const drawer = $("#study-dialog");
const drawerVideo = $("#study-video");
const drawerNote = $("#study-video-note");
const drawerSentence = $("#study-sentence");
const drawerWord = $("#study-word");
const lessonCache = new Map();
let drawerState = null;
let clipEnd = null;

drawerVideo.addEventListener("timeupdate", () => {
  if (clipEnd !== null && drawerVideo.currentTime * 1000 >= clipEnd - 80) {
    drawerVideo.pause();
    clipEnd = null;
  }
});
$("#study-close").addEventListener("click", () => drawer.close());
drawer.addEventListener("close", () => {
  stopSpeaking();
  drawerVideo.pause();
  drawerState = null;
  refreshLibrary();
});

async function lessonFor(lessonId) {
  if (!lessonCache.has(lessonId)) lessonCache.set(lessonId, apiJson(`/api/lessons/${lessonId}`));
  try {
    return await lessonCache.get(lessonId);
  } catch (error) {
    lessonCache.delete(lessonId);
    throw error;
  }
}

function drawerContext(lesson, wordsById, cueIndexById) {
  return {
    lesson,
    wordsById,
    cueIndexById,
    playClip: (index) => {
      if (!lesson.media?.available) return false;
      const cue = lesson.cues[index];
      clipEnd = cue.end_ms;
      drawerVideo.currentTime = cue.start_ms / 1000;
      drawerVideo.play().catch(() => {});
      return true;
    },
    pause: () => drawerVideo.pause(),
    onChange: () => renderDrawer(),
    showWord: (wordId, index) => {
      drawerState.wordId = wordId;
      drawerState.occurrence = index;
      const cueId = wordsById.get(wordId)?.occurrences[index]?.cue_id;
      if (cueId) drawerState.cueId = cueId;
      renderDrawer();
      drawerWord.scrollIntoView({ block: "nearest", behavior: "smooth" });
    },
    openInVideo: (focus) => {
      drawer.close();
      handlers.openLesson(lesson.id, focus);
    },
    onClose: () => {
      drawerState.wordId = null;
      renderDrawer();
    },
  };
}

function renderDrawer() {
  if (!drawerState) return;
  const { lesson, wordsById, cueIndexById } = drawerState;
  const ctx = drawerContext(lesson, wordsById, cueIndexById);
  const cueIndex = cueIndexById.get(drawerState.cueId) ?? 0;
  renderSentenceCard(drawerSentence, ctx, cueIndex);
  drawerWord.hidden = !drawerState.wordId;
  if (drawerState.wordId) renderWordCard(drawerWord, ctx, drawerState.wordId, drawerState.occurrence || 0);
}

/** Open a saved word or sentence with every study feature, without leaving the library. */
export async function openStudy({ lessonId, cueId, wordId }) {
  let lesson;
  try {
    lesson = await lessonFor(lessonId);
  } catch (error) {
    window.alert(error.message);
    return;
  }
  const wordsById = new Map(lesson.vocabulary.map((word) => [word.id, word]));
  const cueIndexById = new Map(lesson.cues.map((cue, index) => [cue.id, index]));
  const occurrence = wordId ? Math.max(0, wordsById.get(wordId)?.occurrences.findIndex((item) => item.cue_id === cueId) ?? 0) : 0;
  drawerState = { lesson, wordsById, cueIndexById, cueId, wordId, occurrence };
  $("#study-title").textContent = lesson.filename || "Bài học";
  if (lesson.media?.available) {
    const source = apiUrl(lesson.media.url);
    if (drawerVideo.dataset.lesson !== lesson.id) {
      drawerVideo.src = source;
      drawerVideo.dataset.lesson = lesson.id;
    }
    drawerVideo.hidden = false;
    drawerNote.hidden = true;
  } else {
    drawerVideo.hidden = true;
    drawerNote.hidden = false;
    drawerNote.textContent =
      "Video chưa được tải về máy nên “Câu gốc” sẽ đọc bằng giọng máy. Bấm 🎬 để xem đúng đoạn này trên YouTube.";
  }
  renderDrawer();
  if (!drawer.open) drawer.showModal();
}
