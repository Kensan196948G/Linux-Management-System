#!/bin/bash
# ==============================================================================
# deploy.sh - Linux Management System 本番デプロイスクリプト
#
# 機能:
#   本番環境への完全デプロイを半自動化する。
#   各ステップでの確認プロンプトによりオペレーターの承認を要求する。
#
# 使用方法:
#   sudo ./scripts/deploy.sh [--dry-run] [--yes] [--skip-sudoers]
#
# オプション:
#   --dry-run       実際には変更せず、実行予定の操作を表示
#   --yes           確認プロンプトをスキップ（CI/CD環境用）
#   --skip-sudoers  sudoers セットアップをスキップ（既設定済みの場合）
#
# デプロイ手順:
#   Phase 1: 前提条件チェック
#   Phase 2: ディレクトリ・ファイル配置
#   Phase 3: Python 仮想環境・依存関係インストール
#   Phase 4: sudoers セットアップ（--skip-sudoers でスキップ可能）
#   Phase 5: systemd サービスインストール・起動
#   Phase 6: ヘルスチェック
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ==============================================================================
# 定数
# ==============================================================================

DEPLOY_USER="svc-adminui"
DEPLOY_HOME="/opt/linux-management"
VENV_DIR="$DEPLOY_HOME/venv-prod"
SERVICE_NAME="linux-management-prod"
ENV_FILE="$DEPLOY_HOME/.env"
LOG_FILE="/var/log/linux-management/deploy-$(date +%Y%m%d-%H%M%S).log"

# ==============================================================================
# 引数解析
# ==============================================================================

DRY_RUN=false
AUTO_YES=false
SKIP_SUDOERS=false

for arg in "$@"; do
    case "$arg" in
        --dry-run)       DRY_RUN=true ;;
        --yes)           AUTO_YES=true ;;
        --skip-sudoers)  SKIP_SUDOERS=true ;;
        --help|-h)
            sed -n '/^# 使用方法/,/^#$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            exit 1
            ;;
    esac
done

# ==============================================================================
# ユーティリティ
# ==============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${CYAN}  ℹ ${NC} $*"; }
success() { echo -e "${GREEN}  ✅ ${NC} $*"; }
warning() { echo -e "${YELLOW}  ⚠️  ${NC} $*"; }
error()   { echo -e "${RED}  ❌ ${NC} $*" >&2; }
step()    { echo -e "\n${BOLD}${CYAN}━━ $* ${NC}"; }

confirm() {
    local msg="${1:-続行しますか？}"
    if $AUTO_YES; then
        info "(--yes フラグにより自動確認)"
        return 0
    fi
    read -r -p "  $msg [y/N]: " answer
    [[ "$answer" =~ ^[Yy]$ ]]
}

run_cmd() {
    if $DRY_RUN; then
        info "[DRY-RUN] $*"
    else
        "$@"
    fi
}

# ==============================================================================
# Phase 1: 前提条件チェック
# ==============================================================================

phase1_prerequisites() {
    step "Phase 1: 前提条件チェック"

    # root 権限
    if [[ $EUID -ne 0 ]]; then
        error "root 権限が必要です: sudo ./scripts/deploy.sh"
        exit 1
    fi
    success "root 権限"

    # OS チェック（Ubuntu 推奨）
    if command -v lsb_release &>/dev/null; then
        local os_info
        os_info=$(lsb_release -d 2>/dev/null | awk -F: '{print $2}' | xargs)
        info "OS: $os_info"
    fi

    # Python 3.10+
    if ! command -v python3 &>/dev/null; then
        error "python3 が見つかりません"
        exit 1
    fi
    local py_ver
    py_ver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if python3 -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)"; then
        success "Python $py_ver"
    else
        error "Python 3.10 以上が必要です（現在: $py_ver）"
        exit 1
    fi

    # .env ファイル
    if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
        error ".env ファイルが見つかりません: $PROJECT_ROOT/.env"
        info ".env.example をコピーして設定してください:"
        info "  cp $PROJECT_ROOT/.env.example $PROJECT_ROOT/.env"
        exit 1
    fi
    success ".env ファイル"

    # gunicorn インストール確認（venv に後でインストール）
    if command -v gunicorn &>/dev/null; then
        success "gunicorn $(gunicorn --version 2>&1 | awk '{print $1}')"
    else
        info "gunicorn は venv インストール後に利用可能になります"
    fi

    # systemd
    if ! command -v systemctl &>/dev/null; then
        error "systemctl が見つかりません（systemd が必要です）"
        exit 1
    fi
    success "systemd"

    # ポート確認
    local prod_port
    prod_port=$(grep -E '^PROD_PORT=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2 | tr -d '"' || echo "5000")
    if ss -tlnp "sport = :$prod_port" 2>/dev/null | grep -q LISTEN; then
        warning "ポート $prod_port は既に使用中です（既存サービスの停止が必要かもしれません）"
    else
        success "ポート $prod_port: 利用可能"
    fi
}

# ==============================================================================
# Phase 2: ディレクトリ・ファイル配置
# ==============================================================================

phase2_files() {
    step "Phase 2: ディレクトリ・ファイル配置"

    # ディレクトリ作成
    for dir in \
        "$DEPLOY_HOME" \
        "$DEPLOY_HOME/data" \
        "/var/log/linux-management" \
        "/var/lib/linux-management"
    do
        if [[ ! -d "$dir" ]]; then
            run_cmd mkdir -p "$dir"
            success "ディレクトリ作成: $dir"
        else
            info "既存: $dir"
        fi
    done

    # プロジェクトファイルのコピー
    if [[ "$PROJECT_ROOT" != "$DEPLOY_HOME" ]]; then
        info "プロジェクトファイルをコピー中: $PROJECT_ROOT → $DEPLOY_HOME"
        run_cmd rsync -av --exclude='.git' --exclude='venv*' --exclude='__pycache__' \
            --exclude='*.pyc' --exclude='htmlcov' --exclude='*.egg-info' \
            "$PROJECT_ROOT/" "$DEPLOY_HOME/"
        success "ファイルコピー完了"
    else
        info "デプロイ先がプロジェクトルートと同じです（コピースキップ）"
    fi

    # .env のコピー
    if [[ ! -f "$ENV_FILE" ]]; then
        run_cmd cp "$PROJECT_ROOT/.env" "$ENV_FILE"
        run_cmd chmod 600 "$ENV_FILE"
        success ".env ファイルを配置: $ENV_FILE"
    else
        info "既存の .env を保持: $ENV_FILE"
    fi

    # 所有者設定
    if id "$DEPLOY_USER" &>/dev/null; then
        run_cmd chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_HOME"
        success "所有者設定: $DEPLOY_USER"
    else
        warning "ユーザー $DEPLOY_USER が存在しません（sudoers セットアップ後に実行）"
    fi
}

# ==============================================================================
# Phase 3: Python 仮想環境・依存関係
# ==============================================================================

phase3_python() {
    step "Phase 3: Python 仮想環境・依存関係インストール"

    # 仮想環境作成
    if [[ ! -d "$VENV_DIR" ]]; then
        run_cmd python3 -m venv "$VENV_DIR"
        success "仮想環境作成: $VENV_DIR"
    else
        info "既存の仮想環境: $VENV_DIR"
    fi

    # 依存関係インストール
    local req_file="$DEPLOY_HOME/backend/requirements.txt"
    if [[ -f "$req_file" ]]; then
        run_cmd "$VENV_DIR/bin/pip" install --upgrade pip -q
        run_cmd "$VENV_DIR/bin/pip" install -r "$req_file" -q
        run_cmd "$VENV_DIR/bin/pip" install gunicorn -q
        success "依存関係インストール完了"
    else
        warning "requirements.txt が見つかりません: $req_file"
    fi
}

# ==============================================================================
# Phase 4: sudoers セットアップ
# ==============================================================================

phase4_sudoers() {
    step "Phase 4: sudoers セットアップ"

    if $SKIP_SUDOERS; then
        info "--skip-sudoers が指定されています（スキップ）"
        return
    fi

    local sudoers_script="$SCRIPT_DIR/setup/setup-sudoers.sh"
    if [[ ! -f "$sudoers_script" ]]; then
        error "setup-sudoers.sh が見つかりません: $sudoers_script"
        exit 1
    fi

    local flags=""
    $DRY_RUN  && flags="$flags --dry-run"
    $AUTO_YES && flags="$flags --yes"

    # shellcheck disable=SC2086
    run_cmd bash "$sudoers_script" $flags
}

# ==============================================================================
# Phase 5: systemd サービス
# ==============================================================================

phase5_systemd() {
    step "Phase 5: systemd サービスインストール・起動"

    local service_file="$PROJECT_ROOT/systemd/$SERVICE_NAME.service"
    if [[ ! -f "$service_file" ]]; then
        error "サービスファイルが見つかりません: $service_file"
        exit 1
    fi

    # サービスファイルのインストール
    run_cmd cp "$service_file" "/etc/systemd/system/$SERVICE_NAME.service"
    success "サービスファイルをインストール: /etc/systemd/system/$SERVICE_NAME.service"

    run_cmd systemctl daemon-reload
    success "systemd デーモンをリロード"

    # 既存サービスの停止
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        warning "既存のサービスを停止します: $SERVICE_NAME"
        run_cmd systemctl stop "$SERVICE_NAME"
    fi

    # 自動起動の有効化
    run_cmd systemctl enable "$SERVICE_NAME"
    success "自動起動を有効化: $SERVICE_NAME"

    # サービス起動
    if ! $DRY_RUN; then
        run_cmd systemctl start "$SERVICE_NAME"
        sleep 3  # 起動待機
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            success "サービス起動: $SERVICE_NAME"
        else
            error "サービスの起動に失敗しました"
            error "journalctl -u $SERVICE_NAME -n 50 で確認してください"
            exit 1
        fi
    else
        info "[DRY-RUN] systemctl start $SERVICE_NAME"
    fi
}

# ==============================================================================
# Phase 6: ヘルスチェック
# ==============================================================================

phase6_healthcheck() {
    step "Phase 6: ヘルスチェック"

    if $DRY_RUN; then
        info "[DRY-RUN] ヘルスチェックをスキップ"
        return
    fi

    local prod_port
    prod_port=$(grep -E '^PROD_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 | tr -d '"' || echo "5000")

    local max_retries=10
    local retry=0
    local health_url="http://localhost:$prod_port/health"

    info "ヘルスチェック中: $health_url"
    while [[ $retry -lt $max_retries ]]; do
        if curl -sf "$health_url" &>/dev/null; then
            success "ヘルスチェック成功: $health_url"
            break
        fi
        retry=$((retry + 1))
        info "待機中... ($retry/$max_retries)"
        sleep 3
    done

    if [[ $retry -ge $max_retries ]]; then
        error "ヘルスチェックタイムアウト: $health_url"
        warning "journalctl -u $SERVICE_NAME -n 50 でログを確認してください"
        exit 1
    fi

    # API バージョン確認
    local api_url="http://localhost:$prod_port/api"
    if curl -sf "$api_url" &>/dev/null; then
        success "API エンドポイント確認: $api_url"
    fi

    info "デプロイ完了サマリー:"
    systemctl status "$SERVICE_NAME" --no-pager -l | head -15
}

# ==============================================================================
# メイン処理
# ==============================================================================

main() {
    echo ""
    echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  Linux Management System - 本番デプロイ${NC}"
    if $DRY_RUN; then
        echo -e "${YELLOW}  モード: DRY-RUN（実際の変更は行いません）${NC}"
    fi
    echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
    echo ""
    info "プロジェクト: $PROJECT_ROOT"
    info "デプロイ先:   $DEPLOY_HOME"
    info "サービス名:   $SERVICE_NAME"
    echo ""

    if ! $AUTO_YES; then
        warning "本番環境へのデプロイを実行します。"
        confirm "続行しますか？" || { info "キャンセルしました"; exit 0; }
    fi

    # デプロイログの初期化
    if ! $DRY_RUN; then
        mkdir -p "$(dirname "$LOG_FILE")"
        exec > >(tee -a "$LOG_FILE") 2>&1
        info "デプロイログ: $LOG_FILE"
    fi

    phase1_prerequisites
    phase2_files
    phase3_python
    phase4_sudoers
    phase5_systemd
    phase6_healthcheck

    echo ""
    echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
    if $DRY_RUN; then
        echo -e "${GREEN}  DRY-RUN 完了（変更は行われていません）${NC}"
    else
        echo -e "${GREEN}  デプロイ完了 🎉${NC}"
        info "サービス状態: systemctl status $SERVICE_NAME"
        info "ログ確認:     journalctl -u $SERVICE_NAME -f"
        info "デプロイログ: $LOG_FILE"
    fi
    echo -e "${BOLD}══════════════════════════════════════════════════════${NC}"
}

main "$@"
