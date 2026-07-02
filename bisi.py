# cron: 0 10 * * *
# new Env('比思论坛签到')

import os
import re
import time
import random
import requests
from notify import send

print("【比思论坛签到】多账号任务开始...")

def get_all_cookies():
    raw = os.getenv("BISI_COOKIE", "")
    if not raw:
        print("❌ 未设置 BISI_COOKIE 环境变量")
        exit(1)
    cookies_list = [c.strip() for line in raw.split('&') for c in line.split('\n') if c.strip()]
    return [c for c in cookies_list if len(c) > 20]

def get_sign_stats(cookie):
    try:
        url = "http://hkcdn4.space/plugin.php?id=dsu_paulsign:sign"
        resp = requests.get(url, headers={"Cookie": cookie}, timeout=15)
        text = resp.text
        stats = {}

        m = re.search(r'累計已簽到[:：]?\s*<b>(\d+)</b>\s*天', text)
        if m: stats['累计签到'] = m.group(1)

        m = re.search(r'本月已累計簽到[:：]?\s*<b>(\d+)</b>\s*天', text)
        if m: stats['本月签到'] = m.group(1)

        m = re.search(r'上次簽到時間[:：]?<font[^>]*>(.*?)</font>', text)
        if m: stats['上次签到'] = m.group(1).strip()

        m = re.search(r'上次獲得的獎勵為[:：]?金錢\s*<font[^>]*><b>(\d+)</b>', text)
        if m: stats['上次奖励'] = m.group(1)

        return stats
    except:
        return {}

def get_current_money(cookie):
    try:
        url = "http://hkcdn4.space/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu"
        resp = requests.get(url, headers={"Cookie": cookie}, timeout=15)
        match = re.search(r'<span[^>]*id=["\']hcredit_2["\'][^>]*>(.*?)</span>', resp.text)
        return match.group(1).strip() if match else None
    except:
        return None

if os.getenv("RANDOM_SIGNIN", "false").lower() == "true":
    delay = random.randint(1, int(os.getenv("MAX_RANDOM_DELAY", 3600)))
    print(f"⏳ 随机延迟 {delay} 秒...")
    time.sleep(delay)

always_notify = os.getenv("ALWAYS_NOTIFY", "false").lower() == "true"
cookie_list = get_all_cookies()
all_results = []

for idx, cookie in enumerate(cookie_list, 1):
    print(f"\n📌 开始处理第 {idx}/{len(cookie_list)} 个账号")

    try:
        sign_page = requests.get(
            "http://hkcdn4.space/plugin.php?id=dsu_paulsign:sign",
            headers={"Cookie": cookie},
            timeout=15
        ).text

        if "您今天已經簽到過了或者簽到時間還未開始" in sign_page or "已經簽到過了" in sign_page:
            stats = get_sign_stats(cookie)
            money = get_current_money(cookie)

            result = f"✅ 今日已签到 | 账号{idx} | 本月{stats.get('本月签到', '?')}天 | 累计{stats.get('累计签到', '?')}天"
            if stats.get('上次奖励'):
                result += f" | 上次奖励为: {stats['上次奖励']}"
            if money:
                result += f" | 当前金钱: {money}"

            print(result)
            all_results.append(result)
            continue

        formhash_match = re.search(r'formhash=(.+?)">', sign_page)
        if not formhash_match:
            raise Exception("未找到 formhash")

        formhash = formhash_match.group(1)

        post_data = {"formhash": formhash, "qdxq": "fd"}
        requests.post(
            "http://hkcdn4.space/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1",
            headers={"Cookie": cookie},
            data=post_data,
            timeout=15
        )

        time.sleep(2)

        stats = get_sign_stats(cookie)
        money = get_current_money(cookie)

        result_text = f"✅ 签到成功 | 账号{idx} | 本月{stats.get('本月签到', '?')}天 | 累计{stats.get('累计签到', '?')}天"
        if stats.get('上次奖励'):
            result_text += f" | 奖励为: {stats['上次奖励']}"
        if money:
            result_text += f" | 当前金钱: {money}"

        print(result_text)
        all_results.append(result_text)

    except Exception as e:
        error_msg = f"❌ 签到失败 | 账号{idx} | 执行异常: {str(e)}"
        print(error_msg)
        all_results.append(error_msg)

if all_results:
    print("\n【比思论坛签到】结果汇总：")
    print("\n".join(all_results))

    # ALWAYS_NOTIFY=true：成功/失败都发；false：仅失败时发
    has_fail = any("❌" in r or "执行异常" in r or "失败" in r for r in all_results)
    if send and (always_notify or has_fail):
        send("比思论坛签到", "\n".join(all_results))
        print("🎉 通知已发送" + ("（ALWAYS_NOTIFY=true）" if always_notify and not has_fail else "（存在签到失败）" if has_fail else ""))
    else:
        print("✅ 全部签到成功/已签到，ALWAYS_NOTIFY=false，跳过通知")

print("【比思论坛签到】任务执行完毕")
