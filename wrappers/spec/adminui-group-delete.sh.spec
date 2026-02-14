# Wrapper Specification: adminui-group-delete.sh
#
# Created: 2026-02-14
# Author: users-planner (v03-planning-team)
# Phase: v0.3 Phase 2 (Write Operations)
# Risk Level: HIGH
# Sudo Required: YES
# Approval Required: YES (Admin role ONLY)
#
# ===================================================================
# PURPOSE
# ===================================================================
#
# Delete a group from the Linux system.
# Requires Admin-level approval before execution.
# Cannot delete groups that are primary groups of existing users.
#
# ===================================================================
# INSTALLATION
# ===================================================================
#
# Location: /usr/local/sbin/adminui-group-delete.sh
# Owner: root:root
# Permissions: 0755
# sudoers: adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-group-delete.sh
#
# ===================================================================
# USAGE
# ===================================================================
#
# sudo /usr/local/sbin/adminui-group-delete.sh --name=<groupname>
#
# ===================================================================
# INPUT VALIDATION
# ===================================================================
#
# Group name:
#   Pattern: ^[a-z_][a-z0-9_-]{0,31}$
#   FORBIDDEN_CHARS check
#   Must exist (getent group)
#   GID must be >= 1000
#   GID must be < 60000
#   Must NOT be any user's primary group
#
# ===================================================================
# SECURITY CONTROLS
# ===================================================================
#
# 1.  set -euo pipefail
# 2.  Group name format validation
# 3.  FORBIDDEN_CHARS check
# 4.  GID >= 1000 check (system group protection)
# 5.  GID < 60000 check
# 6.  Primary group check (cannot delete if users depend on it)
# 7.  groupdel via array execution
# 8.  Logger tag: adminui-users
#
# ===================================================================
# EXECUTION FLOW
# ===================================================================
#
# 1. Parse --name argument
# 2. Validate group name format
# 3. Verify group exists (getent group)
# 4. Get GID and verify >= 1000 and < 60000
# 5. Check no users have this as primary group
#    - getent passwd | awk -F: '$4 == GID' must be empty
# 6. Execute: groupdel <groupname>
# 7. Verify group deleted
# 8. Output JSON result
#
# ===================================================================
# OUTPUT FORMAT (JSON)
# ===================================================================
#
# Success:
# {
#   "status": "success",
#   "message": "Group deleted successfully",
#   "deleted_group": {
#     "name": "<string>",
#     "gid": <int>,
#     "had_members": <int>
#   },
#   "timestamp": "<ISO8601>"
# }
#
# ===================================================================
# LINUX COMMANDS USED
# ===================================================================
#
# getent group <name>    : Verify existence, get GID and members
# getent passwd          : Check no primary group dependencies
# groupdel <name>        : Delete group
#
# ===================================================================
# ERROR CASES
# ===================================================================
#
# Group does not exist:
#   Exit: 1
#
# System group (GID < 1000):
#   Exit: 1
#   Log: "SECURITY: System group deletion blocked"
#
# Group is primary group of users:
#   Exit: 1
#   Output includes list of dependent users
#
# groupdel failure:
#   Exit: 1
#
# ===================================================================
# TEST CASES (Required)
# ===================================================================
#
# Normal:
#   1. Delete existing group with no members
#   2. Delete existing group with supplementary members (members lose membership)
#   3. Verify group no longer exists
#
# Security:
#   4. Delete system group (GID < 1000) -> rejected
#   5. Delete root group -> rejected
#   6. Delete sudo group -> rejected
#   7. Group name with injection chars -> rejected
#
# Error:
#   8. Delete non-existent group -> error
#   9. Delete group that is a primary group -> error
#   10. Missing --name argument -> error
