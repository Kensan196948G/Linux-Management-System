#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const FILE = path.join(ROOT, "docs", "openapi.json");
const REQUIRED_PATHS = [
  "/api/v1/processes",
  "/api/cron",
  "/api/cron/{job_id}",
  "/api/users",
  "/api/groups",
  "/api/approval/request",
  "/api/approval/pending",
  "/api/approval/{request_id}/approve",
  "/api/approval/history",
];
const REQUIRED_OPERATIONS = [
  ["/api/v1/processes", "get"],
  ["/api/cron", "get"],
  ["/api/cron", "post"],
  ["/api/users", "get"],
  ["/api/users", "post"],
  ["/api/approval/request", "post"],
  ["/api/approval/pending", "get"],
  ["/api/approval/{request_id}/approve", "post"],
  ["/api/approval/history", "get"],
];
const REQUIRED_APPROVAL_STATUSES = ["pending", "approved", "rejected", "expired", "executed", "execution_failed", "cancelled"];

const buf = fs.readFileSync(FILE);
const hasBom = buf.length >= 3 && buf[0] === 0xef && buf[1] === 0xbb && buf[2] === 0xbf;
const text = buf.toString("utf8").replace(/^\uFEFF/, "");

let doc;
try {
  doc = JSON.parse(text);
} catch (e) {
  console.error(`JSON parse error: ${e.message}`);
  process.exit(1);
}

const errors = [];
if (hasBom) errors.push("BOM detected (UTF-8 BOM).");
if (!doc.openapi) errors.push("Missing `openapi`.");
if (!doc.info?.version) errors.push("Missing `info.version`.");
if (!doc.paths || typeof doc.paths !== "object") errors.push("Missing `paths` object.");
for (const p of REQUIRED_PATHS) {
  if (!doc.paths?.[p]) errors.push(`Missing path: ${p}`);
}
for (const [url, method] of REQUIRED_OPERATIONS) {
  if (!doc.paths?.[url]?.[method]) errors.push(`Missing operation: ${method.toUpperCase()} ${url}`);
}

const approvalEnum = doc.components?.schemas?.ApprovalStatus?.enum;
if (!Array.isArray(approvalEnum)) {
  errors.push("Missing components.schemas.ApprovalStatus.enum");
} else {
  for (const v of REQUIRED_APPROVAL_STATUSES) {
    if (!approvalEnum.includes(v)) errors.push(`ApprovalStatus missing enum value: ${v}`);
  }
}

const allOps = [];
for (const [url, methods] of Object.entries(doc.paths || {})) {
  for (const [method, def] of Object.entries(methods || {})) {
    allOps.push([url, method, def]);
    if (!def.responses || typeof def.responses !== "object") {
      errors.push(`Missing responses: ${method.toUpperCase()} ${url}`);
    }
    if (url.startsWith("/api/approval") || url.startsWith("/api/cron") || url.startsWith("/api/users") || url.startsWith("/api/groups") || url.startsWith("/api/v1/processes")) {
      const hasPerm = Array.isArray(def["x-required-permissions"]) || Array.isArray(def["x-required-permissions-anyOf"]);
      if (!hasPerm) errors.push(`Missing x-required-permissions*: ${method.toUpperCase()} ${url}`);
    }
  }
}

if (errors.length) {
  console.error("OpenAPI validation failed:");
  for (const e of errors) console.error(`- ${e}`);
  process.exit(1);
}

const protectedOps = allOps.filter(([, , def]) => Array.isArray(def.security) && def.security.length > 0).length;
console.log(`OK: ${path.relative(ROOT, FILE)}`);
console.log(`- openapi: ${doc.openapi}`);
console.log(`- version: ${doc.info.version}`);
console.log(`- paths: ${Object.keys(doc.paths || {}).length}`);
console.log(`- operations: ${allOps.length}`);
console.log(`- protected operations: ${protectedOps}`);
console.log(`- BOM: ${hasBom ? "present" : "none"}`);
