# 陌城qqbot框架

基于 Python 的 QQ 群管机器人框架,自包含架构,开箱即用,带有可视化 WebUI 管理界面。支持多适配器架构,可同时接入 OneBot v11 协议端(NapCat/Lagrange 等)和 QQ 官方机器人接口。

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
- 🔌 多适配器架构,支持 OneBot v11 和 QQ 官方机器人接口,WebUI 可视化管理多个适配器
- 🛡️ 适配器严格隔离,OneBot 调 OneBot、官方调官方,互不混淆
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
- 适配器管理(OneBot v11 / QQ 官方机器人,支持增删改查、启停、测试连接)
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

陌城qqbot框架基于 **Python** 构建,支持两种适配器接入方式:

### 方式一:OneBot v11 协议(第三方实现)

```
QQ 协议端(NapCat/Lagrange)  ⇄  陌城qqbot框架(Python 程序)
```

- **QQ 协议端**:负责与 QQ 服务器通信,收发消息
- **陌城qqbot框架**:处理消息逻辑、插件、WebUI 管理后台
- 两者通过 WebSocket 通信
- 适合:需要完整 QQ 功能(群管、禁言、踢人等)的场景

### 方式二:QQ 官方机器人接口(腾讯合规 API)

```
陌城qqbot框架(Python 程序)  ⇄  QQ 开放平台(q.qq.com)
```

- 直接对接腾讯官方机器人 API,无需第三方协议端
- 合规不封号,但功能受限(被动回复为主,主动消息有配额)
- 适合:需要合规运营的场景

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

## 适配器配置

框架支持在 WebUI「适配器管理」页面同时配置多个 bot 适配器,每种适配器类型调用对应的接口实现,互不混淆。

### OneBot v11 适配器

通过 OneBot v11 协议连接第三方 QQ 协议端(NapCat/Lagrange/go-cqhttp 等)。

**配置项**:
- 名称:适配器显示名(如「主群 OneBot」)
- 类型:`onebot_v11`
- 连接模式:
  - `ws_client`(正向 WS):框架主动连接协议端的 WebSocket 服务
  - `ws_server`(反向 WS):协议端主动连接框架的 WebSocket 服务
- ws_client 模式:WebSocket 地址、Access Token
- ws_server 模式:监听地址、端口、Access Token

### QQ 官方机器人适配器

直接对接腾讯 QQ 开放平台(https://q.qq.com)的官方机器人 API,合规无封号风险。

**前置准备**:
1. 访问 https://q.qq.com 注册开发者账号并创建机器人应用
2. 获取机器人的 **AppID**、**AppSecret**
3. 配置机器人权限(群@消息、C2C 消息等)
4. 框架使用 WebSocket 模式接收事件,无需配置回调地址

**配置项**:
- 名称:适配器显示名(如「官方机器人」)
- 类型:`qq_official`
- AppID:机器人 AppID
- AppSecret:机器人 AppSecret

**事件支持**:
- `GROUP_AT_MESSAGE_CREATE`:群@机器人消息(所有机器人默认可订阅,被动回复)
- `GROUP_MESSAGE_CREATE`:群全量消息(需申请"全量消息"权限白名单,开通后才会推送)
- `C2C_MESSAGE_CREATE`:C2C 私聊消息
- `GROUP_ADD_ROBOT`/`GROUP_DEL_ROBOT`:机器人被加入/移出群
- `FRIEND_ADD`/`FRIEND_DEL`:添加/删除好友

**权限配置(重要)**:
QQ 官方 API 不提供查询群成员角色的能力,因此 `GROUP_ADMIN`/`GROUP_OWNER` 权限在官方适配器下**回退到 `SUPERUSER` 检查**。使用官方适配器执行管理员命令(如"授权群聊")前,需将你的 `member_openid` 加入 `superusers` 配置:

1. 在群里发任意消息,查看日志获取你的 `member_openid`:
   ```
   [消息] 适配器=qq_official 类型=group 群=xxx 用户=XXX 内容='xxx'
   ```
2. 将 `XXX`(member_openid)加入 `config/config.json` 的 `bot.superusers` 数组
3. 重启框架

**功能限制**:
- `user_id` 是 `member_openid`(加密字符串,非 QQ 号),与 OneBot 适配器数据不互通
- 不支持群管操作(禁言/踢人/撤回/群成员管理等)
- 不支持 `get_group_member_info`、`get_group_member_list` 等查询 API
- 被动回复限制:5 秒内需回复,AI 聊天等耗时操作可能超时
- 主动消息有配额限制,需 msg_id 且有时效
- `msg_type` 自动判定:纯文本=0、Markdown=2、Ark=3、图片(media)=7
- 鉴权 token(access_token)由框架自动管理,按实际 expires_in 缓存(留 60 秒余量自动刷新)

### 适配器隔离机制

框架根据 `bot.adapter_type` 严格路由 API 调用:
- `adapter_type = "onebot_v11"` → 调用 OneBot WebSocket API
- `adapter_type = "qq_official"` → 调用官方 HTTPS API

官方适配器不支持的 API(如 `set_group_kick`)会抛出 `NotImplementedError`,不会误调用 OneBot 适配器。两个适配器的群消息分别处理,群 ID 体系不同(OneBot 用数字群号,官方用 `group_openid`),授权管理、群设置等需分别配置。

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

## 插件开发

陌城qqbot框架提供完整的插件开发接口,开发者可以编写自定义插件扩展功能。**自定义插件不会被在线更新覆盖。**

> 📖 完整文档请访问[官网插件开发文档](https://bot.mcyvps.top/develop.php)

### 快速开始

在 `plugins/` 目录下创建 `.py` 文件(文件名不要以 `_` 开头),框架启动时自动加载。

### 插件骨架

```python
import os
from core import on_command, on_startup, on_shutdown, SUPERUSER
from core.onebot import Bot, GroupMessageEvent, Message, CommandArg
from plugins.utils import reply, JsonDataManager
from core.menu_registry import menu_registry

# 数据管理器(可选)
class MyDataManager(JsonDataManager):
    def __init__(self):
        super().__init__("my_plugin.json", default_data={})

data_mgr = MyDataManager()

# 注册命令
my_cmd = on_command("我的命令", priority=1, block=True,
                    permission=SUPERUSER)

@my_cmd.handle()
async def handle_my_cmd(bot: Bot, event: GroupMessageEvent,
                        args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    await my_cmd.finish(reply(event, f"你输入了: {text}"))

# 生命周期钩子(可选)
@on_startup
async def _startup():
    data_mgr.load()

@on_shutdown
async def _shutdown():
    data_mgr.shutdown()

# 菜单注册(文件底部)
menu_registry.register(
    category="我的插件",
    item_name="我的命令",
    text="🎯 我的命令",
    category_title="🎯◇━我的插件━◇🔧",
    category_trigger="我的插件",
    category_description="自定义功能示例",
)
```

### 统一消息构造

所有插件应使用 `plugins/utils.py` 提供的函数,保证消息格式统一:

| 函数 | 说明 |
|------|------|
| `reply(event, msg)` | 通用回复(自动识别群/私聊) |
| `reply_msg(event, msg)` | 群消息回复(引用+@+内容) |
| `reply_private(event, msg)` | 私聊回复 |
| `at_msg(user_id, msg)` | @用户+内容(通知场景) |
| `text_msg(text)` | 纯文本 |
| `at(user_id)` | @消息段 |
| `image(url/file/base64)` | 图片消息段 |
| `face(face_id)` | QQ表情 |
| `record(url/file/base64)` | 语音 |

### 事件注册

```python
from core import on_command, on_message, on_notice, on_request

# 命令(支持权限检查)
cmd = on_command("命令名", priority=1, block=True,
                 permission=GROUP_ADMIN | SUPERUSER)

# 消息监听(不触发命令)
msg_handler = on_message(priority=99, block=False)

# 通知事件(进群/撤回等)
notice_handler = on_notice(priority=15, block=False)

# 请求事件(加好友/加群)
request_handler = on_request(priority=10, block=False)
```

- `priority`: 越小越先执行(1=常规命令, -1=日志采集, 99=消息收集)
- `block`: True 则执行后停止后续 matcher

### 权限系统

```python
from core import SUPERUSER, GROUP_ADMIN, GROUP_OWNER

# 在 on_command 中声明(推荐)
cmd = on_command("管理命令", permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

# 或在 handler 内手动检查
if await SUPERUSER(bot, event):
    # 超管逻辑
```

### 数据持久化

继承 `JsonDataManager` 基类,自动获得懒加载/线程安全/延迟保存:

```python
from plugins.utils import JsonDataManager

class CounterManager(JsonDataManager):
    def __init__(self):
        super().__init__("counter.json", default_data={"count": 0})

counter = CounterManager()

# 使用
counter.load()
counter.data["count"] += 1
counter.mark_dirty()  # 标记脏数据,3秒后自动保存
```

### Bot API

Handler 中通过 `bot: Bot` 参数调用 OneBot API:

```python
await bot.send(event, "消息")              # 自动识别群/私聊
await bot.send_group_msg(group_id, "消息")  # 发送群消息
await bot.send_private_msg(user_id, "消息") # 发送私聊
await bot.delete_msg(message_id)            # 撤回消息
await bot.set_group_ban(group_id, user_id, duration)  # 禁言
await bot.set_group_kick(group_id, user_id)           # 踢人
await bot.set_group_special_title(group_id, user_id, title)  # 设置头衔
await bot.send_group_notice(group_id, content)  # 群公告
await bot.call_api(action, **params)  # 通用 API 调用
```

完整 API 列表见[官网文档](https://bot.mcyvps.top/develop.php)。

### 自定义插件与在线更新

- 自定义插件放在 `plugins/` 目录下
- 在线更新时只覆盖框架内置插件,**自定义插件原样保留**
- 命名建议加前缀避免冲突(如 `custom_xxx.py`)
- 文件名不要以 `_` 开头(会被加载器跳过)

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

**Q: QQ 官方适配器收不到消息?**
A: 1) 确认 AppID/AppSecret 正确;2) 确认机器人已在群里被添加;3) 查看日志是否有"鉴权成功"和"收到事件"记录;4) 未开通"全量消息"权限时,只有 @机器人 才会收到事件(GROUP_AT_MESSAGE_CREATE)。

**Q: QQ 官方适配器命令无法执行?**
A: QQ 官方 API 不支持查询群成员角色,管理员命令需将 `member_openid` 加入 `superusers`。在群里发消息查看日志获取 member_openid,加入 `config/config.json` 的 `bot.superusers` 数组后重启。

**Q: QQ 官方适配器和 OneBot 适配器数据能互通吗?**
A: 不能。官方适配器的 user_id 是 member_openid(加密字符串),group_id 是 group_openid,与 OneBot 的 QQ 号和群号体系完全不同。两个适配器的积分、签到、统计等数据相互独立。

**Q: 两个适配器能同时运行吗?**
A: 可以。在 WebUI「适配器管理」页面同时添加并启用两个适配器,框架会并行启动,互不阻塞。但群消息会分别处理,群 ID 体系不同,授权管理需分别配置。

## 许可证

MIT License
