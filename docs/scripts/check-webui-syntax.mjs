#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const ROOT = process.cwd();
const files = [
  "webui-sample/app.js",
  "webui-sample/js/config.js",
  "webui-sample/js/store.js",
  "webui-sample/js/api/client.js",
  "webui-sample/js/api/endpoints.js",
  "webui-sample/js/api/index.js",
  "webui-sample/js/modules/processes.js",
  "webui-sample/js/modules/approvals.js",
  "webui-sample/js/modules/cron.js",
  "webui-sample/js/modules/users.js",
  "webui-sample/js/modules/services.js",
  "webui-sample/js/modules/validation.js",
];

const errors = [];
for (const rel of files) {
  const abs = path.join(ROOT, rel);
  const code = fs.readFileSync(abs, "utf8");
  try {
    const tmp = path.join(os.tmpdir(), `codex-syntax-${Date.now()}-${Math.random().toString(16).slice(2)}.mjs`);
    fs.writeFileSync(tmp, code, "utf8");
    const res = spawnSync(process.execPath, ["--check", tmp], { encoding: "utf8" });
    fs.unlinkSync(tmp);
    if (res.status !== 0) {
      throw new Error((res.stderr || res.stdout || `exit ${res.status}`).trim());
    }
  } catch (e) {
    errors.push(`${rel}: ${e.message}`);
  }
}

const html = fs.readFileSync(path.join(ROOT, "webui-sample", "index.html"), "utf8");
if (!/id="cronTable"/.test(html)) errors.push("webui-sample/index.html: missing #cronTable");
if (!/<script\s+type="module"\s+src="\.\/*app\.js"/i.test(html)) errors.push("webui-sample/index.html: app.js script tag is not module");
if (!/id="toastStack"[^>]*aria-live="polite"/.test(html)) errors.push("webui-sample/index.html: toastStack aria-live missing");

const singlePath = path.join(ROOT, "webui-sample", "index.singlefile.html");
if (fs.existsSync(singlePath)) {
  const single = fs.readFileSync(singlePath, "utf8");
  if (/<script\s+type="module"/i.test(single)) errors.push("webui-sample/index.singlefile.html: module script tag remains");
  if (!/window\.__WEBUI_CONFIG__\s*=/.test(single)) errors.push("webui-sample/index.singlefile.html: config bootstrap missing");
  if (!/<style>[\s\S]*:root\s*\{/.test(single)) errors.push("webui-sample/index.singlefile.html: styles not inlined");

  const scripts = [...single.matchAll(/<script>([\s\S]*?)<\/script>/gi)];
  if (!scripts.length) {
    errors.push("webui-sample/index.singlefile.html: no inline script found");
  } else {
    const js = scripts[scripts.length - 1][1];
    const tmp = path.join(os.tmpdir(), `codex-singlefile-${Date.now()}-${Math.random().toString(16).slice(2)}.js`);
    fs.writeFileSync(tmp, js, "utf8");
    const res = spawnSync(process.execPath, ["--check", tmp], { encoding: "utf8" });
    try { fs.unlinkSync(tmp); } catch {}
    if (res.status !== 0) {
      errors.push(`webui-sample/index.singlefile.html: embedded script syntax error: ${(res.stderr || res.stdout || "").trim()}`);
    }
  }
}

if (errors.length) {
  console.error("WebUI syntax/smoke check failed:");
  for (const e of errors) console.error(`- ${e}`);
  process.exit(1);
}

console.log("OK: webui-sample syntax/smoke");
console.log(`- modules parsed: ${files.length}`);
console.log("- checks: cronTable / module-script / toast aria-live / singlefile(optional)");
