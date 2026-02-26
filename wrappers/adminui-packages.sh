#!/bin/bash
# ==============================================================================
# adminui-packages.sh - パッケージ管理ラッパー（読み取り専用）
#
# 機能:
#   インストール済みパッケージ・更新可能パッケージ・セキュリティ更新を取得する。
#   全操作は読み取り専用。パッケージのインストール/削除は行わない。
#
# 使用方法:
#   adminui-packages.sh <subcommand>
#
# サブコマンド:
#   list     - インストール済みパッケージ一覧 (dpkg-query)
#   updates  - 更新可能なパッケージ一覧 (apt list --upgradable)
#   security - セキュリティ更新一覧 (unattended-upgrade --dry-run / apt-get --just-print)
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - 許可サブコマンドのみ実行（allowlist方式）
#   - ユーザー入力は受け付けない（引数 = サブコマンドのみ）
#   - 読み取り専用: インストール/削除操作は一切行わない
# ==============================================================================

set -euo pipefail

ALLOWED_SUBCOMMANDS=("list" "updates" "security")

if [ "$#" -ne 1 ]; then
    echo '{"status":"error","message":"Usage: adminui-packages.sh <subcommand>"}' >&2
    exit 1
fi

SUBCOMMAND="$1"

ALLOWED=false
for cmd in "${ALLOWED_SUBCOMMANDS[@]}"; do
    if [ "$cmd" = "$SUBCOMMAND" ]; then
        ALLOWED=true
        break
    fi
done

if [ "$ALLOWED" = false ]; then
    echo "{\"status\":\"error\",\"message\":\"Unknown subcommand: ${SUBCOMMAND}\"}" >&2
    exit 1
fi

# ==============================================================================
# subcommand: list - インストール済みパッケージ一覧
# ==============================================================================

if [ "$SUBCOMMAND" = "list" ]; then
    if ! command -v dpkg-query >/dev/null 2>&1; then
        echo '{"status":"error","message":"dpkg-query not available"}' >&2
        exit 1
    fi

    PACKAGES=$(dpkg-query -W -f='${Package}\t${Version}\t${Status}\t${Architecture}\n' 2>/dev/null | \
        python3 -c "
import sys, json

packages = []
for line in sys.stdin:
    line = line.rstrip('\n')
    if not line:
        continue
    parts = line.split('\t')
    if len(parts) >= 3:
        pkg = {
            'name': parts[0],
            'version': parts[1] if len(parts) > 1 else '',
            'status': parts[2] if len(parts) > 2 else '',
            'arch': parts[3] if len(parts) > 3 else '',
        }
        # install ok installedのみ返す
        if 'installed' in pkg['status']:
            packages.append(pkg)

print(json.dumps({'status':'success','packages':packages,'count':len(packages),'timestamp':'$(date -u +%Y-%m-%dT%H:%M:%SZ)'}))
" 2>/dev/null)

    if [ $? -eq 0 ] && [ -n "$PACKAGES" ]; then
        echo "$PACKAGES"
    else
        echo '{"status":"error","message":"Failed to list packages"}' >&2
        exit 1
    fi
    exit 0
fi

# ==============================================================================
# subcommand: updates - 更新可能なパッケージ一覧
# ==============================================================================

if [ "$SUBCOMMAND" = "updates" ]; then
    if ! command -v apt-get >/dev/null 2>&1; then
        echo '{"status":"error","message":"apt-get not available"}' >&2
        exit 1
    fi

    # apt list --upgradable（非特権で実行可能）
    UPGRADABLE=$(apt list --upgradable 2>/dev/null | python3 -c "
import sys, json, re

packages = []
for line in sys.stdin:
    line = line.rstrip()
    # 例: nginx/focal-updates 1.18.0-0ubuntu1.3 amd64 [upgradable from: 1.18.0-0ubuntu1.2]
    m = re.match(r'^(\S+)/(\S+)\s+(\S+)\s+(\S+)\s+\[upgradable from: (\S+)\]', line)
    if m:
        packages.append({
            'name': m.group(1),
            'repository': m.group(2),
            'new_version': m.group(3),
            'arch': m.group(4),
            'current_version': m.group(5),
        })
print(json.dumps({'status':'success','updates':packages,'count':len(packages),'timestamp':'$(date -u +%Y-%m-%dT%H:%M:%SZ)'}))
" 2>/dev/null)

    if [ $? -eq 0 ] && [ -n "$UPGRADABLE" ]; then
        echo "$UPGRADABLE"
    else
        echo '{"status":"success","updates":[],"count":0,"message":"No updates available or apt unavailable","timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}' 
    fi
    exit 0
fi

# ==============================================================================
# subcommand: security - セキュリティ更新一覧
# ==============================================================================

if [ "$SUBCOMMAND" = "security" ]; then
    # セキュリティ更新のみフィルタ（-security リポジトリ）
    SECURITY=$(apt list --upgradable 2>/dev/null | python3 -c "
import sys, json, re

packages = []
for line in sys.stdin:
    line = line.rstrip()
    # -security を含むリポジトリのみ
    if '-security' not in line and 'security' not in line.lower():
        continue
    m = re.match(r'^(\S+)/(\S+)\s+(\S+)\s+(\S+)\s+\[upgradable from: (\S+)\]', line)
    if m:
        packages.append({
            'name': m.group(1),
            'repository': m.group(2),
            'new_version': m.group(3),
            'arch': m.group(4),
            'current_version': m.group(5),
            'is_security': True,
        })
print(json.dumps({'status':'success','security_updates':packages,'count':len(packages),'timestamp':'$(date -u +%Y-%m-%dT%H:%M:%SZ)'}))
" 2>/dev/null)

    if [ $? -eq 0 ] && [ -n "$SECURITY" ]; then
        echo "$SECURITY"
    else
        echo '{"status":"success","security_updates":[],"count":0,"message":"No security updates or apt unavailable","timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}' 
    fi
    exit 0
fi

echo '{"status":"error","message":"Unhandled subcommand"}' >&2
exit 1
