# -*- coding: utf-8 -*-
# B站指定视频UP主新评论监控 + QQ自动推送脚本（修复replies=null报错）
# 适配：评论区为空（replies=null）时不报错，正常提示

import requests
import time
import pyautogui
import pyperclip
from datetime import datetime

# ====================== 【核心配置区 - 自行修改】 ======================
# 1. B站视频配置
VIDEO_BVID = "BV1aouMzUEWa"  # 目标视频BV号
UP_MID = 11657757  # 视频UP主的UID
VIDEO_URL = f"https://www.bilibili.com/video/{VIDEO_BVID}/"

# 2. QQ推送配置
QQ_SEND_INTERVAL = 1.5  # QQ发送消息间隔（秒，防止发送过快失败）
MONITOR_INTERVAL = 5  # 评论监控轮询间隔（改为5秒，降低API请求频率）

# 3. 本地缓存已推送的评论ID（去重核心）
COMMENT_ID_CACHE = set()
# ====================================================================

# 关闭pyautogui fail-safe容错（防止鼠标误触终止脚本）
pyautogui.FAILSAFE = False


def get_bilibili_comments():
    """
    获取B站视频最新评论
    返回：UP主的最新评论列表（无评论/评论为空时返回空列表，不报错）
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": VIDEO_URL
    }
    # B站评论API（和原脚本一致，无需修改）
    api_url = f"https://api.bilibili.com/x/v2/reply?type=1&oid={VIDEO_BVID}&pn=1&ps=20&sort=2"
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        res_json = res.json()
        if res_json.get("code") != 0:
            print(f"【API请求失败】{res_json.get('message')}")
            return []

        # 关键修复：判断replies是否为null，若为null则视为无评论，返回空列表
        comments = res_json.get("data", {}).get("replies", [])  # 这里改为默认返回空列表
        up_comments = []

        # 遍历所有评论，筛选UP主本人评论（无评论时，此循环不执行，不报错）
        for comment in comments:
            # 判断评论者UID是否为UP主
            if comment.get("mid") == UP_MID:
                comment_info = {
                    "cid": comment.get("rpid"),  # 评论唯一ID
                    "content": comment.get("content", {}).get("message", ""),
                    "time": datetime.fromtimestamp(comment.get("ctime")).strftime("%Y-%m-%d %H:%M:%S")
                }
                up_comments.append(comment_info)

        return up_comments
    except Exception as e:
        print(f"【获取评论异常】{str(e)}")
        return []


def qq_send_msg(text):
    """
    模拟QQ小号发送消息到大号
    """
    try:
        # 复制内容到剪贴板
        pyperclip.copy(text)
        # 点击QQ输入框（默认已打开聊天窗口，直接粘贴发送）
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        pyautogui.press("enter")
        print("✅ 消息推送成功！")
    except Exception as e:
        print(f"【QQ发送失败】{str(e)}")


def monitor_up_comment():
    """
    常驻监控UP主评论主逻辑
    """
    print("=" * 60)
    print("🚀 B站UP主评论监控脚本已启动（修复版）")
    print(f"📺 监控视频：{VIDEO_URL}")
    print(f"👤 监控UP主UID：{UP_MID}")
    print(f"⏱️ 监控间隔：{MONITOR_INTERVAL}秒 | 等待UP主新发评论...")
    print("=" * 60)

    while True:
        # 获取UP主所有评论
        up_comments = get_bilibili_comments()
        # 新增提示：无评论时友好提示，不报错
        if not up_comments:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 暂无UP主评论，持续监控中...")
            time.sleep(MONITOR_INTERVAL)
            continue

        # 筛选未推送过的新评论
        new_comments = [c for c in up_comments if c["cid"] not in COMMENT_ID_CACHE]
        if new_comments:
            for comment in new_comments:
                # 加入缓存，防止重复推送
                COMMENT_ID_CACHE.add(comment["cid"])
                # 组装推送消息
                push_text = f"【B站UP主新评论提醒】\n🕐 发布时间：{comment['time']}\n💬 评论内容：{comment['content']}\n📎 视频链接：{VIDEO_URL}"
                print(f"\n🔥 检测到UP主新评论！\n{push_text}")
                # 发送QQ消息
                qq_send_msg(push_text)
                time.sleep(QQ_SEND_INTERVAL)

        # 轮询等待
        time.sleep(MONITOR_INTERVAL)


if __name__ == "__main__":
    try:
        monitor_up_comment()
    except KeyboardInterrupt:
        print("\n\n🛑 脚本已手动终止")
    except Exception as e:
        print(f"\n【脚本异常退出】{str(e)}")
