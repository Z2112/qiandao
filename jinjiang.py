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

random_signin = os.getenv('RANDOM_SIGNIN', 'false').lower() == 'true'
always_notify = os.getenv('ALWAYS_NOTIFY', 'false').lower() == 'true'
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
    print(f"\n{'='*50}")
    print(f"📌 第 {idx} 个账号")
    masked = cookie[:12] + "..." + cookie[-8:] if len(cookie) > 20 else cookie

    try:
        headers = get_headers(cookie)
        resp = requests.get("https://m.jjwxc.net/my/signIn", headers=headers, timeout=15)
        response = resp.json()

        # ====================== 保存完整返回 ======================
        try:
            with open("jinjiang_last_response.json", "w", encoding="utf-8") as f:
                json.dump(response, f, ensure_ascii=False, indent=2)
            print("📁 已保存完整返回 JSON 到: jinjiang_last_response.json")
        except Exception as e:
            print(f"⚠️ 保存失败: {e}")

        # ====================== 正确解析结构 ======================
        result = response.get("data", {})          # 真正的数据在这里
        message = response.get("message", "")
        print(f"📢 返回信息: {message}")

        is_already_signed = (
            "当天已经签到" in message or 
            "不需要重复签到" in message or 
            "70003" in str(message)
        )

        points_msg = ""
        is_fail = False
        if is_already_signed:
            print("ℹ️ 今日已签到，无需重复操作")
            sign_result = f"✅ 今日已签到 | 账号{idx}"
        else:
            # ====================== 正确提取 signdays 和 coins ======================
            signdays = result.get("signdays")
            coins = result.get("coins")

            # 兜底正则（兼容 message 里带天数的情况）
            if signdays is None:
                m = re.search(r'连续签到\s*(\d+)', message)
                if m:
                    signdays = m.group(1)

            if coins is None:
                m = re.search(r'月石\s*(\d+)', message)
                if m:
                    coins = m.group(1)

            # 输出
            if signdays:
                print(f"🔥【连续签到】{signdays} 天")
            if coins:
                print(f"💎【月石余额】{coins} 枚")

            parts = ["✅ 签到成功", f"账号{idx}"]
            if signdays:
                parts.append(f"连续签到{signdays}天")
            if coins:
                parts.append(f"月石: {coins}")
            if not signdays and not coins and message:
                parts.append(message)
            sign_result = " | ".join(parts)
            points_msg = sign_result
            print(f"📊 {sign_result}")

        # ALWAYS_NOTIFY=true：成功/失败都发；false：仅失败时发
        if send and (always_notify or is_fail):
            send("晋江文学城签到", sign_result)
            print("📨 已推送通知" + ("（ALWAYS_NOTIFY=true）" if always_notify else ""))
        else:
            print("✅ 签到成功/已签到，ALWAYS_NOTIFY=false，跳过通知")

    except Exception as e:
        error_line = f"❌ 签到失败 | 账号{idx} | 执行异常: {e}"
        print(error_line)
        if send:
            send("晋江文学城签到", error_line)

    print(f"{'='*50}")

print("\n【晋江文学城签到】执行完毕")
