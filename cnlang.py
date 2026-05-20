# cron: 0 9 * * *
# new Env('国语视界签到[完整积分版]')

"""
【青龙面板使用说明】

1. 依赖安装（必须）：
   - 青龙面板 → 依赖管理 → Node.js 依赖 → 新增：
     - requests
     - beautifulsoup4
   - 安装完成后重启青龙

2. 环境变量设置：
   - CNLANG_COOKIE       （必填，支持多账号）多个 Cookie 用 & 分割 或 换行分割
   - FLARESOLVERR_URL    （必填）FlareSolverr 服务地址
   - RANDOM_SIGNIN       （可选）true = 开启随机延迟
   - MAX_RANDOM_DELAY    （可选）随机延迟最大秒数，默认 3600 秒

3. 多账号配置示例（CNLANG_COOKIE 中填写）：
   Cookie字符串1&Cookie字符串2&Cookie字符串3
   或者每行一个 Cookie（推荐）：
   Cookie字符串1
   Cookie字符串2
   Cookie字符串3

4. 注意事项：
   - 已签到的账号完全不发送通知
   - 只有签到成功 或 签到失败 时才会推送通知
   - 多账号时只会发送一条汇总通知
"""

import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup
from notify import send   # 青龙系统通知

FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL")
SIGNIN_URL = "https://cnlang.org/dsu_paulsign-sign.html?mobile=no"


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
    
    print("🔄 正在通过 FlareSolverr 解决 Cloudflare 保护...")   # 新增提示
    
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
            print("✅ FlareSolverr 成功绕过 Cloudflare")
            return data.get("solution")
        else:
            print("❌ FlareSolverr 失败:", data.get("message"))
            return None
    except Exception as e:
        print("❌ 调用 FlareSolverr 出错:", e)
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


def get_all_cookies():
    raw = os.getenv("CNLANG_COOKIE", "")
    if not raw:
        msg = "❌ 未设置 CNLANG_COOKIE 环境变量"
        print(msg)
        send("国语视界签到", msg)
        return []

    cookies_list = [c.strip() for line in raw.split('&') for c in line.split('\n') if c.strip()]
    cookies_list = [c for c in cookies_list if len(c) > 20]

    if not cookies_list:
        msg = "❌ CNLANG_COOKIE 内容为空或格式错误"
        print(msg)
        send("国语视界签到", msg)
        return []

    print(f"✅ 从 CNLANG_COOKIE 读取到 {len(cookies_list)} 个账号")
    return cookies_list


def main():
    print("【国语视界签到】多账号任务开始...")

    if os.getenv("RANDOM_SIGNIN", "").lower() == "true":
        max_delay = int(os.getenv("MAX_RANDOM_DELAY", 3600))
        delay_seconds = random.randint(1, max_delay)
        minutes = delay_seconds // 60
        seconds = delay_seconds % 60
        print(f"【随机延迟】已开启，将在 {minutes} 分钟 {seconds} 秒后开始执行...")
        time.sleep(delay_seconds)
    else:
        print("✅ 未开启随机延迟")

    cookie_list = get_all_cookies()
    if not cookie_list:
        return

    all_results = []

    for idx, cookie_str in enumerate(cookie_list, 1):
        print(f"\n📌 开始处理第 {idx}/{len(cookie_list)} 个账号")

        try:
            solution = get_flare_solution(SIGNIN_URL, cookie_str)
            if not solution:
                all_results.append(f"账号{idx}: FlareSolverr 调用失败")
                continue

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
                try:
                    r = session.get(SIGNIN_URL, timeout=20)
                    html = r.text
                except:
                    pass

            if "Cloudflare" in html and "challenge" in html.lower():
                all_results.append(f"账号{idx}: 仍被 Cloudflare 拦截")
                continue

            soup = BeautifulSoup(html, "html.parser")
            formhash_tag = soup.find("input", {"name": "formhash"})

            if not formhash_tag and ("今天已经签到过了" in html or "已经签到" in html or "今日已签到" in html):
                money = get_current_money(session)
                result = f"账号{idx}: 您今日已经签到，请明天再来！"
                if money:
                    result += f" 当前大洋: {money}"
                print(result)
                all_results.append(result)
                continue   # 已签到 → 不发通知

            if not formhash_tag:
                all_results.append(f"账号{idx}: 未找到 formhash")
                continue

            formhash = formhash_tag.get("value")
            print(f"✅ formhash 获取成功: {formhash}")

            old_money = get_current_money(session)

            try:
                xq = requests.get("https://v1.hitokoto.cn/?encode=text", timeout=6).text.strip()
                if len(xq) < 6 or len(xq) > 50:
                    xq = "每天签到，水一发~"
            except:
                xq = "每天签到，水一发~"

            qiandao_url = "https://cnlang.org/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1"
            payload = {
                "formhash": formhash,
                "qdxq": "kx",
                "qdmode": "1",
                "todaysay": xq,
                "fastreply": "0"
            }

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

            # 删除重复的“本次获得 X 大洋”提示（保留“当前大洋”）
            result_text = re.sub(r'本次获得 \d+ 大洋\s*', '', result_text).strip()

            print(f"签到结果: {result_text}")
            all_results.append(f"账号{idx}: {result_text}")

            # 只有成功或失败才通知
            if "已经签到" not in result_text and "今日已经签到" not in result_text:
                send("国语视界签到", f"账号{idx} {result_text}")

        except Exception as e:
            error_msg = f"账号{idx} 执行异常: {str(e)}"
            print(error_msg)
            all_results.append(error_msg)
            send("国语视界签到", error_msg)

    if all_results:
        summary = "\n".join(all_results)
        print("\n【国语视界签到】全部完成\n" + summary)

    print("【国语视界签到】多账号任务执行完毕")


if __name__ == "__main__":
    main()
