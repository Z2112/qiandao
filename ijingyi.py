# cron: 0 10 * * *
# new Env('精易论坛签到')

"""
【青龙面板使用说明】

1. 依赖安装（无需额外操作）：
   - 本脚本仅使用 requests + notify（青龙内置）

2. 环境变量设置：
   - IJINGYI_COOKIE      （必填，支持多账号）
   - RANDOM_SIGNIN       （可选）true = 开启随机延迟
   - MAX_RANDOM_DELAY    （可选）随机延迟最大秒数

3. 注意事项：
   - 已签到的账号不发送通知
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
        if send: send("精易论坛签到", msg)
        sys.exit(1)

    cookies_list = [c.strip() for line in raw.split('&') for c in line.split('\n') if c.strip() and len(c.strip()) > 20]

    if not cookies_list:
        msg = "❌ IJINGYI_COOKIE 内容为空或格式错误"
        print(msg)
        if send: send("精易论坛签到", msg)
        sys.exit(1)

    print(f"✅ 从 IJINGYI_COOKIE 读取到 {len(cookies_list)} 个账号")
    return cookies_list

# 随机延迟
random_signin = os.getenv('RANDOM_SIGNIN', 'false').lower() == 'true'
if random_signin:
    try:
        max_d = int(os.getenv('MAX_RANDOM_DELAY', 3600))
        delay_sec = random.randint(1, max_d)
        print(f"⏳ 随机延迟: 等待 {delay_sec//60} 分钟 {delay_sec % 60} 秒后开始执行")
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/95.0.4638.69 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cookie": cookie,
        "Connection": "keep-alive",
    }
    session.headers.update(base_headers)

    try:
        # 获取 formhash
        sign_url = "https://bbs.ijingyi.com/plugin.php?id=dsu_paulsign:sign"
        resp1 = session.get(sign_url, timeout=15)
        formhash = re.search(r'name="formhash" value="(.+?)"', resp1.text).group(1)

        # 执行签到
        qiandao_url = "https://bbs.ijingyi.com/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1"
        post_data = {"formhash": formhash, "submit": "1", "qdxq": "yl"}
        post_headers = {**base_headers, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"}

        resp2 = session.post(qiandao_url, data=post_data, headers=post_headers, timeout=15)
        content = resp2.text

        # 判断签到结果
        if '今天已经签到' in content or '已签到' in content:
            sign_result = "今日已签到"
            notify_flag = False
            reward_text = "今日已签到，无新奖励"
        elif '签到成功' in content or '获得' in content:
            sign_result = "✅ 签到成功"
            notify_flag = True
            reward_match = re.search(r'获得\s*([^<。！]+)', content)
            reward_text = reward_match.group(1).strip() if reward_match else "未检测到奖励"
        else:
            sign_result = "❌ 签到失败"
            notify_flag = True
            reward_text = "签到失败"

        print(f"📢 签到结果: {sign_result}")

        # 获取连续签到天数
        streak_days = "N/A"
        try:
            streak_resp = session.get("https://bbs.ijingyi.com/dsu_paulsign-sign.html", headers=base_headers, timeout=15)
            if streak_resp.status_code == 200:
                m = re.search(r'class="continuous"[^>]*>\s*连续签到\s*(\d+)\s*天', streak_resp.text)
                if m: streak_days = m.group(1)
        except:
            pass

        # 获取精币（清理单位）
        credit_resp = session.get("https://bbs.ijingyi.com/home.php?mod=spacecp&ac=credit&showcredit=1", headers=base_headers, timeout=15)
        jb_match = re.search(r'精币: .*?>(.*?)<', credit_resp.text)
        jb_val = jb_match.group(1).strip() if jb_match else 'N/A'
        jb_val = re.sub(r'[^\d]', '', jb_val)  # 只保留数字

        # 紧凑输出格式
        compact_line = f"当前账户 --- 【连续签到天数】：{streak_days} 天 --- 【签到奖励】：{reward_text} --- 【精币】：{jb_val}"
        print(compact_line)

        all_results.append(f"账号{idx}: {sign_result}\n{compact_line}")

        if not notify_flag:
            print("ℹ️ 今日已签到，无需通知")

    except Exception as e:
        print(f"❌ 账号{idx} 执行异常: {str(e)}")
        all_results.append(f"账号{idx}: 签到失败")

# 汇总通知
if all_results:
    summary = "\n\n".join(all_results)
    has_action = any("签到成功" in r or "签到失败" in r for r in all_results)

    if has_action and send:
        send("精易论坛签到结果", f"【精易论坛多账号签到完成】\n\n{summary}\n\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("🎉 通知已发送")
    else:
        print("✅ 所有账号已签到，无需发送通知")

print("【精易论坛签到】任务执行完毕")
