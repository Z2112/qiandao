# cron: 0 10 * * *
# new Env('Hassbian签到')

import os
import time
import random
import requests
import re
import sys

def main():
    print("=== 🌟 Hassbian论坛自动签到 开始 ===")
    
    # 获取环境变量
    cookie_str = os.getenv('HASSBIAN_COOKIE')
    if not cookie_str:
        print("❌ 未找到 HASSBIAN_COOKIE 环境变量，请先在青龙面板中添加！")
        sys.exit(1)
    
    # ==================== 随机延迟配置 ====================
    random_signin = os.getenv('RANDOM_SIGNIN', 'false').lower() in ['true', '1', 'yes', 'on']
    max_delay_str = os.getenv('MAX_RANDOM_DELAY', '3600')
    try:
        max_delay = int(max_delay_str)
        if max_delay < 1:
            max_delay = 3600
    except ValueError:
        max_delay = 3600
    
    if random_signin and max_delay > 0:
        delay = random.randint(1, max_delay)
        print(f"⏰ 已开启随机延迟，计划等待 {delay} 秒后开始执行")
        
        # 实时显示“剩余多少分钟多少秒”
        for remaining in range(delay, 0, -1):
            mins = remaining // 60
            secs = remaining % 60
            print(f"\r⏳ 等待 {mins} 分 {secs} 秒后开始执行", end="", flush=True)
            time.sleep(1)
        print("\n🚀 延迟结束，开始执行签到...")
    else:
        print("🚀 随机延迟未开启，立即开始执行签到...")
    
    # ==================== 请求准备 ====================
    session = requests.Session()
    
    # 通用 headers（复刻 HAR 中的请求头）
    base_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:85.0) Gecko/20100101 Firefox/85.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    }
    
    # 将 Cookie 字符串转为 dict（更稳定）
    cookies = {}
    for item in cookie_str.split(';'):
        item = item.strip()
        if '=' in item:
            k, v = item.split('=', 1)
            cookies[k.strip()] = v.strip()
    
    # ==================== Step 1: 每日登录 - 访问首页 ====================
    print("📍 Step 1: 访问论坛首页（每日登录）...")
    try:
        headers1 = base_headers.copy()
        headers1.update({
            "Referer": "https://bbs.hassbian.com",
            "Upgrade-Insecure-Requests": "1",
        })
        
        r1 = session.get(
            "https://bbs.hassbian.com/",
            headers=headers1,
            cookies=cookies,
            timeout=20
        )
        
        if r1.status_code == 200:
            print("✅ 首页访问成功")
        else:
            print(f"⚠️ 首页返回状态码: {r1.status_code}")
    except Exception as e:
        print(f"❌ 首页请求异常: {e}")
    
    # ==================== Step 2: 获取积分 ====================
    print("📊 Step 2: 获取当前积分...")
    try:
        headers2 = base_headers.copy()
        headers2.update({
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://bbs.hassbian.com/home.php?mod=spacecp&ac=credit&showcredit=1",
        })
        
        r2 = session.get(
            "https://bbs.hassbian.com/?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu",
            headers=headers2,
            cookies=cookies,
            timeout=15
        )
        
        if r2.status_code == 200:
            # 提取积分（与 HAR 中的正则完全一致）
            match = re.search(r'<span id="hcredit_2">(.+?)</span>', r2.text, re.DOTALL)
            if match:
                points = match.group(1).replace('\xa0', ' ').strip()  # 处理 HAR 中替换的非断行空格
                print(f"🎉 签到完成！当前积分: {points}")
            else:
                print("⚠️ 未匹配到积分信息（可能需要手动登录确认）")
                print("响应预览:", r2.text[:300])
        else:
            print(f"❌ 获取积分失败，状态码: {r2.status_code}")
    except Exception as e:
        print(f"❌ 获取积分请求异常: {e}")
    
    print("=== ✅ Hassbian签到任务执行完毕 ===")

if __name__ == "__main__":
    main()
