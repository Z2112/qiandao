# cron: 0 9 * * *
# new Env('国语视界签到[完整积分版]')

import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup
from notify import send

FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL")
SIGNIN_URL = "https://cnlang.org/dsu_paulsign-sign.html?mobile=no"


def parse_cookie_to_list(cookie_str):
    return [{"name": item.split('=', 1)[0].strip(), "value": item.split('=', 1)[1].strip()}
            for item in cookie_str.split(';') if '=' in item]


def get_flare_solution(url, cookie_str):
    if not FLARESOLVERR_URL:
        print("错误：未设置 FLARESOLVERR_URL")
        return None

    print("🔄 正在通过 FlareSolverr 解决 Cloudflare 保护...")
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": 60000,
        "session": "cnlang_qd",
        "cookies": parse_cookie_to_list(cookie_str)
    }
    try:
        resp = requests.post(FLARESOLVERR_URL, json=payload, timeout=75)
        data = resp.json()
        if data.get("status") == "ok":
            return data.get("solution")
        else:
            print(f"❌ FlareSolverr 返回失败: {data.get('message', '未知错误')}")
            return None
    except Exception as e:
        print(f"❌ FlareSolverr 调用失败: {e}")
        return None


def set_cookies(session, cookies, user_agent):
    for c in cookies:
        domain = c.get("domain", ".cnlang.org").lstrip(".")
        session.cookies.set(c["name"], c["value"], domain=domain)
    if user_agent:
        session.headers.update({"User-Agent": user_agent})


def get_sign_stats(session, html=None):
    try:
        if not html:
            html = session.get("https://cnlang.org/dsu_paulsign-sign.html", timeout=15).text

        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        stats = {}

        m = re.search(r'累计已签到[:：]?\s*(\d+)\s*天', text)
        if m: stats['累计签到'] = m.group(1)

        m = re.search(r'本月已累计签到[:：]?\s*(\d+)\s*天', text)
        if m: stats['本月签到'] = m.group(1)

        m = re.search(r'上次签到时间[:：]?\s*([\d\-: ]+)', text)
        if m: stats['上次签到'] = m.group(1).strip()

        m = re.search(r'上次获得的奖励为[:：]?\s*大洋\s*(\d+)', text)
        if m: stats['上次奖励'] = m.group(1)

        return stats
    except:
        return {}


def get_current_money(session):
    try:
        url = "https://cnlang.org/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu"
        resp = session.get(url, timeout=15)
        match = re.search(r'<span id="hcredit_2">(\d+)</span>', resp.text)
        return match.group(1) if match else None
    except:
        return None


def get_all_cookies():
    raw = os.getenv("CNLANG_COOKIE", "")
    return [c.strip() for line in raw.split('&') for c in line.split('\n') if len(c.strip()) > 20]


def main():
    print("【国语视界签到】多账号任务开始...")

    if os.getenv("RANDOM_SIGNIN", "").lower() == "true":
        delay = random.randint(1, int(os.getenv("MAX_RANDOM_DELAY", 3600)))
        print(f"【随机延迟】将在 {delay // 60} 分钟 {delay % 60} 秒后开始执行...")
        time.sleep(delay)

    cookie_list = get_all_cookies()
    all_results = []

    for idx, cookie_str in enumerate(cookie_list, 1):
        print(f"\n📌 处理第 {idx}/{len(cookie_list)} 个账号")

        try:
            solution = get_flare_solution(SIGNIN_URL, cookie_str)
            if not solution:
                all_results.append(f"账号{idx}: FlareSolverr 调用失败")
                continue

            session = requests.Session()
            set_cookies(session, solution.get("cookies", []), solution.get("userAgent", ""))

            html = session.get(SIGNIN_URL, timeout=20).text

            # ==================== 更严格的已签到判断 ====================
            already_signed_keywords = [
                "您今天已经签到过了或者签到时间还未开始",
                "今天已经签到过了",
                "您今天已经签到"
            ]
            is_already_signed = any(kw in html for kw in already_signed_keywords)

            if is_already_signed:
                stats = get_sign_stats(session, html)
                money = get_current_money(session)

                result = f"账号{idx}: 今日已签到 | 本月{stats.get('本月签到', '?')}天 | 累计{stats.get('累计签到', '?')}天"
                if stats.get('上次奖励'):
                    result += f" | 上次奖励为: {stats['上次奖励']}"
                if money:
                    result += f" | 当前大洋: {money}"

                print(result)
                all_results.append(result)
                continue

            # ==================== 执行签到 ====================
            soup = BeautifulSoup(html, "html.parser")
            formhash_tag = soup.find("input", {"name": "formhash"})
            if not formhash_tag:
                all_results.append(f"账号{idx}: 未找到 formhash")
                continue

            formhash = formhash_tag.get("value")

            payload = {
                "formhash": formhash,
                "qdxq": "kx",
                "qdmode": "1",
                "todaysay": "每天签到，水一发~",
                "fastreply": "0"
            }

            session.post(
                "https://cnlang.org/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1",
                data=payload, timeout=20
            )

            time.sleep(2)
            stats = get_sign_stats(session)
            money = get_current_money(session)

            result_text = f"账号{idx}: 签到成功 | 本月{stats.get('本月签到', '?')}天 | 累计{stats.get('累计签到', '?')}天"
            if stats.get('上次奖励'):
                result_text += f" | 奖励为: {stats['上次奖励']}"
            if money:
                result_text += f" | 当前大洋: {money}"

            print(result_text)
            all_results.append(result_text)

            send("国语视界签到", result_text)

        except Exception as e:
            error_msg = f"账号{idx} 执行异常: {str(e)}"
            print(error_msg)
            all_results.append(error_msg)

    if all_results:
        print("\n【国语视界签到】结果汇总：")
        print("\n".join(all_results))

        # 只要有结果就发送通知（包括失败和异常）
        if send:
            summary = "\n".join(all_results)
            send("国语视界签到", f"【国语视界签到结果】\n\n{summary}")
            print("🎉 通知已发送")

    print("【国语视界签到】任务执行完毕")


if __name__ == "__main__":
    main()