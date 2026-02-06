# サイドメニュー構造再編成設計書

**作成日**: 2026-02-06
**ステータス**: 設計完了（実装待ち）

---

## 📋 設計目標

1. **階層の統一**: トップレベルとカテゴリの明確な分離
2. **拡張性**: 100+モジュール対応可能な構造
3. **セキュリティ統制**: システム設定カテゴリの新設
4. **Webmin互換**: 標準的なカテゴリ構成を踏襲

---

## 🎯 新しいメニュー構造

### トップレベル（非折りたたみ）

```
📊 ダッシュボード               [常に表示]
```

### カテゴリ（アコーディオン）

#### 1. ⚙️ Linux Management System
**用途**: システム全体の統制・管理機能

```
⚙️ Linux Management System
  ├─ System Configuration      [計画中]
  ├─ System Users              [計画中]
  ├─ System Servers            [実装済み] ※サービス管理
  ├─ System Actions Log        [実装済み] ※監査ログ
  ├─ System Themes             [計画中]
  └─ System Modules            [計画中]
```

#### 2. 💻 System
**用途**: OS基本機能の管理

```
💻 System
  ├─ Bootup and Shutdown           [v0.2]
  ├─ Disk and Network Filesystems  [v0.2]
  ├─ Disk Quotas                   [v0.3]
  ├─ Local Disk                    [実装済み]
  ├─ Users and Groups              [v0.2]
  ├─ Software Package Updates      [v0.3]
  ├─ Cron Jobs                     [v0.2]
  └─ Running Processes             [実装済み]
```

**変更点**:
- 「サービス管理」を削除（LMSカテゴリに統合）
- Running Processesをこのカテゴリのサブメニューに配置

#### 3. 📜 System Logs
**用途**: システムログの閲覧・検索

```
📜 System Logs
  ├─ System Logs          [実装済み]
  ├─ Kernel Messages      [v0.2]
  ├─ Auth Logs            [v0.2]
  └─ Application Logs     [v0.3]
```

#### 4. 🖥️ Servers
**用途**: アプリケーションサーバー管理

```
🖥️ Servers
  ├─ Apache Webserver      [v0.3]
  ├─ BIND DNS Server       [v0.4]
  ├─ Postfix / Sendmail    [v0.4]
  ├─ MySQL / MariaDB       [v0.3]
  ├─ PostgreSQL            [v0.3]
  ├─ SSH Server            [v0.2]
  ├─ ProFTPD / WU-FTP      [v0.4]
  ├─ Squid Proxy           [v0.4]
  └─ DHCP Server           [v0.4]
```

#### 5. 🌐 Networking
**用途**: ネットワーク設定・監視

```
🌐 Networking
  ├─ Linux Firewall            [サンプル]
  ├─ Network Configuration     [サンプル]
  ├─ Routing and Gateways      [サンプル]
  ├─ Netstat                   [サンプル]
  └─ Bandwidth Monitoring      [サンプル]
```

#### 6. 🔧 Hardware
**用途**: ハードウェア監視・設定

```
🔧 Hardware
  ├─ Partitions on Local Disks  [サンプル]
  ├─ System Time                [サンプル]
  ├─ SMART Drive Status         [サンプル]
  └─ Sensors (lm-sensors)       [サンプル]
```

#### 7. 🔗 Cluster / Tools
**用途**: クラスタ管理・ユーティリティ

```
🔗 Cluster / Tools
  ├─ Cluster SSH            [v0.5]
  ├─ Cluster Cron Jobs      [v0.5]
  ├─ Cluster Users          [v0.5]
  ├─ Command Shell          [禁止] ※セキュリティ上削除
  ├─ File Manager           [v0.4]
  ├─ Scheduled Commands     [v0.3]
  └─ Custom Commands        [v0.3]
```

#### 8. ⚡ System Settings（新規カテゴリ）
**用途**: システム統制・セキュリティ設定

```
⚡ System Settings
  ├─ User Management           [v0.2] ※ユーザー・ロール管理
  ├─ Security Settings         [v0.3] ※セキュリティポリシー設定
  ├─ Audit Log Settings        [v0.2] ※監査ログ保存期間・通知
  ├─ Notification Settings     [v0.3] ※メール・Slack通知
  ├─ Backup Settings           [v0.4] ※バックアップスケジュール
  ├─ System Information        [実装済み] ※現在のダッシュボード情報
  └─ About / License           [v0.2] ※バージョン情報
```

---

## 📊 変更点サマリー

### 削除項目

| 項目 | 場所 | 理由 |
|------|------|------|
| サービス管理（トップレベル） | トップレベル | LMSカテゴリに統合 |
| Running Processes（トップレベル） | トップレベル | Systemカテゴリに移動 |

### 追加項目

| 項目 | 場所 | 優先度 |
|------|------|--------|
| System Settings カテゴリ | 新規カテゴリ | v0.2 |
| User Management | System Settings | v0.2 |
| Security Settings | System Settings | v0.3 |
| Audit Log Settings | System Settings | v0.2 |

### 移動項目

| 項目 | 移動前 | 移動後 |
|------|--------|--------|
| Running Processes | トップレベル | System > Running Processes |

---

## 🎨 HTMLマークアップ設計

### トップレベル（ダッシュボードのみ）

```html
<nav class="sidebar-menu">
    <!-- ダッシュボード -->
    <div class="menu-item active" onclick="showPage('dashboard')">
        <span class="menu-item-icon">📊</span>
        <span>ダッシュボード</span>
    </div>

    <!-- カテゴリはここから -->
</nav>
```

### カテゴリ例：Linux Management System

```html
<!-- Linux Management System カテゴリ -->
<div class="accordion-item">
    <div class="accordion-header" onclick="toggleAccordion(this)">
        <div class="accordion-title">
            <span>⚙️</span>
            <span>Linux Management System</span>
        </div>
        <span class="accordion-icon">▼</span>
    </div>
    <div class="accordion-content">
        <div class="accordion-submenu">
            <div class="submenu-item disabled">
                <div class="submenu-item-name">System Configuration</div>
                <div class="submenu-item-badge">計画中</div>
            </div>
            <div class="submenu-item disabled">
                <div class="submenu-item-name">System Users</div>
                <div class="submenu-item-badge">計画中</div>
            </div>
            <div class="submenu-item" onclick="showPage('services')">
                <div class="submenu-item-name">System Servers</div>
                <div class="submenu-item-badge">実装済み</div>
            </div>
            <div class="submenu-item" onclick="showPage('audit-log')">
                <div class="submenu-item-name">System Actions Log</div>
                <div class="submenu-item-badge">実装済み</div>
            </div>
            <div class="submenu-item disabled">
                <div class="submenu-item-name">System Themes</div>
                <div class="submenu-item-badge">計画中</div>
            </div>
            <div class="submenu-item disabled">
                <div class="submenu-item-name">System Modules</div>
                <div class="submenu-item-badge">計画中</div>
            </div>
        </div>
    </div>
</div>
```

### カテゴリ例：System Settings（新規）

```html
<!-- System Settings カテゴリ（新規） -->
<div class="accordion-item">
    <div class="accordion-header" onclick="toggleAccordion(this)">
        <div class="accordion-title">
            <span>⚡</span>
            <span>System Settings</span>
        </div>
        <span class="accordion-icon">▼</span>
    </div>
    <div class="accordion-content">
        <div class="accordion-submenu">
            <div class="submenu-item disabled">
                <div class="submenu-item-name">User Management</div>
                <div class="submenu-item-badge">v0.2</div>
            </div>
            <div class="submenu-item disabled">
                <div class="submenu-item-name">Security Settings</div>
                <div class="submenu-item-badge">v0.3</div>
            </div>
            <div class="submenu-item disabled">
                <div class="submenu-item-name">Audit Log Settings</div>
                <div class="submenu-item-badge">v0.2</div>
            </div>
            <div class="submenu-item disabled">
                <div class="submenu-item-name">Notification Settings</div>
                <div class="submenu-item-badge">v0.3</div>
            </div>
            <div class="submenu-item disabled">
                <div class="submenu-item-name">Backup Settings</div>
                <div class="submenu-item-badge">v0.4</div>
            </div>
            <div class="submenu-item" onclick="showPage('system-info')">
                <div class="submenu-item-name">System Information</div>
                <div class="submenu-item-badge">実装済み</div>
            </div>
            <div class="submenu-item disabled">
                <div class="submenu-item-name">About / License</div>
                <div class="submenu-item-badge">v0.2</div>
            </div>
        </div>
    </div>
</div>
```

---

## 🔄 移行計画

### Phase 1: 構造変更（即座に実施可能）

1. **トップレベルから削除**:
   - サービス管理（既にLMSカテゴリに存在）
   - Running Processes（Systemカテゴリに移動）

2. **カテゴリの更新**:
   - System カテゴリに「Running Processes」を追加

3. **新規カテゴリの追加**:
   - System Settings カテゴリを追加（サブメニューは「計画中」）

### Phase 2: System Settings 実装（v0.2〜v0.4）

| サブメニュー | 実装時期 | 依存関係 |
|------------|---------|---------|
| User Management | v0.2 | ユーザーCRUD API |
| Audit Log Settings | v0.2 | 監査ログAPI拡張 |
| System Information | v0.1 | 既存ダッシュボード移植 |
| Security Settings | v0.3 | セキュリティポリシーAPI |
| Notification Settings | v0.3 | 通知API |
| Backup Settings | v0.4 | バックアップAPI |
| About / License | v0.2 | 静的ページ |

---

## 🎯 実装時の注意点

### セキュリティ

```python
# System Settings の各機能は Admin ロールのみアクセス可能
@router.get("/api/settings/security")
async def get_security_settings(
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    # ...
```

### アイコン選定

| カテゴリ | アイコン | 理由 |
|---------|---------|------|
| System Settings | ⚡ | 設定・統制を象徴 |
| Linux Management System | ⚙️ | 管理機能全般 |
| System | 💻 | OS基本機能 |

### アクセシビリティ

- 各メニュー項目に `aria-label` 属性を追加
- キーボードナビゲーション対応（矢印キー）
- スクリーンリーダー対応

---

## 📝 完成後のメニュー構造（全体図）

```
🖥️ Linux管理運用
├─ 📊 ダッシュボード ────────────────── [トップレベル]
│
├─ ⚙️ Linux Management System ────── [カテゴリ]
│   ├─ System Configuration
│   ├─ System Users
│   ├─ System Servers ★実装済み
│   ├─ System Actions Log ★実装済み
│   ├─ System Themes
│   └─ System Modules
│
├─ 💻 System ──────────────────────── [カテゴリ]
│   ├─ Bootup and Shutdown
│   ├─ Disk and Network Filesystems
│   ├─ Disk Quotas
│   ├─ Local Disk ★実装済み
│   ├─ Users and Groups
│   ├─ Software Package Updates
│   ├─ Cron Jobs
│   └─ Running Processes ★実装済み ←移動
│
├─ 📜 System Logs ─────────────────── [カテゴリ]
│   ├─ System Logs ★実装済み
│   ├─ Kernel Messages
│   ├─ Auth Logs
│   └─ Application Logs
│
├─ 🖥️ Servers ─────────────────────── [カテゴリ]
│   ├─ Apache Webserver
│   ├─ BIND DNS Server
│   ├─ MySQL / MariaDB
│   ├─ PostgreSQL
│   └─ ...
│
├─ 🌐 Networking ──────────────────── [カテゴリ]
│   ├─ Linux Firewall
│   ├─ Network Configuration
│   └─ ...
│
├─ 🔧 Hardware ────────────────────── [カテゴリ]
│   ├─ Partitions on Local Disks
│   ├─ SMART Drive Status
│   └─ ...
│
├─ 🔗 Cluster / Tools ─────────────── [カテゴリ]
│   ├─ Cluster SSH
│   ├─ File Manager
│   └─ ...
│
└─ ⚡ System Settings ─────────────── [カテゴリ・新規]
    ├─ User Management
    ├─ Security Settings
    ├─ Audit Log Settings
    ├─ Notification Settings
    ├─ Backup Settings
    ├─ System Information ★実装済み
    └─ About / License
```

---

## ✅ 承認・レビュー

- [ ] @team-lead 承認
- [ ] @arch-reviewer セキュリティレビュー
- [ ] @code-implementer 実装可能性確認

---

**📌 この設計は team-lead の承認後、frontend/dev/dashboard.html に反映されます。**
