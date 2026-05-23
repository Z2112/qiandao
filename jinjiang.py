# cron: 0 10 * * *
# new Env('晋江文学城签到')

import os
import re
import sys
import time
import random
import json
import requests
from datetime import datetime

try:
    from notify import send
except ImportError:
    send = None

print("【晋江文学城签到】开始执行...")

JINJIANG_COOKIE = os.getenv('JINJIANG_COOKIE')
if not JINJIANG_COOKIE:
    print("❌ 未设置 JINJIANG_COOKIE 环境变量")
    sys.exit(1)

# 随机延迟
random_signin = os.getenv('RANDOM_SIGNIN', 'false').lower() == 'true'
if random_signin:
    try:
        max_d = int(os.getenv('MAX_RANDOM_DELAY', 3600))
        delay = random.randint(1, max_d)
        print(f"⏳ 随机延迟 {delay} 秒...")
        time.sleep(delay)
    except:
        pass
else:
    print("✅ 未开启随机延迟")

def parse_cookies(env_value):
    return [c.strip() for c in re.split(r'[\n@&]', env_value) if c.strip()]

cookies_list = parse_cookies(JINJIANG_COOKIE)
print(f"✅ 共检测到 {len(cookies_list)} 个账号")

def get_headers(cookie):
    return {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
        "Cookie": cookie,
    }

for idx, cookie in enumerate(cookies_list, 1):
    print(f"\n📌 第 {idx} 个账号")
    masked = cookie[:12] + "..." + cookie[-8:] if len(cookie) > 20 else cookie

    try:
        headers = get_headers(cookie)

        # 签到接口
        resp = requests.get("https://m.jjwxc.net/my/signIn", headers=headers, timeout=15)
        data = resp.json()

        # ==================== 保存返回内容（调试用）====================
        save_path = os.path.join(os.getcwd(), "jinjiang_last_response.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"📁 已保存响应到: {save_path}")

        message = data.get("message", "")
        print(f"📢 返回信息: {message}")

        # 尝试获取 signdays 和 coins
        signdays = data.get("signdays")
        coins = data.get("coins")

        # 如果没有，就尝试从 message 解析
        if signdays is None:
            m = re.search(r'连续签到\s*(\d+)', message)
            signdays = m.group(1) if m else "?"

        if coins is None:
            m = re.search(r'月石\s*(\d+)', message)
            coins = m.group(1) if m else "?"

        # 判断状态
        if "当天已经签到" in message or "不需要重复签到" in message or "70003" in str(message):
            sign_result = "今日已签到"
            notify_flag = False
        elif "签到成功" in message:
            sign_result = "✅ 签到成功"
            notify_flag = True
        else:
            sign_result = "❌ 签到异常"
            notify_flag = True

        # 输出
        if signdays == "?" or coins == "?":
            points_msg = f"{message}"
        else:
            points_msg = f"{message}！--- 您已连续签到{signdays}天，累计获得月石{coins}枚。"

        print(points_msg)

        # 通知
        if notify_flag and send:
            send("晋江文学城签到", f"账号: {masked}\n{sign_result}\n\n{points_msg}")

        if not notify_flag:
            print("ℹ️ 今日已签到，无需通知")

    except Exception as e:
        print(f"❌ 执行异常: {e}")

print("\n【晋江文学城签到】执行完毕")
