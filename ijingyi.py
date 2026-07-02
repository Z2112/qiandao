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

always_notify = os.getenv('ALWAYS_NOTIFY', 'false').lower() == 'true'
cookie_list = get_all_cookies()
all_results = []

def get_sign_info(session):
    """
    从签到页面一次性提取：
    - 连续签到天数
    - 上次获得奖励（精币）
    """
    try:
        resp = session.get("https://bbs.ijingyi.com/dsu_paulsign-sign.html", timeout=15)
        text = resp.text

        # 连续签到天数
        streak_match = re.search(r'连续签到\s*(\d+)\s*天', text)
        streak_days = streak_match.group(1) if streak_match else "?"

        # 上次获得奖励 - 显式匹配 <b>1</b>
        reward_match = re.search(r'上次获得奖励：.*?<b>(\d+)</b>.*?精币', text, re.DOTALL)
        last_reward = reward_match.group(1) if reward_match else "?"

        return streak_days, last_reward
    except:
        return "?", "?"

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
            timeout=15)
        content = resp2.text

        # 签到结果判断
        if '今天已签到' in content or '已签到' in content or '您今日已签到' in content:
            status_text = "今日已签到"
        else:
            status_text = "签到成功"

        print(f"📢 签到结果: ✅ {status_text}")

        # 从签到页面获取连续天数 + 上次奖励
        streak_days, last_reward = get_sign_info(session)

        # 获取当前精币
        credit_url = "https://bbs.ijingyi.com/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu"
        credit_text = session.get(credit_url, timeout=15).text
        jb_match = re.search(r'id="hcredit_4">([\d,]+)', credit_text)
        jb_val = jb_match.group(1).replace(',', '') if jb_match else "N/A"

        # 紧凑日志样式：✅/❌ 置前
        log_line = f"✅ {status_text} | 账号{idx} | 连续签到{streak_days}天 | 上次获得奖励: {last_reward}精币 | 精币: {jb_val}"
        print(log_line)

        all_results.append(log_line)

    except Exception as e:
        error_line = f"❌ 签到失败 | 账号{idx} | 执行异常: {e}"
        print(error_line)
        all_results.append(error_line)

# 汇总通知：ALWAYS_NOTIFY=true 成功/失败都发；false 仅失败时发
if all_results:
    summary = "\n".join(all_results)
    has_fail = any("❌" in r or "签到失败" in r or "执行异常" in r for r in all_results)

    if send and (always_notify or has_fail):
        send("精易论坛签到结果", f"【精易论坛多账号签到完成】\n\n{summary}\n\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("🎉 通知已发送" + ("（ALWAYS_NOTIFY=true）" if always_notify and not has_fail else "（存在签到失败）" if has_fail else ""))
    else:
        print("✅ 全部签到成功/已签到，ALWAYS_NOTIFY=false，跳过通知")

print("【精易论坛签到】任务执行完毕")