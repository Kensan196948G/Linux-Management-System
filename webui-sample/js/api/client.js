export class ApiError extends Error {
  constructor(message, options = {}) {
    super(message);
    this.name = "ApiError";
    this.status = options.status ?? 0;
    this.code = options.code || "API_ERROR";
    this.detail = options.detail;
    this.payload = options.payload;
    this.url = options.url;
    this.method = options.method;
    this.retryable = Boolean(options.retryable);
  }
}

export function createApiClient({ baseUrl, timeoutMs = 10000, getToken }) {
  async function request(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const timeout = options.timeoutMs || timeoutMs;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    const headers = new Headers(options.headers || {});
    if (!headers.has("Accept")) headers.set("Accept", "application/json");
    const token = typeof getToken === "function" ? getToken() : null;
    if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
    let body = options.body;
    if (body && typeof body === "object" && !(body instanceof FormData) && !(body instanceof Blob) && !(body instanceof ArrayBuffer)) {
      if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
      body = JSON.stringify(body);
    }

    const url = path.startsWith("http") ? path : `${baseUrl}${path.startsWith("/") ? "" : "/"}${path}`;
    try {
      const res = await fetch(url, { ...options, method, headers, body, signal: controller.signal });
      clearTimeout(timer);
      const text = await res.text();
      let data = null;
      if (text) {
        try { data = JSON.parse(text); } catch { data = text; }
      }
      if (!res.ok) {
        throw new ApiError(extractErrorMessage(data, res.statusText), {
          status: res.status,
          detail: data?.detail || data?.message || null,
          payload: data,
          url,
          method,
          code: classifyStatusCode(res.status),
          retryable: res.status >= 500,
        });
      }
      return { ok: true, status: res.status, data, headers: res.headers };
    } catch (err) {
      clearTimeout(timer);
      if (err instanceof ApiError) throw err;
      if (err?.name === "AbortError") {
        throw new ApiError(`Request timeout (${timeout}ms)`, { code: "TIMEOUT", url, method, retryable: true });
      }
      throw new ApiError(err?.message || "Network error", { code: "NETWORK_ERROR", url, method, retryable: true });
    }
  }

  return { request };
}

export function extractErrorMessage(payload, fallback) {
  if (!payload) return fallback || "Request failed";
  if (typeof payload === "string") return payload;
  if (typeof payload.detail === "string") return payload.detail;
  if (typeof payload.message === "string") return payload.message;
  if (Array.isArray(payload.detail) && payload.detail.length) {
    const first = payload.detail[0];
    if (first?.msg) return first.msg;
  }
  return fallback || "Request failed";
}

export function mapValidationErrors(payload) {
  const items = Array.isArray(payload?.detail) ? payload.detail : [];
  return items.map((item) => ({
    field: Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "",
    message: item.msg || "Validation error",
    type: item.type || "",
  }));
}

function classifyStatusCode(status) {
  if (status === 400 || status === 422) return "VALIDATION_ERROR";
  if (status === 401) return "UNAUTHORIZED";
  if (status === 403) return "FORBIDDEN";
  if (status === 404) return "NOT_FOUND";
  if (status === 409) return "CONFLICT";
  if (status >= 500) return "SERVER_ERROR";
  return "HTTP_ERROR";
}

