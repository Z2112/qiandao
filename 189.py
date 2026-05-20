# cron: 0 10 * * *
# new Env('天翼云盘签到')

import os
import sys
import time
import random
import re
import base64
import rsa
import requests

# ==================== 通知模块 ====================
try:
    from notify import send
except ImportError:
    send = None

print("【天翼云盘签到】开始执行...")

# ==================== 获取环境变量 ====================
username = os.getenv('CLOUD189_USERNAME')
password = os.getenv('CLOUD189_PASSWORD')
if not username or not password:
    msg = "❌ 未设置 CLOUD189_USERNAME 或 CLOUD189_PASSWORD 环境变量，请检查青龙面板变量配置"
    print(msg)
    if send:
        send("天翼云盘签到", msg)
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

# ==================== RSA 加密辅助函数 ====================
BI_RM = list("0123456789abcdefghijklmnopqrstuvwxyz")
B64MAP = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

def int2char(a):
    return BI_RM[a]

def b64tohex(a):
    d, e, c = "", 0, 0
    for i in range(len(a)):
        if a[i] != "=":
            v = B64MAP.index(a[i])
            if e == 0:
                e = 1
                d += int2char(v >> 2)
                c = 3 & v
            elif e == 1:
                e = 2
                d += int2char(c << 2 | v >> 4)
                c = 15 & v
            elif e == 2:
                e = 3
                d += int2char(c)
                d += int2char(v >> 2)
                c = 3 & v
            else:
                e = 0
                d += int2char(c << 2 | v >> 4)
                d += int2char(15 & v)
    if e == 1:
        d += int2char(c << 2)
    return d

def rsa_encode(j_rsakey, string):
    rsa_key = f"-----BEGIN PUBLIC KEY-----\n{j_rsakey}\n-----END PUBLIC KEY-----"
    pubkey = rsa.PublicKey.load_pkcs1_openssl_pem(rsa_key.encode())
    result = b64tohex(base64.b64encode(rsa.encrypt(str(string).encode(), pubkey)).decode())
    return result

# ==================== 登录函数 ====================
def login(uname, pwd):
    s = requests.Session()
    # 第一步：获取登录跳转地址
    url_token = "https://m.cloud.189.cn/udb/udb_login.jsp?pageId=1&pageKey=default&clientType=wap&redirectURL=https://m.cloud.189.cn/zhuanti/2021/shakeLottery/index.html"
    r = s.get(url_token, timeout=15)
    match = re.search(r"https?://[^\s'\"]+", r.text)
    if not match:
        raise Exception("获取登录页面失败")
    url = match.group()

    r = s.get(url, timeout=15)
    match = re.search(r'<a id="j-tab-login-link"[^>]*href="([^"]+)"', r.text)
    if not match:
        raise Exception("获取登录链接失败")
    href = match.group(1)

    r = s.get(href, timeout=15)
    captcha_token = re.findall(r"captchaToken' value='(.+?)'", r.text)[0]
    lt = re.findall(r'lt = "(.+?)"', r.text)[0]
    return_url = re.findall(r"returnUrl= '(.+?)'", r.text)[0]
    param_id = re.findall(r'paramId = "(.+?)"', r.text)[0]
    j_rsakey = re.findall(r'j_rsaKey" value="(\S+)"', r.text, re.M)[0]

    s.headers.update({"lt": lt})

    # RSA 加密
    enc_uname = rsa_encode(j_rsakey, uname)
    enc_pwd = rsa_encode(j_rsakey, pwd)

    # 提交登录
    login_url = "https://open.e.189.cn/api/logbox/oauth2/loginSubmit.do"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:74.0) Gecko/20100101 Firefox/76.0",
        "Referer": "https://open.e.189.cn/",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "appKey": "cloud",
        "accountType": "01",
        "userName": f"{{RSA}}{enc_uname}",
        "password": f"{{RSA}}{enc_pwd}",
        "validateCode": "",
        "captchaToken": captcha_token,
        "returnUrl": return_url,
        "mailSuffix": "@189.cn",
        "paramId": param_id,
        "dynamicCheck": "FALSE"
    }
    r = s.post(login_url, data=data, headers=headers, timeout=15)
    resp_json = r.json()
    if resp_json.get("result") != 0:
        raise Exception(f"登录失败: {resp_json.get('msg', '未知错误')}")

    # 登录成功跳转
    redirect_url = resp_json.get("toUrl")
    if redirect_url:
        s.get(redirect_url, timeout=15)
    return s

# ==================== 主流程 ====================
try:
    session = login(username, password)
    print("✅ 登录成功")

    # 签到
    timestamp = str(round(time.time() * 1000))
    sign_url = f"https://api.cloud.189.cn/mkt/userSign.action?rand={timestamp}&clientType=TELEANDROID&version=8.6.3&model=SM-G930K"
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 5.1.1; SM-G930K Build/NRD90M; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/74.0.3729.136 Mobile Safari/537.36 Ecloud/8.6.3 Android/22 clientId/355325117317828 clientModel/SM-G930K imsi/460071114317824 clientChannelId/qq proVersion/1.0.6",
        "Referer": "https://m.cloud.189.cn/zhuanti/2016/sign/index.jsp?albumBackupOpened=1",
        "Host": "m.cloud.189.cn"
    }

    resp_sign = session.get(sign_url, headers=headers, timeout=15)
    data_sign = resp_sign.json()
    netdisk_bonus = data_sign.get("netdiskBonus", 0)
    is_sign = data_sign.get("isSign", 0)

    if str(is_sign) == "1":
        sign_result = "今日已签到"
        notify_flag = False
    else:
        sign_result = f"✅ 签到成功，获得 {netdisk_bonus}M 空间"
        notify_flag = True

    print(f"📢 签到结果: {sign_result}")

    # 抽奖1 + 抽奖2
    draw_headers = headers.copy()
    draw1 = session.get("https://m.cloud.189.cn/v2/drawPrizeMarketDetails.action?taskId=TASK_SIGNIN&activityId=ACT_SIGNIN", headers=draw_headers, timeout=15)
    draw2 = session.get("https://m.cloud.189.cn/v2/drawPrizeMarketDetails.action?taskId=TASK_SIGNIN_PHOTOS&activityId=ACT_SIGNIN", headers=draw_headers, timeout=15)

    prize1 = draw1.json().get("prizeName", "无奖品") if draw1.ok else "抽奖失败"
    prize2 = draw2.json().get("prizeName", "无奖品") if draw2.ok else "抽奖失败"

    result_msg = f"{sign_result}\n第一次抽奖: {prize1}\n第二次抽奖: {prize2}"
    print(result_msg)

    # ==================== 通知 ====================
    if notify_flag and send:
        title = "✅ 天翼云盘签到成功" if "签到成功" in sign_result else "❌ 天翼云盘签到失败"
        send(title, result_msg)
        print("📨 已推送通知")
    elif not notify_flag:
        print("ℹ️ 今日已签到，无需通知")

except Exception as e:
    error_msg = f"❌ 执行异常: {str(e)}"
    print(error_msg)
    if send:
        send("天翼云盘签到", error_msg)

print("【天翼云盘签到】执行完毕")
