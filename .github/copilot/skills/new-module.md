# Skill: new-module
# Linux Management System - 新モジュール追加テンプレート

## 📋 スキル説明

新しい管理モジュールを追加するための手順とテンプレートを提供します。
セキュリティポリシーに準拠した実装パターンを示します。

## 🎯 適用条件

- 新しいシステム管理機能を追加する場合
- 既存モジュールに操作機能を追加する場合

## 📝 実装チェックリスト

```
新モジュール: {MODULE_NAME}
カテゴリ: {CATEGORY}  # system/servers/networking/hardware/tools

1. [ ] セキュリティ評価
   - root権限が必要か？
   - sudo ラッパーで対応可能か？
   - allowlist に追加すべきコマンドは？

2. [ ] ラッパースクリプト作成
   - ファイル: wrappers/adminui-{MODULE_NAME}.sh
   - allowlist 実装
   - 特殊文字チェック
   - set -euo pipefail

3. [ ] バックエンドAPI作成
   - ファイル: backend/api/routes/{MODULE_NAME}.py
   - 型ヒント必須
   - docstring必須
   - 認証・認可実装

4. [ ] 権限追加
   - backend/core/auth.py に read:{MODULE_NAME} 追加
   - ロール別権限設定

5. [ ] テスト作成
   - tests/integration/test_{MODULE_NAME}_api.py
   - 15件以上のテストケース
   - セキュリティテスト必須

6. [ ] フロントエンド
   - frontend/dev/{MODULE_NAME}.html
   - メニュー追加

7. [ ] main.py 登録
   - app.include_router() 追加
```

## 🔧 ラッパースクリプトテンプレート

```bash
#!/bin/bash
# adminui-{MODULE_NAME}.sh - {モジュール説明}
# 実行ユーザー: svc-adminui (sudo 経由)
# allowlist: サブコマンドのみ実行可能

set -euo pipefail

SCRIPT_NAME=$(basename "$0")

# ─── 定数 ───────────────────────────────────────────────────
readonly ALLOWED_SUBCMDS=("status" "list")

# ─── ヘルパー関数 ──────────────────────────────────────────
usage() {
    echo "Usage: $SCRIPT_NAME <subcommand>" >&2
    echo "Allowed: ${ALLOWED_SUBCMDS[*]}" >&2
    exit 1
}

validate_subcmd() {
    local cmd="$1"
    for allowed in "${ALLOWED_SUBCMDS[@]}"; do
        [[ "$cmd" == "$allowed" ]] && return 0
    done
    echo "Error: Subcommand '$cmd' is not allowed" >&2
    exit 1
}

# 特殊文字チェック
validate_safe_string() {
    local input="$1"
    if [[ "$input" =~ [[:space:]\;\|\&\$\(\)\`\>\<\*\?\{\}\[\]] ]]; then
        echo "Error: Unsafe characters in input" >&2
        exit 1
    fi
}

# ─── メイン ────────────────────────────────────────────────
[[ $# -lt 1 ]] && usage

SUBCMD="$1"
validate_subcmd "$SUBCMD"

case "$SUBCMD" in
    status)
        # 実装
        ;;
    list)
        # 実装
        ;;
esac
```

## 🐍 APIルートテンプレート

```python
"""
{モジュール名} API ルーター

GET /api/{module_name}/status  - 状態取得
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.auth import User, get_current_user, require_permission
from ...core.sudo_wrapper import SudoWrapper

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/{module_name}", tags=["{モジュール名}"])
sudo_wrapper = SudoWrapper()

PERMISSION = "read:{module_name}"


@router.get(
    "/status",
    summary="{モジュール名}状態取得",
)
async def get_status(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """{モジュール名}の状態を取得します。

    Returns:
        状態情報の辞書

    Raises:
        HTTPException: 権限不足 (403) またはシステムエラー (500)
    """
    require_permission(current_user, PERMISSION)

    try:
        result = sudo_wrapper.run_wrapper("adminui-{module_name}.sh", ["status"])
        return {"status": "ok", "data": result}
    except Exception as e:
        logger.error("Failed to get {module_name} status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="状態取得に失敗しました",
        ) from e
```
