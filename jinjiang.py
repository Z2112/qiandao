# cron: 0 10 * * *
# new Env('晋江文学签到')

import os
import sys
import time
import random
import requests

# ==================== 通知模块 ====================
try:
    from notify import send
except ImportError:
    send = None

print("【晋江文学城签到】开始执行...")

# ==================== 获取环境变量 ====================
cookie = os.getenv('JINJIANG_COOKIE')
if not cookie:
    msg = "❌ 未设置 JINJIANG_COOKIE 环境变量，请检查青龙面板变量配置"
    print(msg)
    if send:
        send("晋江文学签到", msg)
    sys.exit(1)

# ==================== 随机延迟（可选） ====================
random_signin = os.getenv('RANDOM_SIGNIN', 'false').lower() == 'true'
max_random_delay = os.getenv('MAX_RANDOM_DELAY')

if random_signin:
    try:
        max_d = int(max_random_delay) if max_random_delay else 3600
        if max_d > 0:
            delay_sec = random.randint(1, max_d)
            minutes = delay_sec // 60
            seconds = delay_sec % 60
            print(f"⏳ 随机延迟: 等待 {minutes} 分钟 {seconds} 秒后开始执行")
            time.sleep(delay_sec)
    except Exception as e:
        print(f"⚠️ 随机延迟处理异常（将继续执行）: {e}")
else:
    print("✅ 未开启随机延迟（RANDOM_SIGNIN 未设置为 true）")

# ==================== 请求头 ====================
headers = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
    "referer": "https://m.jjwxc.net/my/signinIndex",
    "Cookie": cookie,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

try:
    # Step 1: GET 签到接口
    sign_url = "https://m.jjwxc.net/my/signIn"
    resp = requests.get(sign_url, headers=headers, timeout=15)
    resp.raise_for_status()

    # 解析 JSON
    data = resp.json()
    message = data.get("message", "")
    signdays = data.get("signdays", "0")
    coins = data.get("coins", "0")

    print(f"📢 签到返回信息: {message}")

    # ==================== 判断签到结果 ====================
    if "当天已经签到" in message or "不需要重复签到" in message:
        sign_result = "今日已签到"
        notify_flag = False
    elif "签到成功" in message or "成功" in message:
        sign_result = "✅ 签到成功"
        notify_flag = True
    else:
        sign_result = "❌ 签到失败或异常"
        notify_flag = True

    # 构建积分信息（与HAR日志格式一致）
    points_msg = f"{message}！--- 您已连续签到{signdays}天，累计获得月石{coins}枚。"
    print(points_msg)

    # ==================== 发送通知 ====================
    if notify_flag and send:
        if "签到成功" in sign_result:
            title = "✅ 晋江文学城签到成功"
            body = f"{sign_result}\n\n{points_msg}"
        else:
            title = "❌ 晋江文学城签到失败"
            body = f"{sign_result}\n\n{points_msg}\n\n响应内容：{resp.text[:300]}"
        send(title, body)
        print("📨 已通过青龙通知系统发送结果")
    elif not notify_flag:
        print("ℹ️ 今日已签到，无需通知")

except requests.exceptions.RequestException as e:
    error_msg = f"❌ 网络请求异常: {str(e)}"
    print(error_msg)
    if send:
        send("晋江文学签到", error_msg)
except Exception as e:
    error_msg = f"❌ 执行异常: {str(e)}"
    print(error_msg)
    if send:
        send("晋江文学签到", error_msg)

print("【晋江文学城签到】执行完毕")
