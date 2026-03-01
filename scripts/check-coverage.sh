#!/bin/bash
# カバレッジチェックスクリプト
# カバレッジが80%未満の場合は非ゼロ終了する
set -euo pipefail

COVERAGE_THRESHOLD="${1:-80}"

echo "🔍 Running tests with coverage check (threshold: ${COVERAGE_THRESHOLD}%)..."
echo ""

python3 -m pytest tests/ \
    --ignore=tests/e2e \
    -q \
    --cov=backend \
    --cov-report=term-missing \
    --cov-fail-under="${COVERAGE_THRESHOLD}"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✅ Coverage check passed (>= ${COVERAGE_THRESHOLD}%)"
else
    echo ""
    echo "❌ Coverage check failed (< ${COVERAGE_THRESHOLD}%)"
fi

exit $EXIT_CODE
