# Wrapper Specification: adminui-user-passwd.sh
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
# Change a user's password.
# Password hash is provided pre-hashed (bcrypt) via stdin.
# This script never handles plain-text passwords.
#
# ===================================================================
# INSTALLATION
# ===================================================================
#
# Location: /usr/local/sbin/adminui-user-passwd.sh
# Owner: root:root
# Permissions: 0755
# sudoers: adminui ALL=(root) NOPASSWD: /usr/local/sbin/adminui-user-passwd.sh
#
# ===================================================================
# USAGE
# ===================================================================
#
# echo "$PASSWORD_HASH" | sudo /usr/local/sbin/adminui-user-passwd.sh \
#   --username=<name>
#
# Password hash is ALWAYS read from stdin (security requirement).
#
# ===================================================================
# INPUT VALIDATION
# ===================================================================
#
# Username:
#   Pattern: ^[a-z_][a-z0-9_-]{0,31}$
#   FORBIDDEN_CHARS check
#   Must exist in system
#   UID must be >= 1000
#   UID must be < 60000
#
# Password Hash (stdin):
#   Pattern: ^\$2[aby]\$[0-9]{2}\$.{53}$ (bcrypt format)
#   Must not be empty
#   Must be exactly one line
#
# ===================================================================
# SECURITY CONTROLS
# ===================================================================
#
# 1.  set -euo pipefail
# 2.  Password hash via stdin ONLY (never as argument)
# 3.  Username format validation
# 4.  UID range check (>= 1000, < 60000)
# 5.  chpasswd -e for pre-hashed password
# 6.  Password hash NEVER logged
# 7.  No echo of stdin content
# 8.  Logger tag: adminui-users
#
# ===================================================================
# EXECUTION FLOW
# ===================================================================
#
# 1. Parse --username argument
# 2. Read password hash from stdin
# 3. Validate username format
# 4. Verify user exists and UID >= 1000
# 5. Validate password hash format (bcrypt)
# 6. Execute: echo "<username>:<hash>" | chpasswd -e
# 7. Verify password change (passwd -S <username>)
# 8. Output JSON result
# 9. Log success (without any password data)
#
# ===================================================================
# OUTPUT FORMAT (JSON)
# ===================================================================
#
# Success:
# {
#   "status": "success",
#   "message": "Password changed successfully",
#   "user": {
#     "username": "<string>",
#     "uid": <int>,
#     "password_status": "set"
#   },
#   "timestamp": "<ISO8601>"
# }
#
# ===================================================================
# ERROR CASES
# ===================================================================
#
# User does not exist:
#   Exit: 1
#
# System user (UID < 1000):
#   Exit: 1
#   Log: "SECURITY: System user password change blocked"
#
# Invalid hash format:
#   Exit: 1
#
# chpasswd failure:
#   Exit: 1
#
# Empty stdin:
#   Exit: 1
#
# ===================================================================
# TEST CASES (Required)
# ===================================================================
#
# Normal:
#   1. Change password for valid user
#   2. Verify password status changes to "set"
#   3. Verify old password no longer works
#
# Security:
#   4. Change root password -> rejected
#   5. Change system user password -> rejected
#   6. Invalid hash format -> rejected
#   7. Password hash NOT in ps output
#   8. Password hash NOT in any logs
#   9. Username with injection chars -> rejected
#
# Error:
#   10. Non-existent user -> error
#   11. Empty stdin -> error
#   12. Multiple lines on stdin -> error (only first line used)
