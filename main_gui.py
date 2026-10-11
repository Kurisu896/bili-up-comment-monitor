# -*- coding: utf-8 -*-
"""
B站UP主评论监控 v3.2
- 支持监控1-5位UP主
- 监控新视频和新动态下的UP主评论和二级回复
- 支持文字和图片显示
"""

import sys
import requests
import time
import os
import pyautogui
import pyperclip
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox, QSpinBox,
    QMessageBox, QStatusBar, QFrame, QStackedWidget
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QByteArray, QSize
from PyQt5.QtGui import QFont, QColor, QPalette, QPixmap, QPainter, QPainterPath

pyautogui.FAILSAFE = False

# ==================== 常量配置 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/"
}
MAX_MONITOR_VIDEOS = 5
MAX_MONITOR_DYNAMICS = 5
COMMENTS_PER_PAGE = 20

# 配色方案
COLOR_BG = "#0D1117"
COLOR_BG_CARD = "#161B22"
COLOR_BG_INPUT = "#1C2333"
COLOR_BORDER = "#30363D"
COLOR_ACCENT = "#FB7299"
COLOR_ACCENT_HOVER = "#FF8DAA"
COLOR_ACCENT_BLUE = "#00A1D6"
COLOR_GREEN = "#3FB950"
COLOR_RED = "#F85149"
COLOR_TEXT = "#E6EDF3"
COLOR_TEXT_DIM = "#8B949E"
COLOR_TEXT_BRIGHT = "#FFFFFF"

# ==================== B站API工具函数 ====================

def get_up_videos(uid, page=1, ps=30):
    """获取UP主视频列表（按发布时间排序）"""
    url = f"https://api.bilibili.com/x/space/arc/search?mid={uid}&ps={ps}&pn={page}&order=pubdate"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            return []
        return data.get("data", {}).get("list", {}).get("vlist", [])
    except Exception:
        return []


def get_up_dynamics(uid, offset=""):
    """获取UP主动态列表"""
    url = f"https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?host_mid={uid}"
    if offset:
        url += f"&offset={offset}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            return [], None
        items = data.get("data", {}).get("items", [])
        next_offset = data.get("data", {}).get("offset", "")
        return items, next_offset
    except Exception:
        return [], None


def get_comments(oid, comment_type=1, page=1, ps=COMMENTS_PER_PAGE, sort=2):
    """
    获取评论列表
    comment_type: 1=视频, 17=动态
    """
    url = f"https://api.bilibili.com/x/v2/reply?type={comment_type}&oid={oid}&pn={page}&ps={ps}&sort={sort}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            return [], 0
        replies = data.get("data", {}).get("replies", [])
        total = data.get("data", {}).get("page", {}).get("count", 0)
        return replies, total
    except Exception:
        return [], 0


def get_sub_replies(oid, root_rpid, comment_type=1, page=1, ps=COMMENTS_PER_PAGE):
    """获取评论的二级回复（子回复）"""
    url = f"https://api.bilibili.com/x/v2/reply/reply?type={comment_type}&oid={oid}&root={root_rpid}&pn={page}&ps={ps}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            return []
        return data.get("data", {}).get("replies", [])
    except Exception:
        return []


def extract_images_from_comment(comment):
    """提取评论中的图片URL列表"""
    pictures = comment.get("content", {}).get("pictures")
    if not pictures:
        return []
    urls = []
    for pic in pictures:
        url = pic.get("img_src", "")
        if url and url.startswith("//"):
            url = "https:" + url
        if url:
            urls.append(url)
    return urls


def get_up_info(uid):
    """获取UP主信息（头像+名字）"""
    url = f"https://api.bilibili.com/x/space/acc/info?mid={uid}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            return None
        return {
            "name": data["data"].get("name", ""),
            "face": data["data"].get("face", ""),
            "mid": data["data"].get("mid", 0),
        }
    except Exception:
        return None


def load_circular_avatar(url, size=40):
    """下载头像并裁剪为圆形"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        raw = QPixmap()
        raw.loadFromData(QByteArray(resp.content))
        scaled = raw.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        circle = QPixmap(size, size)
        circle.fill(Qt.transparent)
        painter = QPainter(circle)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(1, 1, size - 2, size - 2)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        return circle
    except Exception:
        return None


class InfoFetchWorker(QThread):
    """异步获取UP主信息"""
    info_ready = pyqtSignal(dict)

    def __init__(self, uid):
        super().__init__()
        self.uid = uid

    def run(self):
        info = get_up_info(self.uid)
        if info:
            self.info_ready.emit(info)


# ==================== 监控线程 ====================

class UPMonitorThread(QThread):
    """单个UP主的监控线程"""
    message_signal = pyqtSignal(str)

    def __init__(self, uid, up_name, monitor_interval, qq_interval):
        super().__init__()
        self.uid = uid
        self.up_name = up_name or f"UP主{uid}"
        self.monitor_interval = monitor_interval
        self.qq_interval = qq_interval
        self.running = False

        # 缓存
        self.video_cache = set()          # 已知视频bvid
        self.dynamic_cache = set()        # 已知动态id
        self.monitored_videos = []        # 当前监控的视频列表（有序）
        self.monitored_dynamics = []      # 当前监控的动态列表（有序）
        self.comment_cache = set()        # 已处理的一级评论rpid
        self.sub_reply_cache = set()      # 已处理的二级回复rpid

    def run(self):
        self.running = True
        self.message_signal.emit(f"👤 [{self.up_name}] 监控线程已启动")

        try:
            self._init_cache()
        except Exception as e:
            self.message_signal.emit(f"⚠️ [{self.up_name}] 初始化缓存失败: {e}")

        while self.running:
            try:
                self._check_new_videos()
                self._check_new_dynamics()
                self._check_all_comments()
                time.sleep(self.monitor_interval)
            except Exception as e:
                self.message_signal.emit(f"【UP主{self.uid}监控异常】{str(e)}")
                time.sleep(self.monitor_interval)

    def stop(self):
        self.running = False

    # ---- 初始化缓存 ----
    def _init_cache(self):
        """初始化：获取已有视频和动态，并预缓存已有评论，避免首次扫描大量通知"""
        # 缓存已有视频
        videos = get_up_videos(self.uid, page=1, ps=MAX_MONITOR_VIDEOS)
        for v in videos:
            bvid = v.get("bvid")
            if bvid:
                self.video_cache.add(bvid)
                self.monitored_videos.append(bvid)

        # 缓存已有动态
        dynamics, _ = get_up_dynamics(self.uid)
        count = 0
        for d in dynamics:
            if count >= MAX_MONITOR_DYNAMICS:
                break
            did = str(d.get("id_str", ""))
            if did:
                self.dynamic_cache.add(did)
                self.monitored_dynamics.append(did)
                count += 1

        self.message_signal.emit(
            f"  [{self.up_name}] 已缓存 {len(self.monitored_videos)} 个视频, "
            f"{len(self.monitored_dynamics)} 个动态，正在预加载已有评论..."
        )

        # 预缓存已有评论（避免首次扫描报大量通知）
        self._init_comment_cache()

        self.message_signal.emit(f"  [{self.up_name}] 初始化完成，开始持续监控")

    def _init_comment_cache(self):
        """预加载已有评论到缓存"""
        # 视频评论
        for bvid in self.monitored_videos:
            self._cache_existing_comments(bvid, 1)
            time.sleep(0.3)
        # 动态评论
        for did in self.monitored_dynamics:
            self._cache_existing_comments(did, 17)
            time.sleep(0.3)

    def _cache_existing_comments(self, oid, comment_type):
        """将已有评论加入缓存，不发通知"""
        comments, _ = get_comments(oid, comment_type)
        for c in comments:
            if str(c.get("mid", "")) == str(self.uid):
                self.comment_cache.add(c.get("rpid"))
            # 缓存二级回复
            if c.get("rcount", 0) > 0:
                sub_replies = get_sub_replies(oid, c.get("rpid"), comment_type)
                for sr in sub_replies:
                    if str(sr.get("mid", "")) == str(self.uid):
                        self.sub_reply_cache.add(sr.get("rpid"))

    # ---- 检查新内容 ----
    def _check_new_videos(self):
        """检查是否有新视频发布"""
        videos = get_up_videos(self.uid, page=1, ps=MAX_MONITOR_VIDEOS)
        for v in videos:
            bvid = v.get("bvid")
            if not bvid or bvid in self.video_cache:
                continue
            # 发现新视频
            self.video_cache.add(bvid)
            self.monitored_videos.insert(0, bvid)
            if len(self.monitored_videos) > MAX_MONITOR_VIDEOS:
                old = self.monitored_videos.pop()
                self.video_cache.discard(old)

            title = v.get("title", "未知标题")
            created = v.get("created", 0)
            time_str = datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M:%S") if created else "未知"
            video_url = f"https://www.bilibili.com/video/{bvid}/"

            self.message_signal.emit(f"\n🆕 [{self.up_name}] 发布了新视频！")
            self.message_signal.emit(f"   标题：{title}")
            self.message_signal.emit(f"   时间：{time_str}")
            self.message_signal.emit(f"   链接：{video_url}")

            self._push_to_qq(f"【B站UP主新视频】\nUP主：{self.up_name}\n标题：{title}\n时间：{time_str}\n链接：{video_url}")
            time.sleep(self.qq_interval)

    def _check_new_dynamics(self):
        """检查是否有新动态发布"""
        dynamics, _ = get_up_dynamics(self.uid)
        count = 0
        for d in dynamics:
            if count >= MAX_MONITOR_DYNAMICS:
                break
            did = str(d.get("id_str", ""))
            if not did or did in self.dynamic_cache:
                continue
            # 发现新动态
            self.dynamic_cache.add(did)
            self.monitored_dynamics.insert(0, did)
            if len(self.monitored_dynamics) > MAX_MONITOR_DYNAMICS:
                old = self.monitored_dynamics.pop()
                self.dynamic_cache.discard(old)

            desc, dtype_label = self._extract_dynamic_desc(d)
            image_urls = self._extract_dynamic_images(d)
            dynamic_url = f"https://t.bilibili.com/{did}"

            # 构建日志和推送消息
            full_text = desc if desc else dtype_label
            
            # 日志输出
            self.message_signal.emit(f"\n🆕 [{self.up_name}] 发布了新{dtype_label}")
            self.message_signal.emit(f"   内容：{full_text}")
            if image_urls:
                self.message_signal.emit(f"   🖼️ 动态图片({len(image_urls)}张)：\n" + "\n".join(image_urls))
            self.message_signal.emit(f"   链接：{dynamic_url}")

            # QQ推送：先发文字，再发图片
            image_info = ""
            if image_urls:
                image_info = f"\n🖼️ 图片({len(image_urls)}张)：\n" + "\n".join(image_urls)

            self._push_to_qq(
                f"【B站UP主新{dtype_label}】\n"
                f"UP主：{self.up_name}\n"
                f"内容：{full_text}{image_info}\n"
                f"链接：{dynamic_url}"
            )
            time.sleep(self.qq_interval)
            count += 1

    def _extract_dynamic_desc(self, dynamic):
        """
        提取动态的文本描述，返回 (text, type_label)
        覆盖所有动态类型的文字提取
        """
        try:
            modules = dynamic.get("modules", {})
            md = modules.get("module_dynamic", {})
            desc_obj = md.get("desc")
            major = md.get("major", {})
            mtype = major.get("type", "")

            type_map = {
                "MAJOR_TYPE_DRAW": "图片动态",
                "MAJOR_TYPE_ARTICLE": "专栏",
                "MAJOR_TYPE_OPUS": "图文动态",
                "MAJOR_TYPE_ARCHIVE": "视频动态",
                "MAJOR_TYPE_LIVE_RCMD": "直播动态",
                "MAJOR_TYPE_COMMON": "动态",
                "MAJOR_TYPE_PGC": "剧集动态",
            }
            dtype_label = type_map.get(mtype, "动态")

            # 1. 优先取 desc.text（大部分动态的文字在这里）
            if desc_obj and desc_obj.get("text"):
                return desc_obj["text"].strip(), dtype_label

            # 2. MAJOR_TYPE_OPUS: 图文动态的文字在 major.opus 里
            if mtype == "MAJOR_TYPE_OPUS":
                opus = major.get("opus", {})
                # summary.text 或 title
                summary = opus.get("summary", {})
                if summary.get("text"):
                    return summary["text"].strip(), dtype_label
                if opus.get("title"):
                    return opus["title"].strip(), dtype_label

            # 3. MAJOR_TYPE_DRAW: 图片动态，可能每张图有描述
            if mtype == "MAJOR_TYPE_DRAW":
                draw = major.get("draw", {})
                items = draw.get("items", [])
                # 尝试聚合所有图片的描述
                descs = []
                for item in items:
                    d = item.get("description", "")
                    if d:
                        descs.append(d)
                if descs:
                    return "；".join(descs), dtype_label

            # 4. MAJOR_TYPE_ARTICLE: 专栏标题
            if mtype == "MAJOR_TYPE_ARTICLE":
                article = major.get("article", {})
                if article.get("title"):
                    return article["title"].strip(), dtype_label

            # 5. MAJOR_TYPE_ARCHIVE: 视频标题
            if mtype == "MAJOR_TYPE_ARCHIVE":
                archive = major.get("archive", {})
                if archive.get("title"):
                    return archive["title"].strip(), dtype_label

            # 6. MAJOR_TYPE_COMMON: 纯文本动态，尝试从 desc 再取
            if desc_obj:
                # 有些纯文本动态 text 字段可能叫别的
                for key in ("text", "rich_text", "summary"):
                    val = desc_obj.get(key, "")
                    if val:
                        return str(val).strip(), dtype_label

            # 兜底
            return "", dtype_label
        except Exception:
            return "", "动态"

    def _extract_dynamic_images(self, dynamic):
        """提取动态中自带的图片URL列表（非评论区图片）"""
        try:
            modules = dynamic.get("modules", {})
            major = modules.get("module_dynamic", {}).get("major", {})
            mtype = major.get("type", "")
            urls = []

            if mtype == "MAJOR_TYPE_DRAW":
                draw = major.get("draw", {})
                for item in draw.get("items", []):
                    src = item.get("src", "")
                    if src:
                        if src.startswith("//"):
                            src = "https:" + src
                        urls.append(src)

            elif mtype == "MAJOR_TYPE_OPUS":
                opus = major.get("opus", {})
                for pic in opus.get("pics", []):
                    url = pic.get("url", "")
                    if url:
                        if url.startswith("//"):
                            url = "https:" + url
                        urls.append(url)

            return urls
        except Exception:
            return []

    # ---- 检查评论 ----
    def _check_all_comments(self):
        """检查所有监控内容的评论和二级回复"""
        # 视频评论
        for bvid in self.monitored_videos:
            self._check_content_comments(bvid, 1,
                f"视频", f"https://www.bilibili.com/video/{bvid}/")
            time.sleep(0.3)

        # 动态评论
        for did in self.monitored_dynamics:
            self._check_content_comments(did, 17,
                f"动态", f"https://t.bilibili.com/{did}")
            time.sleep(0.3)

    def _check_content_comments(self, oid, comment_type, source_label, source_url):
        """检查指定内容的评论"""
        comments, _ = get_comments(oid, comment_type)
        for comment in comments:
            mid = str(comment.get("mid", ""))
            rpid = comment.get("rpid")

            # 一级评论：UP主本人发表的
            if mid == str(self.uid) and rpid and rpid not in self.comment_cache:
                self.comment_cache.add(rpid)
                self._notify_comment(comment, source_label, source_url)
                time.sleep(self.qq_interval)

            # 二级回复：检查该评论下UP主是否回复了别人
            if comment.get("rcount", 0) > 0 and rpid:
                self._check_sub_replies(oid, rpid, comment_type, source_label, source_url, comment)

    def _check_sub_replies(self, oid, root_rpid, comment_type, source_label, source_url, parent_comment):
        """检查某条评论下的二级回复"""
        sub_replies = get_sub_replies(oid, root_rpid, comment_type)
        for reply in sub_replies:
            mid = str(reply.get("mid", ""))
            srpid = reply.get("rpid")
            if mid != str(self.uid) or not srpid or srpid in self.sub_reply_cache:
                continue

            self.sub_reply_cache.add(srpid)

            text = reply.get("content", {}).get("message", "")
            ctime = reply.get("ctime", 0)
            time_str = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S") if ctime else "未知"

            parent_text = parent_comment.get("content", {}).get("message", "")[:60]
            parent_user = parent_comment.get("member", {}).get("uname", "用户")

            image_urls = extract_images_from_comment(reply)
            image_info = ""
            if image_urls:
                image_info = f"\n🖼️ 图片({len(image_urls)}张)：\n" + "\n".join(image_urls)

            msg = (
                f"\n🔁 [{self.up_name}] 在{source_label}回复了「{parent_user}」\n"
                f"   时间：{time_str}\n"
                f"   被回复：{parent_text}...\n"
                f"   回复内容：{text}{image_info}\n"
                f"   链接：{source_url}"
            )
            self.message_signal.emit(msg)
            self._push_to_qq(msg)
            time.sleep(self.qq_interval)

    def _notify_comment(self, comment, source_label, source_url):
        """通知一级评论"""
        text = comment.get("content", {}).get("message", "")
        ctime = comment.get("ctime", 0)
        time_str = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S") if ctime else "未知"

        image_urls = extract_images_from_comment(comment)
        image_info = ""
        if image_urls:
            image_info = f"\n🖼️ 图片({len(image_urls)}张)：\n" + "\n".join(image_urls)

        msg = (
            f"\n💬 [{self.up_name}] 在{source_label}发表了新评论\n"
            f"   时间：{time_str}\n"
            f"   内容：{text}{image_info}\n"
            f"   链接：{source_url}"
        )
        self.message_signal.emit(msg)
        self._push_to_qq(msg)

    def _push_to_qq(self, text):
        """模拟QQ发送消息"""
        try:
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            pyautogui.press("enter")
            self.message_signal.emit("  ✅ QQ消息推送成功")
        except Exception as e:
            self.message_signal.emit(f"  ⚠️ QQ发送失败: {e}")


# ==================== GUI界面 ====================

class UPSlotWidget(QFrame):
    """单个UP主槽位 — 横向卡片，空/满两种状态，hover可更换UID"""
    uid_changed = pyqtSignal()

    def __init__(self, index):
        super().__init__()
        self.index = index
        self._up_info = None
        self._fetch_worker = None
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._do_fetch)
        self._pending_uid = None

        self.setObjectName("upSlot")
        self.setMinimumSize(140, 170)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(4)

        # 序号徽章
        self.badge = QLabel(str(index + 1))
        self.badge.setFixedSize(22, 22)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setObjectName("upSlotBadge")

        # 内容堆叠
        self.stack = QStackedWidget()

        # --- 空状态页 ---
        self.empty_page = QWidget()
        el = QVBoxLayout(self.empty_page)
        el.setContentsMargins(0, 2, 0, 0)
        el.setSpacing(6)
        el.setAlignment(Qt.AlignCenter)
        hint = QLabel("待配置")
        hint.setObjectName("upSlotPlaceholder")
        hint.setAlignment(Qt.AlignCenter)
        el.addWidget(hint)
        self.uid_edit = QLineEdit()
        self.uid_edit.setPlaceholderText("输入UID")
        self.uid_edit.setObjectName("upSlotInput")
        self.uid_edit.setAlignment(Qt.AlignCenter)
        self.uid_edit.textChanged.connect(self._on_text_changed)
        self.uid_edit.returnPressed.connect(self._on_return_pressed)
        el.addWidget(self.uid_edit)
        el.addStretch()
        self.stack.addWidget(self.empty_page)

        # --- 满状态页 ---
        self.filled_page = QWidget()
        fl = QVBoxLayout(self.filled_page)
        fl.setContentsMargins(0, 2, 0, 0)
        fl.setSpacing(10)
        fl.setAlignment(Qt.AlignCenter)

        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(64, 64)
        self.avatar_label.setObjectName("upSlotAvatar")
        self.avatar_label.setAlignment(Qt.AlignCenter)
        fl.addWidget(self.avatar_label, 0, Qt.AlignCenter)

        self.name_label = QLabel("")
        self.name_label.setObjectName("upSlotName")
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        fl.addWidget(self.name_label, 0, Qt.AlignCenter)

        fl.addStretch()
        self.stack.addWidget(self.filled_page)

        root.addWidget(self.badge, 0, Qt.AlignLeft)
        root.addWidget(self.stack, 1)

        # ---- Hover遮罩（绝对定位，覆盖整个widget） ----
        self.overlay = QLabel("点击更换", self)
        self.overlay.setObjectName("upSlotOverlay")
        self.overlay.setAlignment(Qt.AlignCenter)
        self.overlay.hide()

        self.stack.setCurrentIndex(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.overlay.setGeometry(self.rect())

    def enterEvent(self, event):
        if self._up_info is not None and self.stack.currentIndex() == 1:
            self.overlay.show()
            self.overlay.raise_()

    def leaveEvent(self, event):
        self.overlay.hide()

    def mousePressEvent(self, event):
        if self._up_info is not None and self.stack.currentIndex() == 1:
            # 切换到编辑模式
            self._up_info = None
            self.avatar_label.clear()
            self.name_label.setText("")
            self.uid_edit.clear()
            self.stack.setCurrentIndex(0)
            self.uid_edit.setFocus()
        super().mousePressEvent(event)

    def get_uid(self):
        return self.uid_edit.text().strip()

    def get_info(self):
        return self._up_info

    def set_enabled(self, enabled):
        self.uid_edit.setEnabled(enabled)

    def _on_text_changed(self, text):
        text = text.strip()
        try:
            uid = int(text)
            if uid > 0:
                self._pending_uid = uid
                self._debounce_timer.start(500)
                return
        except ValueError:
            pass
        self._pending_uid = None
        self._debounce_timer.stop()

    def _on_return_pressed(self):
        self._debounce_timer.stop()
        uid_text = self.uid_edit.text().strip()
        try:
            uid = int(uid_text)
            if uid > 0:
                self._fetch_up_info(uid)
        except ValueError:
            pass

    def _do_fetch(self):
        if self._pending_uid:
            self._fetch_up_info(self._pending_uid)

    def _fetch_up_info(self, uid):
        if self._fetch_worker and self._fetch_worker.isRunning():
            self._fetch_worker.terminate()
        self._fetch_worker = InfoFetchWorker(uid)
        self._fetch_worker.info_ready.connect(self._on_info_ready)
        self._fetch_worker.start()

    def _on_info_ready(self, info):
        self._up_info = info
        pixmap = load_circular_avatar(info["face"], 64)
        if pixmap:
            self.avatar_label.setPixmap(pixmap)
        self.name_label.setText(info["name"])
        self.stack.setCurrentIndex(1)
        self.uid_changed.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.monitor_threads = []
        self.up_slots = []
        self._running = False
        self._elapsed = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick_runtime)
        self.init_ui()

    # ==================== UI 构建 ====================

    def init_ui(self):
        self.setWindowTitle("BiliMonitor · B站评论监控")
        self.setGeometry(100, 100, 940, 820)
        self.setMinimumSize(720, 620)

        # ---- 全局样式表 ----
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLOR_BG};
            }}
            QWidget {{
                font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
            }}
            QLabel {{
                color: {COLOR_TEXT};
                font-size: 13px;
            }}
            QLineEdit {{
                background: {COLOR_BG_INPUT};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
                padding: 9px 14px;
                color: {COLOR_TEXT};
                font-size: 13px;
                selection-background-color: {COLOR_ACCENT};
            }}
            QLineEdit:focus {{
                border-color: {COLOR_ACCENT};
                background: {COLOR_BG_CARD};
            }}
            QLineEdit:disabled {{
                opacity: 0.45;
            }}
            QSpinBox {{
                background: {COLOR_BG_INPUT};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
                padding: 8px 12px;
                color: {COLOR_TEXT};
                font-size: 13px;
                min-width: 85px;
            }}
            QSpinBox:focus {{
                border-color: {COLOR_ACCENT};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 22px;
                border: none;
                background: transparent;
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                border-radius: 3px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {COLOR_BORDER};
                border-radius: 3px;
                min-height: 36px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {COLOR_ACCENT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}

            /* ====== UP主槽位 ====== */
            #upSlot {{
                background: {COLOR_BG_CARD};
                border: 1px solid {COLOR_BORDER};
                border-radius: 14px;
            }}
            #upSlot:hover {{
                border-color: rgba(251, 114, 153, 0.5);
            }}
            #upSlotBadge {{
                background: {COLOR_ACCENT};
                color: {COLOR_TEXT_BRIGHT};
                border-radius: 11px;
                font-weight: bold;
                font-size: 11px;
            }}
            #upSlotPlaceholder {{
                color: {COLOR_TEXT_DIM};
                font-size: 12px;
            }}
            #upSlotInput {{
                border: 1px solid {COLOR_BORDER};
                background: {COLOR_BG_INPUT};
                border-radius: 8px;
                padding: 8px 6px;
                color: {COLOR_TEXT};
                font-size: 13px;
                max-width: 120px;
            }}
            #upSlotInput:focus {{
                border-color: {COLOR_ACCENT};
                background: {COLOR_BG};
            }}
            #upSlotAvatar {{
                border: 3px solid {COLOR_ACCENT};
                border-radius: 32px;
                background: {COLOR_BG};
            }}
            #upSlotName {{
                color: {COLOR_TEXT_BRIGHT};
                font-size: 13px;
                font-weight: 700;
                max-width: 120px;
            }}
            #upSlotOverlay {{
                background: rgba(13, 17, 23, 0.82);
                color: {COLOR_ACCENT};
                font-size: 14px;
                font-weight: 700;
                border-radius: 14px;
            }}

            /* ====== 面板卡片 ====== */
            #panelCard {{
                background: {COLOR_BG_CARD};
                border: 1px solid {COLOR_BORDER};
                border-radius: 14px;
                padding: 20px;
            }}

            /* ====== 设置面板 ====== */
            #settingsPanel {{
                background: {COLOR_BG_CARD};
                border: 1px solid {COLOR_BORDER};
                border-radius: 14px;
                padding: 16px;
            }}

            /* ====== 标题标签 ====== */
            #sectionTitle {{
                color: {COLOR_TEXT_BRIGHT};
                font-size: 14px;
                font-weight: 700;
                margin-bottom: 2px;
            }}
            #sectionSubtitle {{
                color: {COLOR_TEXT_DIM};
                font-size: 11px;
            }}
            #sectionIcon {{
                font-size: 16px;
            }}

            /* ====== 日志区 ====== */
            #logArea {{
                background: {COLOR_BG};
                border: 1px solid {COLOR_BORDER};
                border-radius: 12px;
                color: {COLOR_TEXT};
                font-family: "Cascadia Code", "Fira Code", "Consolas", "Monaco", monospace;
                font-size: 12px;
                padding: 14px;
                line-height: 1.7;
                selection-background-color: {COLOR_ACCENT};
            }}

            /* ====== 主按钮 ====== */
            #btnStart {{
                background: {COLOR_ACCENT};
                border: none;
                border-radius: 12px;
                padding: 14px 48px;
                color: white;
                font-size: 16px;
                font-weight: 700;
            }}
            #btnStart:hover {{
                background: {COLOR_ACCENT_HOVER};
            }}
            #btnStart:pressed {{
                background: #E05A80;
            }}
            #btnStart:disabled {{
                background: {COLOR_BORDER};
                color: {COLOR_TEXT_DIM};
            }}

            #btnStop {{
                background: transparent;
                border: 2px solid {COLOR_RED};
                border-radius: 12px;
                padding: 12px 46px;
                color: {COLOR_RED};
                font-size: 16px;
                font-weight: 700;
            }}
            #btnStop:hover {{
                background: rgba(248, 81, 73, 0.12);
            }}
            #btnStop:pressed {{
                background: rgba(248, 81, 73, 0.22);
            }}
            #btnStop:disabled {{
                border-color: {COLOR_BORDER};
                color: {COLOR_TEXT_DIM};
            }}

            /* ====== Header ====== */
            #headerLogo {{
                font-size: 24px;
                font-weight: 800;
                color: {COLOR_ACCENT};
                letter-spacing: 1px;
            }}
            #headerVersion {{
                font-size: 11px;
                color: {COLOR_TEXT_DIM};
                padding-top: 10px;
            }}
            #headerDivider {{
                color: {COLOR_BORDER};
                font-size: 18px;
                padding-top: 4px;
            }}
            #gearBtn {{
                background: transparent;
                border: 1px solid {COLOR_BORDER};
                border-radius: 10px;
                color: {COLOR_TEXT_DIM};
                font-size: 18px;
                padding: 4px 8px;
            }}
            #gearBtn:hover {{
                background: rgba(251, 114, 153, 0.1);
                border-color: {COLOR_ACCENT};
                color: {COLOR_ACCENT};
            }}
            #gearBtn:checked {{
                background: rgba(251, 114, 153, 0.15);
                border-color: {COLOR_ACCENT};
                color: {COLOR_ACCENT};
            }}

            /* ====== 状态栏 ====== */
            QStatusBar {{
                background: {COLOR_BG_CARD};
                border-top: 1px solid {COLOR_BORDER};
                color: {COLOR_TEXT_DIM};
                font-size: 12px;
                padding: 4px 14px;
            }}
        """)

        # 主容器
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(16)
        root.setContentsMargins(24, 22, 24, 18)

        # ==================== Header ====================
        header = QHBoxLayout()
        header.setSpacing(10)

        logo = QLabel("BiliMonitor")
        logo.setObjectName("headerLogo")
        header.addWidget(logo)

        version = QLabel("v3.2")
        version.setObjectName("headerVersion")
        header.addWidget(version)

        div = QLabel("·")
        div.setObjectName("headerDivider")
        header.addWidget(div)

        self.status_led = QLabel("●")
        self.status_led.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 12px; padding-top: 2px;")
        header.addWidget(self.status_led)

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_DIM}; padding-top: 2px;")
        header.addWidget(self.status_label)

        header.addStretch()

        # 齿轮按钮
        self.gear_btn = QPushButton("⚙")
        self.gear_btn.setObjectName("gearBtn")
        self.gear_btn.setFixedSize(38, 38)
        self.gear_btn.setToolTip("监控设置")
        self.gear_btn.setCheckable(True)
        self.gear_btn.clicked.connect(self._toggle_settings)
        header.addWidget(self.gear_btn)

        root.addLayout(header)

        # ==================== 设置面板（默认隐藏） ====================
        self.settings_panel = QFrame()
        self.settings_panel.setObjectName("settingsPanel")
        self.settings_panel.setVisible(False)
        cfg_layout = QHBoxLayout(self.settings_panel)
        cfg_layout.setContentsMargins(16, 12, 16, 12)
        cfg_layout.setSpacing(20)

        cfg_icon = QLabel("⚙️")
        cfg_icon.setObjectName("sectionIcon")
        cfg_layout.addWidget(cfg_icon)

        cfg_title = QLabel("监控设置")
        cfg_title.setObjectName("sectionTitle")
        cfg_layout.addWidget(cfg_title)

        cfg_layout.addStretch()

        for label_text, spin_obj_name, val, rng, suffix, tip in [
            ("轮询间隔", "monitorSpin", 10, (3, 120), " 秒", "检查新视频/动态/评论的间隔"),
            ("发送间隔", "qqSpin", 1, (1, 10), " 秒", "多条消息之间发送间隔"),
        ]:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 12px;")
            cfg_layout.addWidget(lbl)
            sp = QSpinBox()
            sp.setRange(*rng)
            sp.setValue(val)
            sp.setSuffix(suffix)
            sp.setToolTip(tip)
            if spin_obj_name == "monitorSpin":
                self.monitor_spin = sp
            else:
                self.qq_spin = sp
            cfg_layout.addWidget(sp)

        root.addWidget(self.settings_panel)

        # ==================== UP主配置面板 ====================
        up_panel = QFrame()
        up_panel.setObjectName("panelCard")
        up_panel_layout = QVBoxLayout(up_panel)
        up_panel_layout.setSpacing(12)
        up_panel_layout.setContentsMargins(20, 18, 20, 16)

        # 标题行
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_icon = QLabel("👥")
        title_icon.setObjectName("sectionIcon")
        title_row.addWidget(title_icon)
        title = QLabel("UP 主配置")
        title.setObjectName("sectionTitle")
        title_row.addWidget(title)
        subtitle = QLabel("5 位常驻 · 点击已配置的可更换")
        subtitle.setObjectName("sectionSubtitle")
        title_row.addWidget(subtitle)
        title_row.addStretch()
        self.up_count_label = QLabel("0/5")
        self.up_count_label.setStyleSheet(f"color: {COLOR_ACCENT}; font-size: 14px; font-weight: 700;")
        title_row.addWidget(self.up_count_label)
        up_panel_layout.addLayout(title_row)

        # 5 位槽位横向排列
        slots_row = QHBoxLayout()
        slots_row.setSpacing(12)
        for i in range(5):
            slot = UPSlotWidget(i)
            slot.uid_changed.connect(self._update_up_count)
            self.up_slots.append(slot)
            slots_row.addWidget(slot, 1)
        up_panel_layout.addLayout(slots_row)

        root.addWidget(up_panel, 0)

        # ==================== 日志区 ====================
        log_header = QHBoxLayout()
        log_header.setSpacing(8)
        log_icon = QLabel("📋")
        log_icon.setObjectName("sectionIcon")
        log_header.addWidget(log_icon)
        log_label = QLabel("运行日志")
        log_label.setObjectName("sectionTitle")
        log_header.addWidget(log_label)
        log_header.addStretch()
        root.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setObjectName("logArea")
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("  · 监控日志将在此实时显示...")
        root.addWidget(self.log_text, 1)

        # ==================== 控制按钮 ====================
        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)
        btn_row.addStretch()

        self.start_btn = QPushButton("▶  开始监控")
        self.start_btn.setObjectName("btnStart")
        self.start_btn.setFixedHeight(52)
        self.start_btn.setMinimumWidth(180)
        self.start_btn.clicked.connect(self.start_monitor)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹  停止监控")
        self.stop_btn.setObjectName("btnStop")
        self.stop_btn.setFixedHeight(52)
        self.stop_btn.setMinimumWidth(180)
        self.stop_btn.clicked.connect(self.stop_monitor)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.stop_btn)

        btn_row.addStretch()
        root.addLayout(btn_row)

        # ==================== 状态栏 ====================
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("  就绪 — 请添加 UP 主 UID 后点击开始监控")

    def _toggle_settings(self):
        show = self.gear_btn.isChecked()
        self.settings_panel.setVisible(show)

    # ==================== UP主管理 ====================

    def _update_up_count(self):
        n = sum(1 for s in self.up_slots if s.get_info() is not None)
        self.up_count_label.setText(f"{n}/5")

    # ==================== 日志 ====================

    def append_log(self, text):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"<span style='color:{COLOR_TEXT_DIM};'>[{ts}]</span> {text}")
        bar = self.log_text.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ==================== 监控控制 ====================

    def start_monitor(self):
        uids = []
        for slot in self.up_slots:
            uid_text = slot.get_uid()
            if not uid_text:
                continue
            try:
                uid = int(uid_text)
                if uid > 0:
                    uids.append(uid)
            except ValueError:
                pass

        if not uids:
            QMessageBox.warning(self, "提示", "请至少输入一个有效的 UP 主 UID！")
            return

        if len(uids) != len(set(uids)):
            QMessageBox.warning(self, "提示", "存在重复的 UP 主 UID，请检查！")
            return

        self._running = True
        self._elapsed = 0
        self._timer.start(1000)

        # 关闭设置面板
        self.gear_btn.setChecked(False)
        self.settings_panel.setVisible(False)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.gear_btn.setEnabled(False)
        for slot in self.up_slots:
            slot.set_enabled(False)

        self.status_led.setStyleSheet(f"color: {COLOR_GREEN}; font-size: 14px;")
        self.status_label.setText(f"监控中 · {len(uids)} 位 UP 主")
        self.status_bar.showMessage(f"  监控运行中 | 共 {len(uids)} 位 UP 主")

        self.monitor_threads = []
        for uid in uids:
            # 从 slot 中获取 UP 主名字
            up_name = None
            for slot in self.up_slots:
                if slot.get_uid() == str(uid) and slot.get_info():
                    up_name = slot.get_info().get("name", "")
                    break
            thread = UPMonitorThread(
                uid=uid,
                up_name=up_name,
                monitor_interval=self.monitor_spin.value(),
                qq_interval=self.qq_spin.value()
            )
            thread.message_signal.connect(self.append_log)
            thread.start()
            self.monitor_threads.append(thread)

        self.append_log("━" * 50)
        self.append_log(f"<b style='color:{COLOR_ACCENT};'>监控已启动</b> · {len(uids)} 位 UP 主 · 间隔 {self.monitor_spin.value()}s")
        self.append_log("━" * 50)

    def stop_monitor(self):
        self._running = False
        self._timer.stop()

        for thread in self.monitor_threads:
            thread.stop()
        self.status_bar.showMessage("  正在停止...")

        for thread in self.monitor_threads:
            thread.wait(3000)

        self.monitor_threads = []
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.gear_btn.setEnabled(True)
        for slot in self.up_slots:
            slot.set_enabled(True)

        self.status_led.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 14px;")
        self.status_label.setText("已停止")
        self.status_bar.showMessage("  已停止 — 可修改配置后重新开始")
        self.append_log(f"<b style='color:{COLOR_RED};'>监控已停止</b>")

    def _tick_runtime(self):
        self._elapsed += 1
        m, s = divmod(self._elapsed, 60)
        h, m = divmod(m, 60)
        runtime = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        self.status_bar.showMessage(f"  运行中 {runtime}  | 共 {len(self.monitor_threads)} 位 UP 主")

    def closeEvent(self, event):
        self._timer.stop()
        for thread in self.monitor_threads:
            if thread.isRunning():
                thread.stop()
                thread.wait(3000)
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())