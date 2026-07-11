@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title 陌城qqbot框架

echo ========================================
echo    陌城qqbot框架 - 一键启动
echo ========================================
echo.

cd /d "%~dp0"

:: ============ 检查 Python ============
echo [1/6] 正在检查 Python 环境...

where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python!
    echo 请安装 Python 3.8 以上版本
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    goto :error
)

:: 获取 Python 版本
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PYVER=%%v"

if not defined PYVER (
    echo [错误] 无法检测 Python 版本
    goto :error
)

:: 解析主版本号和次版本号
set "PYMAJOR="
set "PYMINOR="
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set "PYMAJOR=%%a"
    set "PYMINOR=%%b"
)

if not defined PYMAJOR (
    echo [错误] 无法解析 Python 版本: %PYVER%
    goto :error
)

if %PYMAJOR% LSS 3 (
    echo [错误] Python 版本过低: %PYVER%,需要 3.8 以上
    goto :error
)

if %PYMAJOR% EQU 3 if %PYMINOR% LSS 8 (
    echo [错误] Python 版本过低: %PYVER%,需要 3.8 以上
    goto :error
)

echo 已检测到 Python %PYVER%

:: ============ 创建虚拟环境 ============
echo.
echo [2/6] 正在设置虚拟环境...

if not exist "venv\Scripts\python.exe" (
    echo 正在创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败!
        goto :error
    )
    echo 虚拟环境创建完成
) else (
    echo 虚拟环境已存在
)

:: ============ 安装依赖 ============
echo.
echo [3/6] 正在安装依赖...

set "PY=venv\Scripts\python.exe"

:: 升级 pip(使用 python -m pip 避免非 ASCII 路径导致启动器损坏)
%PY% -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple -q 2>nul

:: 安装依赖,最多重试 3 次
set "RETRY=0"
set "MAX_RETRY=3"

:install_deps
set /a RETRY+=1
echo 正在安装依赖(第 !RETRY! 次尝试)...
%PY% -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt -q
if errorlevel 1 (
    if !RETRY! LSS %MAX_RETRY% (
        echo 安装失败,正在重试...
        goto install_deps
    ) else (
        echo [错误] 安装依赖失败,已重试 %MAX_RETRY% 次
        echo 请检查网络连接,或手动执行:
        echo   venv\Scripts\python.exe -m pip install -r requirements.txt
        goto :error
    )
)
echo 依赖安装完成

:: ============ 检查 WebUI ============
echo.
echo [4/6] 正在检查 WebUI...

if exist "webui\frontend\dist\index.html" (
    echo WebUI 已构建,跳过
    goto :skip_webui
)

where node >nul 2>&1
if errorlevel 1 (
    echo [警告] 未找到 Node.js,跳过 WebUI 构建
    echo 如需 WebUI,请安装 Node.js 18 以上版本: https://nodejs.org/
    goto :skip_webui
)

if not exist "webui\frontend\node_modules" (
    echo 正在安装前端依赖...
    cd webui\frontend
    call npm install --registry https://registry.npmmirror.com 2>nul
    if errorlevel 1 (
        echo [警告] npm install 失败,WebUI 可能无法使用
        cd ..\..
        goto :skip_webui
    )
    cd ..\..
)

echo 正在构建前端...
cd webui\frontend
call npx vite build 2>nul
if errorlevel 1 (
    echo [警告] WebUI 构建失败,WebUI 可能无法使用
    cd ..\..
    goto :skip_webui
)
cd ..\..
echo WebUI 构建完成

:skip_webui

:: ============ 检测版本更新 ============
echo.
echo [5/6] 检测版本更新...

REM 调用 updater_cli --check 获取 JSON 结果
set "UPDATE_JSON="
for /f "delims=" %%i in ('"%PY%" -m core.updater_cli --check 2^>nul') do set "UPDATE_JSON=%%i"

REM 检查 has_update 字段
echo %UPDATE_JSON% | findstr /C:"\"has_update\": true" >nul
if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   检测到新版本可用!
    for /f "tokens=2 delims=:," %%a in ('echo %UPDATE_JSON% ^| findstr /C:"latest_version"') do set "LATEST_VER=%%~a"
    for /f "tokens=2 delims=:," %%a in ('echo %UPDATE_JSON% ^| findstr /C:"version_name"') do set "LATEST_NAME=%%~a"
    echo   最新版本: !LATEST_VER!
    echo   版本名称: !LATEST_NAME!
    echo ========================================
    set /p "UPDATE_CHOICE=是否立即更新? (y/n): "
    if /i "!UPDATE_CHOICE!"=="y" (
        echo 正在更新...
        "%PY%" -m core.updater_cli --force
        if errorlevel 1 (
            echo [警告] 更新失败,将使用当前版本启动
        )
    ) else (
        echo 已跳过更新
    )
) else (
    echo 当前已是最新版本
)

:: ============ 启动 Bot ============
echo.
echo [6/6] 正在启动陌城qqbot框架...
echo.

if not exist "config\config.json" (
    echo ========================================
    echo   首次运行 - 正在生成默认配置...
    echo ========================================
    echo.
)

"%PY%" main.py

if errorlevel 1 (
    echo.
    echo [错误] 框架异常退出
)

echo.
echo ========================================
echo   陌城qqbot框架 已停止
echo ========================================
echo.
pause
exit /b 0

:error
echo.
echo 启动失败,请检查上方的错误信息
echo.
pause
exit /b 1
