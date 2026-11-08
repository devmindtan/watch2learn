// Backend connection: same origin by default, or a remote backend (e.g. this
// machine exposed over HTTPS) when the UI is hosted elsewhere.
const STORE_KEY = "watch2learn-server";
const unauthorizedListeners = new Set();

function readSettings() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY)) || {};
  } catch {
    return {};
  }
}

let settings = readSettings();

export function serverSettings() {
  return { base: settings.base || "", token: settings.token || "" };
}

export function saveServerSettings({ base = "", token = "" }) {
  settings = { base: base.trim().replace(/\/+$/, ""), token: token.trim() };
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(settings));
  } catch {
    /* storage unavailable: settings last for this page only */
  }
}

export function apiUrl(path) {
  return /^https?:\/\//.test(path) ? path : `${settings.base || ""}${path}`;
}

export function onUnauthorized(listener) {
  unauthorizedListeners.add(listener);
}

export async function apiFetch(path, init = {}) {
  const headers = new Headers(init.headers || {});
  if (settings.token) headers.set("Authorization", `Bearer ${settings.token}`);
  const response = await fetch(apiUrl(path), { ...init, headers });
  if (response.status === 401) unauthorizedListeners.forEach((listener) => listener());
  return response;
}

export async function responseJson(response) {
  if (response.status === 204) return {};
  let result = {};
  try {
    result = await response.json();
  } catch {
    if (response.ok) throw new Error("Máy chủ trả về dữ liệu không hợp lệ.");
  }
  if (!response.ok) {
    const detail = Array.isArray(result.detail) ? "Dữ liệu gửi lên không hợp lệ." : result.detail;
    const error = new Error(detail || `Yêu cầu không thành công (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return result;
}

export async function apiJson(path, init = {}) {
  const options = { ...init };
  if (options.json !== undefined) {
    options.body = JSON.stringify(options.json);
    options.headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    delete options.json;
  }
  return responseJson(await apiFetch(path, options));
}
