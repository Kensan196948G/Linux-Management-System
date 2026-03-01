#!/bin/bash
# ファイルマネージャー ラッパースクリプト
# 読み取り専用ファイル操作のみ許可（list/stat/read/search）
set -euo pipefail

SUBCOMMAND="${1:-}"

ALLOWED_SUBCOMMANDS=("list" "stat" "read" "search")

ALLOWED_BASE_DIRS=(
    "/var/log"
    "/etc/nginx"
    "/etc/apache2"
    "/etc/ssh"
    "/tmp"
    "/var/www"
    "/home"
)

# 使用方法
usage() {
    echo "Usage: $0 <subcommand> [args...]" >&2
    echo "  list   <path>                    - ディレクトリ一覧" >&2
    echo "  stat   <path>                    - ファイル属性" >&2
    echo "  read   <path> <lines>            - ファイル内容 (最大200行)" >&2
    echo "  search <directory> <pattern>     - ファイル検索" >&2
    exit 1
}

# サブコマンド検証
if [[ -z "${SUBCOMMAND}" ]]; then
    usage
fi

VALID_SUBCMD=0
for cmd in "${ALLOWED_SUBCOMMANDS[@]}"; do
    if [[ "${SUBCOMMAND}" == "${cmd}" ]]; then
        VALID_SUBCMD=1
        break
    fi
done

if [[ "${VALID_SUBCMD}" -eq 0 ]]; then
    echo "Error: Unknown subcommand: ${SUBCOMMAND}" >&2
    echo "Allowed: ${ALLOWED_SUBCOMMANDS[*]}" >&2
    exit 1
fi

# パス検証関数
validate_path() {
    local path="$1"

    # 空チェック
    if [[ -z "${path}" ]]; then
        echo "Error: Path must not be empty" >&2
        exit 1
    fi

    # ../ を含む場合は拒否
    if [[ "${path}" == *"../"* || "${path}" == *"/.."* || "${path}" == ".." ]]; then
        echo "Error: Path traversal detected: ${path}" >&2
        exit 1
    fi

    # null バイトを含む場合は拒否
    if printf '%s' "${path}" | grep -qP '\x00'; then
        echo "Error: Null byte detected in path" >&2
        exit 1
    fi

    # ALLOWED_BASE_DIRS のいずれかで始まるか確認
    local allowed=0
    for base_dir in "${ALLOWED_BASE_DIRS[@]}"; do
        if [[ "${path}" == "${base_dir}" || "${path}" == "${base_dir}/"* ]]; then
            allowed=1
            break
        fi
    done

    if [[ "${allowed}" -eq 0 ]]; then
        echo "Error: Path not in allowed directories: ${path}" >&2
        exit 1
    fi
}

# パターン検証関数（search 用）
validate_pattern() {
    local pattern="$1"
    if [[ -z "${pattern}" ]]; then
        echo "Error: Pattern must not be empty" >&2
        exit 1
    fi
    # 危険な文字を拒否
    if [[ "${pattern}" =~ [';''|''&''$''('')''\`''>''<'] ]]; then
        echo "Error: Forbidden characters in pattern" >&2
        exit 1
    fi
}

case "${SUBCOMMAND}" in
    list)
        TARGET_PATH="${2:-}"
        validate_path "${TARGET_PATH}"
        ls -la --time-style=+"%Y-%m-%dT%H:%M:%S" "${TARGET_PATH}"
        ;;

    stat)
        TARGET_PATH="${2:-}"
        validate_path "${TARGET_PATH}"
        stat --format='{"name":"%n","size":%s,"type":"%F","permissions":"%A","owner":"%U","group":"%G","modified":"%y","inode":%i}' "${TARGET_PATH}"
        ;;

    read)
        TARGET_PATH="${2:-}"
        LINES="${3:-50}"
        validate_path "${TARGET_PATH}"
        # 行数検証（1-200）
        if ! [[ "${LINES}" =~ ^[0-9]+$ ]] || [[ "${LINES}" -lt 1 ]] || [[ "${LINES}" -gt 200 ]]; then
            echo "Error: lines must be between 1 and 200" >&2
            exit 1
        fi
        head -n "${LINES}" "${TARGET_PATH}"
        ;;

    search)
        SEARCH_DIR="${2:-}"
        PATTERN="${3:-}"
        validate_path "${SEARCH_DIR}"
        validate_pattern "${PATTERN}"
        find "${SEARCH_DIR}" -maxdepth 2 -name "${PATTERN}" -print 2>/dev/null || true
        ;;
esac
