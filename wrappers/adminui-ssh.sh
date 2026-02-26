#!/bin/bash
# ==============================================================================
# adminui-ssh.sh - SSHサーバー設定読み取りラッパー（読み取り専用）
#
# 機能:
#   sshd_config の状態・設定を読み取る。危険設定の警告も出力する。
#   全操作は読み取り専用。設定の変更は行わない。
#
# 使用方法:
#   adminui-ssh.sh <subcommand>
#
# サブコマンド:
#   status   - SSHサービスの状態 (systemctl status sshd)
#   config   - sshd_config のパース結果 + 危険設定チェック
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - 許可サブコマンドのみ実行（allowlist方式）
#   - sshd_config は読み取り専用（書き込み操作なし）
# ==============================================================================

set -euo pipefail

ALLOWED_SUBCOMMANDS=("status" "config")
SSHD_CONFIG="/etc/ssh/sshd_config"

if [ "$#" -ne 1 ]; then
    echo '{"status":"error","message":"Usage: adminui-ssh.sh <subcommand>"}' >&2
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
# subcommand: status - SSHサービス状態
# ==============================================================================

if [ "$SUBCOMMAND" = "status" ]; then
    # サービス名を確認（sshd または ssh）
    SSH_SERVICE="sshd"
    if ! systemctl list-units --type=service 2>/dev/null | grep -q "sshd.service"; then
        SSH_SERVICE="ssh"
    fi

    ACTIVE_STATE=$(systemctl is-active "${SSH_SERVICE}" 2>/dev/null | head -1 || echo "unknown")
    ENABLED_STATE=$(systemctl is-enabled "${SSH_SERVICE}" 2>/dev/null | head -1 || echo "unknown")
    PID=$(systemctl show "${SSH_SERVICE}" --property=MainPID 2>/dev/null | cut -d= -f2 || echo "0")

    # リスニングポートの確認
    SSH_PORT="22"
    if [ -r "${SSHD_CONFIG}" ]; then
        PORT_LINE=$(grep -E "^\s*Port\s+" "${SSHD_CONFIG}" 2>/dev/null | head -1 || echo "")
        if [ -n "$PORT_LINE" ]; then
            SSH_PORT=$(echo "$PORT_LINE" | awk '{print $2}')
        fi
    fi

    echo "{\"status\":\"success\",\"service\":\"${SSH_SERVICE}\",\"active_state\":\"${ACTIVE_STATE}\",\"enabled_state\":\"${ENABLED_STATE}\",\"pid\":\"${PID}\",\"port\":\"${SSH_PORT}\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    exit 0
fi

# ==============================================================================
# subcommand: config - sshd_config パース + 危険設定チェック
# ==============================================================================

if [ "$SUBCOMMAND" = "config" ]; then
    if [ ! -r "${SSHD_CONFIG}" ]; then
        echo "{\"status\":\"error\",\"message\":\"Cannot read ${SSHD_CONFIG} (permission denied or not found)\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
        exit 0
    fi

    python3 -c "
import sys, json, re

config_path = '${SSHD_CONFIG}'
settings = {}
warnings = []

# 危険な設定のチェックルール
DANGER_CHECKS = [
    ('PermitRootLogin', 'yes', 'CRITICAL', 'rootログインが許可されています。PermitRootLogin no または prohibit-password に変更してください。'),
    ('PasswordAuthentication', 'yes', 'WARNING', 'パスワード認証が有効です。公開鍵認証のみにすることを推奨します。'),
    ('PermitEmptyPasswords', 'yes', 'CRITICAL', '空パスワードが許可されています。即座にnoに変更してください。'),
    ('ChallengeResponseAuthentication', 'yes', 'WARNING', 'チャレンジレスポンス認証が有効です。'),
    ('X11Forwarding', 'yes', 'LOW', 'X11転送が有効です。不要であれば無効化を推奨します。'),
    ('AllowTcpForwarding', 'yes', 'LOW', 'TCPポート転送が有効です。'),
    ('GatewayPorts', 'yes', 'WARNING', 'ゲートウェイポートが有効です。'),
]

try:
    with open(config_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = re.match(r'^(\w+)\s+(.+)$', line)
            if m:
                key = m.group(1)
                val = m.group(2).split('#')[0].strip()
                settings[key] = val

    # 危険設定チェック
    for key, danger_val, level, msg in DANGER_CHECKS:
        actual = settings.get(key, '').lower()
        if actual == danger_val.lower():
            warnings.append({
                'key': key,
                'value': settings.get(key, ''),
                'level': level,
                'message': msg,
            })

    # ポート確認
    port = int(settings.get('Port', '22'))
    if port == 22:
        warnings.append({
            'key': 'Port',
            'value': '22',
            'level': 'LOW',
            'message': 'デフォルトポート22を使用しています。変更を検討してください。',
        })

    result = {
        'status': 'success',
        'config_path': config_path,
        'settings': settings,
        'warnings': warnings,
        'warning_count': len(warnings),
        'critical_count': sum(1 for w in warnings if w['level'] == 'CRITICAL'),
        'timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
    }
    print(json.dumps(result))
except PermissionError:
    print(json.dumps({'status': 'error', 'message': 'Permission denied reading sshd_config', 'timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'}))
except Exception as e:
    print(json.dumps({'status': 'error', 'message': str(e), 'timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'}))
" 2>/dev/null
    exit 0
fi

echo '{"status":"error","message":"Unhandled subcommand"}' >&2
exit 1
