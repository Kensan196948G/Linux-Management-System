import { mapValidationErrors } from "../api/client.js";

export function validateUsername(value) {
  return /^[a-z_][a-z0-9_-]{0,31}$/.test(String(value || ""));
}

export function validateCronSchedule(value) {
  const s = String(value || "").trim();
  return s.length > 0 && s.length <= 50 && /^[\d*\/,\-\s]+$/.test(s) && s !== "* * * * *";
}

export function validateCronArguments(value) {
  return !/[;|&$()]/.test(String(value || ""));
}

export function validateStrongPassword(password, username = "") {
  const p = String(password || "");
  if (p.length < 8 || p.length > 128) return false;
  if (username && p.toLowerCase().includes(String(username).toLowerCase())) return false;
  if (!/[a-z]/.test(p) || !/[A-Z]/.test(p) || !/[0-9]/.test(p) || !/[^A-Za-z0-9]/.test(p)) return false;
  return !["password", "admin123", "qwerty", "12345678"].some((w) => p.toLowerCase().includes(w));
}

export function explainApiError(err) {
  if (!err) return { message: "Unknown error", details: [] };
  if (err.code === "VALIDATION_ERROR" && err.payload) {
    const details = mapValidationErrors(err.payload);
    return {
      message: details.length ? details.map((d) => `${d.field || "input"}: ${d.message}`).join(" / ") : (err.message || "Validation error"),
      details,
    };
  }
  return { message: err.message || "Request failed", details: [] };
}

