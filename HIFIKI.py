# cron: 0 10 * * *
# new Env('HIFIKI签到')

import os
import re
import time
import random
import requests

def main():
    # 获取环境变量
    cookie_env = os.environ.get('HIFIKI_COOKIE', '').strip()
    if not cookie_env:
        print('❌ 未设置环境变量 HIFIKI_COOKIE，请在青龙面板添加后重试')
        return

    # 支持多账号（用 & 分隔，青龙面板常用方式）
    cookies = [ck.strip() for ck in cookie_env.split('&') if ck.strip()]
    if not cookies:
        print('❌ HIFIKI_COOKIE 为空或格式错误')
        return

    # 随机延迟配置（可选）
    random_signin = os.environ.get('RANDOM_SIGNIN', 'false').lower() == 'true'
    try:
        max_delay = int(os.environ.get('MAX_RANDOM_DELAY', '3600'))
        if max_delay < 1:
            max_delay = 3600
    except:
        max_delay = 3600

    if random_signin and max_delay > 0:
        delay = random.randint(1, max_delay)
        print(f'⏳ 随机延迟 {delay} 秒后开始执行...')
        # 倒计时显示：剩余多少分钟多少秒（符合用户要求）
        for remaining in range(delay, 0, -1):
            minutes = remaining // 60
            seconds = remaining % 60
            if minutes > 0:
                print(f'\r⏰ 剩余 {minutes}分钟 {seconds}秒', end='', flush=True)
            else:
                print(f'\r⏰ 剩余 {seconds}秒', end='', flush=True)
            time.sleep(1)
        print('\n🚀 延迟结束，开始执行签到...')
    else:
        print('🚀 随机延迟未启用，直接开始签到...')

    url = "https://www.hifiki.com/sg_sign.htm"
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

    for idx, cookie in enumerate(cookies, 1):
        print(f'\n=== 开始签到 账号 {idx}/{len(cookies)} ===')

        # ==================== 第一步：GET 获取 sign ====================
        headers_get = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "max-age=0",
            "Referer": "https://www.hifiki.com/sg_sign.htm",
            "Cookie": cookie,
        }

        try:
            resp_get = requests.get(url, headers=headers_get, timeout=15, allow_redirects=True)
            resp_get.raise_for_status()
        except Exception as e:
            print(f'❌ GET 请求失败: {e}')
            continue

        # 提取 sign（精确匹配 HAR 中的正则）
        sign_match = re.search(r'var sign = "(.+?)"', resp_get.text)
        if not sign_match:
            print('❌ 未找到 sign 值，可能是 Cookie 失效或页面变化')
            print('页面预览（前300字符）:', resp_get.text[:300])
            continue

        sign = sign_match.group(1)
        print(f'✅ 获取 sign 成功: {sign[:40]}...')

        # ==================== 第二步：POST 提交签到 ====================
        headers_post = {
            "User-Agent": ua,
            "Accept": "text/plain, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://www.hifiki.com",
            "Referer": "https://www.hifiki.com/sg_sign.htm",
            "X-Requested-With": "XMLHttpRequest",
            "Cookie": cookie,
        }

        data = {"sign": sign}

        try:
            resp_post = requests.post(url, headers=headers_post, data=data, timeout=15)
            resp_post.raise_for_status()
        except Exception as e:
            print(f'❌ POST 请求失败: {e}')
            continue

        # 提取返回消息（匹配 HAR 中的正则）
        msg_match = re.search(r'"message":\s*"([^"]+)"', resp_post.text)
        if msg_match:
            message = msg_match.group(1)
            print(f'🎉 签到结果: {message}')
        else:
            print('⚠️ 签到完成，但未解析到 message')
            print('响应内容:', resp_post.text[:300])

    print('\n✅ 所有账号 HIFIKI 签到任务执行完毕！')


if __name__ == '__main__':
    main()
