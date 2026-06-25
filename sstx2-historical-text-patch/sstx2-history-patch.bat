@echo off
chcp 65001 >nul
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "ACTION=%~1"
set "GAME_ROOT=%~2"

if "%ACTION%"=="" goto menu
if /I "%ACTION%"=="all" goto run
if /I "%ACTION%"=="phonetic" goto run
if /I "%ACTION%"=="restore" goto run
goto usage

:menu
echo.
echo 《盛世天下：女帝篇》历史称谓补丁
echo.
echo   1. 全部替换
echo   2. 谐音替换
echo   3. 还原原文
echo.
choice /C 123 /N /M "请选择操作: "
if errorlevel 3 goto menu_restore
if errorlevel 2 goto menu_phonetic
if errorlevel 1 goto menu_all
goto menu

:menu_all
set "ACTION=all"
goto run

:menu_phonetic
set "ACTION=phonetic"
goto run

:menu_restore
set "ACTION=restore"
goto run

:run
if "%GAME_ROOT%"=="" call :find_game_root
if "%GAME_ROOT%"=="" goto no_game_root
if not exist "%GAME_ROOT%\Data\StreamingAssets" goto bad_game_root
call :ensure_admin
if errorlevel 1 exit /b %ERRORLEVEL%

call :run_python
set "EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %EXIT_CODE%

:find_game_root
if not exist "%SCRIPT_DIR%Data\StreamingAssets" goto find_parent
set "GAME_ROOT=%SCRIPT_DIR:~0,-1%"
exit /b 0

:find_parent
for %%I in ("%SCRIPT_DIR%..") do set "PARENT_DIR=%%~fI"
if not exist "%PARENT_DIR%\Data\StreamingAssets" exit /b 0
set "GAME_ROOT=%PARENT_DIR%"
exit /b 0

:ensure_admin
net session >nul 2>nul
if not errorlevel 1 exit /b 0
echo.
echo 需要管理员权限来屏蔽线上字幕域名。
echo 即将以管理员权限重新打开补丁窗口。
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList @('%ACTION%','%GAME_ROOT%') -Verb RunAs"
exit /b 1

:run_python
if not exist "%SCRIPT_DIR%python\python.exe" goto try_py
"%SCRIPT_DIR%python\python.exe" "%SCRIPT_DIR%patch_sstx2_history.py" %ACTION% "%GAME_ROOT%"
exit /b %ERRORLEVEL%

:try_py
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 "%SCRIPT_DIR%patch_sstx2_history.py" %ACTION% "%GAME_ROOT%"
exit /b %ERRORLEVEL%

:try_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python "%SCRIPT_DIR%patch_sstx2_history.py" %ACTION% "%GAME_ROOT%"
exit /b %ERRORLEVEL%

:no_python
echo 未找到 Python。请安装 Python 3，或把嵌入式 Python 文件夹放到本补丁目录下。
exit /b 2

:no_game_root
echo.
echo 未找到游戏根目录。
echo 请把整个 sstx2-historical-text-patch 文件夹放到游戏根目录下，和 Data 文件夹同级。
echo.
echo 正确结构:
echo   roadtoempress2\Data
echo   roadtoempress2\sstx2-historical-text-patch
echo.
pause
exit /b 2

:bad_game_root
echo.
echo 游戏根目录无效:
echo   %GAME_ROOT%
echo.
echo 该目录下没有 Data\StreamingAssets。
pause
exit /b 2

:usage
echo 用法:
echo   %~nx0 all "X:\Games\roadtoempress2"
echo   %~nx0 phonetic "X:\Games\roadtoempress2"
echo   %~nx0 restore "X:\Games\roadtoempress2"
exit /b 2
