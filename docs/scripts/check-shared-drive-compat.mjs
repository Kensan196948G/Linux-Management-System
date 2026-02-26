#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();

const TARGET_GLOBS = [
  ".editorconfig",
  "docs/scripts",
  "webui-sample/build-singlefile.cmd",
  "webui-sample/build-singlefile.sh",
  "webui-sample/README.md",
  "docs/webui-shared-drive-usage.md",
  "docs/webui-v03-test-checklist.md",
  "docs/README.md",
];

const errors = [];
const warnings = [];
const files = [];

function collect(relPath) {
  const abs = path.join(ROOT, relPath);
  if (!fs.existsSync(abs)) {
    warnings.push(`Missing target (skipped): ${relPath}`);
    return;
  }
  const stat = fs.statSync(abs);
  if (stat.isDirectory()) {
    for (const entry of fs.readdirSync(abs, { withFileTypes: true })) {
      if (entry.name.startsWith(".")) continue;
      collect(path.join(relPath, entry.name));
    }
    return;
  }
  files.push(relPath.replace(/\\/g, "/"));
}

function expectedEol(rel) {
  return rel.endsWith(".cmd") || rel.endsWith(".bat") ? "crlf" : "lf";
}

function scanFile(rel) {
  const abs = path.join(ROOT, rel);
  const buf = fs.readFileSync(abs);
  const hasBom = buf.length >= 3 && buf[0] === 0xef && buf[1] === 0xbb && buf[2] === 0xbf;
  if (hasBom) errors.push(`${rel}: UTF-8 BOM is not allowed`);

  const text = buf.toString("utf8");
  const hasCrlf = /\r\n/.test(text);
  const hasLf = /\n/.test(text.replace(/\r\n/g, "")); // bare LF only
  if (hasCrlf && hasLf) errors.push(`${rel}: mixed line endings (CRLF + LF)`);
  const mode = expectedEol(rel);
  if (mode === "lf" && hasCrlf) errors.push(`${rel}: expected LF, found CRLF`);
  if (mode === "crlf" && hasLf && !hasCrlf) warnings.push(`${rel}: LF detected (CRLF preferred for .cmd/.bat)`);

  if (rel.startsWith("docs/scripts/") || rel.endsWith(".cmd") || rel.endsWith(".sh")) {
    const driveMatch = text.match(/\b[A-Za-z]:[\\/]/);
    if (driveMatch) errors.push(`${rel}: absolute drive-letter path found (${driveMatch[0]})`);
  }

  if ((rel.endsWith(".mjs") || rel.endsWith(".sh") || rel.endsWith(".cmd")) && !text.endsWith("\n") && !text.endsWith("\r\n")) {
    errors.push(`${rel}: missing trailing newline`);
  }
}

for (const t of TARGET_GLOBS) collect(t);
for (const f of files) scanFile(f);

if (errors.length) {
  console.error("Shared drive compatibility check failed:");
  for (const e of errors) console.error(`- ${e}`);
  if (warnings.length) {
    console.error("Warnings:");
    for (const w of warnings) console.error(`- ${w}`);
  }
  process.exit(1);
}

console.log("OK: shared-drive compatibility");
console.log(`- files checked: ${files.length}`);
console.log("- policy: UTF-8 (no BOM), relative paths in scripts, normalized EOL by file type");
if (warnings.length) {
  console.log("- warnings:");
  for (const w of warnings) console.log(`  - ${w}`);
}
