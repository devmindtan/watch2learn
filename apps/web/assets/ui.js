// Small DOM and formatting helpers shared by the screens.

export const $ = (selector) => document.querySelector(selector);

export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

export function button(className, text, onClick) {
  const node = element("button", className, text);
  node.type = "button";
  if (onClick) node.addEventListener("click", onClick);
  return node;
}

export function timeLabel(milliseconds) {
  const seconds = Math.floor((milliseconds || 0) / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = String(seconds % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

/** Lowercase, without Vietnamese/pinyin diacritics — for forgiving search. */
export function plain(text) {
  return (text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").toLowerCase();
}

export function sizeLabel(bytes) {
  return bytes > 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(bytes / 1e6))} MB`;
}

export const delay = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export function readStore(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

export function writeStore(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: keep in-memory state only */
  }
}

/** Dictionary senses without classifier notes ("LT:"/"CL:"), plus those notes. */
export function cleanSenses(definitions = []) {
  const senses = [];
  const notes = [];
  for (const definition of definitions || []) {
    const classifier = definition.match(/^(?:LT|CL):(.*)$/);
    if (classifier) notes.push(`Lượng từ: ${classifier[1].replace(/\[[^\]]*]/g, "").replace(/,/g, ", ")}`);
    else senses.push(definition);
  }
  return { senses, notes };
}

export function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function scoreLabel(score) {
  if (score >= 85) return "Rất tốt";
  if (score >= 60) return "Khá — luyện thêm chút nữa";
  return "Cần luyện thêm";
}

/**
 * Action buttons share one look per purpose so they are told apart at a glance:
 * listen (blue), practice (amber), lesson (violet), save (gold when on),
 * learned (green when on), video (filled), danger (red text), plain (neutral).
 */
export function actionButton(kind, icon, label, onClick, { title, pressed } = {}) {
  const node = button(`btn btn-${kind}`, null, onClick);
  if (icon) node.append(element("span", "btn-icon", icon));
  if (label) node.append(element("span", "btn-label", label));
  if (title) node.title = title;
  if (!label) node.setAttribute("aria-label", title || icon);
  if (pressed !== undefined) node.setAttribute("aria-pressed", String(Boolean(pressed)));
  return node;
}
