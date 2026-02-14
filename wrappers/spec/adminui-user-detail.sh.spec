# Wrapper Specification: adminui-user-detail.sh
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
# Retrieve detailed information for a single user by username or UID.
# Read-only operation, no system modification.
#
# ===================================================================
# INSTALLATION
# ===================================================================
#
# Location: /usr/local/sbin/adminui-user-detail.sh
# Owner: root:root
# Permissions: 0755
# sudoers: Not required (read-only)
#
# ===================================================================
# USAGE
# ===================================================================
#
# adminui-user-detail.sh --username=<name>
# adminui-user-detail.sh --uid=<number>
#
# Exactly one of --username or --uid must be provided.
#
# ===================================================================
# INPUT VALIDATION
# ===================================================================
#
# Username:
#   Pattern: ^[a-z_][a-z0-9_-]{0,31}$
#   Forbidden chars: ;|&$()` ><*?{}[]\'"
#   Must exist in system (getent passwd check)
#
# UID:
#   Pattern: ^[0-9]+$
#   Range: 1000-59999
#   Must exist in system (getent passwd check)
#
# ===================================================================
# SECURITY CONTROLS
# ===================================================================
#
# 1. set -euo pipefail
# 2. Username format validation (allowlist pattern)
# 3. FORBIDDEN_CHARS check
# 4. UID range check: must be >= 1000 and < 60000
# 5. If username provided, resolve to UID and verify range
# 6. Password hash is NEVER included in output
# 7. /etc/shadow is NEVER accessed
# 8. Logger tag: adminui-users
#
# ===================================================================
# OUTPUT FORMAT (JSON)
# ===================================================================
#
# {
#   "status": "success",
#   "user": {
#     "username": "<string>",
#     "uid": <int>,
#     "gid": <int>,
#     "primary_group": "<string>",
#     "gecos": "<string>",
#     "home": "<string>",
#     "shell": "<string>",
#     "groups": ["<string>", ...],
#     "locked": <bool>,
#     "password_status": "<set|locked|no_password>",
#     "last_login": "<string|null>",
#     "last_password_change": "<string|null>",
#     "account_expires": "<string|null>",
#     "home_dir_exists": <bool>,
#     "home_dir_size_kb": <int|null>,
#     "running_processes": <int>
#   },
#   "timestamp": "<ISO8601>"
# }
#
# ===================================================================
# DATA SOURCES
# ===================================================================
#
# - getent passwd <user>          : Basic user info
# - id -Gn <user>                 : Group membership
# - id -gn <user>                 : Primary group name
# - passwd -S <user>              : Password/lock status
# - lastlog -u <user>             : Last login
# - chage -l <user>               : Password aging info (requires sudo for some fields)
# - du -sk /home/<user> 2>/dev/null : Home directory size
# - ps -u <user> --no-headers | wc -l : Running process count
#
# ===================================================================
# ERROR CASES
# ===================================================================
#
# Neither --username nor --uid provided:
#   Exit: 1
#   Output: {"status": "error", "message": "Either --username or --uid required"}
#
# Both --username and --uid provided:
#   Exit: 1
#   Output: {"status": "error", "message": "Only one of --username or --uid allowed"}
#
# Invalid username format:
#   Exit: 1
#   Output: {"status": "error", "message": "Invalid username format"}
#
# User not found:
#   Exit: 1
#   Output: {"status": "error", "message": "User not found"}
#
# System user (UID < 1000):
#   Exit: 1
#   Output: {"status": "error", "message": "Cannot query system user (UID < 1000)"}
#
# ===================================================================
# LOGGING
# ===================================================================
#
# Success: "User detail retrieved: user=<name>, uid=<uid>, caller=<user>"
# Error:   "ERROR: <description>"
# Security: "SECURITY: System user query blocked - user=<name>, uid=<uid>, caller=<user>"
#
# ===================================================================
# TEST CASES (Required)
# ===================================================================
#
# Normal:
#   1. Query by valid username
#   2. Query by valid UID
#   3. Verify all output fields present
#   4. Verify groups list is correct
#   5. Verify locked status matches passwd -S
#
# Security:
#   6. Query root by username -> rejected
#   7. Query root by UID (0) -> rejected
#   8. Query www-data (UID < 1000) -> rejected
#   9. Query nobody (UID 65534) -> rejected
#   10. Username with injection chars -> rejected
#   11. UID with non-numeric chars -> rejected
#   12. Verify no password hash in output
#
# Error:
#   13. Non-existent username -> error
#   14. Non-existent UID -> error
#   15. Empty username -> error
#   16. Both --username and --uid -> error
#   17. Neither --username nor --uid -> error
