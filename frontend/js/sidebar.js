/**
 * サイドバー制御
 */

/**
 * アコーディオンの開閉
 */
function toggleAccordion(element) {
    const accordionItem = element.parentElement;
    accordionItem.classList.toggle('open');

    // 開閉状態をlocalStorageに保存
    saveAccordionState();
}

/**
 * アコーディオンの状態を保存
 */
function saveAccordionState() {
    const openAccordions = [];
    document.querySelectorAll('.accordion-item.open').forEach((item, index) => {
        openAccordions.push(index);
    });
    localStorage.setItem('accordionState', JSON.stringify(openAccordions));
}

/**
 * アコーディオンの状態を復元
 */
function restoreAccordionState() {
    try {
        const savedState = localStorage.getItem('accordionState');
        if (savedState) {
            const openAccordions = JSON.parse(savedState);
            const accordionItems = document.querySelectorAll('.accordion-item');
            openAccordions.forEach(index => {
                if (accordionItems[index]) {
                    accordionItems[index].classList.add('open');
                }
            });
        }
    } catch (error) {
        console.error('Failed to restore accordion state:', error);
    }
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
        'users': 'Users and Groups - ユーザー・グループ',
        'cron': 'Cron Jobs - Cronジョブ',
        'approvals': 'Approval Workflow - 承認ワークフロー',
        'firewall': 'Linux Firewall - ファイアウォール管理',
        'network-config': 'Network Configuration - ネットワーク設定',
        'routing': 'Routing and Gateways - ルーティング',
        'netstat': 'Netstat - ネットワーク統計',
        'bandwidth': 'Bandwidth Monitoring - 帯域幅監視',
        'partitions': 'Partitions - パーティション管理',
        'bootup': 'Bootup and Shutdown - 起動・シャットダウン',
        'system-time': 'System Time - システム時刻',
        'quotas': 'Disk Quotas - ディスククォータ管理',
        'dbmonitor': 'Database Monitor - DB監視',
        'bandwidth-monitoring': 'Bandwidth Monitoring - 帯域幅監視',
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
        case 'users':
            location.href = 'users.html';
            return;
        case 'cron':
            location.href = 'cron.html';
            return;
        case 'approvals':
            location.href = 'approval.html';
            return;
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
        case 'bootup':
            location.href = 'bootup.html';
            return;
        case 'system-time':
            location.href = 'time.html';
            return;
        case 'quotas':
            location.href = 'quotas.html';
            return;
        case 'dbmonitor':
            location.href = 'dbmonitor.html';
            return;
        case 'bandwidth-monitoring':
        case 'bandwidth':
            location.href = 'bandwidth.html';
            return;
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
    // ユーザーメニュー内の情報を更新
    document.getElementById('user-menu-username').textContent = user.username || '-';
    document.getElementById('user-menu-email').textContent = user.email || user.username || '-';

    const roleElement = document.getElementById('user-menu-role');
    roleElement.textContent = user.role || '-';

    // ロールに応じたクラスを適用
    roleElement.className = 'user-menu-role';
    const roleLower = (user.role || '').toLowerCase();
    if (roleLower === 'viewer') {
        roleElement.classList.add('role-viewer');
    } else if (roleLower === 'operator') {
        roleElement.classList.add('role-operator');
    } else if (roleLower === 'admin') {
        roleElement.classList.add('role-admin');
    }
}

/**
 * ユーザーメニューのトグル
 */
function toggleUserMenu(event) {
    event.stopPropagation();
    const userInfo = event.currentTarget;
    const userMenu = document.getElementById('user-menu');

    userInfo.classList.toggle('active');
    userMenu.classList.toggle('show');
}

// ページのどこかをクリックしたらメニューを閉じる
document.addEventListener('click', function(event) {
    const userMenu = document.getElementById('user-menu');
    const userInfo = document.querySelector('.user-info');

    if (userMenu && userMenu.classList.contains('show')) {
        if (!event.target.closest('.user-info')) {
            userInfo.classList.remove('active');
            userMenu.classList.remove('show');
        }
    }
});
