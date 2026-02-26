#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import path from "node:path";

const ROOT = process.cwd();
const args = process.argv.slice(2);
const runtimeArgIndex = args.indexOf("--runtime");
const runtimeArgs = runtimeArgIndex >= 0 ? ["--runtime", args[runtimeArgIndex + 1]] : [];
const compareStrict = args.includes("--strict-openapi-runtime");

const steps = [
  ["build singlefile", ["node", ["docs/scripts/build-webui-singlefile.mjs"]]],
  ["validate docs/openapi", ["node", ["docs/scripts/validate-openapi.mjs"]]],
  ["webui syntax/smoke", ["node", ["docs/scripts/check-webui-syntax.mjs"]]],
  ["shared-drive compatibility", ["node", ["docs/scripts/check-shared-drive-compat.mjs"]]],
  ["openapi docs↔runtime compare (optional)", ["node", ["docs/scripts/compare-openapi-docs-vs-runtime.mjs", ...runtimeArgs, ...(compareStrict ? ["--strict-missing"] : [])]]],
];

for (const [label, [cmd, cmdArgs]] of steps) {
  console.log(`\n== ${label} ==`);
  const res = spawnSync(cmd, cmdArgs, { cwd: ROOT, stdio: "inherit" });
  if (res.status !== 0) process.exit(res.status ?? 1);
}

console.log("\nOK: shared-drive checks complete");
console.log(`cwd=${path.relative(ROOT, ROOT) || "."}`);
