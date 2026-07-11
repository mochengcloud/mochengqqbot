#!/bin/bash

echo "========================================"
echo "   QQ群管机器人 - 一键启动"
echo "========================================"
echo ""

cd "$(dirname "$0")"

# ============ 检测 Python ============
echo "[1/6] 检测 Python 环境..."

if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "[错误] 未检测到 Python！"
    echo "请安装 Python 3.8 或更高版本"
    echo "Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "CentOS/RHEL: sudo yum install python3"
    exit 1
fi

# 检测 Python 版本 >= 3.8
PYVER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYMAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PYMINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 8 ]; }; then
    echo "[错误] Python 版本过低: $PYVER"
    echo "请升级到 Python 3.8 或更高版本"
    exit 1
fi

echo "Python $PYVER 检测通过"

# ============ 创建虚拟环境 ============
echo ""
echo "[2/6] 准备虚拟环境..."

if [ ! -f "venv/bin/python" ]; then
    echo "正在创建虚拟环境..."
    $PYTHON -m venv venv
    if [ $? -ne 0 ]; then
        echo "[错误] 创建虚拟环境失败！"
        echo "请确保已安装 python3-venv"
        echo "Ubuntu/Debian: sudo apt install python3-venv"
        exit 1
    fi
    echo "虚拟环境创建成功"
else
    echo "虚拟环境已存在"
fi

# ============ 安装依赖 ============
echo ""
echo "[3/6] 安装/更新依赖..."

PY=venv/bin/python
PIP=venv/bin/pip

# 升级 pip
$PY -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple -q 2>/dev/null

# 安装依赖，最多重试3次
RETRY=0
MAX_RETRY=3

while [ $RETRY -lt $MAX_RETRY ]; do
    RETRY=$((RETRY + 1))
    echo "正在安装依赖 (第 $RETRY 次)..."
    $PIP install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt -q
    if [ $? -eq 0 ]; then
        echo "依赖安装成功"
        break
    fi
    if [ $RETRY -lt $MAX_RETRY ]; then
        echo "安装失败，正在重试..."
    else
        echo "[错误] 依赖安装失败，已重试 $MAX_RETRY 次"
        echo "请检查网络连接，或手动执行:"
        echo "  venv/bin/pip install -r requirements.txt"
        exit 1
    fi
done

# ============ 构建 WebUI ============
echo ""
echo "[4/6] 构建 WebUI..."

if ! command -v node &>/dev/null; then
    echo "[警告] 未检测到 Node.js，跳过 WebUI 构建"
    echo "如需使用 WebUI，请安装 Node.js 18+"
    echo "Ubuntu/Debian: curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt install -y nodejs"
    SKIP_WEBUI=true
fi

if [ "$SKIP_WEBUI" != "true" ]; then
    if [ ! -d "webui/frontend/node_modules" ]; then
        echo "正在安装前端依赖..."
        cd webui/frontend
        npm install --registry https://registry.npmmirror.com 2>/dev/null
        if [ $? -ne 0 ]; then
            echo "[警告] npm install 失败，WebUI 可能无法使用"
            cd ../..
            SKIP_WEBUI=true
        else
            cd ../..
        fi
    fi

    if [ "$SKIP_WEBUI" != "true" ] && [ ! -f "webui/frontend/dist/index.html" ]; then
        echo "正在构建前端..."
        cd webui/frontend
        npx vite build 2>/dev/null
        if [ $? -ne 0 ]; then
            echo "[警告] WebUI 构建失败，WebUI 可能无法使用"
            cd ../..
        else
            cd ../..
            echo "WebUI 构建成功"
        fi
    else
        if [ "$SKIP_WEBUI" != "true" ]; then
            echo "WebUI 已构建"
        fi
    fi
fi

# ============ 检测版本更新 ============
echo ""
echo "[5/6] 检测版本更新..."

UPDATE_JSON=$($PY -m core.updater_cli --check 2>/dev/null)
if [ $? -eq 0 ] && echo "$UPDATE_JSON" | grep -q '"has_update": true'; then
    LATEST_VER=$(echo "$UPDATE_JSON" | grep -o '"latest_version": *"[^"]*"' | head -1 | sed 's/.*: *"//;s/"$//')
    LATEST_NAME=$(echo "$UPDATE_JSON" | grep -o '"version_name": *"[^"]*"' | head -1 | sed 's/.*: *"//;s/"$//')
    echo ""
    echo "========================================"
    echo "  检测到新版本可用!"
    echo "  最新版本: $LATEST_VER"
    echo "  版本名称: $LATEST_NAME"
    echo "========================================"
    read -p "是否立即更新? (y/n): " UPDATE_CHOICE
    if [ "$UPDATE_CHOICE" = "y" ] || [ "$UPDATE_CHOICE" = "Y" ]; then
        echo "正在更新..."
        $PY -m core.updater_cli --force
        if [ $? -ne 0 ]; then
            echo "[警告] 更新失败,将使用当前版本启动"
        fi
    else
        echo "已跳过更新"
    fi
else
    echo "当前已是最新版本"
fi

# ============ 首次启动提示 ============
echo ""
echo "[6/6] 启动机器人..."

FIRST_RUN=false
if [ ! -f "config.json" ]; then
    FIRST_RUN=true
    echo ""
    echo "========================================"
    echo "  首次启动，正在生成默认配置..."
    echo "========================================"
fi

# 启动程序
$PY main.py

if [ $? -ne 0 ]; then
    echo ""
    echo "[错误] 程序异常退出"
fi

if [ "$FIRST_RUN" = true ]; then
    echo ""
    echo "首次启动完成！配置文件已生成: config.json"
    echo "请在 WebUI 中查看和修改配置"
fi
