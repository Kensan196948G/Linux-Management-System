# Wrapper Specification: adminui-group-add.sh
#
# Created: 2026-02-14
# Author: users-planner (v03-planning-team)
# Phase: v0.3 Phase 2 (Write Operations)
# Risk Level: MEDIUM
# Sudo Required: YES
# Approval Required: YES (Approver or Admin role)
#
# ===================================================================
# PURPOSE
# ===================================================================
#
# Create a new group on the Linux system.
# Requires approval workflow before execution.
#
# ===================================================================
# INSTALLATION
# ===================================================================
#
# Location: /usr/local/sbin/adminui-group-add.sh
# Owner: root:root
# Permissions: 0755
# sudoers: adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-group-add.sh
#
# ===================================================================
# USAGE
# ===================================================================
#
# sudo /usr/local/sbin/adminui-group-add.sh --name=<groupname>
#
# ===================================================================
# INPUT VALIDATION
# ===================================================================
#
# Group name:
#   Pattern: ^[a-z_][a-z0-9_-]{0,31}$
#   FORBIDDEN_GROUPS check (35+ entries)
#   FORBIDDEN_USERNAMES check (prevent user/group name collision)
#   FORBIDDEN_CHARS check
#   Must NOT already exist (getent group)
#
# ===================================================================
# SECURITY CONTROLS
# ===================================================================
#
# 1.  set -euo pipefail
# 2.  Group name format validation
# 3.  FORBIDDEN_GROUPS check
# 4.  FORBIDDEN_USERNAMES check (collision prevention)
# 5.  FORBIDDEN_CHARS check
# 6.  Existence check (must not already exist)
# 7.  groupadd via array execution
# 8.  GID auto-assigned (>= 1000)
# 9.  Logger tag: adminui-users
#
# ===================================================================
# EXECUTION FLOW
# ===================================================================
#
# 1. Parse --name argument
# 2. Validate group name format
# 3. Check against FORBIDDEN_GROUPS
# 4. Check against FORBIDDEN_USERNAMES
# 5. Verify group does not exist
# 6. Execute: groupadd <groupname>
# 7. Verify group created (getent group <groupname>)
# 8. Output JSON result
#
# ===================================================================
# OUTPUT FORMAT (JSON)
# ===================================================================
#
# Success:
# {
#   "status": "success",
#   "message": "Group created successfully",
#   "group": {
#     "name": "<string>",
#     "gid": <int>
#   },
#   "timestamp": "<ISO8601>"
# }
#
# ===================================================================
# LINUX COMMANDS USED
# ===================================================================
#
# getent group <name>  : Check existence
# groupadd <name>      : Create group
#
# ===================================================================
# TEST CASES (Required)
# ===================================================================
#
# Normal:
#   1. Create valid group
#   2. Verify group exists with correct GID (>= 1000)
#
# Security:
#   3. FORBIDDEN_GROUPS: "sudo" -> rejected
#   4. FORBIDDEN_GROUPS: "docker" -> rejected
#   5. FORBIDDEN_GROUPS: "root" -> rejected
#   6. FORBIDDEN_GROUPS: "wheel" -> rejected
#   7. FORBIDDEN_USERNAMES collision: "admin" -> rejected
#   8. Group name with injection chars -> rejected
#   9. Group already exists -> rejected
#
# Error:
#   10. Invalid group name format -> rejected
#   11. Empty group name -> rejected
#   12. Missing --name argument -> error
