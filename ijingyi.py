# cron: 0 10 * * *
# new Env('精易论坛签到')

"""
【青龙面板使用说明】

1. 依赖安装（无需额外操作）：
   - 本脚本仅使用 requests + notify（青龙内置）

2. 环境变量设置：
   - IJINGYI_COOKIE      （必填，支持多账号）
   - RANDOM_SIGNIN       （可选）true = 开启随机延迟
   - MAX_RANDOM_DELAY    （可选）随机延迟最大秒数，默认 3600 秒

3. 注意事项：
   - 已签到的账号不会发送通知
   - 只有签到成功或失败时才会推送
"""

import os
import sys
import time
import random
import re
import requests

try:
    from notify import send
except ImportError:
    send = None

print("【精易论坛签到】多账号任务开始...")

def get_all_cookies():
    raw = os.getenv('IJINGYI_COOKIE')
    if not raw:
        msg = "❌ 未设置 IJINGYI_COOKIE 环境变量"
        print(msg)
        if send:
            send("精易论坛签到", msg)
        sys.exit(1)

    cookies_list = raw.split('&')
    cookies_list = [c.strip() for line in cookies_list for c in line.split('\n') if c.strip()]
    cookies_list = [c for c in cookies_list if len(c) > 20]

    if not cookies_list:
        msg = "❌ IJINGYI_COOKIE 内容为空或格式错误"
        print(msg)
        if send:
            send("精易论坛签到", msg)
        sys.exit(1)

    print(f"✅ 从 IJINGYI_COOKIE 读取到 {len(cookies_list)} 个账号")
    return cookies_list

# 随机延迟
random_signin = os.getenv('RANDOM_SIGNIN', 'false').lower() == 'true'
max_random_delay = os.getenv('MAX_RANDOM_DELAY')

if random_signin:
    try:
        max_d = int(max_random_delay) if max_random_delay else 3600
        if max_d > 0:
            delay_sec = random.randint(1, max_d)
            print(f"⏳ 随机延迟: 等待 {delay_sec//60} 分钟 {delay_sec%60} 秒后开始执行")
            time.sleep(delay_sec)
    except Exception as e:
        print(f"⚠️ 随机延迟异常: {e}")
else:
    print("✅ 未开启随机延迟")

cookie_list = get_all_cookies()
all_results = []

for idx, cookie in enumerate(cookie_list, 1):
    print(f"\n📌 开始处理第 {idx}/{len(cookie_list)} 个账号")
    session = requests.Session()

    base_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cookie": cookie,
        "Connection": "keep-alive",
    }
    session.headers.update(base_headers)

    try:
        # Step 1: 获取 formhash
        sign_url = "https://bbs.ijingyi.com/plugin.php?id=dsu_paulsign:sign"
        resp1 = session.get(sign_url, timeout=15)
        resp1.raise_for_status()

        formhash_match = re.search(r'name="formhash" value="(.+?)"', resp1.text)
        if not formhash_match:
            raise Exception("未找到 formhash")
        formhash = formhash_match.group(1)

        # Step 2: 执行签到
        qiandao_url = "https://bbs.ijingyi.com/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1"
        post_data = {
            "formhash": formhash,
            "submit": "1",
            "targerurl": "",
            "todaysay": "",
            "qdxq": "yl"
        }
        post_headers = base_headers.copy()
        post_headers.update({
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://bbs.ijingyi.com",
            "Referer": sign_url,
        })

        resp2 = session.post(qiandao_url, data=post_data, headers=post_headers, timeout=15)
        content = resp2.text

        # 判断签到结果
        if '今天已经签到' in content or '已签到' in content or '您今日已经签到' in content:
            sign_result = "今日已签到"
            notify_flag = False
        elif '签到成功' in content or '恭喜您' in content or '获得' in content:
            sign_result = "✅ 签到成功"
            notify_flag = True
        else:
            sign_result = "❌ 签到失败或异常"
            notify_flag = True

        print(f"📢 签到结果: {sign_result}")

        # ==================== 提取本次签到奖励 ====================
        reward_text = "未检测到"
        reward_match = re.search(r'获得\s*([^<。！]+)', content)
        if reward_match:
            reward_text = reward_match.group(1).strip()

        # ==================== 新增：访问 dsu_paulsign-sign.html 获取连续签到天数 ====================
        streak_days = "N/A"
        try:
            streak_resp = session.get("https://bbs.ijingyi.com/dsu_paulsign-sign.html", headers=base_headers, timeout=15)
            if streak_resp.status_code == 200:
                streak_match = re.search(r'class="continuous"[^>]*>\s*连续签到\s*(\d+)\s*天', streak_resp.text)
                if streak_match:
                    streak_days = streak_match.group(1)
        except Exception as e:
            print(f"⚠️ 获取连续签到天数失败: {e}")

        # 获取精币（保留其他资产）
        credit_url = "https://bbs.ijingyi.com/home.php?mod=spacecp&ac=credit&showcredit=1"
        credit_resp = session.get(credit_url, headers=base_headers, timeout=15)

        jb = re.search(r'精币: .*?>(.*?)<', credit_resp.text)
        jb_val = jb.group(1).strip() if jb else 'N/A'

        # ==================== 新的紧凑输出格式 ====================
        compact_line = (
            f"当前账户 --- 【连续签到天数】：{streak_days} 天 "
            f"--- 【签到奖励】：{reward_text} "
            f"--- 【精币】：{jb_val} 枚"
        )
        print(compact_line)

        all_results.append(f"账号{idx}: {sign_result}\n{compact_line}")

        if not notify_flag:
            print("ℹ️ 今日已签到，无需通知")

    except Exception as e:
        print(f"❌ 账号{idx} 执行异常: {str(e)}")
        all_results.append(f"账号{idx}: 签到失败（执行异常）")

# ==================== 汇总通知 ====================
if all_results:
    summary = "\n\n".join(all_results)
    has_action = any("签到成功" in r or "签到失败" in r for r in all_results)

    if has_action and send:
        send("精易论坛签到结果", 
             f"【精易论坛多账号签到完成】\n\n{summary}\n\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("🎉 通知已发送")
    else:
        print("✅ 所有账号已签到，无需发送通知")

print("【精易论坛签到】任务执行完毕")
