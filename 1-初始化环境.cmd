@echo off
chcp 65001 >nul
title VIDU-CLI-SKILL - 初始化
cd /d "%~dp0"
setlocal

echo ============================================================
echo   VIDU-CLI-SKILL  一次性环境检查
echo   跑一次就好，以后不用再跑
echo ============================================================
echo.

rem ---- 找 Python：py -^> python -^> python3 ----
set "RT="
for %%P in (py.exe) do if not defined RT set "RT=%%~$PATH:P"
for %%P in (python.exe) do if not defined RT set "RT=%%~$PATH:P"
for %%P in (python3.exe) do if not defined RT set "RT=%%~$PATH:P"
if defined RT goto ready

echo [1/2] 没找到 Python，尝试自动安装...
echo.
set "WINGET="
for %%P in (winget.exe) do if not defined WINGET set "WINGET=%%~$PATH:P"
if not defined WINGET goto manual

"%WINGET%" install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
goto recheck

:recheck
set "RT="
for %%P in (py.exe) do if not defined RT set "RT=%%~$PATH:P"
for %%P in (python.exe) do if not defined RT set "RT=%%~$PATH:P"
for %%P in (python3.exe) do if not defined RT set "RT=%%~$PATH:P"
if defined RT goto ready

echo.
echo     Python 装好了，但这个窗口还看不到它 —— Windows 的正常现象。
echo     关掉这个窗口，再双击一次就行了。
echo.
pause
exit /b 0

:manual
echo.
echo     这台机器没有 winget，装不了 Python。
echo     下面会打开下载页，装的时候记得勾上 "Add python.exe to PATH"。
echo.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:ready
echo [OK] Python: %RT%
"%RT%" --version
echo.
"%RT%" "scripts\init_env.py" %*
echo.
pause
exit /b 0
