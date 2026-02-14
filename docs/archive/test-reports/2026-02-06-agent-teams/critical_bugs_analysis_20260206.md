# プロセス管理画面 - 重大バグ詳細分析レポート

**作成日**: 2026-02-06
**分析者**: processes-tester
**優先度**: 🔴 **CRITICAL**

---

## 🚨 バグサマリー

| ID | 重要度 | 問題 | 影響範囲 | 状態 |
|----|--------|------|---------|------|
| **#1** | 🔴 **HIGH** | CPU/Memory パーセント計算の誤り | 全プロセス表示 | 未修正 |
| **#3** | 🔴 **HIGH** | フィルタパラメータ名の不一致 | ユーザーフィルタ機能 | 未修正 |
| **#4** | 🔴 **CRITICAL** | モデルフィールド名の3重不一致 | プロセス詳細表示 | 未修正 |

---

## 🔴 バグ#1: CPU/Memory パーセント計算の誤り

### 問題の詳細

**ファイル**: `/mnt/LinuxHDD/Linux-Management-Systm/frontend/js/processes.js` (178-203行)

**誤ったコード**:
```javascript
// 178-181行
const cpuPercent = proc.cpu_percent / 10.0;  // ❌ 間違い！
cpuCell.textContent = cpuPercent.toFixed(1);

// 192-195行
const memPercent = proc.mem_percent / 10.0;  // ❌ 間違い！
memCell.textContent = memPercent.toFixed(1);
```

**コメントの主張**:
```javascript
// ps aux returns integer in 0.1% units, convert to percentage
```

### 実際の仕様確認

**Wrapper Script**: `/mnt/LinuxHDD/Linux-Management-Systm/wrappers/adminui-processes.sh` (323-324行)

```bash
CPU=$(echo "$line" | awk '{print $3}')  # ps aux の %CPU カラム
MEM=$(echo "$line" | awk '{print $4}')  # ps aux の %MEM カラム
```

**ps aux の出力例**:
```
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root         1  0.0  0.4 168652 13420 ?        Ss   Jan01   0:02 /sbin/init
www-data  1234 10.5  2.3 234560 78900 ?        S    12:00   0:15 nginx: worker
```

**事実**:
- `ps aux` の `%CPU` と `%MEM` カラムは**既にパーセント値**です
- 値の範囲: 0.0 ~ 100.0（例: 10.5 = 10.5%）
- 整数ではなく**浮動小数点数**です

### 影響

| 実際のCPU使用率 | 表示される値 | 誤差 |
|----------------|-------------|------|
| 0.1%           | 0.01%       | **90%減** |
| 1.0%           | 0.1%        | **90%減** |
| 10.0%          | 1.0%        | **90%減** |
| 50.0%          | 5.0%        | **90%減** |
| 100.0%         | 10.0%       | **90%減** |

**ユーザーへの影響**:
- ✅ 高CPU/高メモリのハイライト（50%以上）が機能しない
- ✅ CPU使用率カラーリング（緑/オレンジ/赤）の閾値が誤る
- ✅ ユーザーが誤った情報で判断する
- ✅ トラブルシューティングが困難になる

### 修正コード

**修正前**:
```javascript
// ❌ 誤り
const cpuPercent = proc.cpu_percent / 10.0;
const memPercent = proc.mem_percent / 10.0;
```

**修正後**:
```javascript
// ✅ 正しい
const cpuPercent = proc.cpu_percent;  // 既にパーセント値
const memPercent = proc.mem_percent;  // 既にパーセント値
```

**修正箇所**:
- 178行目: `const cpuPercent = proc.cpu_percent;`
- 192行目: `const memPercent = proc.mem_percent;`
- 296-297行（プロセス詳細モーダル）: 除算を削除

**修正後のコード**:
```javascript
// 178-189行
const cpuCell = document.createElement('td');
cpuCell.className = 'cpu-usage';
const cpuPercent = proc.cpu_percent;  // ✅ 修正
cpuCell.textContent = cpuPercent.toFixed(1);
if (cpuPercent < 10) {
    cpuCell.classList.add('cpu-low');
} else if (cpuPercent < 50) {
    cpuCell.classList.add('cpu-medium');
} else {
    cpuCell.classList.add('cpu-high');
}
row.appendChild(cpuCell);

// 192-203行
const memCell = document.createElement('td');
memCell.className = 'mem-usage';
const memPercent = proc.mem_percent;  // ✅ 修正
memCell.textContent = memPercent.toFixed(1);
if (memPercent < 10) {
    memCell.classList.add('cpu-low');
} else if (memPercent < 50) {
    memCell.classList.add('cpu-medium');
} else {
    memCell.classList.add('cpu-high');
}
row.appendChild(memCell);

// 296-297行（プロセス詳細モーダル）
<p><strong>CPU %:</strong> ${proc.cpu_percent.toFixed(2)}</p>
<p><strong>Memory %:</strong> ${proc.memory_percent.toFixed(2)}</p>
```

### テストケース

**単体テスト** (`tests/unit/test_processes_js.py`):
```python
def test_cpu_percent_display():
    """CPU使用率が正しく表示されること"""
    process = {
        "cpu_percent": 10.5,
        "mem_percent": 2.3,
        # ...
    }

    # 期待値: 10.5% → "10.5"
    # 誤り:   10.5% / 10.0 → "1.1"
    assert display_cpu(process) == "10.5"
```

---

## 🔴 バグ#3: フィルタパラメータ名の不一致

### 問題の詳細

**ファイル**: `/mnt/LinuxHDD/Linux-Management-Systm/frontend/js/processes.js` (104-106行)

**誤ったコード**:
```javascript
if (this.currentFilters.user) {
    params.append('user', this.currentFilters.user);  // ❌ 間違い！
}
```

**APIの期待値**: `/mnt/LinuxHDD/Linux-Management-Systm/backend/api/routes/processes.py` (63-65行)
```python
filter_user: Optional[str] = Query(
    None, min_length=1, max_length=32, pattern="^[a-zA-Z0-9_-]+$"
),
```

**Wrapper Script**: `/mnt/LinuxHDD/Linux-Management-Systm/wrappers/adminui-processes.sh` (100-102行)
```bash
--filter-user=*)
    FILTER_USER="${1#*=}"
```

### 影響

**テストシナリオ**:
1. ユーザーがフィルタに「root」を入力
2. JavaScriptが `?user=root` をAPIに送信
3. APIが `filter_user` パラメータを期待
4. パラメータ名不一致により、フィルタが無視される
5. 全ユーザーのプロセスが返される

**APIレスポンス**:
```json
{
  "status": "success",
  "filters": {
    "user": "",  // ❌ フィルタが適用されていない
    "min_cpu": 0.0,
    "min_mem": 0.0
  },
  "processes": [
    // 全ユーザーのプロセス（フィルタされていない）
  ]
}
```

### 修正コード

**修正前**:
```javascript
// ❌ 誤り
if (this.currentFilters.user) {
    params.append('user', this.currentFilters.user);
}
```

**修正後**:
```javascript
// ✅ 正しい
if (this.currentFilters.user) {
    params.append('filter_user', this.currentFilters.user);
}
```

**修正箇所**:
- 105行目: `params.append('filter_user', this.currentFilters.user);`

### テストケース

**統合テスト** (`tests/integration/test_processes_integration.py`):
```python
def test_user_filter_applied(test_client, auth_headers):
    """ユーザーフィルタが正しく適用されること"""
    response = test_client.get("/api/processes?filter_user=root", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["filters"]["user"] == "root"

    # 全プロセスが root ユーザーのみ
    for proc in data["processes"]:
        assert proc["user"] == "root"
```

---

## 🔴 バグ#4: モデルフィールド名の3重不一致（CRITICAL）

### 問題の詳細

**3つの異なるフィールド名が使用されている**:

#### 1. Wrapper Script (正)
**ファイル**: `/mnt/LinuxHDD/Linux-Management-Systm/wrappers/adminui-processes.sh` (362行)

```json
{
  "pid": 1234,
  "user": "root",
  "cpu_percent": 10.5,
  "mem_percent": 2.3,
  "vsz": 234560,
  "rss": 78900,
  "tty": "?",
  "stat": "S",
  "start": "12:00",
  "time": "0:15",
  "command": "nginx: worker"
}
```

#### 2. API Model (正)
**ファイル**: `/mnt/LinuxHDD/Linux-Management-Systm/backend/api/routes/processes.py` (26-40行)

```python
class ProcessInfo(BaseModel):
    pid: int
    user: str
    cpu_percent: float
    mem_percent: float
    vsz: int
    rss: int        # ✅ Wrapper と一致
    tty: str
    stat: str       # ✅ Wrapper と一致
    start: str      # ✅ Wrapper と一致
    time: str
    command: str
```

#### 3. JavaScript (誤)
**ファイル**: `/mnt/LinuxHDD/Linux-Management-Systm/frontend/js/processes.js`

```javascript
// 207行目
proc.memory_rss_mb  // ❌ 期待: "rss" または "memory_rss_mb"

// 214行目
proc.state  // ❌ 期待: "stat"

// 221行目
proc.started_at  // ❌ 期待: "start"

// 227行目
proc.time  // ✅ 正しい
```

### フィールド名マッピング表

| Wrapper/API | JavaScript期待値 | 一致? | 影響 |
|-------------|-----------------|------|------|
| `stat` | `state` | ❌ | プロセス状態バッジが表示されない |
| `start` | `started_at` | ❌ | 開始時刻が表示されない |
| `rss` | `memory_rss_mb` | ❌ | RSSメモリサイズが表示されない |
| `time` | `time` | ✅ | 正常 |
| `cpu_percent` | `cpu_percent` | ✅ | 正常（ただしバグ#1の影響） |
| `mem_percent` | `mem_percent` | ✅ | 正常（ただしバグ#1の影響） |

### 影響

**プロセステーブル表示** (142-244行):
```javascript
// 214行目 - プロセス状態バッジ
const stateBadge = document.createElement('span');
stateBadge.className = `state-badge state-${proc.state}`;  // ❌ proc.state は undefined
stateBadge.textContent = proc.state;  // ❌ undefined が表示される
```

**実際の表示**:
- プロセス状態カラム: **空白または "undefined"**
- 状態バッジのCSSクラス: `state-badge state-undefined`（スタイルが適用されない）
- 開始時刻カラム: **空白または "undefined"**
- RSSメモリカラム: **空白または "-"**

**プロセス詳細モーダル** (287-304行):
```javascript
<p><strong>State:</strong> <span class="state-badge state-${proc.state}">${proc.state}</span></p>
// ❌ proc.state は undefined

<p><strong>Started:</strong> ${this.escapeHtml(this.formatDateTime(proc.started_at))}</p>
// ❌ proc.started_at は undefined

<p><strong>RSS (MB):</strong> ${proc.memory_rss_mb ? proc.memory_rss_mb.toFixed(2) : '-'}</p>
// ❌ proc.memory_rss_mb は undefined
```

### 修正方針

**オプション1: JavaScript側でフィールド名を修正** (推奨)
- メリット: API/Wrapperの変更不要、影響範囲が小さい
- デメリット: なし

**オプション2: API側で変換レイヤーを追加**
- メリット: フロントエンドの変更が少ない
- デメリット: バックエンドの複雑化、パフォーマンス劣化

**オプション3: Wrapper側でフィールド名を変更**
- メリット: 統一性が向上
- デメリット: sudoラッパーの変更が必要、影響範囲が大きい

### 修正コード（オプション1: JavaScript側修正）

**修正箇所1**: プロセステーブル描画 (207-229行)

**修正前**:
```javascript
// 207行目 - RSS (MB)
const rssCell = document.createElement('td');
rssCell.textContent = proc.memory_rss_mb ? proc.memory_rss_mb.toFixed(1) : '-';  // ❌

// 214行目 - State
const stateBadge = document.createElement('span');
stateBadge.className = `state-badge state-${proc.state}`;  // ❌
stateBadge.textContent = proc.state;  // ❌

// 221行目 - Started
startedCell.textContent = this.formatDateTime(proc.started_at);  // ❌
```

**修正後**:
```javascript
// 207行目 - RSS (MB) ✅ 修正
const rssCell = document.createElement('td');
// rss はキロバイト単位なので、メガバイトに変換
const rssMB = proc.rss ? (proc.rss / 1024).toFixed(1) : '-';
rssCell.textContent = rssMB;
rssCell.style.textAlign = 'right';
row.appendChild(rssCell);

// 214行目 - State ✅ 修正
const stateCell = document.createElement('td');
const stateBadge = document.createElement('span');
stateBadge.className = `state-badge state-${proc.stat}`;  // ✅ proc.stat
stateBadge.textContent = proc.stat;  // ✅ proc.stat
stateCell.appendChild(stateBadge);
row.appendChild(stateCell);

// 221行目 - Started ✅ 修正
const startedCell = document.createElement('td');
startedCell.textContent = this.formatDateTime(proc.start);  // ✅ proc.start
startedCell.style.fontSize = '11px';
row.appendChild(startedCell);
```

**修正箇所2**: プロセス詳細モーダル (287-304行)

**修正前**:
```javascript
<div class="col-md-6">
    <p><strong>State:</strong> <span class="state-badge state-${proc.state}">${proc.state}</span></p>  // ❌
</div>
<div class="col-md-6">
    <p><strong>CPU %:</strong> ${proc.cpu_percent.toFixed(2)}</p>
    <p><strong>Memory %:</strong> ${proc.memory_percent.toFixed(2)}</p>  // ❌ proc.memory_percent
    <p><strong>RSS (MB):</strong> ${proc.memory_rss_mb ? proc.memory_rss_mb.toFixed(2) : '-'}</p>  // ❌
    <p><strong>Started:</strong> ${this.escapeHtml(this.formatDateTime(proc.started_at))}</p>  // ❌
</div>
```

**修正後**:
```javascript
<div class="col-md-6">
    <p><strong>PID:</strong> ${this.escapeHtml(proc.pid.toString())}</p>
    <p><strong>Name:</strong> ${this.escapeHtml(proc.name || '-')}</p>
    <p><strong>User:</strong> ${this.escapeHtml(proc.user)}</p>
    <p><strong>State:</strong> <span class="state-badge state-${proc.stat}">${proc.stat}</span></p>  // ✅ proc.stat
</div>
<div class="col-md-6">
    <p><strong>CPU %:</strong> ${proc.cpu_percent.toFixed(2)}</p>
    <p><strong>Memory %:</strong> ${proc.mem_percent.toFixed(2)}</p>  // ✅ proc.mem_percent
    <p><strong>RSS (MB):</strong> ${proc.rss ? (proc.rss / 1024).toFixed(2) : '-'}</p>  // ✅ proc.rss / 1024
    <p><strong>Started:</strong> ${this.escapeHtml(this.formatDateTime(proc.start))}</p>  // ✅ proc.start
</div>
```

**修正箇所3**: ハイライトロジック (154-160行)

**修正前**:
```javascript
// 高CPU/高メモリのハイライト
if (proc.cpu_percent > 50) {  // ❌ バグ#1の影響
    row.classList.add('high-cpu');
}
if (proc.memory_percent > 50) {  // ❌ フィールド名誤り
    row.classList.add('high-memory');
}
```

**修正後**:
```javascript
// 高CPU/高メモリのハイライト
if (proc.cpu_percent > 50) {  // ✅ バグ#1修正後は正常
    row.classList.add('high-cpu');
}
if (proc.mem_percent > 50) {  // ✅ proc.mem_percent
    row.classList.add('high-memory');
}
```

### RSS メモリサイズの単位変換について

**Wrapper Script の rss フィールド**:
- `ps aux` の RSS カラムはキロバイト単位
- 例: `78900` = 78900 KB ≈ 77 MB

**JavaScript での変換**:
```javascript
const rssMB = proc.rss / 1024;  // KB → MB
```

### テストケース

**単体テスト** (`tests/unit/test_processes_js.py`):
```python
def test_process_fields_mapping():
    """プロセスフィールドが正しくマッピングされること"""
    process = {
        "pid": 1234,
        "stat": "S",
        "start": "12:00",
        "rss": 78900,  # KB
        "cpu_percent": 10.5,
        "mem_percent": 2.3
    }

    # JavaScript の期待動作
    assert get_state(process) == "S"
    assert get_started_at(process) == "12:00"
    assert get_rss_mb(process) == pytest.approx(77.05, rel=0.1)
```

**統合テスト** (`tests/integration/test_processes_integration.py`):
```python
def test_process_detail_display(test_client, auth_headers):
    """プロセス詳細が正しく表示されること"""
    response = test_client.get("/api/processes?limit=1", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    if len(data["processes"]) > 0:
        proc = data["processes"][0]

        # 必須フィールドの存在確認
        assert "stat" in proc
        assert "start" in proc
        assert "rss" in proc

        # フィールド名の不一致がないこと
        assert "state" not in proc
        assert "started_at" not in proc
        assert "memory_rss_mb" not in proc
```

---

## 📊 修正優先度と推定工数

| バグID | 優先度 | 修正難易度 | 推定工数 | 推奨対応時期 |
|--------|--------|-----------|---------|------------|
| **#4** | 🔴 CRITICAL | 中 | 2時間 | **即時** |
| **#3** | 🔴 HIGH | 低 | 30分 | **即時** |
| **#1** | 🔴 HIGH | 低 | 30分 | **即時** |

**総推定工数**: 3時間

---

## 🧪 修正後のテスト計画

### 1. 単体テスト
```bash
pytest tests/unit/test_processes.py -v
```

### 2. 統合テスト
```bash
pytest tests/integration/test_processes_integration.py -v
```

### 3. セキュリティテスト
```bash
pytest tests/security/test_processes_security.py -v
```

### 4. E2E テスト（手動）
- [ ] プロセス一覧ページを開く
- [ ] CPU使用率50%以上のプロセスが赤色ハイライトされるか確認
- [ ] ユーザーフィルタで「root」を入力し、rootユーザーのプロセスのみ表示されるか確認
- [ ] プロセス行をクリックし、詳細モーダルで状態・開始時刻・RSSが正しく表示されるか確認

### 5. リグレッションテスト
```bash
pytest tests/ -v --cov=backend --cov=frontend
```

---

## 🔐 セキュリティ影響評価

### バグ#1の影響
- ✅ セキュリティリスクなし（表示のみの問題）

### バグ#3の影響
- ⚠️ **中リスク**: ユーザーフィルタが機能しないため、意図しないユーザーのプロセスが表示される可能性
- ✅ allowlist 検証は有効（バックエンド側で検証）
- ✅ コマンドインジェクションリスクなし

### バグ#4の影響
- ✅ セキュリティリスクなし（表示のみの問題）
- ⚠️ プロセス詳細が表示されないことで、ユーザビリティが低下

---

## 📝 修正チェックリスト

### バグ#1修正
- [ ] `frontend/js/processes.js` 178行目の除算を削除
- [ ] `frontend/js/processes.js` 192行目の除算を削除
- [ ] `frontend/js/processes.js` 296-297行（プロセス詳細モーダル）の除算を削除
- [ ] 単体テスト追加: `test_cpu_percent_display()`
- [ ] E2Eテスト: 高CPU/高メモリハイライトの動作確認

### バグ#3修正
- [ ] `frontend/js/processes.js` 105行目のパラメータ名を `filter_user` に修正
- [ ] 統合テスト追加: `test_user_filter_applied()`
- [ ] E2Eテスト: ユーザーフィルタの動作確認

### バグ#4修正
- [ ] `frontend/js/processes.js` 207行目: `proc.memory_rss_mb` → `proc.rss / 1024`
- [ ] `frontend/js/processes.js` 214行目: `proc.state` → `proc.stat`
- [ ] `frontend/js/processes.js` 221行目: `proc.started_at` → `proc.start`
- [ ] `frontend/js/processes.js` 159行目: `proc.memory_percent` → `proc.mem_percent`
- [ ] `frontend/js/processes.js` 293行目（プロセス詳細モーダル）: `proc.state` → `proc.stat`
- [ ] `frontend/js/processes.js` 297行目（プロセス詳細モーダル）: `proc.memory_percent` → `proc.mem_percent`
- [ ] `frontend/js/processes.js` 298行目（プロセス詳細モーダル）: `proc.memory_rss_mb` → `proc.rss / 1024`
- [ ] `frontend/js/processes.js` 299行目（プロセス詳細モーダル）: `proc.started_at` → `proc.start`
- [ ] 単体テスト追加: `test_process_fields_mapping()`
- [ ] 統合テスト追加: `test_process_detail_display()`
- [ ] E2Eテスト: プロセス詳細モーダルの全フィールド表示確認

---

## 📎 関連ファイル

### 修正対象
- `/mnt/LinuxHDD/Linux-Management-Systm/frontend/js/processes.js` (462行)

### 参照ファイル
- `/mnt/LinuxHDD/Linux-Management-Systm/backend/api/routes/processes.py` (163行)
- `/mnt/LinuxHDD/Linux-Management-Systm/wrappers/adminui-processes.sh` (382行)

### テストファイル
- `/mnt/LinuxHDD/Linux-Management-Systm/tests/unit/test_processes.py`
- `/mnt/LinuxHDD/Linux-Management-Systm/tests/integration/test_processes_integration.py`
- `/mnt/LinuxHDD/Linux-Management-Systm/tests/security/test_processes_security.py`

---

**分析者**: processes-tester
**日時**: 2026-02-06
**ステータス**: 分析完了、修正推奨アクション提示
