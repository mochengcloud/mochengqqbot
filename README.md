# 陌城qqbot框架

基于 Python 和 OneBot v11 协议的 QQ 群管机器人框架,自包含架构,开箱即用,带有可视化 WebUI 管理界面。

## 官方资源

- **官网**: https://bot.mcyvps.top
- **官方 QQ 群**: 361490699
- **最新版本下载**: https://bot.mcyvps.top/download.php
- **更新日志**: https://bot.mcyvps.top/changelog.php
- **在线部署教程**: https://bot.mcyvps.top/deploy.php

## 功能特性

### 核心能力
- 🧩 自包含框架,脱离 nonebot,开箱即用
- 📡 完整支持 OneBot v11 协议,兼容 NapCat / Lagrange / go-cqhttp
- 🔌 21 个内置插件(群管理、AI 对话、签到、积分、统计等)
- 🖥️ WebUI 可视化管理后台,告别编辑配置文件
- 🔀 多 AI 供应商故障转移,接口不可用时自动切换
- ⚡ 全局并发控制,可配置并发数量
- 📋 插件菜单自描述系统,框架自动收集
- 🔒 进群验证、违规检测、内容审核,全方位守护群聊
- 🚀 在线自动更新,WebUI 一键升级到最新版本

### 群管功能
- 分群开机/关机
- 打开/关闭菜单
- 开启/解除全体禁言
- 禁言@ / 解除禁言@
- 撤回@ / 撤回关键词 / 撤回最近
- 禁言列表 / 全部解禁
- 踢出@
- 查看/踢出从未发言
- 上群管@ / 下群管@
- 设置头衔@ X
- 清屏
- 发送公告X

### WebUI 功能
- 多级菜单管理(可编辑标题、触发词、描述)
- OneBot 连接配置(支持 WS 客户端/服务端模式)
- 服务器配置
- 机器人配置
- 群设置管理
- 版本更新检测与一键在线更新

## 部署教程

### 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.8+ | 推荐 3.10 或 3.11,安装时勾选 "Add Python to PATH" |
| OneBot 协议端 | - | NapCat / Lagrange / go-cqhttp(任选其一) |
| Node.js | 18+ | 可选,仅自行构建 WebUI 时需要。正式版压缩包已预构建 |

### 部署架构

陌城qqbot框架基于 **Python + OneBot v11 协议** 构建,部署需要两部分:

```
QQ 协议端(NapCat/Lagrange)  ⇄  陌城qqbot框架(Python 程序)
```

- **QQ 协议端**:负责与 QQ 服务器通信,收发消息
- **陌城qqbot框架**:处理消息逻辑、插件、WebUI 管理后台

两者通过 WebSocket 通信。

### 部署步骤

#### 1. 下载框架

从[官网下载页](https://bot.mcyvps.top/download.php)获取最新版本压缩包(推荐下载正式版,已包含预构建的 WebUI)。

将压缩包解压到任意目录,例如:
```
# Windows
D:\qqbot\

# Linux
/opt/qqbot/
```

> 💡 路径中建议不要包含中文,以避免部分依赖库的编码问题。

#### 2. 启动框架

**Windows 系统**:
双击目录中的 `start.bat` 文件,脚本会自动完成:
- 检测 Python 环境
- 创建虚拟环境(venv)
- 安装依赖库(使用清华源加速)
- 检查/构建 WebUI(若已预构建则跳过)
- 启动框架

**Linux / macOS 系统**:
```bash
cd /opt/qqbot
chmod +x start.sh
./start.sh
```

**手动启动(高级)**:
```bash
cd /opt/qqbot
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
python main.py
```

> 💡 首次启动会在 `config/` 目录自动生成默认配置文件(config.json 和 .env),无需手动创建。

#### 3. 部署 OneBot 协议端

框架本身无法直接登录 QQ,需要一个 OneBot 协议端来收发消息。推荐以下几种实现:

| 协议端 | 说明 | 地址 |
|--------|------|------|
| NapCat | 基于 QQNT 的 OneBot 实现,推荐 | [GitHub](https://github.com/NapNeko/NapCatQQ) |
| Lagrange | 跨平台 OneBot 实现 | [GitHub](https://github.com/LagrangeDev/Lagrange.Core) |
| go-cqhttp | 老牌 OneBot 实现 | [GitHub](https://github.com/Mrs4s/go-cqhttp) |

配置协议端连接:
- 框架默认使用 **WebSocket 客户端模式**(框架主动连接协议端)
- 需在协议端开启**正向 WebSocket 服务**
- 默认连接地址: `ws://127.0.0.1:3001`(同一服务器时)

#### 4. 配置框架

框架启动后,打开浏览器访问 WebUI 管理后台:
```
http://127.0.0.1:8081
```

在 WebUI 中完成以下配置:
1. **OneBot 连接配置** - 填写协议端的 WebSocket 地址和 Access Token
2. **机器人配置** - 设置超级用户(QQ 号)、昵称、命令前缀
3. **群设置** - 配置每个群的开关、插件启用状态
4. **菜单管理** - 自定义菜单标题、触发词、分类

> 💡 超级用户:在 config.json 的 bot.superusers 数组中添加你的 QQ 号,即可拥有最高管理权限。

#### 5. 连接测试

完成配置后,按以下步骤验证部署是否成功:
- ✅ 控制台输出 `WebSocket 已连接` - 协议端连接成功
- ✅ 控制台输出 `Bot 已登录: xxxxxxx` - QQ 账号登录成功
- ✅ WebUI 首页显示**在线**状态 - 框架运行正常
- ✅ 在 QQ 群中发送 `菜单` - 机器人回复菜单 - 功能完全可用

### 端口说明

| 服务 | 默认端口 | 说明 |
|------|---------|------|
| Bot WebSocket | 8080 | 框架主服务端口 |
| WebUI 管理后台 | 8081 | 浏览器访问的可视化管理界面 |
| OneBot 协议端 | 3001 | 协议端的正向 WebSocket 服务端口(在协议端配置) |

### 后台常驻运行(Linux)

**方案一:screen(简单)**
```bash
# 创建后台会话
screen -S qqbot

# 启动框架
cd /opt/qqbot && ./start.sh

# 按 Ctrl+A 然后按 D 脱离会话(框架继续运行)
# 重新连接会话
screen -r qqbot
```

**方案二:systemd(推荐生产环境)**

创建服务文件 `/etc/systemd/system/qqbot.service`:
```ini
[Unit]
Description=MoCheng QQBot Framework
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/qqbot
ExecStart=/opt/qqbot/venv/bin/python /opt/qqbot/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动并设置开机自启:
```bash
systemctl daemon-reload
systemctl start qqbot
systemctl enable qqbot

# 查看运行状态
systemctl status qqbot
# 查看日志
journalctl -u qqbot -f
```

## 在线自动更新

v2.0.1-beta 起支持在线自动更新:

- **WebUI 检测**:登录 WebUI 后自动检测新版本,有更新时弹窗提示
- **一键更新**:在"版本更新"页面点击"一键在线更新",自动下载→解压→覆盖→重启
- **启动脚本检测**:`start.bat` / `start.sh` 启动前自动检测,有新版本时询问是否更新
- **数据安全**:更新时严格保留 `config/` 和 `venv/` 目录,不破坏用户配置
- **失败回滚**:更新失败自动回滚到旧版本

## 目录结构

```
qqbot/
├── main.py                 # 主入口
├── start.bat               # Windows 一键启动
├── start.sh                # Linux/macOS 启动脚本
├── requirements.txt        # Python 依赖
├── config_manager.py       # 配置管理
├── log_manager.py          # 日志管理
├── core/                   # 核心代码
│   ├── app.py              # 应用主类
│   ├── version.py          # 版本号
│   ├── updater.py          # 在线更新模块
│   ├── plugin_loader.py    # 插件加载器
│   ├── menu_registry.py    # 菜单注册
│   ├── permission.py       # 权限管理
│   └── onebot/             # OneBot 协议实现
├── plugins/                # 插件目录(21 个内置插件)
│   ├── group_admin.py      # 群管理
│   ├── group_ai_chat.py    # AI 对话
│   ├── group_checkin.py    # 签到
│   ├── group_points.py     # 积分
│   └── ...
├── webui/                  # WebUI 管理后台
│   ├── app.py              # WebUI 服务
│   └── frontend/dist/      # 前端构建产物
├── config/                 # 配置文件
│   ├── config.json         # 主配置(自动生成)
│   ├── .env                # 环境变量(自动生成)
│   └── data/               # 数据存储
└── venv/                   # 虚拟环境(自动创建)
```

## 常见问题

**Q: 启动时提示"未找到 Python"?**
A: 安装 Python 3.8 以上版本,安装时勾选 Add Python to PATH。

**Q: 依赖安装失败?**
A: 启动脚本已配置清华镜像源。若仍失败,手动执行:`python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

**Q: WebUI 打不开?**
A: 检查 8081 端口是否被占用或被防火墙拦截。正式版已预构建 WebUI,无需 Node.js。

**Q: 机器人无法连接协议端?**
A: 1) 确认协议端已启动并登录 QQ;2) 确认 WebSocket 地址端口正确(默认 ws://127.0.0.1:3001);3) 确认 Access Token 一致。

**Q: 路径包含中文导致启动失败?**
A: 建议部署到纯英文路径,如 D:\qqbot\ 或 /opt/qqbot/。

**Q: 如何升级框架?**
A: v2.0.1-beta 起支持在线自动更新(WebUI 一键更新或启动脚本检测)。旧版本请下载新版本压缩包覆盖(保留 config/ 目录)。

## 许可证

MIT License
