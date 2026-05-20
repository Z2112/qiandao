"""
# ==================== 青龙面板使用说明（晋江文学城签到） ====================

# 【脚本名称】 晋江文学城签到（支持多账号）
# 【cron 定时】 每天 10:00 执行（可自行修改）
# 【环境变量】
#    JINJIANG_COOKIE  → Cookie 值（必填，支持多账号）
#       • 单账号：直接粘贴一个 Cookie
#       • 多账号：用换行符（推荐）、& 或 @ 分割
#         示例：
#         Cookie1
#         Cookie2
#         或 Cookie1&Cookie2
# 【可选变量】
#    RANDOM_SIGNIN      → true 开启随机延迟（默认 false）
#    MAX_RANDOM_DELAY   → 最大随机延迟秒数（默认 3600 秒 = 1小时）
# 【通知逻辑】 今日已签到（“当天已经签到”、“不需要重复签到”等）→ 仅打印日志，不通知；签到成功或失败 → 通过青龙通知系统推送
#
# 【详细使用步骤】
# 1. 青龙面板 → 依赖管理 → 新建 Python 依赖，安装以下依赖：
#       requests
# 2. 青龙面板 → 环境变量 → 新建变量 JINJIANG_COOKIE，填入一个或多个 Cookie（支持多行）
# 3. 青龙面板 → 定时任务 → 新建任务，脚本路径指向本文件（例如 task/jinjiang.py）
# 4. 保存后点击“立即执行”测试，查看日志是否显示每个账号的签到结果
#
# 【注意事项】
# • 建议每个 Cookie 对应一个晋江账号
# • Cookie 获取方式：登录 m.jjwxc.net 后，复制整个 Cookie 字符串
# • 脚本会自动识别并处理多个 Cookie
# • 如出现签到失败，可尝试重新登录获取最新 Cookie
#
# 作者：Grok（根据用户提供的 jinjiang.py 优化）
# 更新日期：2026-05-21
"""

# cron: 0 10 * * *
# new Env('晋江文学签到')

import os
import re
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
JINJIANG_COOKIE = os.getenv('JINJIANG_COOKIE')
if not JINJIANG_COOKIE:
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

# ==================== 解析多 Cookie ====================
def parse_cookies(env_value: str):
    """支持换行、&、@ 分割多个 Cookie"""
    if not env_value:
        return []
    # 按换行、&、@ 分割并清理
    cookies = [c.strip() for c in re.split(r'[\n@&]', env_value) if c.strip()]
    return cookies

cookies_list = parse_cookies(JINJIANG_COOKIE)
if not cookies_list:
    msg = "❌ JINJIANG_COOKIE 解析失败，请检查格式"
    print(msg)
    if send:
        send("晋江文学签到", msg)
    sys.exit(1)

print(f"✅ 共检测到 {len(cookies_list)} 个 Cookie，开始签到...")

# ==================== 请求头模板 ====================
def get_headers(cookie: str):
    return {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
        "referer": "https://m.jjwxc.net/my/signinIndex",
        "Cookie": cookie,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

# ==================== 主流程 ====================
for idx, cookie in enumerate(cookies_list, 1):
    print(f"\n📌 第 {idx}/{len(cookies_list)} 个账号")
    # 简单打码显示 Cookie（保护隐私）
    masked_cookie = cookie[:15] + "..." + cookie[-10:] if len(cookie) > 25 else cookie

    try:
        headers = get_headers(cookie)

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

        # ==================== 发送通知（仅成功/失败时通知） ====================
        if notify_flag and send:
            if "签到成功" in sign_result:
                title = "✅ 晋江文学城签到成功"
                body = f"账号: {masked_cookie}\n{sign_result}\n\n{points_msg}"
            else:
                title = "❌ 晋江文学城签到失败"
                body = f"账号: {masked_cookie}\n{sign_result}\n\n{points_msg}\n\n响应内容：{resp.text[:300]}"
            send(title, body)
            print("📨 已通过青龙通知系统发送结果")
        elif not notify_flag:
            print("ℹ️ 今日已签到，无需通知")

    except requests.exceptions.RequestException as e:
        error_msg = f"❌ 网络请求异常: {str(e)}"
        print(error_msg)
        if send:
            send("晋江文学签到", f"账号 {masked_cookie} {error_msg}")
    except Exception as e:
        error_msg = f"❌ 执行异常: {str(e)}"
        print(error_msg)
        if send:
            send("晋江文学签到", f"账号 {masked_cookie} {error_msg}")

print("\n【晋江文学城签到】全部账号执行完毕 ✅")
