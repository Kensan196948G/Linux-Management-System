@echo off
setlocal
cd /d "%~dp0\..\.."
node "docs\scripts\run-shared-drive-checks.mjs" %*
exit /b %errorlevel%
