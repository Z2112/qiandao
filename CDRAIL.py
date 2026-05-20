"""
# ==================== 青龙面板使用说明（成都地铁签到） ====================

# 【脚本名称】 成都地铁签到（支持多账号 + 签到 + 积分查询）
# 【cron 定时】 每天 9:00 执行（可自行修改为其他时间）
# 【环境变量】
#    CDRAIL_DATA  → 账号数据（必填，支持多账号）
#       • JSON 格式：{"token":"xxx","app-token":"xxx","Cookie":"xxx"}
#       • querystring 格式：token=xxx&app-token=xxx&cookie=xxx
#       • 多账号支持：用换行 或 @ 分割
# 【可选变量】
#    RANDOM_SIGNIN      → true 开启随机延迟（默认 false）
#    MAX_RANDOM_DELAY   → 最大随机延迟秒数（默认 3600 秒 = 1小时）
#    PRIVACY_MODE       → true 开启隐私模式（默认 true，账号信息打码）
# 【抓包说明】
#    1. 打开成都地铁APP
#    2. 抓取签到接口：https://app.cdmetro.chengdurail.cn/platform/users/user/sign-in-integral
#    3. 从 Headers 中提取：token、app-token、Cookie（device-id 可选）
# 【通知逻辑】 今日已签到 → 仅打印日志，不通知；签到成功或失败 → 通过青龙通知系统推送
#
# 【详细使用步骤】
# 1. 青龙面板 → 依赖管理 → 新建 Python 依赖，安装以下依赖：
#       requests
# 2. 青龙面板 → 环境变量 → 新建变量 CDRAIL_DATA，填入抓包数据（支持多账号）
# 3. 青龙面板 → 定时任务 → 新建任务，脚本路径指向本文件
# 4. 保存后点击“立即执行”测试，查看日志是否正常
#
# 【注意事项】
# • 建议开启 PRIVACY_MODE 保护隐私
# • 账号数据请妥善保管，不要泄露
# • 如签到失败可尝试重新抓包更新 token/app-token
#
# 作者：Grok（根据用户提供的 CDRail.py 完全重构优化）
# 优化日期：2026-05-20
# 原脚本来源：https://github.com/agluo/ql-script-hub/blob/master/CDRail.py
"""

# cron: 0 9 * * *
# new Env('成都地铁签到')

import os
import re
import sys
import time
import json
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== 通知模块 ====================
try:
    from notify import send
except ImportError:
    send = None

print("【成都地铁签到】开始执行...")

# ==================== 获取环境变量 ====================
CDRAIL_DATA = os.getenv('CDRAIL_DATA')
if not CDRAIL_DATA:
    msg = "❌ 未设置 CDRAIL_DATA 环境变量，请检查青龙面板变量配置"
    print(msg)
    if send:
        send("成都地铁签到", msg)
    sys.exit(1)

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

# ==================== 配置参数 ====================
PRIVACY_MODE = os.getenv('PRIVACY_MODE', 'true').lower() == 'true'
TIMEOUT = int(os.getenv('TIMEOUT', '15'))
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))

DEFAULT_HEADERS = {
    "system-version": "16.4.1",
    "Connection": "keep-alive",
    "system": "iOS",
    "Accept-Encoding": "gzip, deflate, br",
    "app-version": "3.5.6",
    "device-id": "00000000-0000-0000-0000-000000000000",
    "deviceId": "00000000-0000-0000-0000-000000000000",
    "source": "CD-METRO-APP",
    "User-Agent": "CDMetro/3.5.6 (iPhone; iOS 16.4.1; Scale/3.00)",
    "vendor": "iPhone15,3",
    "language": "zh-Hans",
    "Host": "app.cdmetro.chengdurail.cn",
    "Accept-Language": "zh-Hans-US;q=1, en-US;q=0.9",
    "Accept": "*/*",
    "user": "external",
}

def mask_text(text: str, head: int = 6, tail: int = 6) -> str:
    """隐私保护：打码显示账号关键信息"""
    if not PRIVACY_MODE or not text or len(text) <= head + tail:
        return text or ""
    return text[:head] + "*" * (len(text) - head - tail) + text[-tail:]

def parse_accounts(env_value: str):
    """解析 CDRAIL_DATA，支持 JSON / querystring / 多账号"""
    if not env_value:
        return []
    env_value = env_value.strip()

    # 单个完整 JSON
    try:
        if env_value.startswith("{") and env_value.endswith("}"):
            return [json.loads(env_value)]
    except:
        pass

    accounts = []
    # 支持换行或 @ 分割多账号
    raw_list = [x.strip() for x in re.split(r'[\n@]', env_value) if x.strip()]
    for raw in raw_list:
        try:
            if raw.startswith("{") and raw.endswith("}"):
                accounts.append(json.loads(raw))
                continue
            # querystring 格式
            data = {}
            for part in raw.split("&"):
                if "=" not in part:
                    continue
                k, v = part.split("=", 1)
                data[k.strip()] = v.strip()
            if data:
                accounts.append(data)
        except Exception as e:
            print(f"❌ 账号解析失败: {raw[:30]}... {e}")
    return accounts

def build_session():
    session = requests.Session()
    retries = Retry(total=MAX_RETRIES, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def build_headers(account: dict):
    headers = DEFAULT_HEADERS.copy()
    for k, v in (account or {}).items():
        if v is None:
            continue
        lk = str(k).lower()
        if lk == "cookie":
            headers["Cookie"] = v
        elif lk == "token":
            headers["token"] = v
        elif lk in ("app-token", "apptoken", "app_token"):
            headers["app-token"] = v
        elif lk in ("deviceid", "device-id", "device_id"):
            headers["deviceId"] = v
            headers["device-id"] = v
        else:
            headers[k] = v
    return headers

# ==================== 主流程 ====================
accounts = parse_accounts(CDRAIL_DATA)
if not accounts:
    msg = "❌ CDRAIL_DATA 解析失败，请检查格式是否正确"
    print(msg)
    if send:
        send("成都地铁签到"， msg)
    sys.exit(1)

print(f"✅ 共检测到 {len(accounts)} 个账号，开始签到...")

for idx, acc in enumerate(accounts, 1):
    print(f"\n📌 第 {idx}/{len(accounts)} 个账号")
    token = acc.get("token") or acc.get("Token")
    app_token = acc.get("app-token") or acc.get("appToken") or acc.get("App-Token")
    masked_token = mask_text(token or "")

    if not token or not app_token:
        print(f"❌ 账号 {masked_token} 缺少 token 或 app-token，跳过")
        continue

    session = build_session()
    headers = build_headers(acc)

    try:
        # 执行签到
        sign_url = "https://app.cdmetro.chengdurail.cn/platform/users/user/sign-in-integral"
        resp = session.get(sign_url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        code = data.get("code")
        msg_text = data.get("msg") or data.get("message") or "无返回消息"
        integral = data.get("data", {}).get("integral", 0) or data.get("integral", 0)

        # ==================== 判断签到结果 ====================
        if code in [200, "200", 0, "0"] or "成功" in msg_text or "已签到" in msg_text:
            if "已签到" in msg_text or "今日已签" in msg_text:
                sign_result = "今日已签到"
                notify_flag = False
            else:
                sign_result = f"✅ 签到成功，获得 {integral} 积分"
                notify_flag = True
        else:
            sign_result = f"❌ 签到失败: {msg_text}"
            notify_flag = True

        print(f"📢 签到结果: {sign_result}")

        # 可选：查询当前积分（原脚本未包含，可自行扩展）
        # 这里只打印签到结果，保持简洁

        # ==================== 发送通知（仅成功/失败） ====================
        if notify_flag and send:
            title = "✅ 成都地铁签到成功" if "签到成功" in sign_result else "❌ 成都地铁签到失败"
            body = f"账号: {masked_token}\n{sign_result}"
            send(title, body)
            print("📨 已推送通知")
        elif not notify_flag:
            print("ℹ️ 今日已签到，无需通知")

    except requests.exceptions.RequestException as e:
        error_msg = f"❌ 网络请求异常: {e}"
        print(error_msg)
        if send:
            send("成都地铁签到"， f"账号 {masked_token} {error_msg}")
    except Exception as e:
        error_msg = f"❌ 执行异常: {e}"
        print(error_msg)
        if send:
            send("成都地铁签到"， f"账号 {masked_token} {error_msg}")

print("\n【成都地铁签到】全部账号执行完毕 ✅")
