# cron: 0 10 * * *
# new Env('精易论坛签到')

"""
【青龙面板使用说明】

1. 依赖安装（无需额外操作）：
   - 本脚本仅使用 requests + notify（青龙内置）
   - 无需在依赖管理中新增任何依赖

2. 环境变量设置：
   - IJINGYI_COOKIE      （必填，支持多账号）
     多个 Cookie 用 & 分割 或 换行分割（青龙支持直接换行输入）
   - RANDOM_SIGNIN       （可选）true = 开启随机延迟
   - MAX_RANDOM_DELAY    （可选）随机延迟最大秒数，默认 3600 秒（1小时）

3. 多账号配置示例（在 IJINGYI_COOKIE 中填写）：
   Cookie字符1&Cookie字符2&Cookie字符3
   或者每行一个 Cookie（推荐）：
   Cookie字符1
   Cookie字符2
   Cookie字符3

4. 注意事项：
   - 已签到的账号不会发送任何通知（减少骚扰）
   - 只有签到成功 或 签到失败 时才会推送通知
   - 多账号时只会发送一条汇总通知
   - Cookie 获取方式：登录论坛后 F12 → Application → Cookies → 复制全部字符串
"""

import os
import sys
import time
import random
import re
import requests

# ==================== 通知模块 ====================
try:
    from notify import send
except ImportError:
    send = None

print("【精易论坛签到】多账号任务开始...")

# ==================== 获取所有 Cookie（支持 & 或换行分割） ====================
def get_all_cookies():
    raw = os.getenv('IJINGYI_COOKIE')
    if not raw:
        msg = "❌ 未设置 IJINGYI_COOKIE 环境变量，请检查青龙面板变量配置"
        print(msg)
        if send:
            send("精易论坛签到", msg)
        sys.exit(1)

    # 支持 & 分割 和 换行符分割
    cookies_list = raw.split('&')
    cookies_list = [c.strip() for line in cookies_list for c in line.split('\n') if c.strip()]
    cookies_list = [c for c in cookies_list if len(c) > 20]

    if not cookies_list:
        msg = "❌ IJINGYI_COOKIE 内容为空或格式错误"
        print(msg)
        if send:
            send("精易论坛签到", msg)
        sys.exit(1)

    print(f"✅ 从 IJINGYI_COOKIE 读取到 {len(cookies_list)} 个账号")
    return cookies_list

# ==================== 随机延迟（可选） ====================
random_signin = os.getenv('RANDOM_SIGNIN', 'false').lower() == 'true'
max_random_delay = os.getenv('MAX_RANDOM_DELAY')

if random_signin:
    try:
        max_d = int(max_random_delay) if max_random_delay else 3600
        if max_d > 0:
            delay_sec = random.randint(1, max_d)
            minutes = delay_sec // 60
            seconds = delay_sec % 60
            print(f"⏳ 随机延迟: 等待 {minutes} 分钟 {seconds} 秒后开始执行")
            time.sleep(delay_sec)
    except Exception as e:
        print(f"⚠️ 随机延迟处理异常（将继续执行）: {e}")
else:
    print("✅ 未开启随机延迟（RANDOM_SIGNIN 未设置为 true）")

# ==================== Cookie 列表 ====================
cookie_list = get_all_cookies()
all_results = []

# ==================== 处理每个账号 ====================
for idx, cookie in enumerate(cookie_list, 1):
    print(f"\n📌 开始处理第 {idx}/{len(cookie_list)} 个账号")
    session = requests.Session()

    base_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cookie": cookie,
        "Connection": "keep-alive",
    }
    session.headers.update(base_headers)

    try:
        # Step 1: GET 签到页面获取 formhash
        sign_url = "https://bbs.ijingyi.com/plugin.php?id=dsu_paulsign:sign"
        resp1 = session.get(sign_url, timeout=15)
        resp1.raise_for_status()

        formhash_match = re.search(r'name="formhash" value="(.+?)"', resp1.text)
        if not formhash_match:
            raise Exception("未找到 formhash，请检查 Cookie 是否有效或账号已掉线")
        formhash = formhash_match.group(1)
        print(f"✅ 已获取 formhash: {formhash}")

        # Step 2: POST 签到
        qiandao_url = "https://bbs.ijingyi.com/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1"
        post_data = {
            "formhash": formhash,
            "submit": "1",
            "targerurl": "",
            "todaysay": "",
            "qdxq": "yl"
        }
        post_headers = base_headers.copy()
        post_headers.update({
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://bbs.ijingyi.com",
            "Referer": sign_url,
            "sec-ch-ua": "\\"Chromium\\";v=\\"21\\", \\" Not;A Brand\\";v=\\"99\\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\\"Windows\\"",
        })

        resp2 = session.post(qiandao_url, data=post_data, headers=post_headers, timeout=15)
        resp2.raise_for_status()
        content = resp2.text

        # ==================== 判断签到结果 ====================
        if '今天已经签到' in content or '已签到' in content or '您今日已经签到' in content or '签到过了' in content:
            sign_result = "今日已签到"
            notify_flag = False
            reward_text = "今日已签到，无新奖励"
        elif ' 签到成功' in content or '恭喜您' in content or 'success' in content.lower() or '"status":1' in content or '获得' in content:
            sign_result = "✅ 签到成功"
            notify_flag = True
            reward_match = re.search(r'获得\s*([^<。！]+)', content)
            reward_text = reward_match.group(1).strip() if reward_match else "未检测到奖励"
        else:
            sign_result = "❌ 签到失败或异常"
            notify_flag = True
            reward_text = "签到失败"

        print(f"📢 签到结果: {sign_result}")

        # ==================== 新增：获取连续签到天数 ====================
        streak_days = "N/A"
        try:
            streak_url = "https://bbs.ijingyi.com/dsu_paulsign-sign.html"
            streak_resp = session.get(streak_url, headers=base_headers, timeout=15)
            if streak_resp.status_code == 200:
                streak_match = re.search(r'class="continuous"[^>]*>\s*连续签到\s*(\d+)\s*天', streak_resp.text)
                if streak_match:
                    streak_days = streak_match.group(1)
        except Exception as e:
            print(f"⚠️ 获取连续签到天数异常: {e}")

        # Step 3: 获取积分信息（清理精币单位）
        credit_url = "https://bbs.ijingyi.com/home.php?mod=spacecp&ac=credit&showcredit=1"
        credit_headers = base_headers.copy()
        credit_headers.update({
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        })

        credit_resp = session.get(credit_url, headers=credit_headers, timeout=15)
        credit_resp.raise_for_status()

        jb = re.search(r'精币: .*?>(.*?)<', credit_resp.text)
        jb_val = jb.group(1).strip() if jb else 'N/A'
        jb_val = re.sub(r'[^\d]', '', jb_val)  # 只保留数字，避免重复单位

        # ==================== 新的紧凑输出格式 ====================
        compact_line = (
            f"当前账户 --- 【连续签到天数】：{streak_days} 天 "
            f"--- 【签到奖励】：{reward_text} "
            f"--- 【精币】：{jb_val}"
        )
        print(compact_line)

        # 记录结果
        all_results.append(f"账号{idx}: {sign_result}\n{compact_line}")

        if not notify_flag:
            print("ℹ️ 今日已签到，无需通知")

    except requests.exceptions.RequestException as e:
        error_msg = f"❌ 账号{idx} 网络请求异常: {str(e)}"
        print(error_msg)
        all_results.append(f"账号{idx}: 签到失败（网络异常）")
    except Exception as e:
        error_msg = f"❌ 账号{idx} 执行异常: {str(e)}"
        print(error_msg)
        all_results.append(f"账号{idx}: 签到失败（执行异常）")

# ==================== 最终汇总通知（只发送一次） ====================
if all_results:
    summary = "\n\n".join(all_results)
    has_action = any("签到成功" in r or "签到失败" in r for r in all_results)

    if has_action and send:
        send("精易论坛签到结果", 
             f"【精易论坛多账号签到完成】\n\n{summary}\n\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("🎉 多账号签到完成，通知已发送（仅一次）")
    else:
        print("✅ 所有账号已签到，无需发送通知")

print("【精易论坛签到】多账号任务执行完毕")
