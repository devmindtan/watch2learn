// Learner library state kept on the backend (shared by every device), with a one-time
// import of words that older versions stored in this browser's localStorage.
import { apiFetch, apiJson, responseJson } from "./api.js";

const state = { words: {}, sentences: {} };
const listeners = new Set();
const LEGACY_KNOWN = "watch2learn-known";
const LEGACY_MEANINGS = "watch2learn-meanings";

function notify() {
  listeners.forEach((listener) => listener());
}

export function onLearnerChange(listener) {
  listeners.add(listener);
}

export function sentenceKey(lessonId, cueId) {
  return `${lessonId}:${cueId}`;
}

export const wordStatus = (wordId) => state.words[wordId]?.status || null;
export const ownMeaning = (wordId) => state.words[wordId]?.own_meaning || "";
export const sentenceStatus = (lessonId, cueId) => state.sentences[sentenceKey(lessonId, cueId)] || null;

async function importLegacy() {
  let learned = [];
  let meanings = {};
  try {
    learned = JSON.parse(localStorage.getItem(LEGACY_KNOWN) || "[]");
    meanings = JSON.parse(localStorage.getItem(LEGACY_MEANINGS) || "{}");
  } catch {
    return;
  }
  if (!learned.length && !Object.keys(meanings).length) return;
  await apiJson("/api/library/import", { method: "POST", json: { learned, meanings } });
  localStorage.removeItem(LEGACY_KNOWN);
  localStorage.removeItem(LEGACY_MEANINGS);
}

export async function loadLearner() {
  try {
    await importLegacy();
  } catch {
    /* keep the legacy data for the next attempt */
  }
  Object.assign(state, await apiJson("/api/library/state"));
  notify();
}

export async function updateWord(wordId, body) {
  const row = await apiJson(`/api/library/words/${wordId}`, { method: "PUT", json: body });
  state.words[wordId] = { status: row.status, own_meaning: row.own_meaning };
  notify();
  return row;
}

export async function removeWord(wordId) {
  const response = await apiFetch(`/api/library/words/${wordId}`, { method: "DELETE" });
  if (!response.ok && response.status !== 404) await responseJson(response);
  delete state.words[wordId];
  notify();
}

export async function updateSentence(lessonId, cueId, status) {
  const path = `/api/library/sentences/${lessonId}/${encodeURIComponent(cueId)}`;
  const row = await apiJson(path, { method: "PUT", json: { status } });
  state.sentences[sentenceKey(lessonId, cueId)] = row.status;
  notify();
  return row;
}

export async function removeSentence(lessonId, cueId) {
  const path = `/api/library/sentences/${lessonId}/${encodeURIComponent(cueId)}`;
  const response = await apiFetch(path, { method: "DELETE" });
  if (!response.ok && response.status !== 404) await responseJson(response);
  delete state.sentences[sentenceKey(lessonId, cueId)];
  notify();
}

export function counts() {
  const words = Object.values(state.words);
  const sentences = Object.values(state.sentences);
  return {
    words: words.length,
    learnedWords: words.filter((item) => item.status === "learned").length,
    sentences: sentences.length,
  };
}
