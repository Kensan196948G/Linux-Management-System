# メニュー日本語化実装ガイド

## 📋 概要

本ドキュメントは、Linux Management System のサイドメニューを日本語化するための実装ガイドです。

## 🗂️ 成果物ファイル

| ファイルパス | 説明 |
|------------|------|
| `/mnt/LinuxHDD/Linux-Management-Systm/frontend/locales/menu-ja.json` | 日本語マッピングデータ（JSON） |
| `/mnt/LinuxHDD/Linux-Management-Systm/frontend/js/menu-i18n.js` | 国際化ユーティリティ（JavaScript） |
| `/mnt/LinuxHDD/Linux-Management-Systm/docs/menu-i18n-guide.md` | 本実装ガイド |

## 📊 メニュー項目マッピング一覧

### トップレベルメニュー

| 英語 | 日本語 |
|------|--------|
| Dashboard | ダッシュボード |
| Services | サービス管理 |
| Running Processes | 実行中プロセス |

### カテゴリ

| 英語 | 日本語 |
|------|--------|
| Linux Management System | Linux管理システム |
| System | システム |
| System Logs | システムログ |
| Servers | サーバー |
| Networking | ネットワーク |
| Hardware | ハードウェア |
| Cluster / Tools | クラスタ/ツール |

### サブメニュー項目（詳細）

#### Linux Management System

| 英語 | 日本語 |
|------|--------|
| System Configuration | システム設定 |
| System Users | システムユーザー |
| System Servers | システムサーバー |
| System Actions Log | システム操作ログ |
| System Themes | システムテーマ |
| System Modules | システムモジュール |

#### System

| 英語 | 日本語 |
|------|--------|
| Bootup and Shutdown | 起動・シャットダウン |
| Disk and Network Filesystems | ディスク・ネットワークファイルシステム |
| Disk Quotas | ディスククォータ |
| Local Disk | ローカルディスク |
| Users and Groups | ユーザー・グループ |
| Software Package Updates | ソフトウェアパッケージ更新 |
| Cron Jobs | Cronジョブ |
| Running Processes | 実行中プロセス |

#### System Logs

| 英語 | 日本語 |
|------|--------|
| System Logs | システムログ |
| Kernel Messages | カーネルメッセージ |
| Auth Logs | 認証ログ |
| Application Logs | アプリケーションログ |

#### Servers

| 英語 | 日本語 |
|------|--------|
| Apache Webserver | Apache Webサーバー |
| BIND DNS Server | BIND DNSサーバー |
| Postfix / Sendmail | Postfix / Sendmail |
| MySQL / MariaDB | MySQL / MariaDB |
| PostgreSQL | PostgreSQL |
| SSH Server | SSHサーバー |
| ProFTPD / WU-FTP | ProFTPD / WU-FTP |
| Squid Proxy | Squidプロキシ |
| DHCP Server | DHCPサーバー |

#### Networking

| 英語 | 日本語 |
|------|--------|
| Linux Firewall | Linuxファイアウォール |
| Network Configuration | ネットワーク設定 |
| Routing and Gateways | ルーティング・ゲートウェイ |
| Netstat | ネットワーク統計 |
| Bandwidth Monitoring | 帯域幅モニタリング |

#### Hardware

| 英語 | 日本語 |
|------|--------|
| Partitions on Local Disks | ローカルディスクパーティション |
| System Time | システム時刻 |
| SMART Drive Status | SMARTドライブ状態 |
| Sensors (lm-sensors) | センサー (lm-sensors) |

#### Cluster / Tools

| 英語 | 日本語 |
|------|--------|
| Cluster SSH | クラスタSSH |
| Cluster Cron Jobs | クラスタCronジョブ |
| Cluster Users | クラスタユーザー |
| Command Shell | コマンドシェル |
| File Manager | ファイルマネージャー |
| Scheduled Commands | スケジュールコマンド |
| Custom Commands | カスタムコマンド |

## 🔧 実装方法

### オプション1: 自動翻訳スクリプト使用（推奨）

`dashboard.html` の `<head>` セクションに以下を追加:

```html
<!-- 国際化ユーティリティ -->
<script src="../js/menu-i18n.js"></script>
```

これにより、ページ読み込み時に自動的にメニューが日本語化されます。

### オプション2: 手動でHTMLを書き換え

`dashboard.html` の各メニュー項目を直接日本語に書き換えます。

**変更例**:

```html
<!-- 変更前 -->
<div class="menu-item" onclick="location.href='processes.html'">
    <span class="menu-item-icon">⚡</span>
    <span>Running Processes</span>
</div>

<!-- 変更後 -->
<div class="menu-item" onclick="location.href='processes.html'">
    <span class="menu-item-icon">⚡</span>
    <span>実行中プロセス</span>
</div>
```

## 🧪 テスト方法

### 1. ローカルサーバー起動

```bash
cd /mnt/LinuxHDD/Linux-Management-Systm/frontend
python3 -m http.server 8080
```

### 2. ブラウザで確認

```
http://localhost:8080/dev/dashboard.html
```

### 3. 確認ポイント

- ✅ 全メニュー項目が日本語で表示されているか
- ✅ カテゴリタイトルが日本語になっているか
- ✅ サブメニュー項目が日本語になっているか
- ✅ ステータスバッジが日本語になっているか
- ✅ サイドバーフッター（ユーザー、ロール、ログアウト）が日本語になっているか

### 4. ブラウザコンソールで確認

開発者ツールのコンソールに以下が表示されることを確認:

```
Menu translation completed
```

翻訳が見つからないキーがある場合は警告が表示されます:

```
Translation not found for key: "Unknown Item"
```

## 🔄 新規メニュー項目の追加方法

### 1. `menu-ja.json` に翻訳を追加

```json
{
  "submenu_items": {
    "system": {
      "New Feature": "新機能"
    }
  }
}
```

### 2. `dashboard.html` にメニュー項目を追加

```html
<div class="submenu-item" onclick="showPage('new-feature')">
    <div class="submenu-item-name">New Feature</div>
    <div class="submenu-item-badge">実装済み</div>
</div>
```

### 3. `menu-i18n.js` を読み込んでいれば自動翻訳される

ページ読み込み時に自動的に「新機能」と表示されます。

## 📝 使用例（プログラムから翻訳を取得）

### JavaScript から翻訳を取得

```javascript
// MenuI18n インスタンスはグローバルで利用可能
const translatedText = menuI18n.translate('Running Processes');
console.log(translatedText); // "実行中プロセス"

// カテゴリ指定で翻訳を取得
const translatedText2 = menuI18n.translate('Users and Groups', 'system');
console.log(translatedText2); // "ユーザー・グループ"

// 特定カテゴリの全サブメニューアイテムを取得
const systemItems = menuI18n.getSubmenuItems('system');
console.log(systemItems);
/*
{
  "Bootup and Shutdown": "起動・シャットダウン",
  "Disk and Network Filesystems": "ディスク・ネットワークファイルシステム",
  ...
}
*/
```

## 🌐 将来の多言語対応

現在は日本語のみ対応していますが、以下の手順で他言語を追加可能:

### 1. 新しいロケールファイルを作成

```bash
# 英語版
/mnt/LinuxHDD/Linux-Management-Systm/frontend/locales/menu-en.json

# 中国語版
/mnt/LinuxHDD/Linux-Management-Systm/frontend/locales/menu-zh.json
```

### 2. `menu-i18n.js` の `getAvailableLocales()` を更新

```javascript
getAvailableLocales() {
    return ['ja', 'en', 'zh'];
}
```

### 3. ロケール切り替え機能を追加

```javascript
// ロケールを切り替える
await menuI18n.loadTranslations('en');
menuI18n.translateMenuDOM();
```

## 🔒 セキュリティ考慮事項

### XSS対策

- メニュー項目の翻訳はJSONファイルから読み込まれます
- `textContent` プロパティを使用してXSSを防止しています
- ユーザー入力を翻訳キーとして使用しないでください

### CSP（Content Security Policy）対応

翻訳データはJSON形式で提供され、`fetch()` APIで読み込まれます。CSPで `connect-src` に `/locales/` を許可してください。

```http
Content-Security-Policy: connect-src 'self' /locales/;
```

## 📚 参考資料

- [CLAUDE.md - プロジェクト仕様](/mnt/LinuxHDD/Linux-Management-Systm/CLAUDE.md)
- [要件定義書_詳細設計仕様書.md](/mnt/LinuxHDD/Linux-Management-Systm/docs/要件定義書_詳細設計仕様書.md)
- [dashboard.html](/mnt/LinuxHDD/Linux-Management-Systm/frontend/dev/dashboard.html)

## 🎯 今後の課題

- [ ] ユーザー設定でロケールを保存・復元
- [ ] ページタイトル（`<h2 id="page-title">`）の翻訳対応
- [ ] 動的に生成されるメニュー項目の翻訳対応
- [ ] 翻訳ファイルのキャッシュ戦略
- [ ] 翻訳の完全性チェックツール（未翻訳キー検出）

---

**作成日**: 2026-02-06
**作成者**: @menu-translator (Claude SubAgent)
**バージョン**: 1.0.0
