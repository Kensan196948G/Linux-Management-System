# Wrapper Specification: adminui-group-list.sh
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
# List non-system groups (GID >= 1000, < 60000) in JSON format.
# Read-only operation, no system modification.
#
# ===================================================================
# INSTALLATION
# ===================================================================
#
# Location: /usr/local/sbin/adminui-group-list.sh
# Owner: root:root
# Permissions: 0755
# sudoers: Not required (read-only)
#
# ===================================================================
# USAGE
# ===================================================================
#
# adminui-group-list.sh [OPTIONS]
#
# Options:
#   --sort=<name|gid|member_count>  Sort key (default: name)
#   --limit=<N>                     Limit results (default: 100, max: 500)
#
# ===================================================================
# INPUT VALIDATION
# ===================================================================
#
# Sort key:
#   Allowlist: ("name" "gid" "member_count")
#
# Limit:
#   Pattern: ^[0-9]+$
#   Range: 1-500
#
# ===================================================================
# SECURITY CONTROLS
# ===================================================================
#
# 1. set -euo pipefail
# 2. FORBIDDEN_CHARS check on all inputs
# 3. GID >= 1000 filter (system groups excluded)
# 4. GID < 60000 filter
# 5. Logger tag: adminui-users
#
# ===================================================================
# OUTPUT FORMAT (JSON)
# ===================================================================
#
# {
#   "status": "success",
#   "total_groups": <int>,
#   "returned_groups": <int>,
#   "sort_by": "<sort_key>",
#   "groups": [
#     {
#       "name": "<string>",
#       "gid": <int>,
#       "members": ["<string>", ...],
#       "member_count": <int>
#     }
#   ],
#   "timestamp": "<ISO8601>"
# }
#
# ===================================================================
# DATA SOURCES
# ===================================================================
#
# - getent group           : Group list with GID and members
# - getent passwd          : Cross-reference primary groups
#
# ===================================================================
# TEST CASES (Required)
# ===================================================================
#
# Normal:
#   1. List all groups (no options)
#   2. List with --sort=gid
#   3. List with --sort=member_count
#   4. List with --limit=5
#   5. Verify members list is correct
#
# Security:
#   6. System groups (GID < 1000) excluded
#   7. root group excluded
#   8. sudo group excluded
#   9. FORBIDDEN_CHARS in sort value rejected
#
# Error:
#   10. Invalid sort key rejected
#   11. Non-numeric limit rejected
