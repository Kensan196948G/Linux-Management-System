#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const DOCS_FILE = path.join(ROOT, "docs", "openapi.json");
const FOCUS_PATHS = [
  "/api/v1/processes",
  "/api/cron",
  "/api/cron/{job_id}",
  "/api/users",
  "/api/users/{uid}",
  "/api/users/{uid}/password",
  "/api/groups",
  "/api/groups/{gid}",
  "/api/groups/{gid}/members",
  "/api/approval/request",
  "/api/approval/pending",
  "/api/approval/my-requests",
  "/api/approval/{request_id}",
  "/api/approval/{request_id}/approve",
  "/api/approval/{request_id}/reject",
  "/api/approval/{request_id}/cancel",
  "/api/approval/{request_id}/execute",
  "/api/approval/history",
  "/api/approval/history/export",
  "/api/approval/policies",
  "/api/approval/stats",
];

const args = new Map();
for (let i = 2; i < process.argv.length; i += 1) {
  const a = process.argv[i];
  if (a.startsWith("--")) {
    const next = process.argv[i + 1];
    if (next && !next.startsWith("--")) {
      args.set(a, next);
      i += 1;
    } else {
      args.set(a, "true");
    }
  }
}

const runtimePath = resolveRuntimePath(args.get("--runtime"));
const strictMissing = args.has("--strict-missing");

function resolveRuntimePath(p) {
  const candidates = [
    p,
    process.env.RUNTIME_OPENAPI_PATH,
    "artifacts/openapi.runtime.json",
    "backend-openapi.json",
    "tmp/openapi.runtime.json",
  ].filter(Boolean);
  for (const c of candidates) {
    const abs = path.isAbsolute(c) ? c : path.join(ROOT, c);
    if (fs.existsSync(abs)) return abs;
  }
  return null;
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8").replace(/^\uFEFF/, ""));
}

function methodsOf(doc, p) {
  return Object.keys(doc.paths?.[p] || {}).map((m) => m.toLowerCase()).sort();
}

function compare() {
  const docs = readJson(DOCS_FILE);
  if (!runtimePath) {
    const msg = "Runtime OpenAPI JSON not found. Pass `--runtime <path>` or set `RUNTIME_OPENAPI_PATH`.";
    if (strictMissing) {
      console.error(`OpenAPI compare failed: ${msg}`);
      process.exit(1);
    }
    console.log(`OpenAPI compare skipped: ${msg}`);
    console.log("Tip: export backend OpenAPI to compare docs-sync with implementation.");
    return;
  }

  const runtime = readJson(runtimePath);
  const diffs = [];

  for (const p of FOCUS_PATHS) {
    const a = docs.paths?.[p];
    const b = runtime.paths?.[p];
    if (!a && !b) continue;
    if (!a) { diffs.push(`Missing in docs: ${p}`); continue; }
    if (!b) { diffs.push(`Missing in runtime: ${p}`); continue; }
    const ma = methodsOf(docs, p);
    const mb = methodsOf(runtime, p);
    if (ma.join(",") !== mb.join(",")) {
      diffs.push(`Method mismatch ${p} | docs=[${ma.join(",")}] runtime=[${mb.join(",")}]`);
    }
  }

  const docsStatus = docs.components?.schemas?.ApprovalStatus?.enum || [];
  const runtimeStatus = runtime.components?.schemas?.ApprovalStatus?.enum || [];
  if (docsStatus.length && runtimeStatus.length) {
    const d = docsStatus.filter((v) => !runtimeStatus.includes(v));
    const r = runtimeStatus.filter((v) => !docsStatus.includes(v));
    if (d.length || r.length) {
      diffs.push(`ApprovalStatus enum mismatch | docs-only=[${d.join(",")}] runtime-only=[${r.join(",")}]`);
    }
  } else if (docsStatus.length || runtimeStatus.length) {
    diffs.push("ApprovalStatus enum missing on one side");
  }

  // Check permission annotations exist on docs side for focus operations.
  for (const p of FOCUS_PATHS) {
    for (const [m, def] of Object.entries(docs.paths?.[p] || {})) {
      const hasPerm = Array.isArray(def["x-required-permissions"]) || Array.isArray(def["x-required-permissions-anyOf"]);
      if (!hasPerm) diffs.push(`Docs permission annotation missing: ${m.toUpperCase()} ${p}`);
    }
  }

  if (diffs.length) {
    console.error("OpenAPI docs↔runtime compare failed:");
    for (const d of diffs) console.error(`- ${d}`);
    console.error("");
    console.error("Action: update runtime implementation or sync `docs/openapi.json` and `docs/api-reference.md` together.");
    process.exit(1);
  }

  console.log("OK: OpenAPI docs↔runtime compare");
  console.log(`- docs: ${path.relative(ROOT, DOCS_FILE)}`);
  console.log(`- runtime: ${path.relative(ROOT, runtimePath)}`);
  console.log(`- focus paths checked: ${FOCUS_PATHS.length}`);
}

compare();
