# cron: 0 10 * * *
# new Env('精易论坛签到')

import os
import sys
import time
import random
import re
import requests

# ==================== 通知模块 ====================
try:
    from notify import send
except ImportError:
    send = None

print("【精易论坛签到】开始执行...")

# ==================== 获取环境变量 ====================
cookie = os.getenv('IJINGYI_COOKIE')
if not cookie:
    msg = "❌ 未设置 IJINGYI_COOKIE 环境变量，请检查青龙面板变量配置"
    print(msg)
    if send:
        send("精易论坛签到", msg)
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
            # 按用户要求：把“等待 1531 秒后开始执行”修改为剩余多少分钟多少秒
            print(f"⏳ 随机延迟: 等待 {minutes} 分钟 {seconds} 秒后开始执行")
            time.sleep(delay_sec)
    except Exception as e:
        print(f"⚠️ 随机延迟处理异常（将继续执行）: {e}")
else:
    print("✅ 未开启随机延迟（RANDOM_SIGNIN 未设置为 true）")

# ==================== 请求会话 ====================
session = requests.Session()

# 基础请求头（从HAR中提取）
base_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cookie": cookie,
    "Connection": "keep-alive",
}

session.headers.update(base_headers)

try:
    # Step 1: GET 签到页面获取 formhash
    sign_url = "https://bbs.ijingyi.com/plugin.php?id=dsu_paulsign:sign"
    resp1 = session.get(sign_url, timeout=15)
    resp1.raise_for_status()

    formhash_match = re.search(r'name="formhash" value="(.+?)"', resp1.text)
    if not formhash_match:
        raise Exception("未找到 formhash，请检查 Cookie 是否有效或账号已掉线")
    formhash = formhash_match.group(1)
    print(f"✅ 已获取 formhash: {formhash}")

    # Step 2: POST 签到
    qiandao_url = "https://bbs.ijingyi.com/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1"
    post_data = {
        "formhash": formhash,
        "submit": "1",
        "targerurl": "",
        "todaysay": "",
        "qdxq": "yl"
    }
    # POST 专用请求头（从HAR中提取）
    post_headers = base_headers.copy()
    post_headers.update({
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://bbs.ijingyi.com",
        "Referer": sign_url,
        "sec-ch-ua": "\"Chromium\";v=\"21\", \" Not;A Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
    })

    resp2 = session.post(qiandao_url, data=post_data, headers=post_headers, timeout=15)
    resp2.raise_for_status()

    content = resp2.text

    # ==================== 判断签到结果（仅成功/失败才通知） ====================
    if '今天已经签到' in content or '已签到' in content or '您今日已经签到' in content or '签到过了' in content:
        sign_result = "今日已签到"
        notify_flag = False
    elif '签到成功' in content or '恭喜您' in content or 'success' in content.lower() or '"status":1' in content or '获得' in content:
        sign_result = "✅ 签到成功"
        notify_flag = True
    else:
        sign_result = "❌ 签到失败或异常"
        notify_flag = True

    print(f"📢 签到结果: {sign_result}")
    # 可选调试输出（正式运行可注释）
    # print(f"签到响应预览: {content[:600]}...")

    # Step 3: 获取积分信息
    credit_url = "https://bbs.ijingyi.com/home.php?mod=spacecp&ac=credit&showcredit=1"
    credit_headers = base_headers.copy()
    credit_headers.update({
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Dest": "document",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    })

    credit_resp = session.get(credit_url, headers=credit_headers, timeout=15)
    credit_resp.raise_for_status()

    # 使用HAR中提供的正则提取积分（略作优化）
    hp = re.search(r'好评: .*?>(.*?)<', credit_resp.text)
    jb = re.search(r'精币: .*?>(.*?)<', credit_resp.text)
    ry = re.search(r'荣誉: .*?>(.*?)<', credit_resp.text)
    jf = re.search(r'积分: .*?>(.*?)<.*?总积分', credit_resp.text)

    hp_val = hp.group(1).strip() if hp else 'N/A'
    jb_val = jb.group(1).strip() if jb else 'N/A'
    ry_val = ry.group(1).strip() if ry else 'N/A'
    jf_val = jf.group(1).strip() if jf else 'N/A'

    points_msg = (
        f"当前账户 --- 【好评】：{hp_val} "
        f"--- 【精币】：{jb_val} "
        f"--- 【荣誉】：{ry_val} "
        f"--- 【积分】：{jf_val}"
    )
    print(points_msg)

    # ==================== 发送通知 ====================
    if notify_flag and send:
        if "签到成功" in sign_result:
            title = "✅ 精易论坛签到成功"
            body = f"{sign_result}\n\n{points_msg}"
        else:
            title = "❌ 精易论坛签到失败"
            body = f"{sign_result}\n\n{points_msg}\n\n响应预览：{content[:300]}"
        send(title, body)
        print("📨 已通过青龙通知系统发送结果")
    elif not notify_flag:
        print("ℹ️ 今日已签到，无需通知")

except requests.exceptions.RequestException as e:
    error_msg = f"❌ 网络请求异常: {str(e)}"
    print(error_msg)
    if send:
        send("精易论坛签到", error_msg)
except Exception as e:
    error_msg = f"❌ 执行异常: {str(e)}"
    print(error_msg)
    if send:
        send("精易论坛签到", error_msg)

print("【精易论坛签到】执行完毕")
