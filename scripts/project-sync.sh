#!/bin/bash
# ============================================================
# project-sync.sh — GitHub Project V2 ステータス更新
# ============================================================
# Usage: ./project-sync.sh <ISSUE_OR_PR_URL> <STATUS>
#
# STATUS: Inbox | Backlog | Ready | Design | Development |
#         Verify | "Deploy Gate" | Done | Blocked
#
# 環境変数:
#   GH_TOKEN or GITHUB_TOKEN — GitHub API トークン（project スコープ必須）
#   PROJECT_ID  — Project V2 ID (default: PVT_kwHOClgkIc4BSSPy)
#   STATUS_FIELD_ID — Status フィールド ID (default: PVTSSF_lAHOClgkIc4BSSPyzg_3XAY)
# ============================================================
set -euo pipefail

# --- 引数チェック ---
if [ $# -lt 2 ]; then
    echo "Usage: $0 <ISSUE_OR_PR_URL> <STATUS>" >&2
    echo "  STATUS: Todo | 'In Progress' | Done" >&2
    exit 1
fi

ITEM_URL="$1"
STATUS_NAME="$2"

# --- 入力バリデーション ---
if [[ ! "$ITEM_URL" =~ ^https://github\.com/ ]]; then
    echo "Error: Invalid URL format" >&2
    exit 1
fi

# --- 設定 ---
PROJECT_NUMBER="${PROJECT_NUMBER:-5}"
OWNER="${OWNER:-Kensan196948G}"
PROJECT_ID="${PROJECT_ID:-PVT_kwHOClgkIc4BSSPy}"
# Phase フィールド（カスタム: ClaudeOS ステータス）
PHASE_FIELD_ID="${PHASE_FIELD_ID:-PVTSSF_lAHOClgkIc4BSSPyzg_3aa0}"

# --- ステータスマッピング（Phase フィールド） ---
declare -A STATUS_MAP
STATUS_MAP["Inbox"]="d484a4ba"
STATUS_MAP["Backlog"]="22ca697a"
STATUS_MAP["Ready"]="f90a0adc"
STATUS_MAP["Design"]="af2f18a9"
STATUS_MAP["Development"]="94e34be0"
STATUS_MAP["Verify"]="d99dd000"
STATUS_MAP["Deploy Gate"]="4a292afd"
STATUS_MAP["Done"]="454a2945"
STATUS_MAP["Blocked"]="b57b06f6"

OPTION_ID="${STATUS_MAP[$STATUS_NAME]:-}"
if [ -z "$OPTION_ID" ]; then
    echo "Error: Unknown status '$STATUS_NAME'" >&2
    echo "  Valid: Inbox, Backlog, Ready, Design, Development, Verify, 'Deploy Gate', Done, Blocked" >&2
    exit 1
fi

# --- アイテム追加（既に存在する場合はスキップ） ---
echo "Adding item to project..."
ITEM_ID=$(gh project item-add "$PROJECT_NUMBER" \
    --owner "$OWNER" \
    --url "$ITEM_URL" 2>&1 | grep -oP 'PVTI_[a-zA-Z0-9_]+' || echo "")

if [ -z "$ITEM_ID" ]; then
    echo "Item already exists or add succeeded without ID output"
    # 既存アイテムを検索
    ITEM_ID=$(gh project item-list "$PROJECT_NUMBER" \
        --owner "$OWNER" --limit 100 2>&1 | \
        grep "$(basename "$ITEM_URL")" | \
        awk '{print $NF}' | head -1)
fi

if [ -z "$ITEM_ID" ]; then
    echo "Error: Could not find item ID" >&2
    exit 1
fi

# --- ステータス更新 ---
echo "Setting status to '$STATUS_NAME'..."
gh project item-edit \
    --project-id "$PROJECT_ID" \
    --id "$ITEM_ID" \
    --field-id "$PHASE_FIELD_ID" \
    --single-select-option-id "$OPTION_ID"

echo "Done: $ITEM_URL → $STATUS_NAME"
