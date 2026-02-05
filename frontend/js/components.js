/**
 * UI コンポーネント
 * 再利用可能な UI 要素
 */

/**
 * アラートを表示
 */
function showAlert(message, type = 'error') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.textContent = message;

    const container = document.querySelector('.container');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);

        // 5秒後に自動削除
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
}

/**
 * ローディング表示
 */
function showLoading(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                <p>読み込み中...</p>
            </div>
        `;
    }
}

/**
 * システム状態カードを生成
 */
function createSystemStatusCard(statusData) {
    const cpu = statusData.cpu || {};
    const memory = statusData.memory || {};
    const uptime = statusData.uptime || {};

    return `
        <div class="grid grid-3">
            <div class="card">
                <h3 class="card-title">CPU</h3>
                <p>使用率: ${cpu.usage_percent?.toFixed(1) || 0}%</p>
                <p>コア数: ${cpu.cores || 0}</p>
                <p>ロードアベレージ: ${cpu.load_average || 'N/A'}</p>
                <div class="progress-bar mt-1">
                    <div class="progress-fill" style="width: ${cpu.usage_percent || 0}%"></div>
                </div>
            </div>

            <div class="card">
                <h3 class="card-title">メモリ</h3>
                <p>合計: ${memory.total || 0} MB</p>
                <p>使用: ${memory.used || 0} MB</p>
                <p>空き: ${memory.free || 0} MB</p>
                <div class="progress-bar mt-1">
                    <div class="progress-fill" style="width: ${memory.usage_percent || 0}%"></div>
                </div>
            </div>

            <div class="card">
                <h3 class="card-title">稼働時間</h3>
                <p>${uptime.human_readable || 'N/A'}</p>
                <p class="text-secondary">${uptime.seconds || 0} 秒</p>
            </div>
        </div>
    `;
}

/**
 * ディスク使用状況テーブルを生成
 */
function createDiskUsageTable(diskData) {
    if (!diskData || diskData.length === 0) {
        return '<p>ディスク情報がありません</p>';
    }

    let html = `
        <table class="table">
            <thead>
                <tr>
                    <th>デバイス</th>
                    <th>マウントポイント</th>
                    <th>サイズ</th>
                    <th>使用</th>
                    <th>空き</th>
                    <th>使用率</th>
                </tr>
            </thead>
            <tbody>
    `;

    diskData.forEach(disk => {
        html += `
            <tr>
                <td>${disk.source}</td>
                <td>${disk.mountpoint}</td>
                <td>${disk.size}</td>
                <td>${disk.used}</td>
                <td>${disk.available}</td>
                <td>
                    <span class="status-badge ${disk.usage_percent > 80 ? 'status-error' : 'status-active'}">
                        ${disk.usage_percent}%
                    </span>
                </td>
            </tr>
        `;
    });

    html += `
            </tbody>
        </table>
    `;

    return html;
}

/**
 * サービスボタンを生成
 */
function createServiceButton(serviceName) {
    return `
        <button class="btn btn-warning" onclick="restartService('${serviceName}')">
            ${serviceName} を再起動
        </button>
    `;
}

/**
 * ログビューアを生成
 */
function createLogViewer(logs) {
    if (!logs || logs.length === 0) {
        return '<p>ログがありません</p>';
    }

    let html = '<div class="log-viewer">';

    logs.forEach(line => {
        html += `<div class="log-line">${escapeHtml(line)}</div>`;
    });

    html += '</div>';

    return html;
}

/**
 * HTML エスケープ
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 現在時刻を表示
 */
function updateCurrentTime() {
    const timeElement = document.getElementById('current-time');
    if (timeElement) {
        const now = new Date();
        timeElement.textContent = now.toLocaleString('ja-JP');
    }
}

// 1秒ごとに時刻更新
setInterval(updateCurrentTime, 1000);
