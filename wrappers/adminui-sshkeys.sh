#!/usr/bin/env bash
# ==============================================================================
# adminui-sshkeys.sh - SSH Keys 情報取得ラッパー（読み取り専用）
#
# 使用方法:
#   adminui-sshkeys.sh list-keys   - /etc/ssh/ 内の公開鍵一覧 (*.pub)
#   adminui-sshkeys.sh sshd-config - sshd_config の重要パラメータ抽出
#   adminui-sshkeys.sh host-keys   - ホスト鍵フィンガープリント
#   adminui-sshkeys.sh auth-keys   - authorized_keys の存在確認のみ (内容非表示)
#
# セキュリティ:
#   - shell=True 禁止: 全コマンドは配列で実行
#   - allowlist によるサブコマンド制限
#   - 秘密鍵・パスワード情報は返さない
#   - JSON 形式出力
# ==============================================================================

set -euo pipefail

# ==============================================================================
# 定数
# ==============================================================================

ALLOWED_SUBCOMMANDS=("list-keys" "sshd-config" "host-keys" "auth-keys")
SSH_DIR="/etc/ssh"
SSHD_CONFIG="${SSH_DIR}/sshd_config"

# ==============================================================================
# ユーティリティ
# ==============================================================================

error_json() {
    local message="$1"
    printf '{"status":"error","message":"%s","timestamp":"%s"}\n' \
        "$message" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
}

timestamp() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

# ==============================================================================
# サブコマンド検証
# ==============================================================================

SUBCOMMAND="${1:-}"

if [[ -z "${SUBCOMMAND}" ]]; then
    error_json "サブコマンドが指定されていません"
    exit 1
fi

# allowlist 検証
allowed=false
for cmd in "${ALLOWED_SUBCOMMANDS[@]}"; do
    if [[ "${SUBCOMMAND}" == "${cmd}" ]]; then
        allowed=true
        break
    fi
done

if [[ "${allowed}" == "false" ]]; then
    error_json "許可されていないサブコマンド: ${SUBCOMMAND}"
    exit 1
fi

# ==============================================================================
# list-keys: /etc/ssh/ 内の公開鍵一覧
# ==============================================================================

cmd_list_keys() {
    local keys_json="["
    local first=true

    if [[ ! -d "${SSH_DIR}" ]]; then
        printf '{"status":"error","message":"/etc/ssh ディレクトリが存在しません","keys":[],"count":0,"timestamp":"%s"}\n' "$(timestamp)"
        return
    fi

    while IFS= read -r -d '' pubkey; do
        local filename
        filename="$(basename "${pubkey}")"
        local keytype=""
        local keysize=""
        local comment=""

        # ファイル内容の先頭行から鍵タイプとコメントを抽出（内容全体は非表示）
        if [[ -r "${pubkey}" ]]; then
            local firstline
            firstline="$(head -n1 "${pubkey}" 2>/dev/null || true)"
            keytype="$(echo "${firstline}" | awk '{print $1}' 2>/dev/null || true)"
            comment="$(echo "${firstline}" | awk '{print $3}' 2>/dev/null || true)"
        fi

        local size_bytes
        size_bytes="$(stat -c '%s' "${pubkey}" 2>/dev/null || echo "0")"

        if [[ "${first}" == "false" ]]; then
            keys_json+=","
        fi
        keys_json+="$(printf '{"filename":"%s","key_type":"%s","comment":"%s","size_bytes":%s}' \
            "$(json_escape "${filename}")" \
            "$(json_escape "${keytype}")" \
            "$(json_escape "${comment}")" \
            "${size_bytes}")"
        first=false
    done < <(find "${SSH_DIR}" -maxdepth 1 -name "*.pub" -type f -print0 2>/dev/null | sort -z)

    keys_json+="]"

    local count=0
    if [[ "${keys_json}" != "[]" ]]; then
        count=$(echo "${keys_json}" | grep -o '"filename"' | wc -l)
    fi

    printf '{"status":"success","keys":%s,"count":%d,"ssh_dir":"%s","timestamp":"%s"}\n' \
        "${keys_json}" "${count}" "${SSH_DIR}" "$(timestamp)"
}

# ==============================================================================
# sshd-config: 重要パラメータのみ抽出（セキュリティ上の理由で限定）
# ==============================================================================

cmd_sshd_config() {
    if [[ ! -f "${SSHD_CONFIG}" ]]; then
        printf '{"status":"error","message":"sshd_config が見つかりません","config_path":"%s","settings":{},"timestamp":"%s"}\n' \
            "${SSHD_CONFIG}" "$(timestamp)"
        return
    fi

    # 重要パラメータのみ抽出（パスワード・秘密鍵情報は含まない）
    local SAFE_PARAMS=(
        "Port"
        "Protocol"
        "PermitRootLogin"
        "PasswordAuthentication"
        "PubkeyAuthentication"
        "AuthorizedKeysFile"
        "PermitEmptyPasswords"
        "ChallengeResponseAuthentication"
        "UsePAM"
        "X11Forwarding"
        "PrintMotd"
        "AcceptEnv"
        "Subsystem"
        "MaxAuthTries"
        "MaxSessions"
        "LoginGraceTime"
        "AllowTcpForwarding"
        "ClientAliveInterval"
        "ClientAliveCountMax"
        "ListenAddress"
        "AddressFamily"
    )

    local settings_json="{"
    local first=true

    for param in "${SAFE_PARAMS[@]}"; do
        # コメント行を除き、パラメータ値を取得
        local value
        value="$(grep -i "^[[:space:]]*${param}[[:space:]]" "${SSHD_CONFIG}" 2>/dev/null | head -n1 | awk '{$1=""; print $0}' | sed 's/^[[:space:]]*//' || true)"

        if [[ -n "${value}" ]]; then
            if [[ "${first}" == "false" ]]; then
                settings_json+=","
            fi
            settings_json+="$(printf '"%s":"%s"' \
                "$(json_escape "${param}")" \
                "$(json_escape "${value}")")"
            first=false
        fi
    done

    settings_json+="}"

    printf '{"status":"success","config_path":"%s","settings":%s,"timestamp":"%s"}\n' \
        "${SSHD_CONFIG}" "${settings_json}" "$(timestamp)"
}

# ==============================================================================
# host-keys: ホスト鍵フィンガープリント
# ==============================================================================

cmd_host_keys() {
    local fingerprints_json="["
    local first=true

    local HOST_KEY_TYPES=("rsa" "ecdsa" "ed25519" "dsa")

    for keytype in "${HOST_KEY_TYPES[@]}"; do
        local pubkey="${SSH_DIR}/ssh_host_${keytype}_key.pub"
        if [[ -f "${pubkey}" && -r "${pubkey}" ]]; then
            local fp_output
            fp_output="$(ssh-keygen -l -f "${pubkey}" 2>/dev/null || true)"
            if [[ -n "${fp_output}" ]]; then
                local bits
                bits="$(echo "${fp_output}" | awk '{print $1}')"
                local fingerprint
                fingerprint="$(echo "${fp_output}" | awk '{print $2}')"
                local algo
                algo="$(echo "${fp_output}" | grep -oP '\(\K[^)]+' || true)"

                if [[ "${first}" == "false" ]]; then
                    fingerprints_json+=","
                fi
                fingerprints_json+="$(printf '{"key_type":"%s","bits":%s,"fingerprint":"%s","algorithm":"%s","file":"%s"}' \
                    "$(json_escape "${keytype}")" \
                    "${bits:-0}" \
                    "$(json_escape "${fingerprint}")" \
                    "$(json_escape "${algo}")" \
                    "$(json_escape "${pubkey}")")"
                first=false
            fi
        fi
    done

    fingerprints_json+="]"

    local count=0
    if [[ "${fingerprints_json}" != "[]" ]]; then
        count=$(echo "${fingerprints_json}" | grep -o '"key_type"' | wc -l)
    fi

    printf '{"status":"success","host_keys":%s,"count":%d,"timestamp":"%s"}\n' \
        "${fingerprints_json}" "${count}" "$(timestamp)"
}

# ==============================================================================
# auth-keys: authorized_keys の存在確認のみ（内容は非表示）
# ==============================================================================

cmd_auth_keys() {
    # /etc/ssh/ 内の authorized_keys の存在確認のみ
    # ホームディレクトリはセキュリティ上スキャンしない
    local found_json="["
    local first=true

    while IFS= read -r -d '' authfile; do
        local filepath
        filepath="${authfile}"
        local line_count=0

        if [[ -f "${authfile}" ]]; then
            line_count="$(wc -l < "${authfile}" 2>/dev/null || echo "0")"
        fi

        if [[ "${first}" == "false" ]]; then
            found_json+=","
        fi
        found_json+="$(printf '{"path":"%s","entry_count":%d}' \
            "$(json_escape "${filepath}")" \
            "${line_count}")"
        first=false
    done < <(find "${SSH_DIR}" -maxdepth 2 -name "authorized_keys" -type f -print0 2>/dev/null | sort -z)

    found_json+="]"

    local count=0
    if [[ "${found_json}" != "[]" ]]; then
        count=$(echo "${found_json}" | grep -o '"path"' | wc -l)
    fi

    printf '{"status":"success","authorized_keys_files":%s,"count":%d,"note":"内容は非表示（セキュリティポリシー）","timestamp":"%s"}\n' \
        "${found_json}" "${count}" "$(timestamp)"
}

# ==============================================================================
# メイン処理
# ==============================================================================

case "${SUBCOMMAND}" in
    list-keys)
        cmd_list_keys
        ;;
    sshd-config)
        cmd_sshd_config
        ;;
    host-keys)
        cmd_host_keys
        ;;
    auth-keys)
        cmd_auth_keys
        ;;
    *)
        error_json "不明なサブコマンド: ${SUBCOMMAND}"
        exit 1
        ;;
esac
