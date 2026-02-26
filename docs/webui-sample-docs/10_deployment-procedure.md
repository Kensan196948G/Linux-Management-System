# デプロイ・リリース手順書

**文書番号**: WEBUI-DEP-001
**バージョン**: 1.0
**作成日**: 2026-02-25
**対象システム**: Linux管理 WebUI サンプルシステム

---

## 1. デプロイ概要

### 1.1 デプロイ方針

| 項目 | 内容 |
|------|------|
| デプロイ方式 | Blue/Green デプロイ（ダウンタイムゼロ目標） |
| リリース承認 | 情報システム部長の承認必須 |
| 作業時間 | 原則 平日 10:00〜17:00（緊急時を除く） |
| ロールバック | 前バージョンへの即時切り戻し可能 |
| 変更管理 | リリースノート・変更管理票の作成必須 |

### 1.2 環境一覧

| 環境名 | 用途 | URL |
|--------|------|-----|
| 開発環境 | 開発者個人環境 | `localhost:8000` |
| ステージング | 結合テスト・UAT | `https://stg-adminui.example.local` |
| 本番 | 実運用 | `https://adminui.example.local` |

---

## 2. 事前準備チェックリスト

リリース作業前に以下をすべて確認する。

### 2.1 コード・テスト確認

- [ ] 全ユニットテスト・統合テストが PASS していること
- [ ] E2Eテストが PASS していること
- [ ] セキュリティテスト（OWASP ZAP）でCritical/High ゼロであること
- [ ] コードレビューが完了し、Approve されていること
- [ ] `main` ブランチへのマージが完了していること

### 2.2 ドキュメント確認

- [ ] リリースノートが作成されていること
- [ ] 変更管理票（Change Request）が承認されていること
- [ ] ロールバック手順が確認されていること

### 2.3 インフラ確認

- [ ] ステージング環境での動作確認が完了していること
- [ ] 本番環境のディスク残量が十分であること（10GB以上）
- [ ] バックアップが最新であること（直近24時間以内）
- [ ] 監視・アラートが正常に動作していること

---

## 3. 本番デプロイ手順

### Step 1: バックアップ取得

```bash
# データベースバックアップ
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/var/backup/adminui

sudo -u adminui sqlite3 /opt/linux-mgmt-webui/data/adminui.db \
  ".backup ${BACKUP_DIR}/adminui_${DATE}.db"

# または PostgreSQL の場合
# pg_dump -U adminui adminui > ${BACKUP_DIR}/adminui_${DATE}.sql

echo "バックアップ完了: ${BACKUP_DIR}/adminui_${DATE}.db"

# 設定ファイルバックアップ
sudo cp -r /opt/linux-mgmt-webui/config ${BACKUP_DIR}/config_${DATE}

# ラッパースクリプトバックアップ
sudo cp -r /usr/local/sbin/adminui-* ${BACKUP_DIR}/wrappers_${DATE}/
```

### Step 2: リリースパッケージ展開

```bash
# リリースパッケージの取得（Git タグから）
RELEASE_TAG="v1.2.3"
DEPLOY_DIR="/opt/linux-mgmt-webui"
RELEASE_DIR="/opt/linux-mgmt-webui-${RELEASE_TAG}"

# 新バージョンをリリースディレクトリに展開
sudo git clone --branch ${RELEASE_TAG} \
  https://gitrepo.example.local/adminui.git \
  ${RELEASE_DIR}

# Python 依存関係インストール
cd ${RELEASE_DIR}/backend
sudo pip install -r requirements.txt --target ./vendor

# フロントエンドビルド
cd ${RELEASE_DIR}/frontend
npm ci
npm run build
```

### Step 3: ラッパースクリプト更新

```bash
# 新しいラッパースクリプトをコピー
sudo cp ${RELEASE_DIR}/wrappers/* /usr/local/sbin/adminui-*

# 権限設定（所有者: root, 実行権限: root のみ）
sudo chown root:root /usr/local/sbin/adminui-*
sudo chmod 700 /usr/local/sbin/adminui-*

# 確認
ls -la /usr/local/sbin/adminui-*
```

### Step 4: サービス切り替え（Blue/Green）

```bash
# 現行（Blue）環境を停止
sudo systemctl stop adminui-backend

# シンボリックリンクを新バージョン（Green）へ切り替え
sudo ln -sfn ${RELEASE_DIR} /opt/linux-mgmt-webui-current

# 環境設定ファイルをコピー（本番設定）
sudo cp /etc/adminui/production.env ${RELEASE_DIR}/backend/.env

# データベースマイグレーション（必要な場合）
cd ${RELEASE_DIR}/backend
sudo -u svc-adminui python manage.py migrate --check
sudo -u svc-adminui python manage.py migrate

# 新バージョンを起動
sudo systemctl start adminui-backend
sudo systemctl status adminui-backend
```

### Step 5: 動作確認

```bash
# ヘルスチェック
curl -s https://adminui.example.local/api/v1/health | jq .

# ログ確認（エラーなし）
sudo journalctl -u adminui-backend -n 50 --no-pager

# バージョン確認
curl -s https://adminui.example.local/api/v1/version | jq .
```

### Step 6: 最終確認

- [ ] ヘルスチェックエンドポイントが 200 を返すこと
- [ ] ダッシュボードが正常に表示されること
- [ ] ログインが正常に動作すること
- [ ] 主要機能（サービス一覧・ログ閲覧）が正常に動作すること
- [ ] 監視・アラートが正常に動作していること

---

## 4. ロールバック手順

### 4.1 即時ロールバック（15分以内）

```bash
# 新バージョンを停止
sudo systemctl stop adminui-backend

# シンボリックリンクを旧バージョンへ戻す
PREV_VERSION="v1.2.2"
sudo ln -sfn /opt/linux-mgmt-webui-${PREV_VERSION} /opt/linux-mgmt-webui-current

# ラッパースクリプトを旧バージョンへ戻す
sudo cp /var/backup/adminui/wrappers_${DATE}/* /usr/local/sbin/

# 旧バージョンを起動
sudo systemctl start adminui-backend
sudo systemctl status adminui-backend
```

### 4.2 データベースロールバック（必要な場合）

```bash
# !! 注意: 監査ログは追記専用のため、ロールバック対象外 !!

# DBロールバック（マイグレーションが失敗した場合）
sudo systemctl stop adminui-backend
sudo -u svc-adminui python manage.py migrate --reverse
sudo cp ${BACKUP_DIR}/adminui_${DATE}.db /opt/linux-mgmt-webui/data/adminui.db
sudo systemctl start adminui-backend
```

---

## 5. 緊急時対応

### 5.1 緊急リリース手順

1. 緊急変更申請を情報システム部長に提出
2. 承認後、本手順に従って作業実施
3. 作業ログを詳細に記録
4. リリース後に事後報告書を提出

### 5.2 本番障害時の対応フロー

```
本番障害検知
  ↓
影響範囲確認（5分以内）
  ↓
切り戻し判断
  ├── 軽微 → ホットフィックス適用（最大30分）
  └── 重大 → 即時ロールバック（15分以内）
  ↓
復旧確認・報告
```

---

## 6. デプロイ後の確認項目

| 確認項目 | 担当 | 期限 |
|---------|------|------|
| 全機能の動作確認 | 開発担当 | デプロイ後1時間 |
| 監視アラート確認 | 運用担当 | デプロイ後30分 |
| パフォーマンス確認 | 開発担当 | デプロイ後2時間 |
| 利用者への変更通知 | 担当PM | デプロイ後即時 |
| リリースノート公開 | 担当PM | デプロイ当日 |

---

*本文書はLinux管理WebUIサンプルシステムのデプロイ・リリース手順を定めるものである。*
