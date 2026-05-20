# cron: 0 10 * * *
# new Env('HIFIKI签到')

import os
import requests
import time
import random
import json

# 导入青龙通知模块
try:
    from notify import send
except:
    send = None


def format_remaining_time(seconds: int) -> str:
    """将秒数格式化为“X分钟Y秒”"""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}分钟{secs}秒"


def main():
    print("=== HIFIKI 签到任务开始 ===")

    # ==================== 环境变量读取 ====================
    cookie = os.getenv("HIFIKI_COOKIE")
    if not cookie:
        msg = "❌ 未检测到 HIFIKI_COOKIE 环境变量，请检查配置"
        print(msg)
        if send:
            send("HIFIKI签到", msg)
        return

    # 随机化配置（可选）
    random_signin = os.getenv("RANDOM_SIGNIN", "false").lower() == "true"
    max_random_delay_str = os.getenv("MAX_RANDOM_DELAY")

    # ==================== 随机延迟 ====================
    if random_signin and max_random_delay_str:
        try:
            max_delay = int(max_random_delay_str)
            if max_delay > 0:
                delay_seconds = random.randint(1, max_delay)
                print(f"✅ 已开启随机延迟，等待 {format_remaining_time(delay_seconds)} 后开始执行")

                # 倒计时显示（剩余分钟秒）
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

    # ==================== 请求头 ====================
    headers = {
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
        "cookie": cookie
    }

    url = "https://www.hifiki.com/sg_sign.htm"

    try:
        response = requests.post(url, headers=headers, timeout=15)
        print(f"📡 响应状态码: {response.status_code}")

        # 解析返回
        try:
            result = response.json()
            code = str(result.get("code", ""))
            message = result.get("message", str(result))

            # ==================== 通知逻辑修改 ====================
            if code == "0" or "成功" in message:
                # 签到成功 → 需要通知
                status = "✅ 签到成功"
                final_msg = f"{status}\n{message}"
                print(final_msg)
                if send:
                    send("HIFIKI签到", final_msg)

            elif code == "-1" or "今天已经签过" in message:
                # 今天已签过 → 只打印日志，不通知
                status = "ℹ️ 今天已签到"
                final_msg = f"{status}\n{message}"
                print(final_msg)
                # 不执行 send()

            else:
                # 其他情况（未知结果）→ 视为失败，需要通知
                status = "⚠️ 签到结果未知（失败）"
                final_msg = f"{status}\n{message}"
                print(final_msg)
                if send:
                    send("HIFIKI签到", final_msg)

        except json.JSONDecodeError:
            error_msg = f"❌ 返回内容非JSON格式\n{response.text[:300]}"
            print(error_msg)
            if send:
                send("HIFIKI签到", error_msg)

    except requests.exceptions.RequestException as e:
        error_msg = f"❌ 请求失败: {str(e)}"
        print(error_msg)
        if send:
            send("HIFIKI签到", error_msg)
    except Exception as e:
        error_msg = f"❌ 未知错误: {str(e)}"
        print(error_msg)
        if send:
            send("HIFIKI签到", error_msg)


if __name__ == "__main__":
    main()
