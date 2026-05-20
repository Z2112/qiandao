# cron: 0 10 * * *
# new Env('HIFIKI签到')

"""
【青龙面板使用说明】

1. 依赖安装（必须）：
   - 青龙面板 → 依赖管理 → Python3 依赖 → 新增：
     - requests
   - 安装完成后重启青龙

2. 环境变量设置：
   - HIFIKI_COOKIE      （必填，支持多账号）多个 Cookie 用 & 分割 或 换行分割
   - RANDOM_SIGNIN      （可选）true = 开启随机延迟
   - MAX_RANDOM_DELAY   （可选）随机延迟最大秒数，默认 3600 秒

3. 多账号配置示例（HIFIKI_COOKIE 中填写）：
   Cookie字符串1&Cookie字符串2&Cookie字符串3
   或者每行一个 Cookie（推荐）：
   Cookie字符串1
   Cookie字符串2
   Cookie字符串3

4. 注意事项：
   - 已签到的账号完全不发送任何通知
   - 只有签到成功 或 签到失败 时才会推送通知
   - 多账号时只会发送一条汇总通知
"""

import os
import requests
import time
import random
import json
import sys
from notify import send   # 青龙标准通知模块


def format_remaining_time(seconds: int) -> str:
    """将秒数格式化为“X分钟Y秒”"""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}分钟{secs}秒"


def get_all_cookies():
    """支持 & 或换行分割的多账号"""
    raw = os.getenv("HIFIKI_COOKIE", "")
    if not raw:
        msg = "❌ 未检测到 HIFIKI_COOKIE 环境变量，请检查配置"
        print(msg)
        if send:
            send("HIFIKI签到", msg)
        sys.exit(1)

    # 支持 & 分割 和 换行分割
    cookies_list = [c.strip() for line in raw.split('&') for c in line.split('\n') if c.strip()]
    cookies_list = [c for c in cookies_list if len(c) > 20]

    if not cookies_list:
        msg = "❌ HIFIKI_COOKIE 内容为空或格式错误"
        print(msg)
        if send:
            send("HIFIKI签到", msg)
        sys.exit(1)

    print(f"✅ 从 HIFIKI_COOKIE 读取到 {len(cookies_list)} 个账号")
    return cookies_list


def main():
    print("=== HIFIKI 签到任务开始（多账号版） ===")

    cookie_list = get_all_cookies()
    all_results = []

    # ==================== 随机延迟 ====================
    random_signin = os.getenv("RANDOM_SIGNIN", "false").lower() == "true"
    max_random_delay_str = os.getenv("MAX_RANDOM_DELAY")

    if random_signin and max_random_delay_str:
        try:
            max_delay = int(max_random_delay_str)
            if max_delay > 0:
                delay_seconds = random.randint(1, max_delay)
                print(f"✅ 已开启随机延迟，等待 {format_remaining_time(delay_seconds)} 后开始执行")

                for remaining in range(delay_seconds, 0, -1):
                    print(f"\r⏳ 剩余 {format_remaining_time(remaining)} ", end="", flush=True)
                    time.sleep(1)
                print("\n🚀 延迟结束，开始执行签到...")
            else:
                print("⚠️ MAX_RANDOM_DELAY 设置为0，跳过随机延迟")
        except ValueError:
            print("⚠️ MAX_RANDOM_DELAY 格式错误，跳过随机延迟")
    else:
        print("ℹ️ 随机延迟未开启（或未配置 RANDOM_SIGNIN=true），直接执行")

    # ==================== 处理每个账号 ====================
    headers_template = {
        "content-length": "0",
        "sec-ch-ua-platform": "\"Windows\"",
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "accept": "text/plain, */*; q=0.01",
        "sec-ch-ua": "\"Not;A=Brand\";v=\"8\", \"Chromium\";v=\"150\", \"Google Chrome\";v=\"150\"",
        "sec-ch-ua-mobile": "?0",
        "origin": "https://www.hifiki.com",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "referer": "https://www.hifiki.com/",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "zh-CN,zh;q=0.9",
        "priority": "u=1, i",
    }

    url = "https://www.hifiki.com/sg_sign.htm"

    for idx, cookie in enumerate(cookie_list, 1):
        print(f"\n📌 开始处理第 {idx}/{len(cookie_list)} 个账号")
        headers = headers_template.copy()
        headers["cookie"] = cookie

        try:
            response = requests.post(url, headers=headers, timeout=15)
            print(f"📡 响应状态码: {response.status_code}")

            try:
                result = response.json()
                code = str(result.get("code", ""))
                message = result.get("message", str(result))

                if code == "0" or "成功" in message:
                    status = "✅ 签到成功"
                    final_msg = f"{status}\n{message}"
                    print(final_msg)
                    all_results.append(f"账号{idx}: {status}")
                    if send:
                        send("HIFIKI签到", f"账号{idx} {final_msg}")

                elif code == "-1" or "今天已经签过" in message:
                    status = "ℹ️ 今天已签到"
                    final_msg = f"{status}\n{message}"
                    print(final_msg)
                    all_results.append(f"账号{idx}: {status}")
                    # 已签到 → 不发送通知

                else:
                    status = "⚠️ 签到结果未知（失败）"
                    final_msg = f"{status}\n{message}"
                    print(final_msg)
                    all_results.append(f"账号{idx}: {status}")
                    if send:
                        send("HIFIKI签到", f"账号{idx} {final_msg}")

            except json.JSONDecodeError:
                error_msg = f"❌ 返回内容非JSON格式\n{response.text[:300]}"
                print(error_msg)
                all_results.append(f"账号{idx}: 签到失败")
                if send:
                    send("HIFIKI签到", f"账号{idx} {error_msg}")

        except requests.exceptions.RequestException as e:
            error_msg = f"❌ 请求失败: {str(e)}"
            print(error_msg)
            all_results.append(f"账号{idx}: 签到失败")
            if send:
                send("HIFIKI签到", f"账号{idx} {error_msg}")
        except Exception as e:
            error_msg = f"❌ 未知错误: {str(e)}"
            print(error_msg)
            all_results.append(f"账号{idx}: 签到失败")
            if send:
                send("HIFIKI签到", f"账号{idx} {error_msg}")

    # ====================== 最终汇总 ====================
    if all_results:
        summary = "\n".join(all_results)
        print("\n=== HIFIKI 签到任务全部执行完毕 ===")
        print(summary)

if __name__ == "__main__":
    main()
