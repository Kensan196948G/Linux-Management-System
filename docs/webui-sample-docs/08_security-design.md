# セキュリティ設計書

**文書番号**: WEBUI-SEC-001
**バージョン**: 1.0
**作成日**: 2026-02-25
**対象システム**: Linux管理 WebUI サンプルシステム

---

## 1. セキュリティ設計方針

### 1.1 基本方針

本システムはLinuxサーバーの管理操作を扱うため、以下の原則を最優先とする。

1. **最小権限の原則**: 必要最低限の権限のみ付与
2. **多層防御**: ネットワーク・認証・アプリケーション・OS の各層で防御
3. **デフォルト拒否**: 定義されていない操作はすべて拒否
4. **完全な証跡化**: 全操作を記録・保全し改ざんを防止
5. **fail-safe**: 異常時は安全側（操作拒否）にフォールバック

### 1.2 脅威モデル概要

| 脅威カテゴリ | 具体的脅威 | 対策 |
|------------|----------|------|
| 認証迂回 | セッションハイジャック | JWT + HTTPOnly Cookie, HTTPS強制 |
| 権限昇格 | ロール偽装・トークン改ざん | JWT署名検証・ロールチェック |
| コマンドインジェクション | 引数への悪意ある入力 | shell=False・入力バリデーション |
| XSS | スクリプト注入 | CSP・出力エスケープ |
| CSRF | 偽造リクエスト | CSRFトークン |
| 不正ログイン | ブルートフォース | レートリミット・アカウントロック |
| 内部不正 | 管理者による不正操作 | 二人操作・監査ログ・承認フロー |
| 情報漏洩 | ログ・エラー内容の露出 | 詳細エラーの非表示化 |

---

## 2. 認証設計

### 2.1 パスワード認証

| 項目 | 設計 |
|------|------|
| ハッシュアルゴリズム | bcrypt（cost factor: 12） |
| パスワードポリシー | 12文字以上・英大文字・英小文字・数字・記号各1文字以上 |
| 禁止パスワード | 辞書攻撃対象単語・過去3回のパスワードと同一禁止 |
| パスワード有効期限 | 90日（警告: 14日前から） |
| パスワードリセット | 管理者による手動リセットのみ（自動リセット不可） |

### 2.2 多要素認証（MFA）

| 項目 | 設計 |
|------|------|
| 方式 | TOTP（RFC 6238）準拠 |
| 互換アプリ | Google Authenticator, Authy, Microsoft Authenticator |
| コード有効期限 | 30秒 + ±1コード（前後1ステップ許容） |
| 強制適用 | Operator以上は必須 |
| バックアップコード | 8文字×10個（初回設定時生成・1回限り） |

### 2.3 セッション管理

```
JWT Access Token:
  - 有効期限: 1時間
  - ペイロード: user_id, username, role, jti
  - 署名: HMAC-SHA256（シークレットキー 256bit以上）

JWT Refresh Token:
  - 有効期限: 8時間
  - ローテーション: リフレッシュ時に新トークン発行・旧トークン無効化
  - 保存: HTTPOnly, Secure, SameSite=Strict Cookie

セッション無効化（いずれかの条件で即時）:
  - ログアウト操作
  - パスワード変更
  - ロール変更
  - アカウント無効化
  - 管理者による強制ログアウト
```

### 2.4 ブルートフォース対策

| 項目 | 設定 |
|------|------|
| 失敗許容回数 | 5回 |
| ロック時間 | 15分 |
| IPベースレートリミット | 10 req/min（ログインエンドポイント） |
| エラーメッセージ | 汎用（ユーザー名存在有無を明示しない） |

---

## 3. 認可設計（RBAC）

### 3.1 ロール定義

| ロール | レベル | 概要 |
|--------|--------|------|
| Viewer | 1 | 参照のみ |
| Operator | 2 | 許可リスト内の操作 |
| Approver | 3 | 危険操作の承認権限 |
| Admin | 4 | システム全権（2名以上必須） |

### 3.2 API権限マトリクス

| APIエンドポイント | Viewer | Operator | Approver | Admin |
|----------------|--------|----------|----------|-------|
| GET /status/* | ✅ | ✅ | ✅ | ✅ |
| GET /services/* | ✅ | ✅ | ✅ | ✅ |
| POST /services/*/action (restart) | ❌ | ✅ | ✅ | ✅ |
| POST /services/*/action (stop) | ❌ | 申請 | ✅ | ✅ |
| GET /logs/* | ✅ | ✅ | ✅ | ✅ |
| GET /audit/* | ❌ | ✅ | ✅ | ✅ |
| GET /users/* | ❌ | ✅ | ✅ | ✅ |
| POST /users/* | ❌ | ❌ | 申請 | ✅ |
| GET /approvals/* | ❌ | 自分のみ | ✅ | ✅ |
| PUT /approvals/*/approve | ❌ | ❌ | ✅ | ✅ |
| GET /settings/* | ❌ | ❌ | ❌ | ✅ |
| PUT /settings/* | ❌ | ❌ | ❌ | ✅ |

---

## 4. コマンドインジェクション対策

### 4.1 実装ルール（絶対遵守）

```python
# NG: 絶対禁止
subprocess.run(f"systemctl restart {service_name}", shell=True)
os.system(f"systemctl restart {service_name}")

# OK: 必ずリスト形式・shell=False
subprocess.run(
    ["sudo", "/usr/local/sbin/adminui-service-restart", service_name],
    shell=False,
    capture_output=True,
    timeout=30
)
```

### 4.2 入力バリデーション

```python
import re

ALLOWED_SERVICE_NAME = re.compile(r'^[a-zA-Z0-9\-_\.]{1,128}$')
FORBIDDEN_CHARS = re.compile(r'[;|&$()` ><*?{}\\[\]]')

def validate_service_name(name: str) -> bool:
    if not ALLOWED_SERVICE_NAME.match(name):
        raise ValueError("Invalid service name")
    if FORBIDDEN_CHARS.search(name):
        raise ValueError("Forbidden characters detected")
    # allowlist チェック
    if not is_in_allowlist(name):
        raise PermissionError("Service not in allowlist")
    return True
```

### 4.3 sudo / ラッパー設計

```bash
# /etc/sudoers.d/adminui
# 許可: ラッパースクリプト群のみ
svc-adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-*

# 禁止: 直接コマンド（sudoers に記載しない = 拒否）
# systemctl, journalctl, bash, sh 等は直接許可しない
```

---

## 5. Webセキュリティ対策

### 5.1 HTTPレスポンスヘッダー

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### 5.2 CSRF対策

- SPA の場合: `SameSite=Strict` Cookie + `Authorization` ヘッダー（二重送信Cookie不要）
- 非SPA の場合: CSRF トークン（フォームに埋め込み・サーバー側検証）

### 5.3 XSS対策

- Vue.js / React 等フレームワークの自動エスケープを活用
- `innerHTML` の直接使用禁止（`textContent` 使用）
- ユーザー入力はサーバーサイドでもエスケープ処理

---

## 6. 暗号化・機密情報管理

### 6.1 通信暗号化

| 項目 | 設定 |
|------|------|
| TLSバージョン | 1.2以上（1.0/1.1禁止） |
| 推奨暗号スイート | TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256 |
| 証明書更新 | 自動更新（Let's Encrypt / 社内CA） |
| HSTS | max-age=31536000; includeSubDomains |

### 6.2 機密情報の保管

| 情報 | 保管方法 |
|------|---------|
| JWTシークレットキー | 環境変数（`.env` ファイルをGit管理外） |
| データベースパスワード | 環境変数またはシークレット管理ツール |
| MFAシークレット | AES-256暗号化してDBに保存 |
| ユーザーパスワード | bcrypt（cost=12）ハッシュ |

---

## 7. 監査・インシデント対応

### 7.1 セキュリティ関連ログの記録

以下のイベントは必ず監査ログに記録する。

- ログイン成功・失敗
- ログアウト（手動・強制）
- 操作系API の全呼び出し
- 認証エラー・権限エラー
- ロール変更
- allowlist 変更
- 設定変更

### 7.2 インシデント検知

| 検知条件 | アクション |
|---------|----------|
| 10分以内に同一IPから50回以上の認証失敗 | IPブロック + 管理者アラート |
| 深夜帯（0時〜6時）の操作系API呼び出し | 管理者アラート |
| Admin権限での操作 | リアルタイム通知 |
| 異常な大量ログダウンロード | アラート + 一時停止 |

---

## 8. セキュリティレビューチェックリスト

開発フェーズごとに以下を確認する。

- [ ] shell=True の使用がないこと
- [ ] 全入力値のバリデーションが実装されていること
- [ ] sudo allowlist が最小限であること
- [ ] JWT シークレットが適切に管理されていること
- [ ] HTTPSが強制されていること
- [ ] 監査ログが改ざん不可能であること
- [ ] エラーメッセージに内部情報が含まれないこと
- [ ] 依存ライブラリに既知の脆弱性がないこと

---

*本文書はLinux管理WebUIサンプルシステムのセキュリティ設計を定めるものである。*
