# cron: 0 10 * * *
# new Env('精易论坛签到')

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
        print("❌ 未设置 IJINGYI_COOKIE 环境变量")
        sys.exit(1)
    cookies_list = [c.strip() for line in raw.split('&') for c in line.split('\n') if c.strip()]
    return [c for c in cookies_list if len(c) > 20]

if os.getenv('RANDOM_SIGNIN', 'false').lower() == 'true':
    try:
        delay = random.randint(1, int(os.getenv('MAX_RANDOM_DELAY', 3600)))
        print(f"⏳ 随机延迟 {delay} 秒...")
        time.sleep(delay)
    except:
        pass
else:
    print("✅ 未开启随机延迟")

cookie_list = get_all_cookies()
all_results = []

def get_continuous_days(session):
    """ 从签到页面提取连续签到天数 """
    try:
        resp = session.get("https://bbs.ijingyi.com/dsu_paulsign-sign.html", timeout=15)
        match = re.search(r'连续签到\s*(\d+)\s*天', resp.text)
        return match.group(1) if match else "?"
    except:
        return "?"

def get_last_reward(credit_text):
    """ 从积分页面提取上次获得的签到奖励 """
    try:
        # 尝试从信用页或签到记录中提取
        match = re.search(r'上次获得.*?(\d+)\s*精币', credit_text)
        if match:
            return match.group(1)
        match = re.search(r'签到奖励.*?(\d+)', credit_text)
        if match:
            return match.group(1)
        return "?"
    except:
        return "?"

for idx, cookie in enumerate(cookie_list, 1):
    print(f"\n📌 开始处理第 {idx}/{len(cookie_list)} 个账号")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": cookie
    })

    try:
        # 获取 formhash
        sign_url = "https://bbs.ijingyi.com/plugin.php?id=dsu_paulsign:sign"
        resp1 = session.get(sign_url, timeout=15)
        formhash = re.search(r'name="formhash" value="(.+?)"', resp1.text).group(1)

        # 执行签到
        resp2 = session.post(
            "https://bbs.ijingyi.com/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1",
            data={"formhash": formhash, "submit": "1", "qdxq": "yl"},
            timeout=15
        )
        content = resp2.text

        # 签到结果判断
        if '今天已签到' in content or '已签到' in content or '您今日已签到' in content:
            sign_result = "今日已签到"
            notify_flag = False
        else:
            sign_result = "✅ 签到成功"
            notify_flag = True

        print(f"📢 签到结果: {sign_result}")

        # 从正确页面获取连续签到天数
        streak_days = get_continuous_days(session)

        # 获取精币和上次奖励
        credit_url = "https://bbs.ijingyi.com/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu"
        credit_text = session.get(credit_url, timeout=15).text

        jb_match = re.search(r'id="hcredit_4">([\d,]+)', credit_text)
        jb_val = jb_match.group(1).replace(',', '') if jb_match else "N/A"

        last_reward = get_last_reward(credit_text)

        # 紧凑日志样式（参考 enshan.js）
        log_line = f"账号{idx}: {sign_result} | 连续签到{streak_days}天 | 上次获得奖励: {last_reward}精币 | 精币: {jb_val}"
        print(log_line)

        all_results.append(log_line)

        if not notify_flag:
            print("ℹ️ 今日已签到，无需通知")

    except Exception as e:
        print(f"❌ 账号{idx} 执行异常: {e}")
        all_results.append(f"账号{idx}: 签到失败（执行异常）")

# 汇总通知（参考 enshan.js 风格）
if all_results:
    summary = "\n".join(all_results)
    has_action = any("签到成功" in r or "签到失败" in r for r in all_results)

    if has_action and send:
        send("精易论坛签到结果", f"【精易论坛多账号签到完成】\n\n{summary}\n\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("🎉 通知已发送")
    else:
        print("✅ 所有账号已签到，无需发送通知")

print("【精易论坛签到】任务执行完毕")