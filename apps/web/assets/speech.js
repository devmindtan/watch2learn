// Reading aloud. Preferred: local Piper voices on the backend (works in every
// browser — Chrome on Linux has no Web Speech voices by default). Fallback: the
// browser/OS voices when the backend has no voices installed.
import { apiFetch, responseJson } from "./api.js";

const synth = "speechSynthesis" in window ? window.speechSynthesis : null;
const listeners = new Set();
const HAN = /[㐀-䶿一-鿿豈-﫿]/;
const HAN_RUN = /([㐀-䶿一-鿿豈-﫿][㐀-䶿一-鿿豈-﫿，。！？、；：·\s]*)/;
let voices = { zh: null, vi: null };
let serverVoices = false;
let audio = null;
let audioUrl = null;
let playToken = 0;

function pick(prefixes) {
  const all = synth.getVoices();
  for (const prefix of prefixes) {
    const matches = all.filter((voice) => voice.lang.toLowerCase().replace("_", "-").startsWith(prefix));
    const local = matches.find((voice) => voice.localService);
    if (local || matches[0]) return local || matches[0];
  }
  return null;
}

function notify() {
  listeners.forEach((listener) => listener(speechInfo()));
}

function refresh() {
  voices = { zh: pick(["zh-cn", "zh-hans", "cmn", "zh"]), vi: pick(["vi"]) };
  notify();
}

if (synth) {
  refresh();
  synth.addEventListener?.("voiceschanged", refresh);
}

/** Called after the backend health check: use its voices when installed. */
export function configureSpeech({ server }) {
  serverVoices = Boolean(server);
  notify();
}

export function speechInfo() {
  return {
    server: serverVoices,
    browserZh: voices.zh,
    browserVi: voices.vi,
    available: serverVoices || Boolean(voices.zh || voices.vi),
  };
}

export function onVoices(listener) {
  listeners.add(listener);
  listener(speechInfo());
}

export function stopSpeaking() {
  playToken += 1;
  synth?.cancel();
  if (audio) audio.pause();
}

/** Split text into Chinese and Vietnamese runs. */
function expand(parts) {
  const expanded = [];
  for (const part of parts) {
    if (!part?.text?.trim()) continue;
    if (part.lang) {
      expanded.push({ text: part.text.trim(), lang: part.lang, rate: part.rate ?? (part.lang === "zh" ? 0.8 : 1) });
      continue;
    }
    for (const piece of part.text.split(HAN_RUN)) {
      if (!piece.trim()) continue;
      const chinese = HAN.test(piece);
      expanded.push({ text: piece.trim(), lang: chinese ? "zh" : "vi", rate: chinese ? 0.85 : 1 });
    }
  }
  return expanded;
}

async function playOnServer(parts, token, onEnd, onError) {
  const response = await apiFetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parts: parts.map((part) => ({ ...part, text: part.text.slice(0, 600) })) }),
  });
  if (!response.ok) await responseJson(response);
  const blob = await response.blob();
  if (token !== playToken) return;
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audioUrl = URL.createObjectURL(blob);
  audio = new Audio(audioUrl);
  audio.addEventListener("ended", () => token === playToken && onEnd?.(), { once: true });
  await audio.play().catch((error) => onError?.(error));
}

function playInBrowser(parts, onEnd) {
  if (!synth) return false;
  synth.cancel();
  const queue = parts.map((part) => {
    const voice = part.lang === "zh" ? voices.zh : voices.vi;
    const item = new SpeechSynthesisUtterance(part.text);
    item.lang = voice?.lang || (part.lang === "zh" ? "zh-CN" : "vi-VN");
    if (voice) item.voice = voice;
    item.rate = part.rate;
    return item;
  });
  queue[queue.length - 1].onend = () => onEnd?.();
  queue.forEach((item) => synth.speak(item));
  return Boolean(voices.zh || voices.vi);
}

/**
 * Speak a script: parts are {text, lang?, rate?}; parts without `lang` are split
 * into Chinese/Vietnamese automatically. Returns a promise resolving to true when
 * audio started, false when no voice is available.
 */
export async function speakScript(parts, { onEnd, onError } = {}) {
  stopSpeaking();
  const token = playToken;
  const expanded = expand(parts);
  if (!expanded.length) return false;
  if (serverVoices) {
    try {
      await playOnServer(expanded, token, onEnd, onError);
      return true;
    } catch (error) {
      onError?.(error);
      if (token !== playToken) return false;
    }
  }
  return playInBrowser(expanded, onEnd);
}

export function speak(text, rate = 0.75) {
  if (!text) return Promise.resolve(false);
  return speakScript([{ text, lang: "zh", rate }]);
}

const TONE_MARKS = ["āēīōūǖ", "áéíóúǘ", "ǎěǐǒǔǚ", "àèìòùǜ"];
const TONE_DESCRIPTIONS = {
  1: "thanh 1: giọng cao và đều",
  2: "thanh 2: giọng đi lên, gần giống dấu sắc",
  3: "thanh 3: giọng hạ thấp rồi lên, gần giống dấu hỏi",
  4: "thanh 4: giọng rơi mạnh từ cao xuống",
  5: "thanh nhẹ: đọc ngắn và nhẹ",
};

export function toneNumber(syllable) {
  const index = TONE_MARKS.findIndex((marks) => [...syllable].some((character) => marks.includes(character)));
  return index === -1 ? 5 : index + 1;
}

export function toneDescription(syllable) {
  return TONE_DESCRIPTIONS[toneNumber(syllable)];
}
