# Wrapper Specification: adminui-group-modify.sh
#
# Created: 2026-02-14
# Author: users-planner (v03-planning-team)
# Phase: v0.3 Phase 2 (Write Operations)
# Risk Level: HIGH
# Sudo Required: YES
# Approval Required: YES (Approver or Admin role)
#
# ===================================================================
# PURPOSE
# ===================================================================
#
# Modify group membership: add or remove users from a group.
# This is a HIGH-RISK operation because group membership changes
# can affect user privileges.
#
# ===================================================================
# INSTALLATION
# ===================================================================
#
# Location: /usr/local/sbin/adminui-group-modify.sh
# Owner: root:root
# Permissions: 0755
# sudoers: adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-group-modify.sh
#
# ===================================================================
# USAGE
# ===================================================================
#
# sudo /usr/local/sbin/adminui-group-modify.sh \
#   --group=<groupname> \
#   --action=<add|remove> \
#   --user=<username>
#
# ===================================================================
# INPUT VALIDATION
# ===================================================================
#
# Group name:
#   Pattern: ^[a-z_][a-z0-9_-]{0,31}$
#   FORBIDDEN_GROUPS check (35+ entries - cannot add users to forbidden groups)
#   FORBIDDEN_CHARS check
#   Must exist (getent group)
#   GID must be >= 1000
#   GID must be < 60000
#
# Action:
#   Allowlist: ("add" "remove")
#   Exact match only
#
# Username:
#   Pattern: ^[a-z_][a-z0-9_-]{0,31}$
#   FORBIDDEN_CHARS check
#   Must exist (getent passwd)
#   UID must be >= 1000
#   UID must be < 60000
#
# ===================================================================
# SECURITY CONTROLS
# ===================================================================
#
# 1.  set -euo pipefail
# 2.  Group name format validation + FORBIDDEN_GROUPS check
# 3.  Username format validation
# 4.  FORBIDDEN_CHARS check on all inputs
# 5.  GID >= 1000 check (system group protection)
# 6.  UID >= 1000 check (system user protection)
# 7.  FORBIDDEN_GROUPS check prevents adding users to sudo/docker/etc.
# 8.  Action allowlist (only "add" or "remove")
# 9.  usermod via array execution
# 10. Logger tag: adminui-users
#
# ===================================================================
# EXECUTION FLOW
# ===================================================================
#
# For --action=add:
# 1. Parse arguments
# 2. Validate group name, action, username
# 3. Verify group exists and GID >= 1000
# 4. Check group is NOT in FORBIDDEN_GROUPS
# 5. Verify user exists and UID >= 1000
# 6. Check user is not already a member
# 7. Execute: usermod -aG <groupname> <username>
# 8. Verify membership (id -Gn <username>)
# 9. Output JSON result
#
# For --action=remove:
# 1. Parse arguments
# 2. Validate group name, action, username
# 3. Verify group exists and GID >= 1000
# 4. Verify user exists and UID >= 1000
# 5. Check user IS a member (otherwise error)
# 6. Check group is NOT user's primary group
# 7. Execute: gpasswd -d <username> <groupname>
# 8. Verify removal (id -Gn <username>)
# 9. Output JSON result
#
# ===================================================================
# OUTPUT FORMAT (JSON)
# ===================================================================
#
# Success (add):
# {
#   "status": "success",
#   "message": "User added to group",
#   "details": {
#     "username": "<string>",
#     "group": "<string>",
#     "action": "add",
#     "current_groups": ["<string>", ...]
#   },
#   "timestamp": "<ISO8601>"
# }
#
# Success (remove):
# {
#   "status": "success",
#   "message": "User removed from group",
#   "details": {
#     "username": "<string>",
#     "group": "<string>",
#     "action": "remove",
#     "current_groups": ["<string>", ...]
#   },
#   "timestamp": "<ISO8601>"
# }
#
# ===================================================================
# LINUX COMMANDS USED
# ===================================================================
#
# getent group <name>           : Verify group exists, get GID and members
# getent passwd <name>          : Verify user exists
# id -u <username>              : Get UID for range check
# id -Gn <username>             : Get current group list
# usermod -aG <group> <user>    : Add user to group (-a = append, -G = supplementary)
# gpasswd -d <user> <group>     : Remove user from group
#
# ===================================================================
# ERROR CASES
# ===================================================================
#
# Group does not exist:
#   Exit: 1
#
# Group is forbidden (sudo, docker, etc.):
#   Exit: 1
#   Log: "SECURITY: Forbidden group modification blocked"
#
# System group (GID < 1000):
#   Exit: 1
#   Log: "SECURITY: System group modification blocked"
#
# User does not exist:
#   Exit: 1
#
# System user (UID < 1000):
#   Exit: 1
#   Log: "SECURITY: System user group modification blocked"
#
# Invalid action:
#   Exit: 1
#
# User already in group (add):
#   Exit: 1
#
# User not in group (remove):
#   Exit: 1
#
# Cannot remove primary group:
#   Exit: 1
#
# ===================================================================
# TEST CASES (Required)
# ===================================================================
#
# Normal:
#   1. Add user to valid group
#   2. Remove user from valid group
#   3. Verify membership after add
#   4. Verify membership after remove
#
# Security (CRITICAL):
#   5.  Add user to "sudo" group -> REJECTED
#   6.  Add user to "wheel" group -> REJECTED
#   7.  Add user to "docker" group -> REJECTED
#   8.  Add user to "root" group -> REJECTED
#   9.  Add user to "shadow" group -> REJECTED
#   10. Add user to "lxd" group -> REJECTED
#   11. Add user to "adm" group -> REJECTED
#   12. Modify system group (GID < 1000) -> REJECTED
#   13. Modify system user (UID < 1000) -> REJECTED
#   14. Group name with injection chars -> rejected
#   15. Username with injection chars -> rejected
#   16. Invalid action value -> rejected
#
# Error:
#   17. Non-existent group -> error
#   18. Non-existent user -> error
#   19. User already in group (add) -> error
#   20. User not in group (remove) -> error
#   21. Remove user from primary group -> error
#   22. Missing required arguments -> error
