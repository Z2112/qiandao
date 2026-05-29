"""
# ==================== 青龙面板使用说明（天翼云盘签到） ====================

# 【脚本名称】 天翼云盘签到（纯 Cookie 方式）
# 【cron 定时】 每天 10:00 执行（可自行修改）
# 【环境变量】（必须设置）
#    CLOUD189_COOKIES  → 文本格式 Cookie（lt=xxx; STK=yyy; ...）
# 【可选变量】
#    RANDOM_SIGNIN      → true 开启随机延迟（默认 false）
#    MAX_RANDOM_DELAY   → 最大随机延迟秒数（默认 3600 秒 = 1小时）
# 【通知逻辑】 今日已签到 → 仅打印日志，不通知；签到成功或失败 → 通过青龙通知系统推送
#
# 【详细使用步骤】
#
# 使用方式：
# 1. 浏览器登录后使用 "Get cookies.txt LOCALLY" 扩展导出 Cookie
# 2. 设置环境变量 CLOUD189_COOKIES（直接粘贴文本）
# 3. 青龙定时任务直接运行本脚本

# 青龙面板依赖：
#   requests（必须）
#
# 【注意事项】
# • 本脚本**仅支持 Cookie 方式**，已完全移除手机号+密码登录相关代码
# • 抽奖逻辑已替换为 dext7r/189pan 项目的改进版本（支持3次抽奖 + 更好错误判断）
# • 如果在青龙 Docker 中运行失败，常见原因是缺少系统依赖，可尝试在容器内执行：
#   apt-get update && apt-get install -y libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2

# 作者：Grok
# 更新日期：2026-05-29
# 说明：纯 Cookie 模式，已移除所有用户名密码登录逻辑
"""

# cron: 0 10 * * *
# new Env('天翼云盘签到')

import os
import sys
import time
import random
import re
import json
import requests

# ==================== 通知模块 ====================
try:
    from notify import send
except ImportError:
    send = None

print("【天翼云盘签到】开始执行...")

# ==================== Cookie 相关函数（文本模式） ====================

def parse_cookie_string(cookie_str: str):
    """将 'lt=xxx; STK=yyy; ...' 格式的 Cookie 字符串解析为 requests 可用的列表"""
    cookies = []
    if not cookie_str:
        return cookies

    cookie_str = cookie_str.strip().replace('\n', ' ').replace('\r', '')

    for item in cookie_str.split(';'):
        item = item.strip()
        if '=' in item:
            name, value = item.split('=', 1)
            name = name.strip()
            value = value.strip()
            if name:
                cookies.append({
                    "name": name,
                    "value": value,
                    "domain": ".cloud.189.cn"
                })
    return cookies


def load_cookies():
    """仅从环境变量 CLOUD189_COOKIES 加载（纯文本格式）"""
    cookies_env = os.getenv("CLOUD189_COOKIES")

    if not cookies_env:
        return None

    cookies = parse_cookie_string(cookies_env.strip())
    if cookies:
        print("ℹ️ 从环境变量 CLOUD189_COOKIES 加载 Cookie")
        return cookies

    return None





def create_session_from_cookies(cookies):
    """根据 Cookie 列表创建带登录状态的 requests.Session"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    })

    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        domain = cookie.get("domain")
        if name and value:
            session.cookies.set(name, value, domain=domain)
    return session


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

# ==================== 主流程 ====================
def main():
    try:
        cookies = load_cookies()

        if not cookies:
            print("❌ 未检测到 CLOUD189_COOKIES 环境变量。")
            print("   请设置环境变量 CLOUD189_COOKIES（文本格式：lt=xxx; STK=yyy; ...）")
            sys.exit(1)

        print("✅ 使用 Cookie 方式执行")
        session = create_session_from_cookies(cookies)

        print("✅ 会话准备完成，开始执行签到...")

        # 签到
        timestamp = str(round(time.time() * 1000))
        sign_url = f"https://api.cloud.189.cn/mkt/userSign.action?rand={timestamp}&clientType=TELEANDROID&version=8.6.3&model=SM-G930K"
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 5.1.1; SM-G930K Build/NRD90M; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/74.0.3729.136 Mobile Safari/537.36 Ecloud/8.6.3 Android/22 clientId/355325117317828 clientModel/SM-G930K imsi/460071114317824 clientChannelId/qq proVersion/1.0.6",
            "Referer": "https://m.cloud.189.cn/zhuanti/2016/sign/index.jsp?albumBackupOpened=1",
            "Host": "m.cloud.189.cn"
        }

        resp_sign = session.get(sign_url, headers=headers, timeout=15)
        data_sign = resp_sign.json()
        netdisk_bonus = data_sign.get("netdiskBonus", 0)
        is_sign = data_sign.get("isSign", 0)

        if str(is_sign) == "1":
            sign_result = "✅ 今日已签到"
            notify_flag = False
        else:
            sign_result = f"✅ 签到成功，获得 {netdisk_bonus}M 空间"
            notify_flag = True

        print(f"📢 签到结果: {sign_result}")

        print("开始执行抽奖...")

        # 三个抽奖链接（支持3次抽奖）
        draw_urls = [
            "https://m.cloud.189.cn/v2/drawPrizeMarketDetails.action?taskId=TASK_SIGNIN&activityId=ACT_SIGNIN",
            "https://m.cloud.189.cn/v2/drawPrizeMarketDetails.action?taskId=TASK_SIGNIN_PHOTOS&activityId=ACT_SIGNIN",
            "https://m.cloud.189.cn/v2/drawPrizeMarketDetails.action?taskId=TASK_2022_FLDFS_KJ&activityId=ACT_SIGNIN"
        ]

        draw_results = []
        draw_headers = headers.copy()

        for i, url in enumerate(draw_urls, 1):
            try:
                if i > 1:
                    time.sleep(5)  # 抽奖之间间隔5秒，降低风控

                resp = session.get(url, headers=draw_headers, timeout=15)
                data = resp.json()

                if "errorCode" in data:
                    msg = f"第{i}次抽奖失败：次数不足"
                    print(f"❌ {msg}")
                else:
                    prize_name = data.get("prizeName", "未知奖品")
                    msg = f"第{i}次抽奖成功：{prize_name}"
                    print(f"🎉 {msg}")

                draw_results.append(msg)

            except Exception as e:
                msg = f"第{i}次抽奖出错: {e}"
                print(f"❌ {msg}")
                draw_results.append(msg)

        # 构建汇总结果
        result_msg = f"{sign_result}\n" + "\n".join(draw_results)
        print("\n【抽奖汇总】")
        for r in draw_results:
            print(f"  {r}")

        # ==================== 通知 ====================
        if notify_flag and send:
            title = "✅ 天翼云盘签到成功" if "签到成功" in sign_result else "❌ 天翼云盘签到失败"
            send(title, result_msg)
            print("📨 已推送通知")
        elif not notify_flag:
            print("ℹ️ 今日已签到，无需通知")

    except Exception as e:
        error_msg = f"❌ 执行异常: {str(e)}"
        print(error_msg)
        if send:
            send("天翼云盘签到", error_msg)

    print("【天翼云盘签到】执行完毕")


if __name__ == "__main__":
    main()
