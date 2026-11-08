// Pronunciation practice: listen to the model, record yourself, get an estimated score.
import { apiFetch, responseJson } from "./api.js";
import { speak } from "./speech.js";
import { $, button, element, scoreLabel } from "./ui.js";

const dialog = $("#practice-dialog");
const body = $("#practice-body");
const MAX_RECORDING_MS = 15000;
const MIME_TYPES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4", "audio/webm"];
let session = null;

function stopStream() {
  window.clearTimeout(session?.stopTimer);
  window.clearInterval(session?.clock);
  session?.stream?.getTracks().forEach((track) => track.stop());
  if (session?.recordingUrl) URL.revokeObjectURL(session.recordingUrl);
}

dialog.addEventListener("close", () => {
  if (session?.recorder?.state === "recording") {
    session.cancelled = true;
    session.recorder.stop();
  }
  stopStream();
  session = null;
});

function extensionFor(type) {
  if (type.includes("mp4")) return "m4a";
  if (type.includes("ogg")) return "ogg";
  return "webm";
}

async function startRecording(recordButton, status) {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    status.textContent = "Trình duyệt này không cho ghi âm. Cần mở trang qua HTTPS hoặc localhost.";
    return;
  }
  try {
    session.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
  } catch {
    status.textContent = "Chưa được cấp quyền dùng micro.";
    return;
  }
  const mimeType = MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
  const recorder = new MediaRecorder(session.stream, mimeType ? { mimeType } : {});
  const chunks = [];
  session.recorder = recorder;
  recorder.addEventListener("dataavailable", (event) => event.data.size && chunks.push(event.data));
  recorder.addEventListener("stop", () => {
    session?.stream?.getTracks().forEach((track) => track.stop());
    if (!session || session.cancelled) return;
    upload(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }), recordButton, status);
  });
  recorder.start();
  const started = Date.now();
  recordButton.textContent = "⏹ Dừng & chấm điểm";
  recordButton.classList.add("is-recording");
  status.textContent = "Đang ghi âm… hãy đọc to và rõ.";
  session.clock = window.setInterval(() => {
    status.textContent = `Đang ghi âm… ${((Date.now() - started) / 1000).toFixed(0)}s`;
  }, 500);
  session.stopTimer = window.setTimeout(() => recorder.state === "recording" && recorder.stop(), MAX_RECORDING_MS);
}

async function upload(blob, recordButton, status) {
  window.clearInterval(session.clock);
  window.clearTimeout(session.stopTimer);
  recordButton.disabled = true;
  recordButton.classList.remove("is-recording");
  recordButton.textContent = "🎙 Ghi âm lại";
  status.textContent = "Đang chấm điểm trên máy của bạn…";
  if (session.recordingUrl) URL.revokeObjectURL(session.recordingUrl);
  session.recordingUrl = URL.createObjectURL(blob);
  const form = new FormData();
  form.append("audio", blob, `recording.${extensionFor(blob.type)}`);
  form.append("target", session.options.target);
  if (session.options.kind && session.options.itemId) {
    form.append("kind", session.options.kind);
    form.append("item_id", session.options.itemId);
  }
  const current = session;
  try {
    const result = await responseJson(await apiFetch("/api/pronunciation", { method: "POST", body: form }));
    if (session !== current) return;
    status.textContent = "";
    renderResult(result);
    current.options.onScored?.(result);
  } catch (error) {
    if (session === current) status.textContent = error.message;
  } finally {
    recordButton.disabled = false;
  }
}

function renderResult(result) {
  const area = $("#practice-result");
  const tone = result.score >= 85 ? "good" : result.score >= 60 ? "fair" : "poor";
  const summary = element("div", `score-summary is-${tone}`);
  summary.append(element("strong", "score-value", `${result.score}%`), element("span", null, scoreLabel(result.score)));
  const heard = element("p", "heard");
  heard.append("Máy nghe được: ");
  const heardText = element("span", null, result.heard_text || "(không nghe rõ)");
  heardText.lang = "zh";
  heard.append(heardText);
  if (result.heard_pinyin) heard.append(element("span", "muted", ` · ${result.heard_pinyin}`));

  const syllables = element("ol", "syllables");
  for (const item of result.syllables) {
    const ok = item.score >= 100;
    const chip = element("li", `syllable ${ok ? "is-ok" : item.score > 0 ? "is-partial" : "is-missed"}`);
    const character = element("span", "syllable-character", item.character);
    character.lang = "zh";
    chip.append(character, element("span", "syllable-pinyin", item.expected));
    const note = !item.heard
      ? "không nghe thấy"
      : ok
        ? "đúng"
        : [!item.initial && "phụ âm đầu", !item.final && "vần", !item.tone && "thanh điệu"]
            .filter(Boolean)
            .map((part) => `sai ${part}`)
            .join(", ") + ` (nghe: ${item.heard})`;
    chip.append(element("span", "syllable-note", note));
    chip.title = note;
    syllables.append(chip);
  }
  const replay = button("control-button", "▶ Nghe lại giọng bạn", () => new Audio(session.recordingUrl).play());
  const caveat = element(
    "p",
    "practice-caveat",
    "Điểm là ước lượng: máy nghe bằng Whisper rồi so pinyin (phụ âm đầu, vần, thanh) với câu mẫu.",
  );
  area.replaceChildren(summary, heard, syllables, replay, caveat);
}

/**
 * options: { target, pinyin, translation, kind: "word"|"sentence", itemId, playModel, onScored }
 */
export function openPractice(options) {
  if (dialog.open) dialog.close();
  session = { options };
  const target = element("p", "practice-target", options.target);
  target.lang = "zh";
  const status = element("p", "practice-status");
  status.setAttribute("role", "status");
  const recordButton = button("primary-button record-button", "🎙 Bắt đầu ghi âm", () => {
    if (session.recorder?.state === "recording") session.recorder.stop();
    else startRecording(recordButton, status);
  });
  const model = button("control-button", options.playModel ? "▶ Nghe giọng gốc" : "🔈 Nghe mẫu", () =>
    options.playModel ? options.playModel() : speak(options.target, 0.7),
  );
  const slow = button("control-button", "🔈 Đọc chậm", () => speak(options.target, 0.6));
  const controls = element("div", "practice-controls");
  controls.append(model, slow);
  body.replaceChildren(
    element("p", "practice-kind", options.kind === "sentence" ? "Luyện đọc câu" : "Luyện phát âm từ"),
    target,
    element("p", "practice-pinyin", options.pinyin || ""),
    element("p", "practice-translation", options.translation || ""),
    controls,
    recordButton,
    status,
    element("div", "practice-result"),
  );
  body.querySelector(".practice-result").id = "practice-result";
  dialog.showModal();
}
