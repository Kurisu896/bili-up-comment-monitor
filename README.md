# B站 UP主评论监控工具

监控 B站指定 UP 主的新评论和回复，第一时间捕捉实盘观点、操作点评等关键信息。

## 项目初衷

在 B 站关注了几位炒股实盘 UP 主，他们经常会在自己的视频或动态评论区里**发布实时操作、盘中点评、私密观点**，而这些内容往往不会做成正式视频或图文。但手动刷新页面太麻烦，也容易错过。

于是写了这个小工具：常驻后台轮询 B 站评论接口，一旦监控到目标 UP 主发了新评论或二级回复，立即提醒。避免错过任何一条实盘信号。

## 功能特性

### 通用能力

- **多 UP 主同时监控**：GUI 版支持最多 5 位 UP 主并行监控
- **双场景覆盖**：同时监控新投稿视频 + 最新动态（说说/专栏）
- **二级回复追踪**：不仅看 UP 主新发的评论，也会捕捉 UP 主对评论区的回复
- **去重机制**：内部维护评论 ID 缓存，不会重复推送同一条评论
- **防风控**：内置合理的轮询间隔，避免请求过快被 B 站风控

### GUI 版（`main_gui.py`）

- PyQt5 桌面界面，开箱即用
- 支持监控 **文字** 和 **图片** 类型的评论
- 实时显示每条新评论的时间、来源（视频/动态）、完整内容
- 可独立设置每位 UP 主的轮询间隔
- 一键启动/停止，无需懂代码

### 命令行版（`main.py`）

- 轻量脚本，适合常驻后台或服务器运行
- 配合 `pyautogui` + `pyperclip` 实现 **QQ 自动推送**（模拟键盘粘贴 + 回车）
- 自定义视频 BV 号和 UP 主 UID，简单改动即可复用

## 环境要求

- Python 3.8+
- Windows（pyautogui 自动推送依赖 Windows）

## 依赖安装

```bash
pip install requests PyQt5 pyautogui pyperclip
```

## 快速上手

### 方式一：GUI 版（推荐普通人使用）

```bash
python main_gui.py
```

操作步骤：
1. 在界面上填写 UP 主的 **UID**（打开 UP 主页，浏览器地址栏 `space.bilibili.com/` 后面那串数字就是 UID）
2. 设置监控间隔（默认 10 秒，不宜太短）
3. 点击 **开始监控**，新评论会自动出现在下方列表中

### 方式二：命令行版（需要 QQ 自动推送）

编辑 `main.py` 顶部的配置区：

```python
VIDEO_BVID = "BV1aouMzUEWa"   # 目标视频 BV 号
UP_MID = 11657757             # 目标 UP 主 UID
MONITOR_INTERVAL = 5          # 轮询间隔（秒）
QQ_SEND_INTERVAL = 1.5        # QQ 消息之间的发送间隔
```

然后：

```bash
python main.py
```

> **QQ 推送提示**：运行前先把要接收消息的 QQ 聊天窗口打开并保持在前台，脚本会自动剪贴板粘贴并回车发送。建议用小号给大号发，避免打扰。

## 打包成 exe

项目已附带 PyInstaller 的 spec 文件，可以直接打包：

```bash
# GUI 版
pyinstaller BilibiliMonitor.spec --noconsole

# 命令行版
pyinstaller "B站评论监控.spec"
```

打包完成后可执行文件在 `dist/` 目录下，双击即可运行，无需 Python 环境。

## 目录结构

```
comments_monitoring/
├── main.py                 # 命令行版（单视频 + QQ 自动推送）
├── main_gui.py             # GUI 版（多 UP 主 + 视频/动态 + 图片显示）
├── BilibiliMonitor.spec    # GUI 版 PyInstaller 打包配置
├── B站评论监控.spec         # 命令行版 PyInstaller 打包配置
└── .gitignore
```

## 技术说明

- **B 站评论接口**：`https://api.bilibili.com/x/v2/reply`，type=1 为视频评论，sort=2 按热度排序取最新
- **动态接口**：通过 UP 主 UID 拉取最新动态列表，再逐条抓取评论
- **图片评论**：B 站评论中的图片以 `img://` 协议内嵌，GUI 版会自动解析并渲染
- **无反爬绕过**：仅使用 User-Agent + Referer 伪装，不涉及登录态和 Cookie；建议轮询间隔 ≥ 5 秒

## 免责声明

本工具仅供个人学习和自用。请合理设置轮询间隔，尊重 B 站 API 使用规则，不要用于商业用途或大规模滥用。

## License

MIT
