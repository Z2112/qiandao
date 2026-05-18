# -*- coding: utf-8 -*-
"""
青龙面板 - JKForum 签到 + 资产监控（干净版）
"""

import os
import json
import random
import requests
from datetime import datetime

try:
    from sendNotify import send
except ImportError:
    send = lambda t, c: None

JKFORUM_COOKIE = os.environ.get("JKFORUM_COOKIE", "")
DATA_FILE = "jkforum_data.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Origin": "https://jkforum.net",
    "Referer": "https://jkforum.net/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

TRACK_KEYS = {
    1: "名声", 2: "金币", 5: "宝石", 7: "体力", 9: "总积分"
}


def load_last_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_current_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user_info(cookies):
    url = "https://jkforum.net/api/legoin/v1/SignInInformation"
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=15)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None


def jkforum_sign_and_check():
    if not JKFORUM_COOKIE:
        print("❌ 未设置 JKFORUM_COOKIE")
        return

    cookies = {k.strip(): v.strip() for k, v in 
               (item.split("=", 1) for item in JKFORUM_COOKIE.split(";") if "=" in item)}

    # 签到
    sign_url = "https://jkforum.net/api/jkf-dailysign/v1/DailySign"
    payload = {"moodStickerId": random.randint(1, 9), "message": "签到"}

    try:
        sign_resp = requests.put(sign_url, headers=HEADERS, cookies=cookies, json=payload, timeout=15)
        if sign_resp.status_code == 204:
            sign_result = "✅ 签到成功"
        elif sign_resp.status_code == 406:
            sign_result = "✅ 今天已签到"
        else:
            sign_result = f"⚠️ 签到异常 ({sign_resp.status_code})"
    except Exception as e:
        sign_result = f"❌ 签到失败: {e}"

    # 获取用户信息
    user_info = get_user_info(cookies)
    if not user_info or "content" not in user_info:
        print("❌ 获取用户信息失败")
        return

    content = user_info["content"]
    wallet = content.get("wallet", {}).get("credits", [])

    current_assets = {}
    for item in wallet:
        if item["id"] in TRACK_KEYS:
            current_assets[TRACK_KEYS[item["id"]]] = item["point"]

    # 资产变化
    last_assets = load_last_data()
    change_text = ""
    if last_assets:
        changes = []
        for name, current in current_assets.items():
            last = last_assets.get(name, current)
            diff = current - last
            if diff != 0:
                symbol = "+" if diff > 0 else ""
                changes.append(f"{name}: {symbol}{diff}")
        change_text = "\n".join(changes) if changes else "无变化"
    else:
        change_text = "首次运行，已记录当前资产"

    # 输出内容
    output = f"""{sign_result}

【当前资产】
金币: {current_assets.get('金币', 0)}
宝石: {current_assets.get('宝石', 0)}
名声: {current_assets.get('名声', 0)}
体力: {current_assets.get('体力', 0)}

【资产变化】
{change_text}

角色: {content.get('roles', [{}])[0].get('name', '未知')}
未读消息: {content.get('unreadMessageCount', 0)}"""

    print(output)

    # 推送
    title = f"JKForum 签到 | {datetime.now().strftime('%m-%d %H:%M')}"
    send(title, output)

    save_current_data(current_assets)


if __name__ == "__main__":
    jkforum_sign_and_check()
