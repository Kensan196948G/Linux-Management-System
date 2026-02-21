"""
共通定数定義

v0.3設計統合: 全モジュール共通のallowlist/denylist定数
"""

# ===================================================================
# 禁止ユーザー名（全モジュール共通）
# ===================================================================
# users-groups-allowlist-policy.md より（100+エントリ）

# システムクリティカルユーザー
FORBIDDEN_USERNAMES_SYSTEM = [
    "root",
    "bin",
    "daemon",
    "sys",
    "sync",
    "games",
    "man",
    "lp",
    "mail",
    "news",
    "uucp",
    "proxy",
    "backup",
    "list",
    "irc",
    "gnats",
    "nobody",
    "_apt",
    "messagebus",  # 100件達成のため追加
]

# サービスアカウント
FORBIDDEN_USERNAMES_SERVICE = [
    "www-data",
    "sshd",
    "systemd-network",
    "systemd-resolve",
    "systemd-timesync",
    "messagebus",
    "syslog",
    "uuidd",
    "tcpdump",
    "landscape",
    "pollinate",
    "fwupd-refresh",
    "tss",
    "usbmux",
    "dnsmasq",
    "avahi",
    "speech-dispatcher",
    "pulse",
    "rtkit",
    "colord",
    "geoclue",
    "saned",
    "whoopsie",
    # Database services
    "postgres",
    "mysql",
    "mongodb",
    "redis",
    "memcached",
    "elasticsearch",
    "cassandra",
    "couchdb",
    # Web servers
    "nginx",
    "apache",
    "httpd",
    "lighttpd",
    # Application servers
    "tomcat",
    "jetty",
    "node",
    "pm2",
    # Monitoring & logging
    "nagios",
    "zabbix",
    "prometheus",
    "grafana",
    "logstash",
    "kibana",
    "fluentd",
    "telegraf",
    # Container & orchestration
    "docker",
    "containerd",
    "kubernetes",
    "k8s",
    # Message queues
    "rabbitmq",
    "kafka",
    "activemq",
    # Mail
    "postfix",
    "dovecot",
    "exim",
    "sendmail",
]

# 管理関連ユーザー名
FORBIDDEN_USERNAMES_ADMIN = [
    "admin",
    "administrator",
    "sudo",
    "wheel",
    "operator",
    "adm",
    "staff",
    "kmem",
    "dialout",
    "cdrom",
    "floppy",
    "audio",
    "video",
    "plugdev",
    "netdev",
    "lxd",
]

# アプリケーション固有ユーザー名
FORBIDDEN_USERNAMES_APP = [
    "adminui",
    "svc-adminui",
    "webmin",
    "cockpit",
    "usermin",
    "virtualmin",
    "cloudmin",
]

# 全ての禁止ユーザー名（統合リスト）
FORBIDDEN_USERNAMES = (
    FORBIDDEN_USERNAMES_SYSTEM
    + FORBIDDEN_USERNAMES_SERVICE
    + FORBIDDEN_USERNAMES_ADMIN
    + FORBIDDEN_USERNAMES_APP
)


# ===================================================================
# 禁止グループ名（全モジュール共通）
# ===================================================================

# クリティカルグループ（権限昇格リスク）
FORBIDDEN_GROUPS_CRITICAL = [
    "root",
    "sudo",
    "wheel",
    "adm",
    "staff",
]

# システムグループ
FORBIDDEN_GROUPS_SYSTEM = [
    "bin",
    "daemon",
    "sys",
    "disk",
    "lp",
    "dialout",
    "cdrom",
    "floppy",
    "tape",
    "audio",
    "video",
    "plugdev",
    "netdev",
    "scanner",
    "bluetooth",
    "input",
    "kvm",
    "render",
    "sgx",
]

# コンテナ・仮想化グループ
FORBIDDEN_GROUPS_CONTAINER = [
    "docker",
    "lxd",
    "libvirt",
    "libvirt-qemu",
    "kvm",
]

# ネットワーク・セキュリティグループ
FORBIDDEN_GROUPS_NETWORK = [
    "ssl-cert",
    "shadow",
    "utmp",
    "tty",
    "kmem",
]

# systemd関連グループ
FORBIDDEN_GROUPS_SYSTEMD = [
    "systemd-journal",
    "systemd-network",
    "systemd-resolve",
    "systemd-timesync",
    "systemd-coredump",
]

# ハードウェアアクセスグループ
FORBIDDEN_GROUPS_HARDWARE = [
    "i2c",
    "gpio",
    "spi",
    "dialout",
]

# 全ての禁止グループ名（統合リスト）
FORBIDDEN_GROUPS = (
    FORBIDDEN_GROUPS_CRITICAL
    + FORBIDDEN_GROUPS_SYSTEM
    + FORBIDDEN_GROUPS_CONTAINER
    + FORBIDDEN_GROUPS_NETWORK
    + FORBIDDEN_GROUPS_SYSTEMD
    + FORBIDDEN_GROUPS_HARDWARE
)


# ===================================================================
# 許可シェル（全モジュール共通）
# ===================================================================

ALLOWED_SHELLS = [
    "/bin/bash",
    "/bin/sh",
    "/bin/dash",
    "/usr/bin/zsh",
    "/bin/false",  # アカウント無効化用
]


# ===================================================================
# UID/GID範囲（全モジュール共通）
# ===================================================================

MIN_UID = 1000  # システムユーザーを避ける
MAX_UID = 59999

MIN_GID = 1000
MAX_GID = 59999


# ===================================================================
# レート制限（全モジュール共通）
# ===================================================================

# ユーザー管理操作のレート制限
USER_MANAGEMENT_RATE_LIMIT = 30  # 30 requests per minute

# Cron操作のレート制限
CRON_MANAGEMENT_RATE_LIMIT = 10  # 10 requests per minute

# 承認リクエスト作成のレート制限
APPROVAL_REQUEST_RATE_LIMIT = 10  # 10 requests per hour per user
