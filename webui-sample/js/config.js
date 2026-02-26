export const APP_KEYS = {
  session: "lms.webui.sample.session",
  apiBaseUrl: "lms.webui.sample.apiBaseUrl",
  apiMode: "lms.webui.sample.apiMode",
};

export const DEFAULTS = {
  apiBaseUrl: "/api",
  apiMode: "auto", // auto | live | mock
  timeoutMs: 10000,
};

function readMetaContent(name) {
  if (typeof document === "undefined") return "";
  return document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") || "";
}

function readWindowConfig() {
  if (typeof window === "undefined") return {};
  const cfg = window.__WEBUI_CONFIG__ || window.__LMS_WEBUI_CONFIG__;
  return (cfg && typeof cfg === "object") ? cfg : {};
}

export function resolveApiBaseUrl() {
  const url = new URL(window.location.href);
  const query = url.searchParams.get("apiBaseUrl") || url.searchParams.get("api");
  const winCfg = readWindowConfig();
  const meta = readMetaContent("lms-api-base-url");
  const stored = localStorage.getItem(APP_KEYS.apiBaseUrl);
  const raw = query || winCfg.apiBaseUrl || meta || stored || DEFAULTS.apiBaseUrl;
  const normalized = String(raw).trim().replace(/\/+$/, "");
  return normalized || DEFAULTS.apiBaseUrl;
}

export function resolveApiMode() {
  const url = new URL(window.location.href);
  const query = url.searchParams.get("apiMode");
  const winCfg = readWindowConfig();
  const meta = readMetaContent("lms-api-mode");
  const stored = localStorage.getItem(APP_KEYS.apiMode);
  const mode = String(query || winCfg.apiMode || meta || stored || DEFAULTS.apiMode).toLowerCase();
  return ["auto", "live", "mock"].includes(mode) ? mode : DEFAULTS.apiMode;
}

export function persistApiSettings({ baseUrl, mode } = {}) {
  if (baseUrl) localStorage.setItem(APP_KEYS.apiBaseUrl, String(baseUrl).trim().replace(/\/+$/, ""));
  if (mode && ["auto", "live", "mock"].includes(mode)) localStorage.setItem(APP_KEYS.apiMode, mode);
}
