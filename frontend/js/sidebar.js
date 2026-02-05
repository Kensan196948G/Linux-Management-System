/**
 * サイドバー制御
 */

/**
 * アコーディオンの開閉
 */
function toggleAccordion(element) {
    const accordionItem = element.parentElement;
    accordionItem.classList.toggle('open');
}

/**
 * ページを表示
 */
function showPage(pageName) {
    console.log('Showing page:', pageName);

    // ページタイトルを更新
    const titles = {
        'dashboard': 'ダッシュボード',
        'services': 'System Servers - サービス管理',
        'audit-log': 'System Actions Log - 操作ログ',
        'disk': 'Local Disk - ディスク使用状況',
        'logs': 'System Logs - ログ閲覧',
        'firewall': 'Linux Firewall - ファイアウォール管理',
        'network-config': 'Network Configuration - ネットワーク設定',
        'routing': 'Routing and Gateways - ルーティング',
        'netstat': 'Netstat - ネットワーク統計',
        'bandwidth': 'Bandwidth Monitoring - 帯域幅監視',
        'partitions': 'Partitions - パーティション管理',
        'system-time': 'System Time - システム時刻',
        'smart-status': 'SMART Drive Status - ドライブ健全性',
        'sensors': 'Sensors - ハードウェアセンサー',
    };

    document.getElementById('page-title').textContent = titles[pageName] || pageName;

    // メニューのアクティブ状態を更新
    document.querySelectorAll('.menu-item, .submenu-item').forEach(item => {
        item.classList.remove('active');
    });

    // メインコンテンツを更新
    const mainBody = document.getElementById('main-body');

    switch (pageName) {
        case 'dashboard':
            showDashboardPage(mainBody);
            break;
        case 'services':
            showServicesPage(mainBody);
            break;
        case 'audit-log':
            showAuditLogPage(mainBody);
            break;
        case 'disk':
            showDiskPage(mainBody);
            break;
        case 'logs':
            showLogsPage(mainBody);
            break;
        case 'firewall':
            showFirewallPage(mainBody);
            break;
        case 'network-config':
            showNetworkConfigPage(mainBody);
            break;
        case 'routing':
            showRoutingPage(mainBody);
            break;
        case 'netstat':
            showNetstatPage(mainBody);
            break;
        case 'bandwidth':
            showBandwidthPage(mainBody);
            break;
        case 'partitions':
            showPartitionsPage(mainBody);
            break;
        case 'system-time':
            showSystemTimePage(mainBody);
            break;
        case 'smart-status':
            showSmartStatusPage(mainBody);
            break;
        case 'sensors':
            showSensorsPage(mainBody);
            break;
        default:
            mainBody.innerHTML = `
                <div class="card">
                    <h3 class="card-title">${pageName}</h3>
                    <p>このモジュールは今後実装予定です。</p>
                </div>
            `;
    }
}

/**
 * サイドバーのユーザー情報を更新
 */
function updateSidebarUserInfo(user) {
    document.getElementById('sidebar-username').textContent = user.username;
    document.getElementById('sidebar-role').textContent = user.role;
}
