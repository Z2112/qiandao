# cron: 0 10 * * *
# new Env('比思论坛签到')

"""
比思论坛自动签到脚本（适配青龙面板）
环境变量：
    BISI_COOKIE          必填，你的论坛Cookie（完整字符串）
    RANDOM_SIGNIN        可选，设置为 true 开启随机延迟（默认不开启）
    MAX_RANDOM_DELAY     可选，最大延迟秒数（默认3600秒），需配合 RANDOM_SIGNIN=true 使用
"""

import os
import random
import re
import time

import requests

print("【比思论坛签到】脚本开始执行...")

# ====================== 环境变量读取 ======================
cookie = os.environ.get("BISI_COOKIE")
if not cookie:
    print("❌ 未检测到 BISI_COOKIE 环境变量，请先添加！")
    exit(1)

# 随机延迟配置
random_signin = os.environ.get("RANDOM_SIGNIN"， "false").strip().lower() == "true"
max_delay = int(os.environ.get("MAX_RANDOM_DELAY"， "3600").strip())

if random_signin:
    delay_seconds = random.randint(1, max_delay)
    print(f"✅ 已开启随机延迟，本次延迟 {delay_seconds} 秒")
    # 倒计时显示（剩余多少分钟多少秒）
    for remaining 在 range(delay_seconds, 0, -1):
        minutes = remaining // 60
        seconds = remaining % 60
        print(f"\r⏳ 剩余 {minutes} 分 {seconds} 秒后开始签到..."， end="", flush=True)
        time.sleep(1)
    print("\r✅ 随机延迟结束，开始执行签到任务！          ")
else:
    print("ℹ️ 随机延迟未开启，直接执行签到")

# ====================== 请求配置 ======================
base_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Encoding": "gzip, deflate, sdch, br",
    "Connection": "keep-alive",
}

# ====================== Step 1: 获取 formhash ======================
print("🔄 正在获取 formhash...")
get_url = "http://hkcdnmesh.site/plugin.php?id=dsu_paulsign%3Asign"

try:
    resp_get = requests.get(
        get_url,
        headers={**base_headers, "Cookie": cookie}，
        timeout=15，
        allow_redirects=True,
    )
    resp_get.raise_for_status()
except Exception as e:
    print(f"❌ GET 请求失败: {e}")
    exit(1)

# 提取 formhash
formhash_match = re.search(r'formhash=(.+?)">', resp_get.text)
if not formhash_match:
    print("❌ 未在页面中找到 formhash，请检查 Cookie 是否有效")
    exit(1)

formhash = formhash_match.group(1).strip()
print(f"✅ 获取到 formhash: {formhash}")

# ====================== Step 2: 提交签到 ======================
print("🔄 正在提交签到请求...")
post_url = "http://hkcdnmesh.site/plugin.php?id=dsu_paulsign%3Asign&operation=qiandao&infloat=1&sign_as=1&inajax=1"

post_data = {
    "formhash": formhash,
    "qdxq": "fd",
}

post_headers = {
    "Proxy-Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "Upgrade-Insecure-Requests": "1",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cookie": cookie,
}

try:
    resp_post = requests.post(
        post_url,
        headers=post_headers,
        data=post_data,
        timeout=15,
    )
    resp_text = resp_post.text

    if "成功" in resp_text or "签到" in resp_text:
        print("🎉 签到成功！")
        # 尝试提取提示信息
        tip_match = re.search(r'([\u4e00-\u9fa5]+签到成功[^<]*)', resp_text)
        if tip_match:
            print(f"📢 {tip_match.group(1)}")
        else:
            print(f"📢 原始返回: {resp_text[:200]}...")
    else:
        print("⚠️ 签到可能失败，请检查返回内容")
        print(f"返回内容预览: {resp_text[:300]}...")

except Exception as e:
    print(f"❌ POST 请求异常: {e}")

print("【比思论坛签到】脚本执行完毕！")
