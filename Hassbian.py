# cron: 0 10 * * *
# new Env('Hassbian签到')

"""
【青龙面板使用说明】

1. 依赖安装（必须）：
   - 青龙面板 → 依赖管理 → Python3 依赖 → 新增：
     - requests
   - 安装完成后重启青龙

2. 环境变量设置：
   - HASSBIAN_COOKIE    （必填，支持多账号）多个 Cookie 用 & 分割 或 换行分割
   - RANDOM_SIGNIN      （可选）true = 开启随机延迟
   - MAX_RANDOM_DELAY   （可选）随机延迟最大秒数，默认 3600 秒
   - ALWAYS_NOTIFY      （可选）true = 成功/失败都通知；false = 仅失败通知（默认 false）

3. 多账号配置示例（HASSBIAN_COOKIE 中填写）：
   Cookie字符串1&Cookie字符串2&Cookie字符串3
   或者每行一个 Cookie（推荐）：
   Cookie字符串1
   Cookie字符串2
   Cookie字符串3
"""

import os
import time
import random
import requests
import re
import sys
from notify import send

def main():
    print("=== 🌟 Hassbian论坛自动签到（多账号版） 开始 ===")
    
    raw = os.getenv('HASSBIAN_COOKIE', '')
    if not raw:
        msg = "❌ 未找到 HASSBIAN_COOKIE 环境变量，请先在青龙面板中添加！"
        print(msg)
        send("Hassbian签到", msg)
        sys.exit(1)

    cookie_list = [c.strip() for line in raw.split('&') for c in line.split('\n') if c.strip()]
    cookie_list = [c for c in cookie_list if len(c) > 20]

    if not cookie_list:
        msg = "❌ HASSBIAN_COOKIE 内容为空或格式错误"
        print(msg)
        send("Hassbian签到", msg)
        sys.exit(1)

    print(f"✅ 从 HASSBIAN_COOKIE 读取到 {len(cookie_list)} 个账号")

    # ==================== 随机延迟 ====================
    random_signin = os.getenv('RANDOM_SIGNIN', 'false').lower() in ['true', '1', 'yes', 'on']
    max_delay = int(os.getenv('MAX_RANDOM_DELAY', '3600'))

    if random_signin and max_delay > 0:
        delay = random.randint(1, max_delay)
        print(f"⏰ 已开启随机延迟，计划等待 {delay} 秒后开始执行")
        for remaining in range(delay, 0, -1):
            mins = remaining // 60
            secs = remaining % 60
            print(f"\r⏳ 等待 {mins} 分 {secs} 秒后开始执行", end="", flush=True)
            time.sleep(1)
        print("\n🚀 延迟结束，开始执行签到...")
    else:
        print("🚀 随机延迟未开启，立即开始执行签到...")

    script_dir = os.path.dirname(os.path.abspath(__file__))

    all_results = []
    base_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:85.0) Gecko/20100101 Firefox/85.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    }

    for idx, cookie_str in enumerate(cookie_list, 1):
        print(f"\n📌 开始处理第 {idx}/{len(cookie_list)} 个账号")
        cookies = {}
        for item in cookie_str.split(';'):
            item = item.strip()
            if '=' in item:
                k, v = item.split('=', 1)
                cookies[k.strip()] = v.strip()

        session = requests.Session()

        try:
            # 签到前获取积分
            print("📊 签到前获取积分...")
            old_money = None
            try:
                r_old = session.get(
                    "https://bbs.hassbian.com/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu",
                    headers=base_headers, cookies=cookies, timeout=15
                )
                match = re.search(r'<span id="hcredit_2">(.+?)</span>', r_old.text, re.DOTALL)
                if match:
                    old_money = match.group(1).replace('\xa0', ' ').strip()
            except:
                pass

            # 执行签到（访问首页）——这是你要保存的那个API
            print("📍 执行签到（访问首页）...")
            headers1 = base_headers.copy()
            headers1.update({"Referer": "https://bbs.hassbian.com", "Upgrade-Insecure-Requests": "1"})

            r_sign = session.get(
                "https://bbs.hassbian.com/",
                headers=headers1,
                cookies=cookies,
                timeout=20
            )

            # 签到后获取积分
            print("📊 签到后再次获取积分...")
            new_money = None
            try:
                r_new = session.get(
                    "https://bbs.hassbian.com/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu",
                    headers=base_headers, cookies=cookies, timeout=15
                )
                match = re.search(r'<span id="hcredit_2">(.+?)</span>', r_new.text, re.DOTALL)
                if match:
                    new_money = match.group(1).replace('\xa0', ' ').strip()
            except:
                pass

            # 判断结果（✅ 成功/已签到，❌ 失败）
            if old_money and new_money and old_money != new_money:
                try:
                    old_val = int(str(old_money).replace(',', '').replace(' ', '').strip())
                    new_val = int(str(new_money).replace(',', '').replace(' ', '').strip())
                    diff = new_val - old_val
                    if diff > 0:
                        result = f"✅ 签到成功 | 账号{idx} | 登录金钱+{diff} | 当前金钱: {new_val}"
                    else:
                        result = f"✅ 签到成功 | 账号{idx} | 当前金钱: {new_val}"
                except:
                    result = f"✅ 签到成功 | 账号{idx} | 当前金钱: {new_money}"
            else:
                money_part = f" | 当前金钱: {new_money or old_money}" if (new_money or old_money) else ""
                result = f"✅ 今日已签到 | 账号{idx}{money_part}"

            print(result)
            all_results.append({
                "account": idx,
                "result": result,
                "action_type": "success" if (old_money and new_money and old_money != new_money) else "already"
            })

        except Exception as e:
            result = f"❌ 签到失败 | 账号{idx} | 执行异常: {str(e)}"
            print(result)
            all_results.append({
                "account": idx,
                "result": result,
                "action_type": "failed"
            })

    # ==================== 通知逻辑 ====================
    # ALWAYS_NOTIFY=true：成功/失败都发；false：仅失败时发
    always_notify = os.getenv('ALWAYS_NOTIFY', 'false').lower() == 'true'
    if all_results:
        print("\n=== ✅ Hassbian签到任务全部执行完毕 ===")

        summary_lines = []
        has_fail = False
        for item in all_results:
            summary_lines.append(item['result'])
            if item.get('action_type') == "failed":
                has_fail = True

        summary_text = "\n".join(summary_lines)
        print(summary_text)

        if send and (always_notify or has_fail):
            notify_title = "Hassbian签到结果"
            notify_body = f"【Hassbian论坛多账号签到完成】\n\n{summary_text}\n\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"
            send(notify_title, notify_body)
            print("📨 已发送通知" + ("（ALWAYS_NOTIFY=true）" if always_notify and not has_fail else "（存在签到失败）" if has_fail else ""))
        else:
            print("✅ 全部签到成功/已签到，ALWAYS_NOTIFY=false，跳过通知")

if __name__ == "__main__":
    main()
