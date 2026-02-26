#!/bin/bash
# ==============================================================================
# setup-sudoers.sh - Linux Management System sudo 設定セットアップ
#
# 機能:
#   1. サービスユーザー svc-adminui の作成
#   2. sudoラッパースクリプトを /usr/local/sbin/ に配置
#   3. sudoers.d エントリを安全に設定
#
# ⚠️  このスクリプトはシステムセキュリティを変更します。
#     必ず内容を確認してから実行してください。
#     --dry-run フラグで変更内容を事前確認できます。
#
# 使用方法:
#   sudo ./setup-sudoers.sh [--dry-run] [--yes]
#
# オプション:
#   --dry-run    実際には変更せず、実行予定の操作を表示
#   --yes        確認プロンプトをスキップ（CI環境用）
#   --uninstall  設定を削除
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ==============================================================================
# 定数
# ==============================================================================

SERVICE_USER="svc-adminui"
SERVICE_HOME="/opt/linux-management"
WRAPPER_SRC_DIR="$PROJECT_ROOT/wrappers"
WRAPPER_DST_DIR="/usr/local/sbin"
SUDOERS_FILE="/etc/sudoers.d/adminui"
SUDOERS_BACKUP="/etc/sudoers.d/adminui.bak"

# ==============================================================================
# 引数解析
# ==============================================================================

DRY_RUN=false
AUTO_YES=false
UNINSTALL=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --yes)     AUTO_YES=true ;;
        --uninstall) UNINSTALL=true ;;
        --help|-h)
            echo "Usage: sudo $0 [--dry-run] [--yes] [--uninstall]"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            exit 1
            ;;
    esac
done

# ==============================================================================
# カラー出力
# ==============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()    { echo -e "${CYAN}  ℹ ${NC} $*"; }
success() { echo -e "${GREEN}  ✅ ${NC} $*"; }
warning() { echo -e "${YELLOW}  ⚠️  ${NC} $*"; }
error()   { echo -e "${RED}  ❌ ${NC} $*" >&2; }

# ==============================================================================
# 前提条件チェック
# ==============================================================================

check_prerequisites() {
    echo ""
    echo "============================================"
    echo " 前提条件チェック"
    echo "============================================"

    # root 権限チェック
    if [[ $EUID -ne 0 ]]; then
        error "このスクリプトは root 権限で実行する必要があります"
        error "sudo ./setup-sudoers.sh を使用してください"
        exit 1
    fi
    success "root 権限確認"

    # visudo の存在確認
    if ! command -v visudo &>/dev/null; then
        error "visudo が見つかりません。sudo パッケージをインストールしてください"
        exit 1
    fi
    success "visudo コマンド確認"

    # ラッパースクリプトの存在確認
    if [[ ! -d "$WRAPPER_SRC_DIR" ]]; then
        error "ラッパースクリプトディレクトリが見つかりません: $WRAPPER_SRC_DIR"
        exit 1
    fi

    local wrapper_count
    wrapper_count=$(find "$WRAPPER_SRC_DIR" -name "adminui-*.sh" | wc -l)
    if [[ $wrapper_count -eq 0 ]]; then
        error "adminui-*.sh ラッパースクリプトが見つかりません: $WRAPPER_SRC_DIR"
        exit 1
    fi
    success "ラッパースクリプト確認: ${wrapper_count} 件"

    # shellcheck（任意）
    if command -v shellcheck &>/dev/null; then
        info "shellcheck でラッパースクリプトを検証中..."
        local fail=false
        while IFS= read -r -d '' script; do
            if ! shellcheck -S error "$script" 2>/dev/null; then
                warning "shellcheck エラー: $script"
                fail=true
            fi
        done < <(find "$WRAPPER_SRC_DIR" -name "adminui-*.sh" -print0)

        if $fail; then
            error "shellcheck でエラーが検出されました。確認後に再実行してください"
            exit 1
        fi
        success "shellcheck 検証: 問題なし"
    else
        warning "shellcheck が見つかりません（スキップ）: apt install shellcheck を推奨"
    fi
}

# ==============================================================================
# アンインストール
# ==============================================================================

do_uninstall() {
    echo ""
    echo "============================================"
    echo " アンインストール"
    echo "============================================"
    warning "以下の操作を実行します:"
    echo "  1. $SUDOERS_FILE を削除"
    echo "  2. $WRAPPER_DST_DIR/adminui-*.sh を削除"
    echo "  ※ ユーザー $SERVICE_USER は削除しません"

    if ! $AUTO_YES; then
        echo ""
        read -r -p "続行しますか？ [y/N]: " confirm
        [[ "$confirm" =~ ^[Yy]$ ]] || { info "キャンセルしました"; exit 0; }
    fi

    if [[ -f "$SUDOERS_FILE" ]]; then
        if ! $DRY_RUN; then
            rm -f "$SUDOERS_FILE"
        fi
        info "[DRY-RUN] " || true
        success "sudoers ファイルを削除: $SUDOERS_FILE"
    fi

    while IFS= read -r -d '' script; do
        dst="$WRAPPER_DST_DIR/$(basename "$script")"
        if [[ -f "$dst" ]]; then
            if ! $DRY_RUN; then
                rm -f "$dst"
            fi
            success "ラッパー削除: $dst"
        fi
    done < <(find "$WRAPPER_SRC_DIR" -name "adminui-*.sh" -print0)

    success "アンインストール完了"
    exit 0
}

# ==============================================================================
# セットアップ実行
# ==============================================================================

create_service_user() {
    echo ""
    echo "--------------------------------------------"
    echo " ① サービスユーザーの作成"
    echo "--------------------------------------------"

    if id "$SERVICE_USER" &>/dev/null; then
        info "ユーザー $SERVICE_USER は既に存在します（スキップ）"
        return
    fi

    if $DRY_RUN; then
        info "[DRY-RUN] useradd -r -s /bin/bash -d $SERVICE_HOME -m $SERVICE_USER"
    else
        useradd -r -s /bin/bash -d "$SERVICE_HOME" -m "$SERVICE_USER"
        success "ユーザー $SERVICE_USER を作成しました"
    fi
}

install_wrappers() {
    echo ""
    echo "--------------------------------------------"
    echo " ② ラッパースクリプトの配置"
    echo "--------------------------------------------"

    while IFS= read -r -d '' script; do
        local basename_script
        basename_script="$(basename "$script")"
        local dst="$WRAPPER_DST_DIR/$basename_script"

        if $DRY_RUN; then
            info "[DRY-RUN] cp $script $dst"
            info "[DRY-RUN] chown root:root $dst"
            info "[DRY-RUN] chmod 755 $dst"
        else
            cp "$script" "$dst"
            chown root:root "$dst"
            chmod 755 "$dst"
            success "配置: $dst"
        fi
    done < <(find "$WRAPPER_SRC_DIR" -name "adminui-*.sh" -print0)
}

create_sudoers() {
    echo ""
    echo "--------------------------------------------"
    echo " ③ sudoers 設定の作成"
    echo "--------------------------------------------"

    # 許可するラッパーの一覧を生成
    local entries=""
    while IFS= read -r -d '' script; do
        local basename_script
        basename_script="$(basename "$script")"
        local dst="$WRAPPER_DST_DIR/$basename_script"
        entries+="${SERVICE_USER} ALL=(root) NOPASSWD: ${dst}\n"
    done < <(find "$WRAPPER_SRC_DIR" -name "adminui-*.sh" -print0 | sort -z)

    local sudoers_content
    sudoers_content="# Linux Management System - sudo wrapper configuration
# 生成日時: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
# 生成元: $0
#
# ⚠️  このファイルを直接編集しないでください。
#     setup-sudoers.sh を使用して更新してください。
#
# 許可ユーザー: $SERVICE_USER
# 許可操作: adminui-*.sh ラッパースクリプトのみ（NOPASSWD）

Defaults:$SERVICE_USER !requiretty
Defaults:$SERVICE_USER env_reset
Defaults:$SERVICE_USER secure_path=\"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\"

$(printf "$entries")"

    echo ""
    info "sudoers ファイルの内容:"
    echo "---"
    echo "$sudoers_content"
    echo "---"

    if $DRY_RUN; then
        info "[DRY-RUN] $SUDOERS_FILE への書き込みをスキップ"
        return
    fi

    # バックアップ
    if [[ -f "$SUDOERS_FILE" ]]; then
        cp "$SUDOERS_FILE" "$SUDOERS_BACKUP"
        info "既存のsudoersをバックアップ: $SUDOERS_BACKUP"
    fi

    # 一時ファイルで visudo 検証
    local tmpfile
    tmpfile="$(mktemp /tmp/adminui-sudoers.XXXXXX)"
    echo "$sudoers_content" > "$tmpfile"

    if ! visudo -c -f "$tmpfile" 2>&1; then
        error "sudoers の検証に失敗しました"
        rm -f "$tmpfile"
        exit 1
    fi

    # 本番ファイルに配置
    install -m 440 -o root -g root "$tmpfile" "$SUDOERS_FILE"
    rm -f "$tmpfile"

    success "sudoers ファイルを作成: $SUDOERS_FILE"
}

verify_installation() {
    echo ""
    echo "--------------------------------------------"
    echo " ④ インストール検証"
    echo "--------------------------------------------"

    if $DRY_RUN; then
        info "[DRY-RUN] sudo -l -U $SERVICE_USER によるテストをスキップ"
        return
    fi

    # sudoers の構文チェック
    if visudo -c 2>&1; then
        success "sudoers 構文チェック: OK"
    else
        error "sudoers 構文エラーを検出しました"
        exit 1
    fi

    # ラッパーの存在確認
    local missing=0
    while IFS= read -r -d '' script; do
        local dst="$WRAPPER_DST_DIR/$(basename "$script")"
        if [[ ! -x "$dst" ]]; then
            warning "実行可能なラッパーが見つかりません: $dst"
            missing=$((missing + 1))
        fi
    done < <(find "$WRAPPER_SRC_DIR" -name "adminui-*.sh" -print0)

    if [[ $missing -gt 0 ]]; then
        error "${missing} 個のラッパースクリプトが見つかりません"
        exit 1
    fi

    success "全ラッパースクリプトの確認: OK"

    # sudo -l でパーミッション確認
    if id "$SERVICE_USER" &>/dev/null; then
        info "sudo -l -U $SERVICE_USER による権限確認:"
        sudo -l -U "$SERVICE_USER" 2>&1 | grep "adminui" | head -20 || true
    fi
}

# ==============================================================================
# メイン処理
# ==============================================================================

main() {
    echo ""
    echo "============================================"
    echo " Linux Management System - sudoers セットアップ"
    if $DRY_RUN; then
        echo " モード: DRY-RUN（変更は行いません）"
    else
        echo " モード: 本番実行"
    fi
    echo "============================================"

    check_prerequisites

    if $UNINSTALL; then
        do_uninstall
    fi

    # 実行計画の確認
    echo ""
    echo "以下の操作を実行します:"
    echo "  1. サービスユーザー '$SERVICE_USER' の作成（未存在時）"
    echo "  2. ラッパースクリプトを $WRAPPER_DST_DIR/ に配置"
    echo "  3. sudoers.d エントリを $SUDOERS_FILE に作成"
    echo ""

    if ! $AUTO_YES && ! $DRY_RUN; then
        warning "この操作はシステムのセキュリティ設定を変更します。"
        read -r -p "続行しますか？ [y/N]: " confirm
        [[ "$confirm" =~ ^[Yy]$ ]] || { info "キャンセルしました"; exit 0; }
    fi

    create_service_user
    install_wrappers
    create_sudoers
    verify_installation

    echo ""
    echo "============================================"
    if $DRY_RUN; then
        success "DRY-RUN 完了（変更は行われていません）"
        info "実際に実行する場合は --dry-run を外してください"
    else
        success "セットアップ完了"
        info "次のステップ:"
        info "  1. アプリケーションを $SERVICE_USER ユーザーで起動してください"
        info "  2. systemd サービスを設定: scripts/setup/install-service.sh"
    fi
    echo "============================================"
}

main "$@"
