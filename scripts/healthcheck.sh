#!/bin/bash
# ==============================================================================
# healthcheck.sh - Linux Management System ヘルスチェックスクリプト
#
# 機能:
#   バックエンドAPIの動作確認、依存サービスの状態確認
#
# 使用方法:
#   ./scripts/healthcheck.sh [--url http://localhost:8000] [--json]
#
# 終了コード:
#   0: 全チェック PASS
#   1: 1件以上の FAIL
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BASE_URL="http://localhost:8000"
JSON_OUTPUT=false
TIMEOUT=10

usage() {
    echo "Usage: $0 [--url URL] [--json] [--timeout SECONDS]"
    echo ""
    echo "Options:"
    echo "  --url URL       API base URL (default: http://localhost:8000)"
    echo "  --json          Output results as JSON"
    echo "  --timeout N     Request timeout in seconds (default: 10)"
    exit 1
}

# 引数解析
while [[ $# -gt 0 ]]; do
    case "$1" in
        --url) BASE_URL="$2"; shift 2 ;;
        --json) JSON_OUTPUT=true; shift ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --help) usage ;;
        *) echo "Unknown option: $1" >&2; usage ;;
    esac
done

PASS=0
FAIL=0
RESULTS=()

# チェック関数
check() {
    local name="$1"
    local cmd="$2"
    local expected="${3:-0}"

    if eval "$cmd" > /dev/null 2>&1; then
        actual_exit=0
    else
        actual_exit=$?
    fi

    if [[ "$actual_exit" -eq "$expected" ]]; then
        PASS=$((PASS + 1))
        RESULTS+=("PASS|$name")
    else
        FAIL=$((FAIL + 1))
        RESULTS+=("FAIL|$name")
    fi
}

# HTTP チェック関数
check_http() {
    local name="$1"
    local url="$2"
    local expected_status="${3:-200}"

    actual_status=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time "$TIMEOUT" "$url" 2>/dev/null || echo "000")

    if [[ "$actual_status" -eq "$expected_status" ]]; then
        PASS=$((PASS + 1))
        RESULTS+=("PASS|$name (HTTP $actual_status)")
    else
        FAIL=$((FAIL + 1))
        RESULTS+=("FAIL|$name (HTTP $actual_status, expected $expected_status)")
    fi
}

# ==============================================================================
# チェック実行
# ==============================================================================

# 1. プロセス確認
check "Uvicorn process running" \
    "pgrep -f 'uvicorn.*backend.api.main'"

check "Gunicorn process (optional)" \
    "pgrep -f 'gunicorn.*backend.api.main'" || true  # オプション

# 2. API ヘルスチェック
check_http "API health endpoint" \
    "${BASE_URL}/api/health" 200

check_http "API docs (optional)" \
    "${BASE_URL}/api/docs" 200 || true

# 3. 認証エンドポイント確認（401/403 が正常）
check_http "Auth endpoint reachable" \
    "${BASE_URL}/api/auth/login" 405  # GETは405

# 4. ポートリッスン確認
check "Port 8000 listening" \
    "ss -tlnp | grep -q ':8000'"

# 5. Python 環境確認
check "Python venv exists" \
    "test -f '${PROJECT_ROOT}/venv/bin/python'"

check "Backend module importable" \
    "${PROJECT_ROOT}/venv/bin/python -c 'import backend.api.main'"

# 6. ファイル権限確認
check "Wrappers executable" \
    "test -x '${PROJECT_ROOT}/wrappers/adminui-status.sh'"

# 7. ログディレクトリ確認
check "Log directory exists" \
    "test -d '${PROJECT_ROOT}/logs'"

# ==============================================================================
# 結果出力
# ==============================================================================

TOTAL=$((PASS + FAIL))

if [[ "$JSON_OUTPUT" == "true" ]]; then
    # JSON形式出力
    echo "{"
    echo "  \"total\": $TOTAL,"
    echo "  \"pass\": $PASS,"
    echo "  \"fail\": $FAIL,"
    echo "  \"status\": \"$([ $FAIL -eq 0 ] && echo 'healthy' || echo 'unhealthy')\","
    echo "  \"checks\": ["
    first=true
    for result in "${RESULTS[@]}"; do
        status="${result%%|*}"
        name="${result#*|}"
        [[ "$first" == "true" ]] && first=false || echo ","
        printf '    {"status": "%s", "name": "%s"}' "$status" "$name"
    done
    echo ""
    echo "  ]"
    echo "}"
else
    # テキスト形式出力
    echo "========================================"
    echo "Linux Management System - Health Check"
    echo "========================================"
    echo "URL: $BASE_URL"
    echo ""
    for result in "${RESULTS[@]}"; do
        status="${result%%|*}"
        name="${result#*|}"
        if [[ "$status" == "PASS" ]]; then
            echo "  ✅ $name"
        else
            echo "  ❌ $name"
        fi
    done
    echo ""
    echo "Result: $PASS/$TOTAL PASS"
    if [[ $FAIL -eq 0 ]]; then
        echo "Status: ✅ HEALTHY"
    else
        echo "Status: ❌ UNHEALTHY ($FAIL checks failed)"
    fi
    echo "========================================"
fi

exit $([[ $FAIL -eq 0 ]] && echo 0 || echo 1)
