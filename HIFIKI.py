# cron: 0 10 * * *
# new Env('HIFIKI签到')

import os
import re
import sys
import time
import random
import requests
from notify import send

def get_all_cookies():
    raw = os.getenv("HIFIKI_COOKIE", "")
    if not raw:
        print("❌ 未检测到 HIFIKI_COOKIE 环境变量")
        sys.exit(1)
    cookies_list = [c.strip() for line in raw.split('&') for c in line.split('\n') if c.strip()]
    return [c for c in cookies_list if len(c) > 20]

def get_continuous_days(cookie):
    """从 sg_sign.htm 提取连续签到天数"""
    try:
        resp = requests.get("https://www.hifiki.com/sg_sign.htm", headers={"Cookie": cookie}, timeout=15)
        text = resp.text
        match = re.search(r"var s3\s*=\s*['\"]([^'\"]+)['\"]", text)
        if match:
            return match.group(1)
        match = re.search(r'连续签到\s*(\d+)\s*天', text)
        return match.group(0) if match else None
    except:
        return None

def get_total_coins(cookie):
    """从 my-credits.htm 获取总金币"""
    try:
        resp = requests.get("https://www.hifiki.com/my-credits.htm", headers={"Cookie": cookie}, timeout=15)
        text = resp.text
        match = re.search(
            r'<i class="icon-diamond".*?</span>.*?<input[^>]*value="(\d+)"',
            text,
            re.DOTALL
        )
        if match:
            return match.group(1)
        match = re.search(r'金币.*?<input[^>]*value="(\d+)"', text, re.DOTALL)
        return match.group(1) if match else None
    except:
        return None

def main():
    print("=== HIFIKI 签到任务开始 ===")

    cookie_list = get_all_cookies()
    all_results = []

    if os.getenv("RANDOM_SIGNIN", "false").lower() == "true":
        try:
            delay = random.randint(1, int(os.getenv("MAX_RANDOM_DELAY", 3600)))
            print(f"⏳ 随机延迟 {delay} 秒...")
            time.sleep(delay)
        except:
            pass

    url = "https://www.hifiki.com/sg_sign.htm"
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-requested-with": "XMLHttpRequest",
    }

    for idx, cookie in enumerate(cookie_list, 1):
        print(f"\n📌 开始处理第 {idx}/{len(cookie_list)} 个账号")
        headers["cookie"] = cookie

        try:
            resp = requests.post(url, headers=headers, timeout=15)
            result = resp.json()
            code = str(result.get("code", ""))
            message = result.get("message", "")

            # 连续签到天数
            continuous_days = get_continuous_days(cookie)
            continuous_str = f" | {continuous_days}" if continuous_days else ""

            # 今日奖励（从 message 提取）
            reward_match = re.search(r'获得\s*(\d+)\s*金币', message)
            reward_str = f" | 今日奖励: {reward_match.group(1)}金币" if reward_match else ""

            # 总金币
            total_coins = get_total_coins(cookie)
            coins_str = f" | 金币: {total_coins}" if total_coins else ""

            if code == "0" or "成功" in message:
                sign_result = "✅ 签到成功"
                notify_flag = True
            elif "今天已经签过" in message:
                sign_result = "今日已签到"
                notify_flag = False
            else:
                sign_result = "⚠️ 签到结果未知"
                notify_flag = True

            result_text = f"{sign_result}{continuous_str}{reward_str}{coins_str}"
            print(result_text)

            all_results.append(f"账号{idx}: {result_text}")

            if notify_flag and send:
                send("HIFIKI签到", f"账号{idx} {result_text}")

        except Exception as e:
            error_text = f"账号{idx}: 请求异常 | {str(e)}"
            print(error_text)
            all_results.append(error_text)

    if all_results:
        print("\n=== HIFIKI 签到任务全部执行完毕 ===")
        print("\n".join(all_results))

if __name__ == "__main__":
    main()