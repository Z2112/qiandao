# -*- coding: utf-8 -*-
"""
青龙面板 - JKForum 自动签到脚本
接口：PUT https://jkforum.net/api/jkf-dailysign/v1/DailySign
"""

import os
import json
import random
import requests
from datetime import datetime

# ==================== 配置 ====================
JKFORUM_COOKIE = os.environ.get("JKFORUM_COOKIE", "")

# 建议把 User-Agent 换成你自己常用的
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Origin": "https://jkforum.net",           # 青龙环境改成这个
    "Referer": "https://jkforum.net/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

def jkforum_sign():
    if not JKFORUM_COOKIE:
        print("❌ 未设置环境变量 JKFORUM_COOKIE")
        return False

    # 解析 Cookie
    cookies = {}
    for item in JKFORUM_COOKIE.split(";"):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            cookies[k] = v

    url = "https://jkforum.net/api/jkf-dailysign/v1/DailySign"

    # 构造请求体（模拟原脚本随机心情）
    payload = {
        "moodStickerId": random.randint(1, 9),
        "message": "签到"
    }

    try:
        resp = requests.put(
            url,
            headers=HEADERS,
            cookies=cookies,
            json=payload,
            timeout=20
        )

        print(f"[{datetime.now()}] 状态码: {resp.status_code}")
        print(f"返回内容: {resp.text}")

        if resp.status_code == 200:
            print("✅ 签到成功！")
            return True
        else:
            print("❌ 签到失败")
            return False

    except Exception as e:
        print(f"请求异常: {e}")
        return False


if __name__ == "__main__":
    print("开始执行 JKForum 签到任务...")
    jkforum_sign()
