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
        'apache': 'Apache Webserver - Apache管理',
        'postfix': 'Postfix メール - メール管理',
        'ssh': 'SSH Server - SSH管理',
        'smart-status': 'SMART Drive Status - ドライブ健全性',
        'sensors': 'Sensors - ハードウェアセンサー',
        'packages': 'Package Updates - パッケージ管理',
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
            location.href = 'firewall.html';
            return;
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
        case 'apache':
            location.href = 'apache.html';
            return;
        case 'postfix':
            location.href = 'postfix.html';
            return;
        case 'ssh':
            location.href = 'ssh.html';
            return;
        case 'smart-status':
            showSmartStatusPage(mainBody);
            break;
        case 'sensors':
            showSensorsPage(mainBody);
            break;
        case 'packages':
            location.href = 'packages.html';
            return;
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
    // サイドバーフッターのユーザー名
    const sidebarUsername = document.getElementById('sidebar-username');
    if (sidebarUsername) {
        const name = (user.username || user.email || '-').split('@')[0];
        sidebarUsername.textContent = name;
    }

    // ユーザーメニュー内の情報を更新
    const umname = document.getElementById('user-menu-username');
    if (umname) umname.textContent = user.username || '-';
    const umemail = document.getElementById('user-menu-email');
    if (umemail) umemail.textContent = user.email || user.username || '-';

    const roleElement = document.getElementById('user-menu-role');
    if (!roleElement) return;
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
            if (userInfo) userInfo.classList.remove('active');
            userMenu.classList.remove('show');
        }
    }
});

/**
 * サイドバーHTMLを #sidebar-container に注入する
 * @param {string} activePage - アクティブページ識別子
 */
function renderSidebar(activePage) {
    const container = document.getElementById('sidebar-container');
    if (!container) return;

    // クラスを設定（asideタグでない場合に備えて）
    if (!container.classList.contains('sidebar')) {
        container.className = 'sidebar';
    }

    const a = (page) => activePage === page ? ' active' : '';

    // 環境バッジ（URLパスで判定）
    const isProd = window.location.pathname.includes('/prod/');
    const envBadge = isProd
        ? '<span class="env-badge prod" id="env-badge" style="background:#fee2e2;color:#991b1b;font-size:10px;padding:2px 6px;border-radius:3px;font-weight:600;">【本番】</span>'
        : '<span class="env-badge dev" id="env-badge" style="background:#fef3c7;color:#92400e;font-size:10px;padding:2px 6px;border-radius:3px;font-weight:600;">【開発】</span>';

    container.innerHTML = `
        <div class="sidebar-header">
            <h1 class="sidebar-title">🖥️ Linux管理運用</h1>
            <p class="sidebar-subtitle">
                ${envBadge}
            </p>
        </div>

        <nav class="sidebar-menu">
            <!-- ダッシュボード -->
            <div class="menu-item${a('dashboard')}" onclick="location.href='dashboard.html'">
                <span class="menu-item-icon">📊</span>
                <span>ダッシュボード</span>
            </div>

            <!-- Linux管理システム カテゴリ -->
            <div class="accordion-item ${['audit','services'].includes(activePage) ? 'open' : ''}">
                <div class="accordion-header" onclick="toggleAccordion(this)">
                    <div class="accordion-title"><span>⚙️</span><span>Linux管理システム</span></div>
                    <span class="accordion-icon">▼</span>
                </div>
                <div class="accordion-content">
                    <div class="accordion-submenu">
                        <div class="submenu-item disabled">
                            <div class="submenu-item-name">システム設定</div>
                            <div class="submenu-item-badge">計画中</div>
                        </div>
                        <div class="submenu-item${a('services')}" onclick="location.href='servers.html'">
                            <div class="submenu-item-name">システムサーバー</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('audit')}" onclick="location.href='audit.html'">
                            <div class="submenu-item-name">監査ログ</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- システム カテゴリ -->
            <div class="accordion-item ${['bootup','users','cron','processes','logs','packages'].includes(activePage) ? 'open' : ''}">
                <div class="accordion-header" onclick="toggleAccordion(this)">
                    <div class="accordion-title"><span>💻</span><span>システム</span></div>
                    <span class="accordion-icon">▼</span>
                </div>
                <div class="accordion-content">
                    <div class="accordion-submenu">
                        <div class="submenu-item${a('bootup')}" onclick="location.href='bootup.html'">
                            <div class="submenu-item-name">起動・シャットダウン</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('users')}" onclick="location.href='users.html'">
                            <div class="submenu-item-name">ユーザー・グループ</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('cron')}" onclick="location.href='cron.html'">
                            <div class="submenu-item-name">Cronジョブ</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('processes')}" onclick="location.href='processes.html'">
                            <div class="submenu-item-name">実行中プロセス</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('logs')}" onclick="location.href='logs.html'">
                            <div class="submenu-item-name">システムログ</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('packages')}" onclick="location.href='packages.html'">
                            <div class="submenu-item-name">パッケージ管理</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 承認ワークフロー -->
            <div class="menu-item${a('approval')}" onclick="location.href='approval.html'">
                <span class="menu-item-icon">✅</span>
                <span>承認ワークフロー</span>
                <span id="approval-pending-badge" class="badge bg-warning text-dark ms-1" style="display:none">0</span>
            </div>

            <!-- 通知設定 -->
            <div class="menu-item${a('notifications')}" onclick="location.href='notifications.html'">
                <span class="menu-item-icon">🔔</span>
                <span>通知設定</span>
            </div>

            <!-- サーバー カテゴリ -->
            <div class="accordion-item ${['servers','ssh','apache','postfix','dbmonitor'].includes(activePage) ? 'open' : ''}">
                <div class="accordion-header" onclick="toggleAccordion(this)">
                    <div class="accordion-title"><span>🖥️</span><span>サーバー</span></div>
                    <span class="accordion-icon">▼</span>
                </div>
                <div class="accordion-content">
                    <div class="accordion-submenu">
                        <div class="submenu-item${a('servers')}" onclick="location.href='servers.html'">
                            <div class="submenu-item-name">サーバー状態一覧</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('ssh')}" onclick="location.href='ssh.html'">
                            <div class="submenu-item-name">SSH Server</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('apache')}" onclick="location.href='apache.html'">
                            <div class="submenu-item-name">Apache Webサーバー</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('postfix')}" onclick="location.href='postfix.html'">
                            <div class="submenu-item-name">Postfix メール</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('dbmonitor')}" onclick="location.href='dbmonitor.html'">
                            <div class="submenu-item-name">DBモニター</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ネットワーク カテゴリ -->
            <div class="accordion-item ${['network','bandwidth','firewall'].includes(activePage) ? 'open' : ''}">
                <div class="accordion-header" onclick="toggleAccordion(this)">
                    <div class="accordion-title"><span>🌐</span><span>ネットワーク</span></div>
                    <span class="accordion-icon">▼</span>
                </div>
                <div class="accordion-content">
                    <div class="accordion-submenu">
                        <div class="submenu-item${a('network')}" onclick="location.href='network.html'">
                            <div class="submenu-item-name">ネットワーク情報</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('firewall')}" onclick="location.href='firewall.html'">
                            <div class="submenu-item-name">ファイアウォール</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('bandwidth')}" onclick="location.href='bandwidth.html'">
                            <div class="submenu-item-name">帯域幅モニタリング</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ハードウェア カテゴリ -->
            <div class="accordion-item ${['hardware','time','quotas','filemanager'].includes(activePage) ? 'open' : ''}">
                <div class="accordion-header" onclick="toggleAccordion(this)">
                    <div class="accordion-title"><span>🔧</span><span>ハードウェア</span></div>
                    <span class="accordion-icon">▼</span>
                </div>
                <div class="accordion-content">
                    <div class="accordion-submenu">
                        <div class="submenu-item${a('hardware')}" onclick="location.href='hardware.html'">
                            <div class="submenu-item-name">ハードウェア情報</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('filemanager')}" onclick="location.href='filemanager.html'">
                            <div class="submenu-item-name">ファイルシステム</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('time')}" onclick="location.href='time.html'">
                            <div class="submenu-item-name">システム時刻</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                        <div class="submenu-item${a('quotas')}" onclick="location.href='quotas.html'">
                            <div class="submenu-item-name">ディスククォータ</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- システム設定 -->
            <div class="accordion-item ${['settings'].includes(activePage) ? 'open' : ''}">
                <div class="accordion-header" onclick="toggleAccordion(this)">
                    <div class="accordion-title"><span>⚡</span><span>システム設定</span></div>
                    <span class="accordion-icon">▼</span>
                </div>
                <div class="accordion-content">
                    <div class="accordion-submenu">
                        <div class="submenu-item${a('settings')}" onclick="location.href='settings.html'">
                            <div class="submenu-item-name">統合設定</div>
                            <div class="submenu-item-badge">実装済み</div>
                        </div>
                    </div>
                </div>
            </div>
        </nav>

        <!-- サイドバーフッター -->
        <div class="sidebar-footer">
            <div style="padding:10px 12px; border-top:1px solid var(--border-color,#334155)">
                <button id="theme-toggle-btn" onclick="toggleTheme()"
                        style="width:100%; padding:7px; border-radius:6px; border:1px solid var(--border-color,#334155);
                               background:transparent; color:var(--text-primary,#f1f5f9); cursor:pointer; font-size:12px">
                    🌙 ダーク
                </button>
            </div>
            <div class="user-info" onclick="toggleUserMenu(event)">
                <div class="user-avatar" style="display:flex;align-items:center;gap:8px;flex:1;min-width:0;">
                    <span class="avatar-icon">👤</span>
                    <span class="username" id="sidebar-username">-</span>
                </div>
                <span class="user-menu-indicator">▼</span>
                <div class="user-menu" id="user-menu">
                    <div class="user-menu-header">
                        <span class="user-menu-icon">👤</span>
                        <div class="user-menu-info">
                            <div class="user-menu-name" id="user-menu-username">-</div>
                            <div class="user-menu-role" id="user-menu-role">-</div>
                        </div>
                    </div>
                    <div class="user-menu-divider"></div>
                    <div class="user-menu-items">
                        <div class="user-menu-item">
                            <span class="user-menu-item-icon">📧</span>
                            <span class="user-menu-item-text" id="user-menu-email">-</span>
                        </div>
                    </div>
                    <div class="user-menu-divider"></div>
                    <button class="btn btn-danger" onclick="logout(); event.stopPropagation();" style="width:100%;font-size:var(--font-size-sm);">ログアウト</button>
                </div>
            </div>
        </div>
    `;

    // 保存済みのユーザー情報を復元
    try {
        const email = localStorage.getItem('user_email') || localStorage.getItem('userEmail') || '';
        if (email) {
            const uname = email.split('@')[0];
            const el = document.getElementById('sidebar-username');
            if (el) el.textContent = uname;
            const umname = document.getElementById('user-menu-username');
            if (umname) umname.textContent = uname;
            const umemail = document.getElementById('user-menu-email');
            if (umemail) umemail.textContent = email;
        }
    } catch(e) {}
}

/**
 * logout関数（sidebar.jsから呼ばれる場合の共通実装）
 */
if (typeof logout === 'undefined') {
    window.logout = function() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('token_type');
        localStorage.removeItem('user_email');
        localStorage.removeItem('accordionState');
        location.href = 'index.html';
    };
}

/**
 * サイドバーの承認待ち件数バッジを更新する
 */
async function updateApprovalBadge() {
    const token = localStorage.getItem('access_token');
    if (!token) return;
    try {
        const resp = await fetch('/api/approval/pending', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (!resp.ok) return;
        const data = await resp.json();
        const count = (data.requests || []).length;
        const badgeEl = document.getElementById('approval-pending-badge');
        if (badgeEl) {
            badgeEl.textContent = count;
            badgeEl.style.display = count > 0 ? '' : 'none';
        }
    } catch {}
}

// ページロード時とその後30秒ごとにバッジを更新
document.addEventListener('DOMContentLoaded', function() {
    updateApprovalBadge();
    setInterval(updateApprovalBadge, 30000);
});
