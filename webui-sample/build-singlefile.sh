#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

cd "$REPO_ROOT"
node "docs/scripts/build-webui-singlefile.mjs"

printf '\nBuilt: %s\n' "$REPO_ROOT/webui-sample/index.singlefile.html"
