# Wrapper Specification: adminui-user-list.sh
#
# Created: 2026-02-14
# Author: users-planner (v03-planning-team)
# Phase: v0.3 Phase 1 (Read Operations)
# Risk Level: LOW
# Sudo Required: NO
#
# ===================================================================
# PURPOSE
# ===================================================================
#
# List non-system users (UID >= 1000, < 60000) in JSON format.
# Read-only operation, no system modification.
#
# ===================================================================
# INSTALLATION
# ===================================================================
#
# Location: /usr/local/sbin/adminui-user-list.sh
# Owner: root:root
# Permissions: 0755
# sudoers: Not required (read-only)
#
# ===================================================================
# USAGE
# ===================================================================
#
# adminui-user-list.sh [OPTIONS]
#
# Options:
#   --sort=<username|uid|last_login>  Sort key (default: username)
#   --limit=<N>                       Limit results (default: 100, max: 500)
#   --filter-locked=<true|false>      Filter by lock status
#
# ===================================================================
# INPUT VALIDATION
# ===================================================================
#
# Sort key:
#   Allowlist: ("username" "uid" "last_login")
#   Validation: Exact match from allowlist
#
# Limit:
#   Pattern: ^[0-9]+$
#   Range: 1-500
#   Default: 100
#
# Filter-locked:
#   Allowlist: ("true" "false" "")
#   Default: "" (no filter)
#
# ===================================================================
# SECURITY CONTROLS
# ===================================================================
#
# 1. set -euo pipefail (strict mode)
# 2. FORBIDDEN_CHARS check on all inputs
# 3. No shell expansion in commands
# 4. UID >= 1000 filter (system users excluded)
# 5. UID < 60000 filter (reserved UIDs excluded)
# 6. Password hash is NEVER included in output
# 7. Logger tag: adminui-users
#
# ===================================================================
# OUTPUT FORMAT (JSON)
# ===================================================================
#
# {
#   "status": "success",
#   "total_users": <int>,
#   "returned_users": <int>,
#   "sort_by": "<sort_key>",
#   "users": [
#     {
#       "username": "<string>",
#       "uid": <int>,
#       "gid": <int>,
#       "gecos": "<string>",
#       "home": "<string>",
#       "shell": "<string>",
#       "groups": ["<string>", ...],
#       "locked": <bool>,
#       "last_login": "<string|null>"
#     }
#   ],
#   "timestamp": "<ISO8601>"
# }
#
# ===================================================================
# DATA SOURCES
# ===================================================================
#
# - getent passwd         : User list with UID/GID/home/shell
# - id -Gn <username>     : Group membership
# - passwd -S <username>  : Lock status (L=locked, P=set, NP=no password)
# - lastlog -u <username> : Last login time
#
# ===================================================================
# ERROR CASES
# ===================================================================
#
# Invalid sort key:
#   Exit: 1
#   Output: {"status": "error", "message": "Invalid sort key"}
#
# Invalid limit:
#   Exit: 1
#   Output: {"status": "error", "message": "Invalid limit value"}
#
# getent failure:
#   Exit: 1
#   Output: {"status": "error", "message": "Failed to retrieve user list"}
#
# ===================================================================
# LOGGING
# ===================================================================
#
# Success: "User list retrieved: total=N, returned=N, caller=<user>"
# Error:   "ERROR: <description>"
# Security: "SECURITY: <description> - caller=<user>"
#
# ===================================================================
# TEST CASES (Required)
# ===================================================================
#
# Normal:
#   1. List all users (no options)
#   2. List with --sort=uid
#   3. List with --sort=last_login
#   4. List with --limit=5
#   5. List with --filter-locked=true
#   6. List with --filter-locked=false
#   7. Combination: --sort=uid --limit=10
#
# Security:
#   8. Verify system users (UID < 1000) are excluded
#   9. Verify root is excluded
#   10. Verify nobody (UID 65534) is excluded
#   11. Verify password hashes are not in output
#   12. FORBIDDEN_CHARS in --sort value rejected
#   13. FORBIDDEN_CHARS in --limit value rejected
#
# Error:
#   14. Invalid sort key rejected
#   15. Non-numeric limit rejected
#   16. Limit exceeding max (500) capped
#   17. Negative limit rejected
#   18. Unknown option rejected
