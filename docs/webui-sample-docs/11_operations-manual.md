# 運用・保守設計書

**文書番号**: WEBUI-OPS-001
**バージョン**: 1.0
**作成日**: 2026-02-25
**対象システム**: Linux管理 WebUI サンプルシステム

---

## 1. 運用体制

### 1.1 運用担当者

| 役割 | 担当 | 連絡先 | 業務時間 |
|------|------|--------|---------|
| システム管理者 | 情報システム部 A担当 | ext.1234 | 平日 9:00-18:00 |
| 夜間緊急対応 | オンコール担当 | 携帯電話 | 18:00-翌9:00 |
| セキュリティ担当 | CISO / セキュリティチーム | ext.5678 | 平日 9:00-18:00 |
| 開発担当 | ITシステム開発チーム | ext.2345 | 平日 9:00-18:00 |

### 1.2 エスカレーション

```
Lv.1（軽微）: 運用担当者 → 自己対応（1時間以内）
Lv.2（中程度）: 運用担当者 → システム管理者（30分以内）
Lv.3（重大）: システム管理者 → 部長・開発担当 → 即時対応
Lv.4（セキュリティインシデント）: → CISO → 経営層報告
```

---

## 2. 日常運用手順

### 2.1 日次確認作業（毎日 9:00）

```bash
# 1. サービス稼働確認
systemctl status adminui-backend adminui-frontend nginx

# 2. ヘルスチェック確認
curl -s https://adminui.example.local/api/v1/health | jq .

# 3. ディスク使用量確認
df -h /opt/linux-mgmt-webui/

# 4. 前日のエラーログ確認
sudo journalctl -u adminui-backend --since "yesterday" \
  --until "today" -p err --no-pager

# 5. バックアップ確認
ls -la /var/backup/adminui/ | head -5
```

### 2.2 週次確認作業（毎週月曜日）

- [ ] 監査ログの異常アクセスチェック（レポート出力・確認）
- [ ] ディスク使用量の推移確認
- [ ] 依存ライブラリの脆弱性情報確認（pip audit / npm audit）
- [ ] ログローテーション正常動作確認
- [ ] バックアップ復元テスト（データ整合性確認）

### 2.3 月次確認作業

- [ ] 全ユーザーアカウントの棚卸し（不要アカウントの無効化）
- [ ] sudo allowlist の見直し
- [ ] セキュリティパッチの適用検討
- [ ] 操作ログの監査レポート出力・保管
- [ ] パフォーマンス推移レポート作成

---

## 3. 定期メンテナンス

### 3.1 計画停止手順

```bash
# 事前: 利用者へ停止予告（1週間前・前日・当日）

# 1. メンテナンスモード有効化
sudo touch /opt/linux-mgmt-webui/maintenance.flag
# → フロントエンドにメンテナンス画面を表示

# 2. 実行中ジョブの完了待機（最大5分）
sleep 300

# 3. サービス停止
sudo systemctl stop adminui-backend nginx

# 4. メンテナンス作業実施

# 5. サービス起動
sudo systemctl start nginx adminui-backend

# 6. 動作確認
curl -s https://adminui.example.local/api/v1/health

# 7. メンテナンスモード解除
sudo rm /opt/linux-mgmt-webui/maintenance.flag
```

### 3.2 ログローテーション設定

```
# /etc/logrotate.d/adminui
/opt/linux-mgmt-webui/logs/app.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 640 svc-adminui svc-adminui
    postrotate
        systemctl kill -s USR1 adminui-backend
    endscript
}

# 監査ログは別扱い（圧縮のみ・削除禁止）
/opt/linux-mgmt-webui/logs/audit.log {
    monthly
    rotate 120
    compress
    delaycompress
    nocreate
    nomail
    nosharedscripts
}
```

---

## 4. バックアップ・リストア

### 4.1 バックアップ仕様

| バックアップ種別 | 頻度 | 保管期間 | 保管場所 |
|---------------|------|---------|---------|
| DBフルバックアップ | 日次 | 30日 | 別ボリューム |
| 設定ファイル | 日次 | 30日 | 別ボリューム |
| 監査ログアーカイブ | 月次 | 7年 | テープ/オフサイト |
| ラッパースクリプト | 変更時 | 10世代 | Git |

### 4.2 バックアップ自動化スクリプト

```bash
#!/bin/bash
# /usr/local/sbin/adminui-backup.sh
# cron: 0 2 * * * /usr/local/sbin/adminui-backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/var/backup/adminui"
RETENTION_DAYS=30

# DB バックアップ
sqlite3 /opt/linux-mgmt-webui/data/adminui.db \
  ".backup ${BACKUP_DIR}/db/adminui_${DATE}.db"

# 設定ファイルバックアップ
tar czf "${BACKUP_DIR}/config/config_${DATE}.tar.gz" \
  /opt/linux-mgmt-webui/config/ \
  /etc/adminui/

# 古いバックアップの削除（retention 以前）
find "${BACKUP_DIR}/db" -name "*.db" \
  -mtime +${RETENTION_DAYS} -delete
find "${BACKUP_DIR}/config" -name "*.tar.gz" \
  -mtime +${RETENTION_DAYS} -delete

echo "[$(date)] Backup completed successfully" >> /var/log/adminui-backup.log
```

### 4.3 リストア手順

```bash
# 1. サービス停止
sudo systemctl stop adminui-backend

# 2. 現在のDBをバックアップ（安全策）
sudo cp /opt/linux-mgmt-webui/data/adminui.db \
  /tmp/adminui_before_restore.db

# 3. バックアップからリストア
TARGET_BACKUP="/var/backup/adminui/db/adminui_20260225_020000.db"
sudo cp ${TARGET_BACKUP} /opt/linux-mgmt-webui/data/adminui.db
sudo chown svc-adminui:svc-adminui /opt/linux-mgmt-webui/data/adminui.db
sudo chmod 600 /opt/linux-mgmt-webui/data/adminui.db

# 4. データ整合性確認
sqlite3 /opt/linux-mgmt-webui/data/adminui.db "PRAGMA integrity_check;"

# 5. サービス起動
sudo systemctl start adminui-backend
```

---

## 5. 監視・アラート設定

### 5.1 Prometheus メトリクス

エンドポイント: `GET /metrics`（localhost のみアクセス可）

| メトリクス名 | 説明 | アラート閾値 |
|-----------|------|------------|
| `adminui_request_duration_seconds` | API応答時間 | p95 > 5s |
| `adminui_active_sessions` | アクティブセッション数 | > 25 |
| `adminui_login_failures_total` | ログイン失敗累計 | 5分で > 10回 |
| `adminui_wrapper_exec_duration` | ラッパー実行時間 | > 60s |
| `adminui_audit_log_size_bytes` | 監査ログサイズ | > 1GB |

### 5.2 アラートルール例（Alertmanager）

```yaml
groups:
- name: adminui-alerts
  rules:
  - alert: AdminUIHighErrorRate
    expr: rate(adminui_http_errors_total[5m]) > 0.1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "WebUI エラーレート上昇"

  - alert: AdminUILoginAttack
    expr: rate(adminui_login_failures_total[5m]) > 2
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "ブルートフォース攻撃の可能性"
```

---

## 6. 障害対応手順

### 6.1 サービス起動失敗時

```bash
# ログ確認
sudo journalctl -u adminui-backend -n 100 --no-pager

# 設定ファイル確認
sudo -u svc-adminui python -c "from backend.core.config import settings; print('OK')"

# ポート使用確認
sudo ss -tlnp | grep 8000

# 強制再起動
sudo systemctl restart adminui-backend
```

### 6.2 データベース破損時

```bash
# 整合性チェック
sqlite3 /opt/linux-mgmt-webui/data/adminui.db "PRAGMA integrity_check;"

# 破損確認後 → バックアップからリストア（4.3参照）
```

### 6.3 セキュリティインシデント発生時

1. **即時対応**: システムをメンテナンスモードへ（サービス停止）
2. **ログ保全**: 現時点のログを全コピー（改ざん防止）
3. **報告**: CISO・部長へ即時報告
4. **調査**: セキュリティチームによる原因調査
5. **対策適用**: 修正後、セキュリティレビュー経由でリリース

---

*本文書はLinux管理WebUIサンプルシステムの運用・保守設計を定めるものである。*
