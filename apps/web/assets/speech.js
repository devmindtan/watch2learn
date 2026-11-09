// Reading aloud. Preferred: local voices on the backend (VieNeu for Vietnamese,
// Kokoro for Chinese) — works in every browser; Chrome on Linux has no Web Speech
// voices by default. Fallback: browser/OS voices when the backend has none.
// Long scripts are cut into sentence-sized chunks that are synthesized one ahead
// and played as soon as ready, so speech starts within seconds.
import { apiFetch, responseJson } from "./api.js";

const synth = "speechSynthesis" in window ? window.speechSynthesis : null;
const listeners = new Set();
const HAN = /[㐀-䶿一-鿿豈-﫿]/;
const HAN_RUN = /([㐀-䶿一-鿿豈-﫿][㐀-䶿一-鿿豈-﫿，。！？、；：·\s]*)/;
const SENTENCE_END = /[.!?…:;]["”’)]*$/;
const CHUNK_CHARACTERS = 70;
let voices = { zh: null, vi: null };
let serverVoices = false;
let current = null;

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

if (synth) {
  const refresh = () => {
    voices = { zh: pick(["zh-cn", "zh-hans", "cmn", "zh"]), vi: pick(["vi"]) };
    notify();
  };
  refresh();
  synth.addEventListener?.("voiceschanged", refresh);
}

/** Called after the backend health check: use its voices when installed. */
export function configureSpeech({ server }) {
  serverVoices = Boolean(server);
  notify();
}

export function speechInfo() {
  return { server: serverVoices, browserZh: voices.zh, browserVi: voices.vi };
}

export function onVoices(listener) {
  listeners.add(listener);
  listener(speechInfo());
}

/** Split into Chinese/Vietnamese runs, then group runs into sentence-sized chunks. */
export function chunkScript(parts) {
  const runs = [];
  for (const part of parts) {
    if (!part?.text?.trim()) continue;
    const pieces = part.lang ? [part.text] : part.text.split(HAN_RUN);
    for (const piece of pieces) {
      if (!piece.trim()) continue;
      const lang = part.lang || (HAN.test(piece) ? "zh" : "vi");
      const rate = part.rate ?? (lang === "zh" ? 0.85 : 1);
      if (lang === "vi") {
        for (const sentence of piece.split(/(?<=[.!?…])\s+/)) {
          if (sentence.trim()) runs.push({ text: sentence.trim(), lang, rate });
        }
      } else {
        runs.push({ text: piece.trim(), lang, rate });
      }
    }
  }
  const chunks = [];
  let chunk = [];
  let length = 0;
  for (const run of runs) {
    chunk.push(run);
    length += run.text.length;
    // The first chunk ends at the first sentence so speech starts as soon as possible.
    const enough = chunks.length === 0 || length >= CHUNK_CHARACTERS * 0.5;
    if (run.lang === "vi" && SENTENCE_END.test(run.text) && enough) {
      chunks.push(chunk);
      chunk = [];
      length = 0;
    } else if (length >= CHUNK_CHARACTERS * 2) {
      chunks.push(chunk);
      chunk = [];
      length = 0;
    }
  }
  if (chunk.length) chunks.push(chunk);
  return chunks;
}

async function fetchAudio(chunk, voiceOverride) {
  const body = { parts: chunk.map((part) => ({ ...part, text: part.text.slice(0, 600) })) };
  if (voiceOverride) body.voices = voiceOverride;
  const response = await apiFetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) await responseJson(response);
  return URL.createObjectURL(await response.blob());
}

function playUrl(url, narration) {
  return new Promise((resolve) => {
    const audio = new Audio(url);
    narration.audio = audio;
    const finish = () => {
      URL.revokeObjectURL(url);
      resolve();
    };
    audio.addEventListener("ended", finish, { once: true });
    audio.addEventListener("error", finish, { once: true });
    narration.release = finish;
    audio.play().catch(finish);
  });
}

function speakInBrowser(chunk, narration) {
  return new Promise((resolve) => {
    if (!synth) return resolve();
    const items = chunk.map((part) => {
      const voice = part.lang === "zh" ? voices.zh : voices.vi;
      const item = new SpeechSynthesisUtterance(part.text);
      item.lang = voice?.lang || (part.lang === "zh" ? "zh-CN" : "vi-VN");
      if (voice) item.voice = voice;
      item.rate = part.rate;
      return item;
    });
    items[items.length - 1].onend = () => resolve();
    items[items.length - 1].onerror = () => resolve();
    narration.release = resolve;
    items.forEach((item) => synth.speak(item));
  });
}

/**
 * A narration that can grow while it plays: add(parts) any number of times,
 * finish() when no more parts will come. Only one narration plays at a time.
 */
export function createNarration({ onError, onStart, onEnd, voices: voiceOverride } = {}) {
  stopSpeaking();
  const narration = { stopped: false, queue: [], finished: false, wake: null, audio: null, release: null };
  current = narration;
  const nextChunk = async () => {
    while (!narration.queue.length && !narration.finished && !narration.stopped) {
      await new Promise((resolve) => (narration.wake = resolve));
    }
    return narration.stopped ? null : narration.queue.shift() || null;
  };
  const prepare = (chunk) =>
    chunk && serverVoices ? fetchAudio(chunk, voiceOverride).catch((error) => ({ error })) : Promise.resolve(chunk);

  (async () => {
    let started = false;
    let chunk = await nextChunk();
    let pending = prepare(chunk);
    while (chunk && !narration.stopped) {
      const ready = await pending;
      // Synthesize the next chunk while this one plays, if it is already queued.
      const following = narration.queue.length ? narration.queue.shift() : undefined;
      const followingPending = following ? prepare(following) : null;
      if (narration.stopped) break;
      if (ready?.error) {
        onError?.(ready.error);
      } else {
        if (!started) {
          started = true;
          onStart?.();
        }
        if (serverVoices) await playUrl(ready, narration);
        else await speakInBrowser(chunk, narration);
      }
      if (following) {
        chunk = following;
        pending = followingPending;
      } else {
        chunk = await nextChunk();
        pending = prepare(chunk);
      }
    }
    if (!narration.stopped) onEnd?.();
    if (current === narration) current = null;
  })();

  return {
    add(parts) {
      narration.queue.push(...chunkScript(parts));
      narration.wake?.();
    },
    finish() {
      narration.finished = true;
      narration.wake?.();
    },
    stop() {
      if (current === narration) stopSpeaking();
    },
    get available() {
      return serverVoices || Boolean(voices.zh || voices.vi);
    },
  };
}

export function stopSpeaking() {
  if (current) {
    current.stopped = true;
    current.audio?.pause();
    current.release?.();
    current.wake?.();
    current = null;
  }
  synth?.cancel();
}

/** Speak a fixed script. Resolves to false when no voice is available. */
export async function speakScript(parts, { onEnd, onError, voices: voiceOverride } = {}) {
  const narration = createNarration({ onEnd, onError, voices: voiceOverride });
  if (!narration.available) return false;
  narration.add(parts);
  narration.finish();
  return true;
}

export function speak(text, rate = 0.75) {
  if (!text) return Promise.resolve(false);
  return speakScript([{ text, lang: "zh", rate }]);
}

const TONE_MARKS = ["āēīōūǖ", "áéíóúǘ", "ǎěǐǒǔǚ", "àèìòùǜ"];
const TONE_DESCRIPTIONS = {
  1: "thanh 1, giọng cao và đều",
  2: "thanh 2, giọng đi lên, gần giống dấu sắc",
  3: "thanh 3, giọng hạ thấp rồi lên, gần giống dấu hỏi",
  4: "thanh 4, giọng rơi mạnh từ cao xuống",
  5: "thanh nhẹ, đọc ngắn và nhẹ",
};

export function toneNumber(syllable) {
  const index = TONE_MARKS.findIndex((marks) => [...syllable].some((character) => marks.includes(character)));
  return index === -1 ? 5 : index + 1;
}

export function toneDescription(syllable) {
  return TONE_DESCRIPTIONS[toneNumber(syllable)];
}
