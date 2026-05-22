# cron: 0 10 * * *
# new Env('比思论坛签到')

"""
【青龙面板使用说明】

1. 依赖安装（必须）：
   - 青龙面板 → 依赖管理 → Python3 依赖 → 新增：
     - requests
   - 安装完成后重启青龙

2. 环境变量设置：
   - BISI_COOKIE       （必填，支持多账号）多个 Cookie 用 & 分割 或 换行分割
   - RANDOM_SIGNIN     （可选）true = 开启随机延迟
   - MAX_RANDOM_DELAY  （可选）随机延迟最大秒数，默认 3600 秒

3. 多账号配置示例（BISI_COOKIE 中填写）：
   Cookie字符串1&Cookie字符串2&Cookie字符串3
   或者每行一个 Cookie（推荐）：
   Cookie字符串1
   Cookie字符串2
   Cookie字符串3

4. 注意事项：
   - 已签到的账号完全不发送通知
   - 只有签到成功 或 签到失败 时才会推送通知
"""

import os
import random
import re
import time
import requests
from notify import send   # 青龙标准通知模块

print("【比思论坛签到】多账号任务开始...")

# ====================== 获取所有 Cookie ======================
def get_all_cookies():
    raw = os.getenv("BISI_COOKIE", "")
    if not raw:
        msg = "❌ 未设置 BISI_COOKIE 环境变量，请检查青龙面板"
        print(msg)
        send("比思论坛签到", msg)
        exit(1)

    cookies_list = [c.strip() for line in raw.split('&') for c in line.split('\n') if c.strip()]
    cookies_list = [c for c in cookies_list if len(c) > 20]

    if not cookies_list:
        msg = "❌ BISI_COOKIE 内容为空或格式错误"
        print(msg)
        send("比思论坛签到", msg)
        exit(1)

    print(f"✅ 从 BISI_COOKIE 读取到 {len(cookies_list)} 个账号")
    return cookies_list

# ====================== 随机延迟 ======================
random_signin = os.getenv("RANDOM_SIGNIN", "false").strip().lower() == "true"
max_delay = int(os.getenv("MAX_RANDOM_DELAY", "3600").strip())

if random_signin:
    delay_seconds = random.randint(1, max_delay)
    minutes = delay_seconds // 60
    seconds = delay_seconds % 60
    print(f"⏳ 随机延迟: 等待 {minutes} 分钟 {seconds} 秒后开始执行...")
    time.sleep(delay_seconds)
else:
    print("✅ 未开启随机延迟，直接执行签到")

# ====================== 处理每个账号 ======================
cookie_list = get_all_cookies()
all_results = []

base_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Encoding": "gzip, deflate, sdch, br",
    "Connection": "keep-alive",
}

def get_current_money(cookie):
    """获取当前金钱数量"""
    credit_url = "http://hkcdnmesh.site/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu"
    try:
        resp = requests.get(
            credit_url,
            headers={**base_headers, "Cookie": cookie},
            timeout=15
        )
        # 常见 Discuz 金钱显示格式
        match = re.search(r'<span[^>]*id=["\']hcredit_2["\'][^>]*>(.*?)</span>', resp.text, re.DOTALL)
        if match:
            money_str = match.group(1).replace('\xa0', ' ').strip()
            return money_str
    except:
        pass
    return None

for idx, cookie in enumerate(cookie_list, 1):
    print(f"\n📌 开始处理第 {idx}/{len(cookie_list)} 个账号")

    try:
        # 获取签到前金钱
        print("📊 获取签到前金钱...")
        old_money = get_current_money(cookie)

        # Step 1: 获取 formhash
        print("🔄 正在获取 formhash...")
        get_url = "http://hkcdnmesh.site/plugin.php?id=dsu_paulsign%3Asign"

        resp_get = requests.get(
            get_url,
            headers={**base_headers, "Cookie": cookie},
            timeout=15,
            allow_redirects=True,
        )
        resp_get.raise_for_status()

        formhash_match = re.search(r'formhash=(.+?)">', resp_get.text)
        if not formhash_match:
            raise Exception("未找到 formhash，请检查 Cookie 是否有效")

        formhash = formhash_match.group(1).strip()
        print(f"✅ 获取到 formhash: {formhash}")

        # Step 2: 提交签到
        print("🔄 正在提交签到请求...")
        post_url = "http://hkcdnmesh.site/plugin.php?id=dsu_paulsign%3Asign&operation=qiandao&infloat=1&sign_as=1&inajax=1"

        post_data = {
            "formhash": formhash,
            "qdxq": "fd",
        }

        post_headers = {
            "Proxy-Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cookie": cookie,
        }

        resp_post = requests.post(
            post_url,
            headers=post_headers,
            data=post_data,
            timeout=15,
        )
        resp_text = resp_post.text

        # 获取签到后金钱
        print("📊 获取签到后金钱...")
        new_money = get_current_money(cookie)

        # ====================== 判断结果并格式化提示 ======================
        if "成功" in resp_text or "签到成功" in resp_text or "恭喜" in resp_text:
            if old_money and new_money:
                try:
                    old_val = int(str(old_money).replace(',', '').replace(' ', '').strip())
                    new_val = int(str(new_money).replace(',', '').replace(' ', '').strip())
                    diff = new_val - old_val
                    if diff > 0:
                        sign_result = f"✅ 签到成功！登录金钱+{diff}，当前金钱{new_val}"
                    else:
                        sign_result = f"✅ 签到成功！当前金钱{new_val}"
                except:
                    sign_result = f"✅ 签到成功！当前金钱{new_money}"
            else:
                sign_result = "✅ 签到成功"
        elif any(word in resp_text for word in [
            "已經簽到",
            "今日已經簽到",
            "您今日已經簽到",
            "簽到過了"
        ]):
            sign_result = "今日已签到"
        else:
            sign_result = "❌ 签到失败"

        print(f"📢 签到结果: {sign_result}")
        all_results.append({
            "account": idx,
            "result": sign_result,
            "action_type": "success" if "签到成功" in sign_result else ("already" if "今日已签到" in sign_result else "failed")
        })

    except Exception as e:
        error_msg = f"账号{idx} 执行异常: {str(e)}"
        print(error_msg)
        all_results.append({
            "account": idx,
            "result": f"❌ 签到失败: {str(e)}",
            "action_type": "failed"
        })

# ====================== 最终通知 ======================
if all_results:
    summary_lines = []
    has_action = False
    for item in all_results:
        summary_lines.append(f"账号{item['account']}: {item['result']}")
        if item.get("action_type") in ["success", "failed"]:
            has_action = True

    summary_text = "\n".join(summary_lines)

    if has_action:
        send("比思论坛签到结果", f"【比思论坛多账号签到完成】\n\n{summary_text}\n\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("🎉 多账号签到完成，通知已发送")
    else:
        print("✅ 所有账号均已签到，无需发送通知")

print("【比思论坛签到】多账号任务执行完毕")
