import { DEFAULTS, resolveApiBaseUrl, resolveApiMode, persistApiSettings } from "../config.js";
import { createApiClient, ApiError } from "./client.js";
import { createApi } from "./endpoints.js";

export function createApiFacade({ getToken, onNetworkState } = {}) {
  const settings = {
    baseUrl: resolveApiBaseUrl(),
    mode: resolveApiMode(),
    timeoutMs: DEFAULTS.timeoutMs,
  };

  const client = createApiClient({
    baseUrl: settings.baseUrl,
    timeoutMs: settings.timeoutMs,
    getToken,
  });
  const api = createApi(client);

  async function tryLive(fn, { fallback = null, op = "api" } = {}) {
    if (settings.mode === "mock") return { live: false, data: fallback, error: null };
    try {
      const result = await fn();
      onNetworkState?.({ ok: true, op, mode: "live" });
      return { live: true, data: result?.data ?? result, error: null, meta: result };
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      onNetworkState?.({ ok: false, op, mode: "live", error });
      if (settings.mode === "live") throw error;
      return { live: false, data: fallback, error };
    }
  }

  function setMode(mode) {
    if (!["auto", "live", "mock"].includes(mode)) return;
    settings.mode = mode;
    persistApiSettings({ mode });
  }

  function setBaseUrl(baseUrl) {
    settings.baseUrl = String(baseUrl || "").trim().replace(/\/+$/, "") || DEFAULTS.apiBaseUrl;
    persistApiSettings({ baseUrl: settings.baseUrl });
  }

  return {
    api,
    settings,
    tryLive,
    setMode,
    setBaseUrl,
  };
}

