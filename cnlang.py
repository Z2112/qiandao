# -*- coding: utf-8 -*-
"""
cron: 0 9 * * *
new Env('国语视界签到[完整积分版]');
"""

import os
import re
import requests
from bs4 import BeautifulSoup
from sendNotify import send

FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL")
SIGNIN_URL = "https://cnlang.org/dsu_paulsign-sign.html?mobile=no"   # ← 已补充


def parse_cookie_to_list(cookie_str):
    cookie_list = []
    for item in cookie_str.split(';'):
        item = item.strip()
        if '=' in item:
            name, value = item.split('=', 1)
            cookie_list.append({"name": name.strip(), "value": value.strip()})
    return cookie_list


def get_flare_solution(url, cookie_str):
    if not FLARESOLVERR_URL:
        print("错误：未设置环境变量 FLARESOLVERR_URL")
        return None

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
            print("FlareSolverr 失败:", data.get("message"))
            return None
    except Exception as e:
        print("调用 FlareSolverr 出错:", e)
        return None


def set_cookies(session, cookies, user_agent):
    for c in cookies:
        domain = c.get("domain", ".cnlang.org")
        if domain.startswith("."):
            domain = domain[1:]
        session.cookies.set(c["name"], c["value"], domain=domain)
    if user_agent:
        session.headers.update({"User-Agent": user_agent})


def get_current_money(session):
    try:
        url = "https://cnlang.org/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu"
        resp = session.get(url, timeout=15)
        match = re.search(r'<span id="hcredit_2">(\d+)</span>', resp.text)
        if match:
            return match.group(1)
    except Exception as e:
        print("获取积分失败:", e)
    return None


def sign():
    cookie_str = os.getenv("CNLANG_COOKIE", "")
    username = os.getenv("CNLANG_UNAME", "")

    if not cookie_str or not username:
        msg = "缺少 CNLANG_COOKIE 或 CNLANG_UNAME 环境变量"
        print(msg)
        send("国语视界签到", msg)
        return

    if not FLARESOLVERR_URL:
        msg = "未设置环境变量 FLARESOLVERR_URL，请在青龙中添加"
        print(msg)
        send("国语视界签到", msg)
        return

    print("正在通过 FlareSolverr（带登录Cookie）解决 Cloudflare...")

    solution = get_flare_solution(SIGNIN_URL, cookie_str)
    if not solution:
        msg = "FlareSolverr 调用失败"
        print(msg)
        send("国语视界签到", msg)
        return

    cookies = solution.get("cookies", [])
    user_agent = solution.get("userAgent", "")
    html = solution.get("response", "")

    session = requests.Session()
    session.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://cnlang.org/",
    })
    set_cookies(session, cookies, user_agent)

    if "formhash" not in html:
        print("尝试二次请求...")
        try:
            r = session.get(SIGNIN_URL, timeout=20)
            html = r.text
        except Exception as e:
            print("二次请求失败:", e)

    if "Cloudflare" in html and "challenge" in html.lower():
        msg = "仍被 Cloudflare 拦截"
        print(msg)
        send("国语视界签到", msg)
        return

    soup = BeautifulSoup(html, "html.parser")
    formhash_tag = soup.find("input", {"name": "formhash"})
    if not formhash_tag:
        if "今天已经签到过了" in html:
            money = get_current_money(session)
            result = "您今日已经签到，请明天再来！"
            if money:
                result += f" 当前大洋: {money}"
            print(result)
            send("国语视界签到", result)
            return
        print("未找到 formhash")
        send("国语视界签到", "未找到 formhash")
        return

    formhash = formhash_tag.get("value")
    print(f"formhash 获取成功: {formhash}")

    user_match = re.search(r'title="访问我的空间">(.*?)</a>', html)
    if user_match and user_match.group(1) != username:
        msg = "用户名不匹配，Cookie 可能已失效"
        print(msg)
        send("国语视界签到", msg)
        return

    try:
        xq = requests.get("https://v1.hitokoto.cn/?encode=text", timeout=6).text.strip()
        if len(xq) < 6 or len(xq) > 50:
            xq = "每天签到，水一发~"
    except:
        xq = "每天签到，水一发~"
    print(f"想说的话: {xq}")

    old_money = get_current_money(session)

    qiandao_url = "https://cnlang.org/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1"
    payload = {
        "formhash": formhash,
        "qdxq": "kx",
        "qdmode": "1",
        "todaysay": xq,
        "fastreply": "0"
    }

    try:
        qd_resp = session.post(qiandao_url, data=payload, timeout=20)
        qd_text = qd_resp.text

        result_text = ""
        soup2 = BeautifulSoup(qd_text, "html.parser")
        div_c = soup2.find("div", class_="c")
        if div_c:
            result_text = div_c.get_text(strip=True)

        if not result_text or len(result_text) > 80:
            if "签到成功" in qd_text:
                result_text = "签到成功！"
            elif "已经签到" in qd_text or "今天已签到" in qd_text:
                result_text = "您今日已经签到，请明天再来！"
            else:
                result_text = "签到已提交"

        new_money = get_current_money(session)

        if old_money and new_money:
            try:
                gained = int(new_money) - int(old_money)
                if gained > 0:
                    result_text += f" 本次获得 {gained} 大洋"
                result_text += f"，当前大洋: {new_money}"
            except:
                result_text += f"，当前大洋: {new_money}"
        elif new_money:
            result_text += f"，当前大洋: {new_money}"

        print("签到结果:", result_text)
        send("国语视界签到", result_text)

    except Exception as e:
        print("签到失败:", e)
        send("国语视界签到", f"签到失败: {str(e)}")


if __name__ == "__main__":
    sign()
