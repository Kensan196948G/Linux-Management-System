#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const WEBUI_DIR = path.join(ROOT, "webui-sample");
const INPUT_HTML = path.join(WEBUI_DIR, "index.html");
const INPUT_CSS = path.join(WEBUI_DIR, "styles.css");
const OUTPUT_HTML = path.join(WEBUI_DIR, "index.singlefile.html");

const MODULE_ORDER = [
  "js/config.js",
  "js/api/client.js",
  "js/api/endpoints.js",
  "js/api/index.js",
  "js/store.js",
  "js/modules/processes.js",
  "js/modules/approvals.js",
  "js/modules/cron.js",
  "js/modules/users.js",
  "js/modules/services.js",
  "js/modules/validation.js",
];

function read(file) {
  return fs.readFileSync(file, "utf8");
}

function inlineSafe(text) {
  return String(text).replace(/<\/script>/gi, "<\\/script>");
}

function transformModule(code, rel) {
  let out = code.replace(/^\s*import\s.+?;\s*$/gm, "");
  out = out.replace(/^\s*export\s+(?=(const|let|var|function|class)\b)/gm, "");
  out = out.replace(/^\s*export\s*\{[^}]+\}\s*;?\s*$/gm, "");
  return `\n/* --- ${rel} --- */\n${out.trim()}\n`;
}

function transformApp(code) {
  let out = code.replace(/^\s*import\s.+?;\s*$/gm, "");
  return `\n/* --- app.js --- */\n${out.trim()}\n`;
}

function buildBundle() {
  const parts = [];
  parts.push("window.__WEBUI_CONFIG__ = window.__WEBUI_CONFIG__ || {};");
  for (const rel of MODULE_ORDER) {
    parts.push(transformModule(read(path.join(WEBUI_DIR, rel)), rel));
  }
  // app.js imports normalizeApprovalPendingResponse with alias.
  parts.push("\nconst normalizeCronApprovalPending = normalizeApprovalPendingResponse;\n");
  parts.push(transformApp(read(path.join(WEBUI_DIR, "app.js"))));
  return parts.join("\n");
}

function buildSingleHtml() {
  const html = read(INPUT_HTML);
  const css = read(INPUT_CSS);
  const js = buildBundle();

  let out = html;
  out = out.replace(
    /<link rel="stylesheet" href="\.\/styles\.css">\s*/i,
    () => `<style>\n${css}\n</style>\n`
  );

  // Replace the file:// warning bootstrap script with minimal config bootstrap.
  out = out.replace(
    /<script>\s*window\.__WEBUI_CONFIG__\s*=\s*window\.__WEBUI_CONFIG__\s*\|\|\s*\{\};[\s\S]*?<\/script>\s*/i,
    () => `<script>\nwindow.__WEBUI_CONFIG__ = window.__WEBUI_CONFIG__ || {};\n</script>\n`
  );

  const beforeModuleReplace = out;
  out = out.replace(
    /\s*<script\s+type="module"\s+src="\.\/app\.js"><\/script>\s*/i,
    () => `\n<script>\n${inlineSafe(js)}\n</script>\n`
  );

  if (out === beforeModuleReplace) {
    throw new Error("Failed to replace module script tag.");
  }
  if (/<link rel="stylesheet" href="\.\/styles\.css">/i.test(out)) {
    throw new Error("Failed to inline styles.css.");
  }

  const banner = `<!-- Generated file: do not edit manually. Source: index.html + styles.css + app.js + js/* (${new Date().toISOString()}) -->\n`;
  return out.startsWith("<!DOCTYPE html>") ? out.replace("<!DOCTYPE html>", `<!DOCTYPE html>\n${banner.trimEnd()}`) : `${banner}${out}`;
}

function main() {
  const generated = buildSingleHtml().replace(/\r\n/g, "\n");
  fs.writeFileSync(OUTPUT_HTML, generated, "utf8");
  console.log(`Generated ${path.relative(ROOT, OUTPUT_HTML)} (${Buffer.byteLength(generated, "utf8")} bytes)`);
}

main();
