#!/bin/bash
# .env ファイルを読み込んで環境変数として設定

set -a  # 自動的に export
source .env
set +a

echo "✅ Environment variables loaded from .env"
echo "   GITHUB_TOKEN: ${GITHUB_TOKEN:0:10}... (hidden)"
echo "   DEV_PORT: $DEV_PORT"
echo "   PROD_PORT: $PROD_PORT"
