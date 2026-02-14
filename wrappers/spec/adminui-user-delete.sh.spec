# Wrapper Specification: adminui-user-delete.sh
#
# Created: 2026-02-14
# Author: users-planner (v03-planning-team)
# Phase: v0.3 Phase 2 (Write Operations)
# Risk Level: CRITICAL
# Sudo Required: YES
# Approval Required: YES (Admin role ONLY)
#
# ===================================================================
# PURPOSE
# ===================================================================
#
# Delete a user account from the Linux system.
# This is a CRITICAL-RISK operation that requires:
#   1. Prior approval from Admin role (not Approver)
#   2. sudo privilege for userdel execution
#   3. Safety checks (active sessions, running processes)
#   4. Optional home directory backup before deletion
#
# ===================================================================
# INSTALLATION
# ===================================================================
#
# Location: /usr/local/sbin/adminui-user-delete.sh
# Owner: root:root
# Permissions: 0755
# sudoers: adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-delete.sh
#
# ===================================================================
# USAGE
# ===================================================================
#
# sudo /usr/local/sbin/adminui-user-delete.sh \
#   --username=<name> \
#   [--remove-home] \
#   [--backup-home] \
#   [--force-logout]
#
# ===================================================================
# INPUT VALIDATION
# ===================================================================
#
# Username:
#   Pattern: ^[a-z_][a-z0-9_-]{0,31}$
#   FORBIDDEN_CHARS check
#   Must exist in system (getent passwd)
#   UID must be >= 1000 (system user protection)
#   UID must be < 60000 (reserved UID protection)
#
# --remove-home:
#   Boolean flag (no value)
#   If set, home directory is removed after deletion
#   If --backup-home is also set, backup is performed first
#
# --backup-home:
#   Boolean flag (no value)
#   Creates tar.gz backup at /var/backups/adminui/users/<username>_<timestamp>.tar.gz
#   Recommended when --remove-home is used
#
# --force-logout:
#   Boolean flag (no value)
#   If set, kills user's active sessions before deletion
#   Without this flag, deletion is rejected if user has active sessions
#
# ===================================================================
# SECURITY CONTROLS
# ===================================================================
#
# 1.  set -euo pipefail
# 2.  Username format validation
# 3.  FORBIDDEN_CHARS check
# 4.  UID >= 1000 check (system user protection)
# 5.  UID < 60000 check (reserved UID protection)
# 6.  Active session check (who | grep)
# 7.  Running process check (ps -u <user>)
# 8.  Home directory backup before removal (if requested)
# 9.  userdel via array execution (no shell expansion)
# 10. Logger tag: adminui-users
# 11. Full audit trail: username, uid, caller, removal options
#
# ===================================================================
# EXECUTION FLOW
# ===================================================================
#
# 1. Parse arguments
# 2. Validate username format
# 3. Verify user exists (getent passwd)
# 4. Verify UID >= 1000 and < 60000
# 5. Check for active login sessions
#    - If active and --force-logout not set: REJECT
#    - If active and --force-logout set: kill sessions
# 6. Check for running processes (warning only)
# 7. If --backup-home: create backup of home directory
#    - tar -czf /var/backups/adminui/users/<user>_<ts>.tar.gz /home/<user>
# 8. Execute: userdel [-r] <username>
#    - -r only if --remove-home is set
# 9. Verify user deleted (id <username> should fail)
# 10. Output JSON result
# 11. Log success with all details
#
# ===================================================================
# OUTPUT FORMAT (JSON)
# ===================================================================
#
# Success:
# {
#   "status": "success",
#   "message": "User deleted successfully",
#   "deleted_user": {
#     "username": "<string>",
#     "uid": <int>,
#     "home_removed": <bool>,
#     "home_backed_up": <bool>,
#     "backup_path": "<string|null>",
#     "sessions_killed": <int>
#   },
#   "timestamp": "<ISO8601>"
# }
#
# Error:
# {
#   "status": "error",
#   "message": "<error description>",
#   "timestamp": "<ISO8601>"
# }
#
# ===================================================================
# LINUX COMMANDS USED
# ===================================================================
#
# getent passwd <username>  : Verify user exists, get UID
# id -u <username>          : Get UID for range check
# who                       : Check active sessions
# ps -u <username>          : Check running processes
# pkill -u <username>       : Kill user sessions (if --force-logout)
# tar -czf <dst> <src>      : Backup home directory
# userdel [-r] <username>   : Delete user account
# id <username>             : Verify deletion (should fail)
#
# ===================================================================
# ERROR CASES
# ===================================================================
#
# User does not exist:
#   Exit: 1, Output: {"status":"error","message":"User not found: <name>"}
#
# System user (UID < 1000):
#   Exit: 1, Output: {"status":"error","message":"Cannot delete system user (UID < 1000)"}
#   Log: "SECURITY: System user deletion blocked - user=<name>, uid=<uid>, caller=<caller>"
#
# User has active sessions (no --force-logout):
#   Exit: 1, Output: {"status":"error","message":"User has active sessions. Use --force-logout"}
#
# Backup directory creation failure:
#   Exit: 1, Output: {"status":"error","message":"Failed to create backup directory"}
#
# Backup failure:
#   Exit: 1, Output: {"status":"error","message":"Failed to backup home directory"}
#   NOTE: User is NOT deleted if backup fails
#
# userdel failure:
#   Exit: 1, Output: {"status":"error","message":"Failed to delete user"}
#
# ===================================================================
# LOGGING
# ===================================================================
#
# Pre-execution:
#   "User deletion requested: username=<name>, uid=<uid>, remove_home=<bool>, backup=<bool>, caller=<caller>"
#
# Active session warning:
#   "WARN: User has active sessions: username=<name>, sessions=<count>"
#
# Backup:
#   "Home directory backed up: user=<name>, path=<backup_path>, size=<bytes>"
#
# Success:
#   "User deleted successfully: username=<name>, uid=<uid>, home_removed=<bool>, caller=<caller>"
#
# Security:
#   "SECURITY: System user deletion blocked - user=<name>, uid=<uid>, caller=<caller>"
#
# ===================================================================
# TEST CASES (Required)
# ===================================================================
#
# Normal:
#   1. Delete existing user (no home removal)
#   2. Delete existing user with --remove-home
#   3. Delete existing user with --backup-home --remove-home
#   4. Verify user no longer exists after deletion
#   5. Verify home directory removed when --remove-home
#   6. Verify backup file created when --backup-home
#   7. Verify backup file contains correct data
#
# Security (CRITICAL):
#   8.  Delete root (UID 0) -> rejected
#   9.  Delete www-data (UID < 1000) -> rejected
#   10. Delete nobody (UID 65534) -> rejected
#   11. Delete postgres (system service) -> rejected
#   12. Username with injection: "user;rm -rf /" -> rejected
#   13. Username with injection: "user$(id)" -> rejected
#   14. Verify deletion does not affect other users
#   15. Verify backup path cannot be manipulated
#
# Edge cases:
#   16. Delete user with active session (no --force-logout) -> rejected
#   17. Delete user with active session (--force-logout) -> success
#   18. Delete user with running processes -> warning + proceed
#   19. Delete non-existent user -> error
#   20. Delete same user twice -> error on second attempt
