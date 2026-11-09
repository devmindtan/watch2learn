import { apiFetch, apiJson, apiUrl, onUnauthorized, responseJson, saveServerSettings, serverSettings } from "./api.js";
import {
  loadLearner,
  onLearnerChange,
  ownMeaning,
  sentenceStatus,
  updateSentence,
  updateWord,
  wordStatus,
} from "./learner.js";
import { initLibrary, refreshLibrary } from "./library.js";
import { openPractice } from "./practice.js";
import {
  configureSpeech,
  createNarration,
  onVoices,
  speak,
  stopSpeaking,
  toneDescription,
} from "./speech.js";
import {
  $,
  button,
  cleanSenses,
  delay,
  element,
  escapeRegExp,
  plain,
  readStore,
  sizeLabel,
  timeLabel,
  writeStore,
} from "./ui.js";

const form = $("#lesson-form");
const videoInput = $("#video-file");
const subtitleInput = $("#subtitle-file");
const dropzone = $("#dropzone");
const videoName = $("#video-name");
const youtubeUrl = $("#youtube-url");
const youtubeRights = $("#youtube-rights");
const sourceTabs = [...document.querySelectorAll("[data-source]")];
const formNote = $("#form-note");
const readiness = $("#readiness");
const progressBox = $("#job-progress");
const progressBar = $("#job-progress-bar");
const progressStage = $("#job-stage");
const progressPercent = $("#job-percent");

const library = $("#library");
const workspace = $("#workspace");
const libraryButton = $("#library-button");
const lessonTitle = $("#lesson-title");
const viewToggles = $("#view-toggles");
const pinyinToggle = $("#pinyin-toggle");
const translationToggle = $("#translation-toggle");

const video = $("#video");
const youtubeHost = $("#youtube-host");
const videoMissing = $("#video-missing");
const reattachInput = $("#reattach-file");
const sourceBar = $("#source-bar");
const nowIndex = $("#now-index");
const nowTime = $("#now-time");
const nowText = $("#now-text");
const nowTranslation = $("#now-translation");
const prevButton = $("#prev-cue");
const nextButton = $("#next-cue");
const replayButton = $("#replay-cue");
const loopButton = $("#loop-cue");
const speakCueButton = $("#speak-cue");
const saveCueButton = $("#save-cue");
const practiceCueButton = $("#practice-cue");
const learnedCueButton = $("#learned-cue");

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
  source: "file",
  activeCue: -1,
  selectedWord: null,
  selectedOccurrence: 0,
  loop: false,
  clipEnd: null,
  followTranscript: true,
  filter: "all",
  health: null,
  preferYoutube: false,
  download: null,
};
let followTimer = null;
let downloadTimer = null;
const wordsById = new Map();
const cueIndexById = new Map();

const preferences = readStore("watch2learn-preferences", { pinyin: true, translation: true });

onVoices((info) => {
  speakCueButton.title = info.server
    ? "Đọc chậm bằng giọng đọc trên máy chủ"
    : info.browserZh
      ? `Đọc chậm bằng giọng máy (${info.browserZh.name})`
      : "Chưa có giọng đọc — chạy pnpm setup:voices trên máy chủ, hoặc dùng “Nghe lại” để nghe giọng gốc.";
});

/* ---------- Player: saved local file or YouTube embed ---------- */

const player = { mode: null, yt: null, ytReady: false, ticker: null };
let youtubeApi = null;

function loadYoutubeApi() {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (!youtubeApi) {
    youtubeApi = new Promise((resolve, reject) => {
      const previous = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        previous?.();
        resolve(window.YT);
      };
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      script.onerror = () => {
        youtubeApi = null;
        reject(new Error("Không tải được trình phát YouTube (cần kết nối mạng)."));
      };
      document.head.append(script);
    });
  }
  return youtubeApi;
}

function stopTicker() {
  window.clearInterval(player.ticker);
  player.ticker = null;
}

function teardownPlayer() {
  stopTicker();
  video.pause();
  video.removeAttribute("src");
  video.load();
  video.hidden = true;
  if (player.yt) {
    try {
      player.yt.destroy();
    } catch {
      /* already gone */
    }
  }
  player.yt = null;
  player.ytReady = false;
  youtubeHost.replaceChildren();
  youtubeHost.hidden = true;
  videoMissing.hidden = true;
  player.mode = null;
}

function setPlayer(mode, options = {}) {
  const resumeMs = state.activeCue >= 0 ? state.lesson.cues[state.activeCue].start_ms : 0;
  teardownPlayer();
  player.mode = mode;
  if (mode === "file") {
    video.src = apiUrl(options.url);
    video.hidden = false;
    if (resumeMs) {
      video.addEventListener("loadedmetadata", () => (video.currentTime = resumeMs / 1000), { once: true });
    }
  } else if (mode === "youtube") {
    youtubeHost.hidden = false;
    const mount = element("div");
    youtubeHost.append(mount);
    loadYoutubeApi()
      .then((YT) => {
        if (player.mode !== "youtube" || !mount.isConnected) return;
        player.yt = new YT.Player(mount, {
          videoId: options.videoId,
          host: "https://www.youtube-nocookie.com",
          width: "100%",
          height: "100%",
          playerVars: { playsinline: 1, rel: 0, iv_load_policy: 3, start: Math.floor(resumeMs / 1000) },
          events: {
            onReady: () => {
              player.ytReady = true;
            },
            onStateChange: (event) => {
              stopTicker();
              if (event.data === YT.PlayerState.PLAYING) player.ticker = window.setInterval(onTick, 150);
              onTick();
            },
          },
        });
      })
      .catch((error) => {
        youtubeHost.replaceChildren(element("p", "player-error", error.message));
      });
  } else {
    videoMissing.hidden = false;
  }
}

function hasPlayer() {
  return player.mode === "file" ? Boolean(video.src) : player.mode === "youtube" && player.ytReady;
}

function currentMs() {
  if (player.mode === "file") return video.currentTime * 1000;
  if (player.mode === "youtube" && player.ytReady) return player.yt.getCurrentTime() * 1000;
  return 0;
}

function seekMs(milliseconds) {
  if (player.mode === "file") video.currentTime = milliseconds / 1000;
  else if (player.mode === "youtube" && player.ytReady) player.yt.seekTo(milliseconds / 1000, true);
}

function play() {
  if (player.mode === "file") video.play().catch(() => {});
  else if (player.mode === "youtube" && player.ytReady) player.yt.playVideo();
}

function pause() {
  if (player.mode === "file") video.pause();
  else if (player.mode === "youtube" && player.ytReady) player.yt.pauseVideo();
}

function isPaused() {
  if (player.mode === "file") return video.paused;
  if (player.mode === "youtube" && player.ytReady) {
    const playing = [window.YT.PlayerState.PLAYING, window.YT.PlayerState.BUFFERING];
    return !playing.includes(player.yt.getPlayerState());
  }
  return true;
}

function choosePlayer() {
  const lesson = state.lesson;
  const youtubeId = lesson.source?.kind === "youtube" ? lesson.source.video_id : null;
  if (youtubeId && (state.preferYoutube || !lesson.media?.available)) setPlayer("youtube", { videoId: youtubeId });
  else if (lesson.media?.available) setPlayer("file", { url: lesson.media.url });
  else setPlayer(null);
  renderSourceBar();
}

function renderSourceBar() {
  const lesson = state.lesson;
  const media = lesson.media || {};
  const isYoutube = lesson.source?.kind === "youtube";
  const parts = [];
  if (isYoutube) {
    const link = element("a", null, "YouTube");
    link.href = lesson.source.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    parts.push(element("span", "source-kind", "Nguồn: "), link);
    if (lesson.source.channel) parts.push(element("span", "muted", ` · ${lesson.source.channel}`));
  }
  if (media.available) {
    const saved = element("span", "source-path");
    saved.append("Đã lưu: ", element("code", null, media.path), ` (${sizeLabel(media.bytes)})`);
    parts.push(saved);
  }
  const actions = element("span", "source-actions");
  if (isYoutube && media.available) {
    const watchingYoutube = player.mode === "youtube";
    actions.append(
      button("control-button", watchingYoutube ? "Xem bản đã tải" : "Xem trên YouTube", () => {
        state.preferYoutube = !watchingYoutube;
        choosePlayer();
      }),
    );
  } else if (isYoutube) {
    const download = state.download;
    if (download?.status === "running") {
      const progress = element("progress");
      progress.max = 100;
      progress.value = download.progress || 0;
      actions.append(element("span", "muted", `Đang tải video… ${download.progress || 0}%`), progress);
    } else {
      if (download?.status === "failed") actions.append(element("span", "source-error", download.error || "Tải thất bại"));
      actions.append(button("control-button", "⬇ Tải video về máy", startDownload));
    }
  } else if (!media.available) {
    parts.push(element("span", "muted", "Chưa lưu video cho bài học này."));
  }
  if (isYoutube && lesson.transcript?.method === "youtube-subtitle") {
    if (state.relisten?.status === "running") {
      actions.append(element("span", "muted", `Máy đang nghe lại… ${state.relisten.progress || 0}%`));
    } else {
      if (state.relisten?.error) actions.append(element("span", "source-error", state.relisten.error));
      const relisten = button("control-button", "Phụ đề sai? Để máy tự nghe lại", startRelisten);
      relisten.title = "Tạo bài học mới từ giọng nói trong video thay vì phụ đề của người đăng";
      actions.append(relisten);
    }
  }
  sourceBar.replaceChildren(...parts, actions);
}

async function startRelisten() {
  const lesson = state.lesson;
  state.relisten = { status: "running", progress: 0 };
  renderSourceBar();
  try {
    let job = await responseJson(
      await apiFetch("/api/lessons/youtube", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: lesson.source.url, confirm_rights: true, transcript: "asr" }),
      }),
    );
    while (job.status === "queued" || job.status === "processing") {
      await delay(1000);
      job = await responseJson(await apiFetch(`/api/jobs/${job.id}`));
      if (state.lesson !== lesson) return;
      state.relisten = { status: "running", progress: job.progress };
      renderSourceBar();
    }
    if (job.status === "failed") throw new Error(job.error || "Không thể nghe lại video này.");
    state.relisten = null;
    if (state.lesson === lesson) await openSavedLesson(job.id);
  } catch (error) {
    state.relisten = { status: "failed", error: error.message };
    if (state.lesson === lesson) renderSourceBar();
  }
}

async function startDownload() {
  const lessonId = state.lesson.id;
  try {
    state.download = await responseJson(await apiFetch(`/api/lessons/${lessonId}/download`, { method: "POST" }));
  } catch (error) {
    state.download = { status: "failed", error: error.message };
  }
  applyDownloadStatus(lessonId);
}

function applyDownloadStatus(lessonId) {
  if (state.lesson?.id !== lessonId) return;
  if (state.download?.status === "complete") {
    state.lesson.media = state.download.media;
    state.download = null;
  }
  renderSourceBar();
  window.clearTimeout(downloadTimer);
  if (state.download?.status !== "running") return;
  downloadTimer = window.setTimeout(async () => {
    try {
      state.download = await responseJson(await apiFetch(`/api/lessons/${lessonId}/download`));
    } catch (error) {
      state.download = { status: "failed", error: error.message };
    }
    applyDownloadStatus(lessonId);
  }, 1000);
}

async function resumeDownloadStatus(lessonId) {
  try {
    const status = await responseJson(await apiFetch(`/api/lessons/${lessonId}/download`));
    if (status.status === "idle") return;
    state.download = status;
    applyDownloadStatus(lessonId);
  } catch {
    /* status is optional */
  }
}

reattachInput.addEventListener("change", async () => {
  const file = reattachInput.files[0];
  if (!file) return;
  reattachInput.value = "";
  const body = new FormData();
  body.append("video", file);
  sourceBar.replaceChildren(element("span", "muted", "Đang lưu video vào thư mục bài học…"));
  try {
    state.lesson.media = await responseJson(
      await apiFetch(`/api/lessons/${state.lesson.id}/media`, { method: "PUT", body }),
    );
  } catch (error) {
    sourceBar.replaceChildren(element("span", "source-error", error.message));
    return;
  }
  choosePlayer();
});

/* ---------- Library ---------- */

const stageLabels = {
  uploaded: "Đã nhận yêu cầu",
  "probing-video": "Đang đọc cấu trúc video",
  "reading-subtitle": "Đang đọc phụ đề bạn cung cấp",
  "reading-embedded-subtitle": "Đang đọc phụ đề nhúng trong video",
  "fetching-youtube": "Đang đọc thông tin video YouTube",
  "reading-youtube-subtitle": "Đang tải phụ đề tiếng Trung của video",
  "downloading-audio": "Đang tải âm thanh để nhận dạng",
  "extracting-audio": "Đang tách âm thanh",
  "transcribing-mandarin": "Đang nghe và nhận dạng tiếng Trung",
  translating: "Đang dịch từng câu sang tiếng Việt",
  "analyzing-vocabulary": "Đang tách từ và tra từ điển",
  "saving-video": "Đang lưu video vào thư mục bài học",
  complete: "Bài học đã sẵn sàng",
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
    job = await responseJson(await apiFetch(`/api/jobs/${job.id}`));
  }
  showProgress(job);
  if (job.status === "failed") throw new Error(job.error || "Không thể xử lý video này.");
  return job.id;
}

const serverButton = $("#server-button");
const serverLabel = $("#server-label");
const serverDialog = $("#server-dialog");
const serverBase = $("#server-base");
const serverToken = $("#server-token");
const serverStatus = $("#server-status");

function setServerState(kind, label) {
  serverButton.dataset.state = kind;
  serverLabel.textContent = label;
}

function openServerDialog(message = "") {
  const current = serverSettings();
  serverBase.value = current.base;
  serverToken.value = current.token;
  serverStatus.textContent = message;
  if (!serverDialog.open) serverDialog.showModal();
}

async function checkServer() {
  try {
    const health = await responseJson(await apiFetch("/api/health"));
    if (health.auth_required && !health.authorized) {
      setServerState("auth", "Cần mã truy cập");
      return { health: null, message: "Máy chủ yêu cầu mã truy cập (chạy pnpm remote:token trên máy chủ để xem)." };
    }
    setServerState("ok", serverSettings().base ? new URL(serverSettings().base).host : "Máy này");
    return { health, message: "" };
  } catch {
    setServerState("offline", "Mất kết nối");
    const hint = serverSettings().base
      ? "Không kết nối được máy chủ. Máy của bạn có đang bật và chạy pnpm dev không?"
      : "Trang này không chạy cùng máy chủ. Hãy nhập địa chỉ backend trên máy của bạn.";
    return { health: null, message: hint };
  }
}

serverButton.addEventListener("click", () => openServerDialog());
onUnauthorized(() => {
  setServerState("auth", "Cần mã truy cập");
  openServerDialog("Mã truy cập không đúng hoặc chưa nhập.");
});
serverDialog.addEventListener("close", async () => {
  if (serverDialog.returnValue !== "save") return;
  saveServerSettings({ base: serverBase.value, token: serverToken.value });
  await loadHealth();
  if (state.health) await startApp();
});
$("#server-test").addEventListener("click", async () => {
  const previous = serverSettings();
  saveServerSettings({ base: serverBase.value, token: serverToken.value });
  serverStatus.textContent = "Đang kiểm tra…";
  const { health, message } = await checkServer();
  serverStatus.textContent = health ? "Kết nối thành công." : message;
  if (!health) saveServerSettings(previous);
});

async function loadHealth() {
  const { health, message } = await checkServer();
  state.health = health;
  configureSpeech({ server: health?.tts_ready });
  if (!health) {
    openServerDialog(message);
    return;
  }
  const items = [
    ["asr_model_ready", "Nhận dạng giọng nói", "pnpm setup:asr"],
    ["vietnamese_dictionary_loaded", "Từ điển Trung–Việt", "pnpm setup:dictionary"],
    ["dictionary_loaded", "Cách đọc (CC-CEDICT)", "pnpm setup:dictionary"],
    ["translation_model_ready", "Dịch câu offline", "pnpm setup:translation"],
    ["tts_ready", "Giọng đọc Trung–Việt", "pnpm setup:voices"],
    ["explain_model_ready", `Giải thích bằng AI (${state.health.explain_model})`, `ollama pull ${state.health.explain_model}`],
  ];
  readiness.replaceChildren(
    ...items.map(([key, label, command]) => {
      const ready = Boolean(state.health[key]);
      return element("li", ready ? "" : "is-missing", ready ? label : `${label}: chạy ${command}`);
    }),
  );
}

async function openSavedLesson(id, focus = {}) {
  try {
    openLesson(await responseJson(await apiFetch(`/api/lessons/${encodeURIComponent(id)}`)), focus);
  } catch (error) {
    setNote(error.message, true);
    showLibrary();
  }
}

function showLibrary() {
  teardownPlayer();
  window.clearTimeout(downloadTimer);
  stopSpeaking();
  state.lesson = null;
  workspace.hidden = true;
  library.hidden = false;
  libraryButton.hidden = true;
  lessonTitle.hidden = true;
  viewToggles.hidden = true;
  if (location.hash) history.replaceState(null, "", location.pathname);
  document.title = "Watch2Learn · Học tiếng Trung qua video";
  refreshLibrary();
}

function selectSource(source) {
  state.source = source;
  sourceTabs.forEach((tab) => {
    const selected = tab.dataset.source === source;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    $(`#${tab.getAttribute("aria-controls")}`).hidden = !selected;
  });
  setNote("");
}
sourceTabs.forEach((tab) => tab.addEventListener("click", () => selectSource(tab.dataset.source)));

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

async function submitLesson() {
  if (state.source === "youtube") {
    if (!youtubeUrl.value.trim()) throw new Error("Hãy dán link video YouTube.");
    if (!youtubeRights.checked) throw new Error("Hãy xác nhận bạn có quyền sử dụng video này.");
    setNote("Đang gửi link tới bộ xử lý trên máy này…");
    return responseJson(
      await apiFetch("/api/lessons/youtube", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: youtubeUrl.value.trim(),
          confirm_rights: true,
          transcript: form.querySelector("[name=youtube-transcript]:checked")?.value || "subtitles",
        }),
      }),
    );
  }
  const mediaFile = videoInput.files[0];
  if (!mediaFile) throw new Error("Hãy chọn một video hoặc file âm thanh.");
  setNote("Đang gửi video tới bộ xử lý trên máy này…");
  const body = new FormData();
  body.append("video", mediaFile);
  if (subtitleInput.files[0]) body.append("subtitle", subtitleInput.files[0]);
  return responseJson(await apiFetch("/api/lessons/mandarin-video", { method: "POST", body }));
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    const job = await submitLesson();
    const lessonId = await waitForJob(job);
    setNote("Bài học đã sẵn sàng và được lưu trên máy này.");
    progressBox.hidden = true;
    await openSavedLesson(lessonId);
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

libraryButton.addEventListener("click", showLibrary);
$(".brand").addEventListener("click", (event) => {
  if (!state.lesson) return;
  event.preventDefault();
  showLibrary();
});

/* ---------- Lesson rendering ---------- */

function openLesson(lesson, focus = {}) {
  teardownPlayer();
  window.clearTimeout(downloadTimer);
  Object.assign(state, {
    lesson,
    activeCue: -1,
    selectedWord: null,
    loop: false,
    clipEnd: null,
    preferYoutube: false,
    download: null,
    relisten: null,
  });
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
  history.replaceState(null, "", `#lesson=${encodeURIComponent(lesson.id)}`);

  loopButton.setAttribute("aria-pressed", "false");
  wordDetail.hidden = true;
  vocabSearch.value = "";
  dictionaryNotice.hidden = Boolean(lesson.vietnamese_dictionary?.loaded);
  dictionaryNotice.textContent =
    "Chưa có từ điển Trung–Việt offline (CVDICT). Chạy pnpm setup:dictionary rồi mở lại bài học.";

  renderTranscript();
  renderVocabulary();
  selectTab(0);
  transcriptPanel.scrollTop = 0;
  const focusIndex = focus.cueId ? cueIndexById.get(focus.cueId) : undefined;
  setActiveCue(focusIndex ?? 0, { scroll: focusIndex !== undefined });
  choosePlayer();
  if (focus.wordId && wordsById.has(focus.wordId)) {
    const occurrence = wordsById.get(focus.wordId).occurrences.findIndex((item) => item.cue_id === focus.cueId);
    showWord(focus.wordId, Math.max(0, occurrence));
  }
  if (lesson.source?.kind === "youtube" && !lesson.media?.available) resumeDownloadStatus(lesson.id);
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
    const token = button(`token${tokenStatusClass(segment.vocabulary_id)}`);
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
  if (cue.translation_skipped === "not-chinese") return "Không phải tiếng Trung — giữ nguyên, không dịch";
  if (cue.translation_vi) return cue.translation_vi;
  if (cue.translation_vi === "") return "";
  return state.health?.translation_model_ready ? "Đang dịch theo câu…" : "";
}

function updateTranslationNode(node, cue) {
  node.textContent = translationText(cue);
  node.classList.toggle("is-pending", !cue.translation_vi && !cue.translation_skipped);
  node.classList.toggle("is-skipped", cue.translation_skipped === "not-chinese");
}

function endsTranslationGroup(cue) {
  return !cue.translation_group_end || cue.translation_group_end === cue.id;
}

function renderTranscript() {
  const cues = state.lesson.cues;
  cueCount.textContent = cues.length;
  transcript.replaceChildren(
    ...cues.map((cue, index) => {
      const ends = endsTranslationGroup(cue);
      const foreign = cue.translation_skipped === "not-chinese" ? " is-foreign" : "";
      const row = element("li", `cue-row${ends ? "" : " continues"}${foreign}`);
      row.dataset.index = index;
      const time = button("cue-time", timeLabel(cue.start_ms), () => playFromCue(index));
      time.setAttribute("aria-label", `Phát từ ${timeLabel(cue.start_ms)}`);
      const body = element("div");
      const text = element("p", "cue-text");
      text.lang = "zh";
      renderCueText(text, cue, { compact: true });
      body.append(text);
      if (!ends) body.append(element("p", "cue-translation continues-note", "↓ câu còn tiếp — dịch chung với dòng dưới"));
      if (ends) {
        const translation = element("p", "cue-translation translation");
        translation.dataset.translationFor = cue.id;
        updateTranslationNode(translation, cue);
        body.append(translation);
      }
      row.append(time, body);
      return row;
    }),
  );
}

function firstMeaning(word) {
  return ownMeaning(word.id) || cleanSenses(word.definitions_vi).senses[0] || "";
}

/** The dictionary sense whose wording appears in this sentence's Vietnamese translation. */
function contextSense(word, cue) {
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

function matchesFilter(word, query) {
  const known = wordStatus(word.id) === "learned";
  if (state.filter === "known" && !known) return false;
  if (state.filter === "learning" && known) return false;
  if (!query) return true;
  const haystack = plain(
    [word.word, word.traditional, word.pinyin, word.pinyin_numbered, ...(word.definitions_vi || []), ownMeaning(word.id)]
      .filter(Boolean)
      .join(" "),
  );
  return haystack.replace(/\s+/g, "").includes(query.replace(/\s+/g, "")) || haystack.includes(query);
}

function renderVocabulary() {
  const query = plain(vocabSearch.value.trim());
  const words = state.lesson.vocabulary.filter((word) => matchesFilter(word, query));
  const learning = state.lesson.vocabulary.filter((word) => wordStatus(word.id) !== "learned").length;
  wordCount.textContent = `${learning}/${state.lesson.vocabulary.length}`;
  wordCount.title = `${learning} từ đang học trên tổng ${state.lesson.vocabulary.length} từ`;
  vocabEmpty.hidden = words.length > 0;
  vocabularyList.replaceChildren(
    ...words.map((word) => {
      const known = wordStatus(word.id) === "learned";
      const item = element("li", known ? "is-known" : "");
      const row = button(`word-row${word.id === state.selectedWord ? " is-selected" : ""}`, null, () => showWord(word.id));
      row.dataset.wordId = word.id;
      const hanzi = element("strong", null, word.word);
      hanzi.lang = "zh";
      const text = element("span", "word-row-text");
      text.append(
        element("span", "word-row-pinyin", word.pinyin),
        element("span", "word-row-meaning", firstMeaning(word) || "—"),
      );
      row.append(hanzi, text, element("span", "frequency", `${word.occurrence_count}×`));
      const check = button("known-check", "✓", () => toggleKnown(word.id));
      check.setAttribute("aria-pressed", String(known));
      check.setAttribute("aria-label", known ? `Bỏ đánh dấu đã biết ${word.word}` : `Đánh dấu đã biết ${word.word}`);
      item.append(row, check);
      return item;
    }),
  );
}

function tokenStatusClass(wordId) {
  const status = wordStatus(wordId);
  return status === "learned" ? " is-known" : status === "saved" ? " is-saved" : "";
}

function refreshWordMarks(wordId) {
  const classes = tokenStatusClass(wordId);
  document.querySelectorAll(`.token[data-word-id="${wordId}"]`).forEach((token) => {
    token.classList.toggle("is-known", classes.includes("is-known"));
    token.classList.toggle("is-saved", classes.includes("is-saved"));
  });
}

/** Save/learn a word with the occurrence currently shown, so the library keeps its context. */
async function setWordStatus(id, status) {
  const word = wordsById.get(id);
  const occurrence = word?.occurrences[id === state.selectedWord ? state.selectedOccurrence : 0];
  try {
    await updateWord(id, { status, lesson_id: state.lesson.id, cue_id: occurrence?.cue_id });
  } catch (error) {
    window.alert(error.message);
    return;
  }
  refreshWordMarks(id);
  renderVocabulary();
  if (state.selectedWord === id) showWord(id, state.selectedOccurrence, { keepScroll: true });
}

function toggleKnown(id) {
  setWordStatus(id, wordStatus(id) === "learned" ? "saved" : "learned");
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
  const cueIndex = cueIndexById.get(occurrence.cue_id);
  const cue = state.lesson.cues[cueIndex];
  const status = wordStatus(id);
  const own = ownMeaning(id);

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
  const actions = element("div", "word-actions");
  const speakButton = button("control-button", "🔈 Phát âm", () => speak(occurrence.surface || word.word, 0.7));
  const saveButton = button("control-button known-button", status ? "★ Đã lưu" : "☆ Lưu từ", () =>
    status ? setWordStatus(id, status) : setWordStatus(id, "saved"),
  );
  saveButton.setAttribute("aria-pressed", String(Boolean(status)));
  saveButton.disabled = Boolean(status);
  const knownButton = button(
    "control-button known-button",
    status === "learned" ? "✓ Đã thuộc" : "Đánh dấu đã thuộc",
    () => toggleKnown(id),
  );
  knownButton.setAttribute("aria-pressed", String(status === "learned"));
  const close = button("close-button", "×", closeWord);
  close.setAttribute("aria-label", "Đóng chi tiết từ");
  actions.append(speakButton, saveButton, knownButton, close);
  head.append(identity, actions);

  const studyActions = element("div", "study-actions");
  studyActions.append(
    button("control-button", "🎙 Luyện phát âm", () =>
      openPractice({
        target: occurrence.surface || word.word,
        pinyin: occurrence.pinyin || word.pinyin,
        translation: own || cleanSenses(word.definitions_vi).senses[0] || "",
        kind: "word",
        itemId: status ? id : null,
      }),
    ),
    button("control-button explain-button", "📖 Xem bài giảng", () =>
      explainWord(word, occurrence, cue, inContext, { speakIt: false }),
    ),
    button("control-button explain-button", "🗣 Nghe giảng", () =>
      explainWord(word, occurrence, cue, inContext, { speakIt: true }),
    ),
  );

  const meaning = element("div");
  const inContext = contextSense(word, cue);
  if (own) meaning.append(element("p", "own-meaning", `Nghĩa của bạn: ${own}`));
  if (inContext) {
    const highlight = element("p", "context-sense");
    highlight.append("Trong câu này: ", element("strong", null, inContext.text));
    highlight.title = "Nghĩa khớp với bản dịch của câu";
    meaning.append(highlight);
  }
  const vietnamese = cleanSenses(word.definitions_vi);
  if (vietnamese.senses.length) {
    const list = element("ol", "senses");
    vietnamese.senses.forEach((sense, index) => {
      list.append(element("li", inContext?.index === index ? "is-context" : "", sense));
    });
    meaning.append(list);
  } else if (!own) {
    meaning.append(
      element("p", "sense-note", "Từ điển offline chưa có nghĩa tiếng Việt cho từ này — bạn có thể tự ghi nghĩa bên dưới."),
    );
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
  contextActions.append(
    button("control-button", "▶ Nghe câu này", () => playClip(cueIndex)),
    button("control-button", "🔈 Đọc chậm", () => speak(occurrence.cue_text)),
  );
  if (word.occurrences.length > 8) {
    const position = state.selectedOccurrence;
    const previous = button("icon-button", "‹", () => showWord(id, position - 1, { keepScroll: true }));
    previous.disabled = position === 0;
    previous.setAttribute("aria-label", "Lần xuất hiện trước");
    const next = button("icon-button", "›", () => showWord(id, position + 1, { keepScroll: true }));
    next.disabled = position === word.occurrences.length - 1;
    next.setAttribute("aria-label", "Lần xuất hiện sau");
    const label = element("span", "occurrence-step", `Lần ${position + 1}/${word.occurrences.length} · ${timeLabel(occurrence.start_ms)}`);
    contextActions.append(previous, label, next);
  } else if (word.occurrences.length > 1) {
    word.occurrences.forEach((item, position) => {
      const chip = button("occurrence-chip", `${position + 1} · ${timeLabel(item.start_ms)}`, () =>
        showWord(id, position, { keepScroll: true }),
      );
      chip.setAttribute("aria-pressed", String(position === state.selectedOccurrence));
      chip.setAttribute("aria-label", `Lần xuất hiện ${position + 1} tại ${timeLabel(item.start_ms)}`);
      contextActions.append(chip);
    });
  }

  const edit = element("details", "edit-meaning word-section");
  const textarea = element("textarea");
  textarea.value = own;
  textarea.placeholder = "Ví dụ: học (trong câu này nghĩa là “học tập”)";
  textarea.setAttribute("aria-label", "Nghĩa của bạn");
  const save = button("control-button", "Lưu nghĩa", async () => {
    try {
      await updateWord(id, {
        status: status || "saved",
        own_meaning: textarea.value.trim(),
        lesson_id: state.lesson.id,
        cue_id: occurrence.cue_id,
      });
    } catch (error) {
      window.alert(error.message);
      return;
    }
    refreshWordMarks(id);
    renderVocabulary();
    showWord(id, state.selectedOccurrence, { keepScroll: true });
  });
  edit.append(element("summary", null, "Sửa / ghi chú nghĩa của bạn"), textarea, save);

  const explainBox = element("section", "explain-box");
  explainBox.hidden = true;
  wordDetail.replaceChildren(
    head,
    studyActions,
    explainBox,
    section("Nghĩa", meaning),
    section(`Trong video · ${word.occurrence_count} lần`, context, contextActions),
    edit,
  );
  wordDetail.hidden = false;
  wordDetail.scrollTop = keepScroll ? scroll : 0;
  highlightSelection();
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
 * A spoken Vietnamese lesson. `plan` lists the sections in teaching order; each
 * has a title and either fixed content built from verified data, or `ai: key`
 * filled by the local model as it writes. With `speakIt` the narration starts at
 * once and follows the sections in order as they become available.
 */
function lessonPanel(box, { title, request, plan, speakIt }) {
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
    if (item.ai) content.append(element("p", "sense-note", "AI trên máy bạn đang soạn phần này…"));
    body.append(node);
    return { ...item, node, content, ready: false, speech: [] };
  });

  const fill = (section, lines, speech) => {
    section.content.replaceChildren(...lines.map((line) => (line instanceof Node ? line : element("p", null, line))));
    section.speech = speech;
    section.ready = true;
    narrate();
  };
  const narrate = () => {
    if (!narration || box.run !== run) return;
    while (spokenUpTo < sections.length && sections[spokenUpTo].ready) {
      const section = sections[spokenUpTo];
      if (section.speech.length) narration.add([{ text: `${section.spokenTitle || section.title}.`, lang: "vi" }, ...section.speech]);
      spokenUpTo += 1;
    }
    if (spokenUpTo === sections.length) narration.finish();
  };
  const startSpeaking = () => {
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
  const controls = element("div", "explain-controls");
  controls.append(
    button("control-button", "🔊 Nghe giảng", () => {
      pause();
      startSpeaking();
    }),
    button("control-button", "⏹ Dừng", () => stopSpeaking()),
  );
  box.replaceChildren(element("h3", null, title), controls, status, body);
  box.hidden = false;
  if (speakIt) {
    pause();
    startSpeaking();
  }

  const examples = [];
  streamEvents("/api/explain", request, (event) => {
    if (box.run !== run) return false;
    if (event.type === "facts") {
      plan.forEach((item, index) => item.build && fill(sections[index], ...item.build(event.facts)));
    } else if (event.type === "section") {
      const section = sections.find((item) => item.ai === event.key);
      if (section) fill(section, [event.text], [{ text: event.text }]);
    } else if (event.type === "example") {
      examples.push(event);
      const section = sections.find((item) => item.examples);
      if (section?.ready) {
        const line = element("p", "lesson-example");
        const chinese = element("span", "lesson-example-zh", event.zh);
        chinese.lang = "zh";
        line.append(chinese, element("span", "lesson-example-pinyin", ` ${event.pinyin} `), `— ${event.vi}`);
        section.content.append(line);
        if (narration && spokenUpTo > sections.indexOf(section)) {
          narration.add([{ text: "Ví dụ:", lang: "vi" }, { text: event.zh, lang: "zh", rate: 0.8 }, { text: `nghĩa là ${event.vi}.`, lang: "vi" }]);
        } else {
          section.speech.push({ text: "Ví dụ:", lang: "vi" }, { text: event.zh, lang: "zh", rate: 0.8 }, { text: `nghĩa là ${event.vi}.`, lang: "vi" });
        }
      }
    } else if (event.type === "error") {
      sections
        .filter((item) => item.ai && !item.ready)
        .forEach((item) => fill(item, [element("p", "sense-note", event.message)], []));
    } else if (event.type === "done") {
      sections.filter((item) => !item.ready).forEach((item) => fill(item, [element("p", "sense-note", "AI chưa viết được phần này.")], []));
      if (!event.cached || sections.some((item) => item.ai)) {
        body.append(
          element("p", "ai-label", `Các phần “${plan.filter((item) => item.ai).map((item) => item.title).join("”, “")}” do AI chạy trên máy bạn soạn — có thể chưa chính xác.`),
        );
      }
    }
    return true;
  }).catch((error) => {
    if (box.run === run) status.textContent = error.message;
  });
}

function sentenceLine(text) {
  const node = element("p", "lesson-zh", text);
  node.lang = "zh";
  return node;
}

/** Word lesson: how to read it, meaning, pronunciation notes, where it is met, real use. */
function explainWord(word, occurrence, cue, inContext, { speakIt }) {
  const box = wordDetail.querySelector(".explain-box");
  if (!box) return;
  const surface = occurrence.surface || word.word;
  const senses = cleanSenses(word.definitions_vi).senses;
  const meaning = ownMeaning(word.id) || senses.slice(0, 3).join("; ");
  lessonPanel(box, {
    title: `Bài giảng: ${surface}`,
    request: { lesson_id: state.lesson.id, word_id: word.id, cue_id: occurrence.cue_id },
    speakIt,
    plan: [
      {
        title: "Từ này đọc thế nào",
        spokenTitle: "Từ này đọc thế nào",
        build: (facts) => {
          const pinyin = facts.syllables.map((item) => item.pinyin).join(" ");
          const lines = [`${surface} đọc là ${pinyin}.`];
          const speech = [
            { text: "Từ này đọc là", lang: "vi" },
            { text: surface, lang: "zh", rate: 0.8 },
            { text: "Đọc chậm lại:", lang: "vi" },
            { text: surface, lang: "zh", rate: 0.55 },
          ];
          if (facts.syllables.length > 1) {
            facts.syllables.forEach((item) => {
              lines.push(`${item.character} (${item.pinyin}): ${toneDescription(item.pinyin)}.`);
              speech.push(
                { text: "Chữ", lang: "vi" },
                { text: item.character, lang: "zh", rate: 0.6 },
                { text: `${toneDescription(item.pinyin)}.`, lang: "vi" },
              );
            });
          } else if (facts.syllables[0]) {
            lines.push(`${toneDescription(facts.syllables[0].pinyin)}.`);
            speech.push({ text: `Từ này mang ${toneDescription(facts.syllables[0].pinyin)}.`, lang: "vi" });
          }
          return [lines, speech];
        },
      },
      {
        title: "Nghĩa là gì",
        build: () => {
          const lines = [];
          const speech = [];
          if (meaning) {
            lines.push(`Nghĩa: ${meaning}.`);
            speech.push({ text: `Từ này có nghĩa là ${meaning}.`, lang: "vi" });
          }
          if (inContext) {
            lines.push(`Trong câu này: ${inContext.text}.`);
            speech.push({ text: `Trong câu trong video, nó mang nghĩa ${inContext.text}.`, lang: "vi" });
          }
          lines.push(sentenceLine(occurrence.cue_text));
          if (cue?.translation_vi) lines.push(`→ ${cue.translation_vi}`);
          speech.push(
            { text: "Câu trong video là:", lang: "vi" },
            { text: occurrence.cue_text, lang: "zh", rate: 0.85 },
          );
          if (cue?.translation_vi) speech.push({ text: `nghĩa là: ${cue.translation_vi}`, lang: "vi" });
          return [lines, speech];
        },
      },
      {
        title: "Lưu ý khi phát âm",
        build: (facts) =>
          facts.tips.length
            ? [facts.tips, [{ text: facts.tips.join(" ") }]]
            : [["Từ này không có âm đặc biệt khó với người Việt."], [{ text: "Từ này không có âm đặc biệt khó với người Việt.", lang: "vi" }]],
      },
      { title: "Thường gặp ở đâu trong giao tiếp", ai: "giao_tiep" },
      { title: "Sử dụng thực tế như thế nào", ai: "su_dung", examples: true },
    ],
  });
}

/** Sentence lesson: how to read it, meaning word by word, pronunciation, structure, when used. */
function explainSentence({ speakIt }) {
  const cue = state.lesson?.cues[state.activeCue];
  if (!cue) return;
  const glossary = cue.segments
    .filter((segment) => segment.vocabulary_id && wordsById.has(segment.vocabulary_id))
    .map((segment) => ({ text: segment.text, pinyin: segment.pinyin, meaning: firstMeaning(wordsById.get(segment.vocabulary_id)) }))
    .filter((item) => item.meaning);
  lessonPanel($("#sentence-explain"), {
    title: "Bài giảng câu",
    request: { lesson_id: state.lesson.id, cue_id: cue.id },
    speakIt,
    plan: [
      {
        title: "Câu này đọc thế nào",
        build: (facts) => [
          [sentenceLine(cue.text), facts.syllables.map((item) => item.pinyin).join(" ")],
          [
            { text: "Câu này đọc là", lang: "vi" },
            { text: cue.text, lang: "zh", rate: 0.85 },
            { text: "Đọc chậm lại:", lang: "vi" },
            { text: cue.text, lang: "zh", rate: 0.6 },
          ],
        ],
      },
      {
        title: "Nghĩa là gì",
        build: () => {
          const lines = cue.translation_vi ? [`Nghĩa: ${cue.translation_vi}`] : [];
          const speech = cue.translation_vi ? [{ text: `Câu này nghĩa là: ${cue.translation_vi}`, lang: "vi" }] : [];
          if (glossary.length) {
            speech.push({ text: "Từng từ trong câu:", lang: "vi" });
            glossary.forEach((item) => {
              lines.push(`${item.text} (${item.pinyin || ""}): ${item.meaning}`);
              speech.push({ text: item.text, lang: "zh", rate: 0.75 }, { text: `là ${item.meaning}.`, lang: "vi" });
            });
          }
          return [lines, speech];
        },
      },
      {
        title: "Lưu ý khi phát âm",
        build: (facts) =>
          facts.tips.length
            ? [facts.tips, [{ text: facts.tips.join(" ") }]]
            : [["Câu này không có âm đặc biệt khó."], [{ text: "Câu này không có âm đặc biệt khó.", lang: "vi" }]],
      },
      { title: "Cấu trúc câu", ai: "cau_truc" },
      { title: "Thường nói khi nào, ở đâu", ai: "giao_tiep", examples: true },
    ],
  });
}

function closeSentenceExplanation() {
  const box = $("#sentence-explain");
  box.run = null;
  box.hidden = true;
}

function closeWord() {
  const box = wordDetail.querySelector(".explain-box");
  if (box) box.run = null;
  stopSpeaking();
  state.selectedWord = null;
  wordDetail.hidden = true;
  highlightSelection();
}

/* ---------- Playback ---------- */

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
  updateSentenceButtons();
  if (!changed && nowText.childElementCount) return;
  closeSentenceExplanation();
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

function updateSentenceButtons() {
  const cue = state.lesson?.cues[state.activeCue];
  if (!cue) return;
  const status = sentenceStatus(state.lesson.id, cue.id);
  saveCueButton.textContent = status ? "★ Đã lưu câu" : "☆ Lưu câu";
  saveCueButton.setAttribute("aria-pressed", String(Boolean(status)));
  learnedCueButton.setAttribute("aria-pressed", String(status === "learned"));
  learnedCueButton.textContent = status === "learned" ? "✓ Đã thuộc câu" : "Đánh dấu thuộc câu";
  transcript.querySelectorAll(".cue-row").forEach((row) => {
    const rowCue = state.lesson.cues[Number(row.dataset.index)];
    row.classList.toggle("is-saved-sentence", Boolean(sentenceStatus(state.lesson.id, rowCue.id)));
  });
}

async function setSentenceStatus(status) {
  const cue = state.lesson.cues[state.activeCue];
  try {
    await updateSentence(state.lesson.id, cue.id, status);
  } catch (error) {
    window.alert(error.message);
  }
}

$("#explain-cue").addEventListener("click", () => explainSentence({ speakIt: true }));

saveCueButton.addEventListener("click", () => {
  const cue = state.lesson.cues[state.activeCue];
  if (!sentenceStatus(state.lesson.id, cue.id)) setSentenceStatus("saved");
});
learnedCueButton.addEventListener("click", () => {
  const cue = state.lesson.cues[state.activeCue];
  setSentenceStatus(sentenceStatus(state.lesson.id, cue.id) === "learned" ? "saved" : "learned");
});
practiceCueButton.addEventListener("click", () => {
  const index = state.activeCue;
  const cue = state.lesson.cues[index];
  const saved = sentenceStatus(state.lesson.id, cue.id);
  openPractice({
    target: cue.text,
    pinyin: cue.segments.map((segment) => segment.pinyin).filter(Boolean).join(" "),
    translation: cue.translation_vi,
    kind: "sentence",
    itemId: saved ? `${state.lesson.id}:${cue.id}` : null,
    playModel: hasPlayer() ? () => playClip(index) : null,
  });
});
onLearnerChange(() => {
  if (!state.lesson) return;
  updateSentenceButtons();
});

function seekTo(index) {
  const cue = state.lesson.cues[index];
  setActiveCue(index);
  if (!hasPlayer()) return false;
  seekMs(cue.start_ms);
  return true;
}

function playFromCue(index) {
  state.clipEnd = null;
  if (seekTo(index)) play();
}

function playClip(index) {
  if (index === undefined || index < 0) return;
  if (!seekTo(index)) {
    speak(state.lesson.cues[index].text);
    return;
  }
  state.clipEnd = state.loop ? null : state.lesson.cues[index].end_ms;
  play();
}

function stepCue(offset) {
  const target = Math.min(Math.max(state.activeCue + offset, 0), state.lesson.cues.length - 1);
  if (state.loop || !isPaused()) playClip(target);
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

function onTick() {
  if (!state.lesson || !hasPlayer()) return;
  const now = currentMs();
  const active = state.lesson.cues[state.activeCue];
  if (state.loop && active && !isPaused() && (now >= active.end_ms || now < active.start_ms - 300)) {
    seekMs(active.start_ms);
    return;
  }
  if (state.clipEnd !== null && now >= state.clipEnd - 80) {
    // Stop just inside the sentence so the active cue does not jump to the next one.
    pause();
    seekMs(Math.max(active?.start_ms ?? 0, state.clipEnd - 120));
    state.clipEnd = null;
    return;
  }
  if (state.loop) return;
  const index = cueIndexAt(now);
  if (index !== -1 && index !== state.activeCue) setActiveCue(index);
}

video.addEventListener("timeupdate", onTick);
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

/* ---------- Sentence translations for lessons saved earlier ---------- */

async function backfillTranslations() {
  const lesson = state.lesson;
  if (!state.health?.translation_model_ready) return;
  const complete = lesson.cues.every((cue) => typeof cue.translation_vi === "string");
  if (lesson.translation?.unit === state.health.translation_unit && complete) return;
  try {
    const result = await responseJson(await apiFetch(`/api/lessons/${lesson.id}/translations`, { method: "POST" }));
    lesson.translation = result.translation;
    result.cues.forEach((row) => {
      const cue = lesson.cues[cueIndexById.get(row.id)];
      if (cue) Object.assign(cue, row);
    });
  } catch {
    lesson.cues.forEach((cue) => {
      if (typeof cue.translation_vi !== "string") cue.translation_vi = "";
    });
  }
  if (state.lesson !== lesson) return;
  renderTranscript();
  const active = state.activeCue;
  state.activeCue = -1;
  setActiveCue(active, { scroll: false });
  if (state.selectedWord) showWord(state.selectedWord, state.selectedOccurrence, { keepScroll: true });
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
  if (key === " " && !["BUTTON", "SUMMARY", "A"].includes(target.tagName)) {
    event.preventDefault();
    if (!hasPlayer()) return;
    state.clipEnd = null;
    isPaused() ? play() : pause();
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
function openFromHash() {
  if (!state.health) return;
  const lessonId = new URLSearchParams(location.hash.slice(1)).get("lesson");
  if (lessonId && lessonId !== state.lesson?.id) openSavedLesson(lessonId);
}
window.addEventListener("hashchange", openFromHash);
const voiceButton = $("#voice-button");
const voiceDialog = $("#voice-dialog");
const voiceSelects = { vi: $("#voice-vi"), zh: $("#voice-zh") };
const voiceStatus = $("#voice-status");
const VOICE_SAMPLES = {
  vi: [{ text: "Xin chào, mình sẽ giảng cho bạn từng từ tiếng Trung trong video.", lang: "vi" }],
  zh: [{ text: "你好，我们一起学习中文吧。", lang: "zh", rate: 0.9 }],
};

async function openVoiceDialog() {
  voiceStatus.textContent = "Đang tải danh sách giọng…";
  voiceDialog.showModal();
  try {
    const data = await apiJson("/api/voices");
    for (const lang of ["vi", "zh"]) {
      voiceSelects[lang].replaceChildren(
        ...data.available[lang].map((voice) => {
          const option = element("option", null, voice.label);
          option.value = voice.id;
          option.selected = voice.id === data.selected[lang];
          return option;
        }),
      );
    }
    voiceStatus.textContent = "";
  } catch (error) {
    voiceStatus.textContent = error.message;
  }
}

for (const lang of ["vi", "zh"]) {
  $(`#voice-${lang}-test`).addEventListener("click", () => {
    voiceStatus.textContent = "Đang tạo giọng mẫu…";
    const narration = createNarration({
      voices: { [lang]: voiceSelects[lang].value },
      onStart: () => (voiceStatus.textContent = ""),
      onError: (error) => (voiceStatus.textContent = error.message),
    });
    narration.add(VOICE_SAMPLES[lang]);
    narration.finish();
  });
}
voiceButton.addEventListener("click", openVoiceDialog);
voiceDialog.addEventListener("close", async () => {
  stopSpeaking();
  if (voiceDialog.returnValue !== "save") return;
  try {
    await apiJson("/api/voices", {
      method: "PUT",
      json: { vi: voiceSelects.vi.value, zh: voiceSelects.zh.value },
    });
  } catch (error) {
    window.alert(error.message);
  }
});

async function startApp() {
  voiceButton.hidden = !state.health?.tts_ready;
  try {
    await loadLearner();
  } catch {
    /* library state is optional for viewing lessons */
  }
  refreshLibrary();
  openFromHash();
}

initLibrary({ openLesson: (id, focus) => openSavedLesson(id, focus) });
loadHealth().then(() => state.health && startApp());
