#!/bin/bash
# ==============================================================================
# adminui-firewall.sh - ファイアウォールルール取得ラッパー（読み取り専用）
#
# 機能:
#   ファイアウォールルール・ポリシーを取得する。
#   全操作は読み取り専用。ルールの変更は行わない。
#
# 使用方法:
#   adminui-firewall.sh <subcommand>
#
# サブコマンド:
#   rules    - ファイアウォールルール一覧 (iptables-save または nft list ruleset)
#   policy   - デフォルトポリシー取得 (iptables -L -n -v)
#   status   - UFW / firewalld の状態取得
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - 許可サブコマンドのみ実行（allowlist方式）
#   - ユーザー入力は受け付けない（引数 = サブコマンドのみ）
#   - 読み取り専用: 変更操作は一切行わない
# ==============================================================================

set -euo pipefail

# ==============================================================================
# 定数
# ==============================================================================

ALLOWED_SUBCOMMANDS=("rules" "policy" "status")

# ==============================================================================
# 引数チェック
# ==============================================================================

if [ "$#" -ne 1 ]; then
    echo '{"status":"error","message":"Usage: adminui-firewall.sh <subcommand>"}' >&2
    exit 1
fi

SUBCOMMAND="$1"

# allowlist チェック
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
# subcommand: rules - iptables-save または nft list ruleset
# ==============================================================================

if [ "$SUBCOMMAND" = "rules" ]; then
    # iptables-save を試みる
    if command -v iptables-save >/dev/null 2>&1; then
        # iptables-save の出力をパースしてJSONに変換
        RAW_OUTPUT=$(iptables-save 2>/dev/null || echo "")
        if [ -n "$RAW_OUTPUT" ]; then
            # 各行をJSON文字列配列に変換（pythonを利用）
            JSON_RULES=$(echo "$RAW_OUTPUT" | python3 -c "
import sys, json
lines = [l.rstrip() for l in sys.stdin]
tables = {}
current_table = None
for line in lines:
    if line.startswith('#') or not line.strip():
        continue
    if line.startswith('*'):
        current_table = line[1:]
        tables[current_table] = {'chains': {}, 'rules': []}
    elif line.startswith(':') and current_table:
        parts = line.split()
        chain = parts[0][1:]
        policy = parts[1] if len(parts) > 1 else '-'
        tables[current_table]['chains'][chain] = policy
    elif line.startswith('-A') and current_table:
        tables[current_table]['rules'].append(line)
    elif line == 'COMMIT':
        pass
print(json.dumps({'status':'success','backend':'iptables','tables':tables,'raw_lines':lines,'timestamp':'$(date -u +%Y-%m-%dT%H:%M:%SZ)'}))
" 2>/dev/null)
            if [ $? -eq 0 ] && [ -n "$JSON_RULES" ]; then
                echo "$JSON_RULES"
                exit 0
            fi
        fi
    fi

    # nftables を試みる
    if command -v nft >/dev/null 2>&1; then
        RAW_NFT=$(nft list ruleset 2>/dev/null || echo "")
        NFT_JSON=$(nft -j list ruleset 2>/dev/null || echo "")
        if [ -n "$NFT_JSON" ]; then
            # nft -j の出力をそのまま包む
            echo "{\"status\":\"success\",\"backend\":\"nftables\",\"ruleset\":${NFT_JSON},\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
            exit 0
        elif [ -n "$RAW_NFT" ]; then
            ESCAPED=$(echo "$RAW_NFT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
            echo "{\"status\":\"success\",\"backend\":\"nftables\",\"raw\":${ESCAPED},\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
            exit 0
        fi
    fi

    # UFW を試みる
    if command -v ufw >/dev/null 2>&1; then
        UFW_STATUS=$(ufw status verbose 2>/dev/null || echo "inactive")
        ESCAPED=$(echo "$UFW_STATUS" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")
        echo "{\"status\":\"success\",\"backend\":\"ufw\",\"raw\":${ESCAPED},\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
        exit 0
    fi

    echo '{"status":"success","backend":"none","message":"No firewall tool available","rules":[],"timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}'
    exit 0
fi

# ==============================================================================
# subcommand: policy - デフォルトポリシー取得
# ==============================================================================

if [ "$SUBCOMMAND" = "policy" ]; then
    if command -v iptables >/dev/null 2>&1; then
        # 各チェーンのポリシーを取得
        POLICY_OUTPUT=$(iptables -L -n --line-numbers 2>/dev/null | python3 -c "
import sys, json, re
chains = []
current = None
for line in sys.stdin:
    line = line.rstrip()
    m = re.match(r'^Chain (\S+) \(policy (\S+)', line)
    if m:
        if current:
            chains.append(current)
        current = {'chain': m.group(1), 'policy': m.group(2), 'table': 'filter', 'rules': []}
    elif current and line.startswith('num') or (line and not line.startswith(' ')):
        pass
    elif current and re.match(r'^\d+', line.strip()):
        current['rules'].append(line.strip())
if current:
    chains.append(current)
print(json.dumps({'status':'success','chains':chains,'timestamp':'$(date -u +%Y-%m-%dT%H:%M:%SZ)'}))
" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$POLICY_OUTPUT" ]; then
            echo "$POLICY_OUTPUT"
            exit 0
        fi
    fi

    if command -v nft >/dev/null 2>&1; then
        NFT_JSON=$(nft -j list ruleset 2>/dev/null || echo "")
        if [ -n "$NFT_JSON" ]; then
            echo "{\"status\":\"success\",\"backend\":\"nftables\",\"ruleset\":${NFT_JSON},\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
            exit 0
        fi
    fi

    echo '{"status":"success","chains":[],"message":"No iptables/nftables available","timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}'
    exit 0
fi

# ==============================================================================
# subcommand: status - ファイアウォール全体状態
# ==============================================================================

if [ "$SUBCOMMAND" = "status" ]; then
    BACKENDS=()
    UFW_ACTIVE=false
    FIREWALLD_ACTIVE=false
    IPTABLES_AVAILABLE=false
    NFT_AVAILABLE=false

    # UFW チェック
    if command -v ufw >/dev/null 2>&1; then
        UFW_RAW=$(ufw status 2>/dev/null || echo "inactive")
        if echo "$UFW_RAW" | grep -q "Status: active"; then
            UFW_ACTIVE=true
        fi
        BACKENDS+=("ufw")
    fi

    # firewalld チェック
    if command -v firewall-cmd >/dev/null 2>&1; then
        if systemctl is-active --quiet firewalld 2>/dev/null; then
            FIREWALLD_ACTIVE=true
        fi
        BACKENDS+=("firewalld")
    fi

    # iptables チェック
    if command -v iptables >/dev/null 2>&1; then
        IPTABLES_AVAILABLE=true
        BACKENDS+=("iptables")
    fi

    # nftables チェック
    if command -v nft >/dev/null 2>&1; then
        NFT_AVAILABLE=true
        BACKENDS+=("nftables")
    fi

    # backends JSON配列
    BACKENDS_JSON=$(python3 -c "import json; print(json.dumps($(IFS=,; echo "[\"${BACKENDS[*]}\"]" | sed 's/,/","/g')))" 2>/dev/null || echo '[]')

    echo "{\"status\":\"success\",\"ufw_active\":${UFW_ACTIVE},\"firewalld_active\":${FIREWALLD_ACTIVE},\"iptables_available\":${IPTABLES_AVAILABLE},\"nftables_available\":${NFT_AVAILABLE},\"available_backends\":${BACKENDS_JSON},\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    exit 0
fi

echo '{"status":"error","message":"Unhandled subcommand"}' >&2
exit 1
