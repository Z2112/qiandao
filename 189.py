# cron: 0 10 * * *
# new Env('天翼云盘签到')

import os
import sys
import time
import random
import requests
import json

# ==================== 通知模块 ====================
try:
    from notify import send
except ImportError:
    send = None

print("【天翼云盘签到】开始执行...")

# ==================== 获取环境变量 ====================
cookie = os.getenv('189_COOKIE')
if not cookie:
    msg = "❌ 未设置 189_COOKIE 环境变量，请检查青龙面板变量配置（变量名必须为 189_COOKIE）"
    print(msg)
    if send:
        send("天翼云盘签到", msg)
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

# ==================== 请求会话 ====================
session = requests.Session()

# HAR 中提取的移动端签到专用请求头
headers = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 5.1.1; SM-G930K Build/NRD90M; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/74.0.3729.136 Mobile Safari/537.36 Ecloud/8.6.3 Android/22 clientId/355325117317828 clientModel/SM-G930K imsi/460071114317824 clientChannelId/qq proVersion/1.0.6",
    "Referer": "https://m.cloud.189.cn/zhuanti/2016/sign/index.jsp?albumBackupOpened=1",
    "Host": "api.cloud.189.cn",
    "Cookie": cookie,
    "Accept": "*/*",
    "Connection": "keep-alive",
}

session.headers.update(headers)

try:
    # Step 1: 签到
    timestamp = str(int(time.time() * 1000))
    sign_url = f"https://api.cloud.189.cn/mkt/userSign.action?rand={timestamp}&clientType=TELEANDROID&version=8.6.3&model=SM-G930K"
    
    resp_sign = session.get(sign_url, timeout=15)
    resp_sign.raise_for_status()
    data_sign = resp_sign.json()

    is_sign = data_sign.get("isSign", 0)
    netdisk_bonus = data_sign.get("netdiskBonus", 0)

    # ==================== 判断签到结果 ====================
    if is_sign == 1 or str(is_sign) == "1":
        sign_result = "今日已签到"
        notify_flag = False
    elif netdisk_bonus > 0:
        sign_result = f"✅ 签到成功，获得 {netdisk_bonus}M 空间"
        notify_flag = True
    else:
        sign_result = "❌ 签到失败或异常"
        notify_flag = True

    print(f"📢 签到结果: {sign_result}")

    # Step 2: 第一次抽奖（TASK_SIGNIN）
    draw_headers = headers.copy()
    draw_headers["Host"] = "m.cloud.189.cn"
    draw1_url = "https://m.cloud.189.cn/v2/drawPrizeMarketDetails.action?taskId=TASK_SIGNIN&activityId=ACT_SIGNIN"
    resp_draw1 = session.get(draw1_url, headers=draw_headers, timeout=15)
    prize1 = "未知"
    try:
        d1 = resp_draw1.json()
        prize1 = d1.get("prizeName", "无奖品") if d1.get("errorCode") != "UserNotLogin" else "登录状态异常"
    except:
        pass

    # Step 3: 第二次抽奖（TASK_SIGNIN_PHOTOS）
    draw2_url = "https://m.cloud.189.cn/v2/drawPrizeMarketDetails.action?taskId=TASK_SIGNIN_PHOTOS&activityId=ACT_SIGNIN"
    resp_draw2 = session.get(draw2_url, headers=draw_headers, timeout=15)
    prize2 = "未知"
    try:
        d2 = resp_draw2.json()
        prize2 = d2.get("prizeName", "无奖品")
    except:
        pass

    result_msg = f"{sign_result}\n第一次抽奖: {prize1}\n第二次抽奖: {prize2}"
    print(result_msg)

    # ==================== 发送通知（仅成功/失败时通知） ====================
    if notify_flag and send:
        if "签到成功" in sign_result:
            title = "✅ 天翼云盘签到成功"
        else:
            title = "❌ 天翼云盘签到失败"
        send(title, result_msg)
        print("📨 已通过青龙通知系统发送结果")
    elif not notify_flag:
        print("ℹ️ 今日已签到，无需通知")

except requests.exceptions.RequestException as e:
    error_msg = f"❌ 网络请求异常: {str(e)}"
    print(error_msg)
    if send:
        send("天翼云盘签到", error_msg)
except Exception as e:
    error_msg = f"❌ 执行异常: {str(e)}"
    print(error_msg)
    if send:
        send("天翼云盘签到", error_msg)

print("【天翼云盘签到】执行完毕")
