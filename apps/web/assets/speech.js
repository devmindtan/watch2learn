// Text-to-speech with the browser/OS voices (Chinese and Vietnamese). Mixed text is
// split so Chinese characters are read by a Chinese voice and the rest in Vietnamese.

const synth = "speechSynthesis" in window ? window.speechSynthesis : null;
export const canSpeak = Boolean(synth);
const listeners = new Set();
let voices = { zh: null, vi: null };
const HAN = /[㐀-䶿一-鿿豈-﫿]/;
const HAN_RUN = /([㐀-䶿一-鿿豈-﫿][㐀-䶿一-鿿豈-﫿，。！？、；：·\s]*)/;

function pick(prefixes) {
  const all = synth.getVoices();
  for (const prefix of prefixes) {
    const matches = all.filter((voice) => voice.lang.toLowerCase().replace("_", "-").startsWith(prefix));
    const local = matches.find((voice) => voice.localService);
    if (local || matches[0]) return local || matches[0];
  }
  return null;
}

function refresh() {
  voices = { zh: pick(["zh-cn", "zh-hans", "cmn", "zh"]), vi: pick(["vi"]) };
  listeners.forEach((listener) => listener(voices));
}

if (synth) {
  refresh();
  synth.addEventListener?.("voiceschanged", refresh);
}

export function onVoices(listener) {
  listeners.add(listener);
  listener(voices);
}

export function stopSpeaking() {
  synth?.cancel();
}

function utterance(text, lang, rate) {
  const voice = lang === "zh" ? voices.zh : voices.vi;
  const item = new SpeechSynthesisUtterance(text);
  item.lang = voice?.lang || (lang === "zh" ? "zh-CN" : "vi-VN");
  if (voice) item.voice = voice;
  item.rate = rate;
  return item;
}

export function speak(text, rate = 0.75) {
  if (!synth || !text) return;
  synth.cancel();
  synth.speak(utterance(text, "zh", rate));
}

/**
 * Speak a script: parts are {text, lang?, rate?}. Parts without `lang` are split into
 * Chinese and Vietnamese runs automatically. Returns false when speech is unavailable.
 */
export function speakScript(parts, { onEnd } = {}) {
  if (!synth) return false;
  synth.cancel();
  const queue = [];
  for (const part of parts) {
    if (!part?.text) continue;
    if (part.lang) {
      queue.push(utterance(part.text, part.lang, part.rate ?? (part.lang === "zh" ? 0.75 : 1)));
      continue;
    }
    for (const piece of part.text.split(HAN_RUN)) {
      if (!piece.trim()) continue;
      const chinese = HAN.test(piece);
      queue.push(utterance(piece.trim(), chinese ? "zh" : "vi", chinese ? 0.8 : 1));
    }
  }
  if (!queue.length) return false;
  queue[queue.length - 1].onend = () => onEnd?.();
  queue.forEach((item) => synth.speak(item));
  return true;
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
