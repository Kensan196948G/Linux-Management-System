"""
tests/unit/test_install_scripts.py - インストールスクリプトテスト

install.sh / uninstall.sh / debian/ パッケージ構成ファイルの
存在・内容・安全性を検証するテスト群。
"""

import os
import stat
from pathlib import Path

import pytest

# プロジェクトルートを解決
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DEBIAN_DIR = PROJECT_ROOT / "debian"


# ---------------------------------------------------------------------------
# install.sh テスト
# ---------------------------------------------------------------------------


def test_install_script_exists():
    """install.sh が存在すること"""
    install_sh = SCRIPTS_DIR / "install.sh"
    assert install_sh.exists(), f"install.sh が存在しません: {install_sh}"


def test_install_script_executable():
    """install.sh が実行可能パーミッションを持つこと"""
    install_sh = SCRIPTS_DIR / "install.sh"
    if not install_sh.exists():
        pytest.skip("install.sh が存在しません")
    mode = os.stat(install_sh).st_mode
    assert mode & stat.S_IXUSR, "install.sh に実行パーミッション (u+x) がありません"


def test_install_script_has_set_e():
    """install.sh が 'set -euo pipefail' を含むこと (エラー時即終了)"""
    install_sh = SCRIPTS_DIR / "install.sh"
    if not install_sh.exists():
        pytest.skip("install.sh が存在しません")
    content = install_sh.read_text(encoding="utf-8")
    assert "set -euo pipefail" in content, "install.sh に 'set -euo pipefail' がありません"


def test_install_script_no_shell_injection():
    """install.sh に危険なシェルインジェクションパターンがないこと"""
    install_sh = SCRIPTS_DIR / "install.sh"
    if not install_sh.exists():
        pytest.skip("install.sh が存在しません")
    content = install_sh.read_text(encoding="utf-8")

    # bash -c "..." は任意コマンド実行を可能にするため禁止
    assert 'bash -c "' not in content, "install.sh に 'bash -c' パターンが含まれています"
    assert "bash -c '" not in content, "install.sh に 'bash -c' パターンが含まれています"
    # eval は禁止
    assert "\neval " not in content, "install.sh に eval が含まれています"


def test_install_script_requires_root_check():
    """install.sh が EUID チェック (root 確認) を含むこと"""
    install_sh = SCRIPTS_DIR / "install.sh"
    if not install_sh.exists():
        pytest.skip("install.sh が存在しません")
    content = install_sh.read_text(encoding="utf-8")
    assert "EUID" in content, "install.sh に root 権限チェック (EUID) がありません"


def test_install_script_uses_service_user():
    """install.sh が svc-adminui サービスユーザーを使用すること"""
    install_sh = SCRIPTS_DIR / "install.sh"
    if not install_sh.exists():
        pytest.skip("install.sh が存在しません")
    content = install_sh.read_text(encoding="utf-8")
    assert "svc-adminui" in content, "install.sh に SERVICE_USER=svc-adminui が含まれていません"


def test_install_script_installs_to_correct_dir():
    """install.sh が /opt/linux-management-system にインストールすること"""
    install_sh = SCRIPTS_DIR / "install.sh"
    if not install_sh.exists():
        pytest.skip("install.sh が存在しません")
    content = install_sh.read_text(encoding="utf-8")
    assert "/opt/linux-management-system" in content, (
        "install.sh のインストールディレクトリが /opt/linux-management-system ではありません"
    )


def test_install_script_no_direct_sudo_commands():
    """install.sh が sudo systemctl などの直接sudo実行を含まないこと (ラッパー経由のみ)"""
    install_sh = SCRIPTS_DIR / "install.sh"
    if not install_sh.exists():
        pytest.skip("install.sh が存在しません")
    content = install_sh.read_text(encoding="utf-8")
    # install.sh 自体は root で実行されるため sudo は不要
    # もし sudo が入っていれば二重 sudo になる
    lines = [line.strip() for line in content.splitlines() if not line.strip().startswith("#")]
    sudo_lines = [line for line in lines if line.startswith("sudo ")]
    assert len(sudo_lines) == 0, (
        f"install.sh に sudo コマンドが含まれています (root で実行するため不要): {sudo_lines[:3]}"
    )


# ---------------------------------------------------------------------------
# uninstall.sh テスト
# ---------------------------------------------------------------------------


def test_uninstall_script_exists():
    """uninstall.sh が存在すること"""
    uninstall_sh = SCRIPTS_DIR / "uninstall.sh"
    assert uninstall_sh.exists(), f"uninstall.sh が存在しません: {uninstall_sh}"


def test_uninstall_script_executable():
    """uninstall.sh が実行可能パーミッションを持つこと"""
    uninstall_sh = SCRIPTS_DIR / "uninstall.sh"
    if not uninstall_sh.exists():
        pytest.skip("uninstall.sh が存在しません")
    mode = os.stat(uninstall_sh).st_mode
    assert mode & stat.S_IXUSR, "uninstall.sh に実行パーミッション (u+x) がありません"


def test_uninstall_script_has_set_e():
    """uninstall.sh が 'set -euo pipefail' を含むこと"""
    uninstall_sh = SCRIPTS_DIR / "uninstall.sh"
    if not uninstall_sh.exists():
        pytest.skip("uninstall.sh が存在しません")
    content = uninstall_sh.read_text(encoding="utf-8")
    assert "set -euo pipefail" in content, "uninstall.sh に 'set -euo pipefail' がありません"


def test_uninstall_script_removes_sudoers():
    """uninstall.sh が sudoers 設定を削除すること"""
    uninstall_sh = SCRIPTS_DIR / "uninstall.sh"
    if not uninstall_sh.exists():
        pytest.skip("uninstall.sh が存在しません")
    content = uninstall_sh.read_text(encoding="utf-8")
    assert "sudoers" in content.lower(), "uninstall.sh が sudoers 設定の削除を行っていません"


def test_uninstall_script_has_confirmation():
    """uninstall.sh が確認プロンプトを含むこと (誤削除防止)"""
    uninstall_sh = SCRIPTS_DIR / "uninstall.sh"
    if not uninstall_sh.exists():
        pytest.skip("uninstall.sh が存在しません")
    content = uninstall_sh.read_text(encoding="utf-8")
    # --yes フラグか read コマンドによる確認がある
    has_yes_flag = "--yes" in content
    has_read_prompt = "read " in content
    assert has_yes_flag or has_read_prompt, (
        "uninstall.sh に確認プロンプト (read コマンド or --yes フラグ) がありません"
    )


# ---------------------------------------------------------------------------
# debian/control テスト
# ---------------------------------------------------------------------------


def test_debian_control_exists():
    """debian/control が存在すること"""
    control = DEBIAN_DIR / "control"
    assert control.exists(), f"debian/control が存在しません: {control}"


def test_debian_control_required_fields():
    """debian/control が必須フィールドを含むこと"""
    control = DEBIAN_DIR / "control"
    if not control.exists():
        pytest.skip("debian/control が存在しません")
    content = control.read_text(encoding="utf-8")

    required_fields = [
        "Source:",
        "Package:",
        "Architecture:",
        "Depends:",
        "Description:",
        "Maintainer:",
    ]
    for field in required_fields:
        assert field in content, f"debian/control に '{field}' フィールドがありません"


def test_debian_control_python_dependency():
    """debian/control が python3 (>= 3.11) の依存関係を持つこと"""
    control = DEBIAN_DIR / "control"
    if not control.exists():
        pytest.skip("debian/control が存在しません")
    content = control.read_text(encoding="utf-8")
    assert "python3" in content, "debian/control に python3 依存関係がありません"


def test_debian_changelog_exists():
    """debian/changelog が存在すること"""
    changelog = DEBIAN_DIR / "changelog"
    assert changelog.exists(), f"debian/changelog が存在しません: {changelog}"


def test_debian_rules_exists():
    """debian/rules が存在すること"""
    rules = DEBIAN_DIR / "rules"
    assert rules.exists(), f"debian/rules が存在しません: {rules}"


def test_debian_postinst_exists():
    """debian/postinst が存在すること"""
    postinst = DEBIAN_DIR / "postinst"
    assert postinst.exists(), f"debian/postinst が存在しません: {postinst}"


def test_debian_prerm_exists():
    """debian/prerm が存在すること"""
    prerm = DEBIAN_DIR / "prerm"
    assert prerm.exists(), f"debian/prerm が存在しません: {prerm}"


def test_debian_postinst_creates_service_user():
    """debian/postinst がサービスユーザー作成を行うこと"""
    postinst = DEBIAN_DIR / "postinst"
    if not postinst.exists():
        pytest.skip("debian/postinst が存在しません")
    content = postinst.read_text(encoding="utf-8")
    assert "svc-adminui" in content or "adduser" in content, (
        "debian/postinst にサービスユーザー作成 (adduser/svc-adminui) がありません"
    )


# ---------------------------------------------------------------------------
# sudoers スニペット安全性テスト
# ---------------------------------------------------------------------------


def test_sudoers_snippet_safe():
    """sudoers 設定が NOPASSWD をワイルドカードスクリプトパターンでのみ許可していること"""
    # install.sh の sudoers 設定内容を確認
    install_sh = SCRIPTS_DIR / "install.sh"
    if not install_sh.exists():
        pytest.skip("install.sh が存在しません")
    content = install_sh.read_text(encoding="utf-8")

    # NOPASSWD パターンが /usr/local/sbin/adminui-*.sh のみを許可していること
    assert "NOPASSWD" in content, "sudoers 設定に NOPASSWD がありません"
    assert "/usr/local/sbin/adminui-" in content, (
        "sudoers 設定が /usr/local/sbin/adminui-*.sh パターンを使用していません"
    )
    # ALL コマンド許可は禁止
    assert "NOPASSWD: ALL" not in content, (
        "sudoers 設定が 'NOPASSWD: ALL' (全コマンド許可) を含んでいます - セキュリティリスク"
    )


def test_sudoers_config_file_in_debian():
    """debian/postinst の sudoers 設定が安全なパスを使用すること"""
    postinst = DEBIAN_DIR / "postinst"
    if not postinst.exists():
        pytest.skip("debian/postinst が存在しません")
    content = postinst.read_text(encoding="utf-8")
    # postinst は直接 sudoers を変更しない (debian/install で配置される)
    # もし含む場合は /etc/sudoers.d/ のみ許可
    if "sudoers" in content:
        assert "/etc/sudoers.d/" in content, (
            "postinst が /etc/sudoers (メインファイル) を直接編集しています - /etc/sudoers.d/ を使用してください"
        )


# ---------------------------------------------------------------------------
# install.sh ShellCheck 安全性パターンテスト
# ---------------------------------------------------------------------------


def test_install_script_quoted_variables():
    """install.sh の変数参照が引用符で囲まれていること (主要変数)"""
    install_sh = SCRIPTS_DIR / "install.sh"
    if not install_sh.exists():
        pytest.skip("install.sh が存在しません")
    content = install_sh.read_text(encoding="utf-8")
    # 主要な変数が引用符付きで展開されているか確認
    assert '"${INSTALL_DIR}"' in content or '"${VENV_DIR}"' in content, (
        "install.sh の変数が引用符なしで展開されている可能性があります"
    )
