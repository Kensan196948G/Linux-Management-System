/**
 * サイドバー制御
 */

/**
 * アコーディオンの開閉
 */
function toggleAccordion(element) {
    const accordionItem = element.parentElement;
    const wasOpen = accordionItem.classList.contains('open');

    // 他の開いているアコーディオンを閉じる（オプション）
    // document.querySelectorAll('.accordion-item.open').forEach(item => {
    //     item.classList.remove('open');
    // });

    // クリックされたアコーディオンを開閉
    if (wasOpen) {
        accordionItem.classList.remove('open');
    } else {
        accordionItem.classList.add('open');
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
