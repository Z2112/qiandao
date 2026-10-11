# cron: 0 9 * * *
# new Env('国语视界签到[完整积分版]')

import os
import re
import time
import random
import urllib.parse
import requests
from bs4 import BeautifulSoup

try:
    from notify import send
except ImportError:
    send = None
    print("⚠️ 未找到 notify 模块，将跳过通知")

FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL")
SIGNIN_URL = "https://cnlang.org/dsu_paulsign-sign.html?mobile=no"
STATS_URL = "https://cnlang.org/dsu_paulsign-sign.html"
POST_URL = "https://cnlang.org/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1"
MONEY_URL = "https://cnlang.org/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu"
ALREADY_SIGNED_KEYWORDS = [
    "您今天已经签到过了或者签到时间还未开始",
    "今天已经签到过了",
    "您今天已经签到",
]
SUCCESS_KEYWORDS = ["签到成功", "恭喜你签到成功"]


def parse_cookie_to_list(cookie_str):
    return [{"name": item.split('=', 1)[0].strip(), "value": item.split('=', 1)[1].strip()}
            for item in cookie_str.split(';') if '=' in item]


def flare_request(url, cookie_str, session_id, post_data=None):
    """通过 FlareSolverr 发送 GET/POST，返回 solution（含 response HTML）或 None"""
    if not FLARESOLVERR_URL:
        print("错误：未设置 FLARESOLVERR_URL")
        return None
    payload = {
        "cmd": "request.post" if post_data is not None else "request.get",
        "url": url,
        "maxTimeout": 60000,
        "session": session_id,
        "cookies": parse_cookie_to_list(cookie_str),
    }
    if post_data is not None:
        payload["postData"] = urllib.parse.urlencode(post_data)
    try:
        resp = requests.post(FLARESOLVERR_URL, json=payload, timeout=75)
        data = resp.json()
        if data.get("status") == "ok":
            return data.get("solution") or {}
        print(f"❌ FlareSolverr 返回失败: {data.get('message', '未知错误')}")
    except (requests.RequestException, ValueError) as e:
        print(f"❌ FlareSolverr 调用失败: {e}")
    return None


def get_flare_solution(url, cookie_str, session_id="cnlang_qd"):
    print("🔄 正在通过 FlareSolverr 解决 Cloudflare 保护...")
    return flare_request(url, cookie_str, session_id)


def html_of(solution):
    return (solution or {}).get("response") or ""


def page_snippet(html, limit=200):
    """页面标题/文本片段，去除 cookie 类内容，用于排错"""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    text = soup.get_text(" ", strip=True)
    text = re.sub(r'([A-Za-z0-9_]+=)[^;&\s"\']{6,}', r'\1***', text)
    return f"标题: {title or '无'} | 内容: {text[:limit] or '空'}"


def get_sign_stats(html):
    try:
        text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    except Exception as e:
        print(f"⚠️ 解析签到统计失败: {e}")
        return {}
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


def get_current_money(cookie_str, session_id):
    sol = flare_request(MONEY_URL, cookie_str, session_id)
    m = re.search(r'<span id="hcredit_2">(\d+)</span>', html_of(sol))
    return m.group(1) if m else None


def get_all_cookies():
    raw = os.getenv("CNLANG_COOKIE", "")
    return [c.strip() for line in raw.split('&') for c in line.split('\n') if len(c.strip()) > 20]


def is_already_signed(html):
    return any(kw in html for kw in ALREADY_SIGNED_KEYWORDS)


def sign_one(idx, cookie_str):
    session_id = f"cnlang_qd_{idx}"
    solution = get_flare_solution(SIGNIN_URL, cookie_str, session_id)
    if solution is None:
        return f"❌ 签到失败 | 账号{idx} | FlareSolverr 调用失败"
    html = html_of(solution)

    if is_already_signed(html):
        stats = get_sign_stats(html)
        money = get_current_money(cookie_str, session_id)
        result = f"✅ 今日已签到 | 账号{idx} | 本月{stats.get('本月签到', '?')}天 | 累计{stats.get('累计签到', '?')}天"
        if stats.get('上次奖励'):
            result += f" | 上次奖励: {stats['上次奖励']}"
        if money:
            result += f" | 当前大洋: {money}"
        return result

    formhash_tag = BeautifulSoup(html, "html.parser").find("input", {"name": "formhash"})
    if not formhash_tag or not formhash_tag.get("value"):
        print(f"页面片段: {page_snippet(html)}")
        return f"❌ 签到失败 | 账号{idx} | 未找到 formhash"

    before = get_sign_stats(html)
    payload = {
        "formhash": formhash_tag.get("value"),
        "qdxq": "kx",
        "qdmode": "1",
        "todaysay": "每天签到，水一发~",
        "fastreply": "0",
    }
    post_sol = flare_request(POST_URL, cookie_str, session_id, post_data=payload)
    if post_sol is None:
        return f"❌ 签到失败 | 账号{idx} | 签到请求失败"
    post_html = html_of(post_sol)

    time.sleep(2)
    after = get_sign_stats(html_of(flare_request(STATS_URL, cookie_str, session_id)))
    money = get_current_money(cookie_str, session_id)

    ok_resp = any(kw in post_html for kw in SUCCESS_KEYWORDS) or is_already_signed(post_html)
    ok_days = (before.get('累计签到', '').isdigit() and after.get('累计签到', '').isdigit()
               and int(after['累计签到']) > int(before['累计签到']))
    if not (ok_resp or ok_days):
        print(f"签到响应片段: {page_snippet(post_html)}")
        return f"❌ 签到失败 | 账号{idx} | 签到未确认成功（响应无成功标志，累计天数未增加）"

    result = f"✅ 签到成功 | 账号{idx} | 本月{after.get('本月签到', '?')}天 | 累计{after.get('累计签到', '?')}天"
    if after.get('上次奖励'):
        result += f" | 本次奖励: {after['上次奖励']}"
    if money:
        result += f" | 当前大洋: {money}"
    return result


def main():
    print("【国语视界签到】多账号任务开始...")

    if os.getenv("RANDOM_SIGNIN", "").lower() == "true":
        delay = random.randint(1, int(os.getenv("MAX_RANDOM_DELAY", 3600)))
        print(f"【随机延迟】将在 {delay // 60} 分钟 {delay % 60} 秒后开始执行...")
        time.sleep(delay)

    always_notify = os.getenv("ALWAYS_NOTIFY", "false").lower() == "true"
    cookie_list = get_all_cookies()
    if not cookie_list:
        print("⚠️ 未设置 CNLANG_COOKIE（或格式无效），无账号可签到")
    all_results = []

    for idx, cookie_str in enumerate(cookie_list, 1):
        print(f"\n📌 处理第 {idx}/{len(cookie_list)} 个账号")
        try:
            result = sign_one(idx, cookie_str)
        except Exception as e:
            result = f"❌ 签到失败 | 账号{idx} | 执行异常: {e}"
        print(result)
        all_results.append(result)

    # ==================== 最终通知 ====================
    # ALWAYS_NOTIFY=true：成功/失败都发；false：仅失败时发
    if all_results:
        print("\n【国语视界签到】结果汇总：")
        print("\n".join(all_results))

        has_fail = any("❌" in r for r in all_results)
        if send and (always_notify or has_fail):
            summary = "\n".join(all_results)
            send("国语视界签到", f"【国语视界签到结果】\n\n{summary}")
            print("🎉 通知已发送" + ("（存在签到失败）" if has_fail else "（ALWAYS_NOTIFY=true）"))
        elif not send:
            print("⚠️ notify 不可用，跳过通知")
        else:
            print("✅ 全部签到成功/已签到，ALWAYS_NOTIFY=false，跳过通知")

    print("【国语视界签到】任务执行完毕")


if __name__ == "__main__":
    main()
