# cron: 0 10 * * *
# new Env('HIFIKI/HIFINI签到')

import os
import re
import sys
import time
import random
import requests
from notify import send


def get_cookies(env_var):
    """从指定环境变量获取cookie列表"""
    raw = os.getenv(env_var, "")
    if not raw:
        return []
    cookies_list = [c.strip() for line in raw.split('&') for c in line.split('\n') if c.strip()]
    return [c for c in cookies_list if len(c) > 20]


def get_continuous_days(cookie, base_url):
    """从 sg_sign.htm 提取连续签到天数"""
    try:
        resp = requests.get(f"{base_url}/sg_sign.htm", headers={"Cookie": cookie}, timeout=15)
        text = resp.text
        match = re.search(r"var s3\s*=\s*['\"]([^'\"]+)['\"]", text)
        if match:
            return match.group(1)
        match = re.search(r'连续签到\s*(\d+)\s*天', text)
        if match:
            return match.group(1)   # 只返回数字，方便格式化
        return None
    except:
        return None


def get_total_coins(cookie, base_url):
    """从 my-credits.htm 获取总金币"""
    try:
        resp = requests.get(f"{base_url}/my-credits.htm", headers={"Cookie": cookie}, timeout=15)
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


def do_signin(site_name, domain, cookie_list):
    """
    执行指定站点的签到任务
    返回: (打印用的结果列表, 需要推送的通知消息列表)
    """
    if not cookie_list:
        return [], []

    base_url = f"https://www.{domain}"
    results = []
    notify_messages = []

    sign_url = f"{base_url}/sg_sign.htm"
    headers_template = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-requested-with": "XMLHttpRequest",
    }

    for idx, cookie in enumerate(cookie_list, 1):
        print(f"\n📌 开始处理第 {idx}/{len(cookie_list)} 个账号 [{site_name}]")
        headers = headers_template.copy()
        headers["cookie"] = cookie

        try:
            resp = requests.post(sign_url, headers=headers, timeout=15)

            result = resp.json()
            code = str(result.get("code", ""))
            message = result.get("message", "")

            # === 今日奖励（支持“总奖励X金币”和“获得X金币”）===
            reward_match = re.search(r'(?:获得|总奖励)\s*(\d+)\s*金币', message)
            reward = reward_match.group(1) if reward_match else None
            reward_str = f"奖励为: {reward}" if reward else ""

            # === 本月连续签到天数 ===
            continuous_days = get_continuous_days(cookie, base_url)
            monthly_str = f"本月{continuous_days}天" if continuous_days else "本月未知"

            # === 累计签到天数（尝试从页面提取，如无则留空）===
            # 这里先用 continuous_days 作为占位，后续可根据实际页面再增强
            total_str = ""

            # === 当前总金币 ===
            total_coins = get_total_coins(cookie, base_url)
            coins_str = f"当前金钱: {total_coins}" if total_coins else ""

            # === 状态判断 ===
            if code == "0" or "成功" in message:
                status_emoji = "✅"
                sign_result = "签到成功"
                notify_flag = True
            elif "今天已经签过" in message:
                status_emoji = "✅"
                sign_result = "今日已签到"
                notify_flag = False
            else:
                status_emoji = "⚠️"
                sign_result = "签到结果未知"
                notify_flag = True

            # === 新格式输出 ===
            parts = [p for p in [monthly_str, total_str, reward_str, coins_str] if p]
            result_text = " | ".join(parts)
            full_line = f"{status_emoji} {site_name} 账号{idx}: {sign_result} | {result_text}"

            print(full_line)

            results.append(full_line)

            if notify_flag:
                notify_messages.append(full_line)

        except Exception as e:
            error_text = f"❌ {site_name} 账号{idx}: 请求异常 | {str(e)}"
            print(error_text)
            results.append(error_text)
            notify_messages.append(error_text)

    return results, notify_messages


def main():
    print("=== HIFIKI / HIFINI 签到任务开始 ===")

    # 随机延迟（如果启用）
    if os.getenv("RANDOM_SIGNIN", "false").lower() == "true":
        try:
            delay = random.randint(1, int(os.getenv("MAX_RANDOM_DELAY", 3600)))
            print(f"⏳ 随机延迟 {delay} 秒...")
            time.sleep(delay)
        except:
            pass

    sites = [
        {"name": "HIFIKI", "domain": "hifiki.com", "env": "HIFIKI_COOKIE"},
        {"name": "HIFINI", "domain": "hifiti.com", "env": "HIFINI_COOKIE"},
    ]

    all_results = []
    all_notify_messages = []

    for site in sites:
        cookie_list = get_cookies(site["env"])
        if not cookie_list:
            print(f"ℹ️ 未检测到 {site['env']} 环境变量，跳过 {site['name']}")
            continue

        print(f"\n=== 开始处理站点: {site['name']} ({site['domain']}) ===")
        site_results, site_notify = do_signin(site["name"], site["domain"], cookie_list)
        all_results.extend(site_results)
        all_notify_messages.extend(site_notify)

    if all_results:
        print("\n=== HIFIKI / HIFINI 签到任务全部执行完毕 ===")
        print("\n".join(all_results))

    # 最后统一推送
    if all_notify_messages and send:
        title = "HIFIKI/HIFINI 签到汇总"
        content = "\n".join(all_notify_messages)
        send(title, content)
        print(f"\n📢 已发送统一推送通知（共 {len(all_notify_messages)} 条）")


if __name__ == "__main__":
    main()
