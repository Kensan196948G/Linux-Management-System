@echo off
setlocal
cd /d "%~dp0\.."
node "docs\scripts\build-webui-singlefile.mjs"
if errorlevel 1 exit /b %errorlevel%
echo.
echo Built: "%CD%\webui-sample\index.singlefile.html"
