# cron: * * * * *
# new Env('TestFilght库存监控')

import os
import requests
import json
import sys
import time

# ==================== 青龙 notify 路径兼容 ====================
ql_dir = os.getenv('QL_DIR', '/ql')
for path in [f'{ql_dir}/scripts', f'{ql_dir}', '/ql/scripts']:
    if os.path.exists(path):
        sys.path.append(path)
        break

try:
    from notify import send
except ImportError:
    print("⚠️ 无法导入notify模块，请确保notify.py存在于/scripts目录")
    def send(title, content):
        print(f"【通知模拟】{title}\n{content}")

# ==================== 环境变量 ====================
TESTFLIGHT_URLS = os.getenv('TESTFLIGHT_URLS', '')

if not TESTFLIGHT_URLS:
    print("❌ 未设置环境变量 TESTFLIGHT_URLS，请在青龙环境变量中添加")
    send("TestFilght库存监控", "❌ 未设置环境变量 TESTFLIGHT_URLS，请检查配置")
    sys.exit(1)

# 解析链接
urls = []
for line in TESTFLIGHT_URLS.replace('&', '\n').splitlines():
    line = line.strip()
    if line:
        if not line.startswith('http'):
            line = f'https://testflight.apple.com/join/{line}'
        urls.append(line)

# 更真实的 iOS 请求头（防限流）
headers = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

STATE_FILE = 'testflight_state.json'

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ==================== 带重试的请求函数 ====================
def get_with_retry(url, max_retries=3, timeout=30):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            r.encoding = 'utf-8'
            return r
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt  # 指数退避
            print(f"⚠️ 第 {attempt+1} 次请求失败: {e}，{wait}秒后重试...")
            time.sleep(wait)
    return None

previous_state = load_state()
current_state = {}
notify_msg = ""

print("🚀 开始执行 TestFilght 库存监控...")

for url in urls:
    code = url.split('/')[-1]
    try:
        r = get_with_retry(url)
        if r is None:
            raise Exception("重试后仍超时")

        html = r.text.lower()

        # 智能提取 App 名称
        app_name = "未知App"
        if '<title>' in r.text:
            title_part = r.text.split('<title>')[1].split('</title>')[0].strip()
            app_name = title_part.replace(' - TestFlight - Apple', '').replace('Join the ', '').replace('Beta', '').strip()

        # 已满关键词（已覆盖你遇到的所有提示）
        full_keywords = [
            'this beta is full',
            "this beta isn't accepting any new testers right now",
            '此测试版已满',
            '此测试版目前不接受任何新测试者',
            '该测试版已满',
            '此 beta 版已满',
            '此 beta 版本的测试员已满',
            '此beta版本的测试员已满',
            '测试员已满',
            'beta版本的测试员已满',
            '测试名额已满',
            '此 beta 已满'
        ]
        is_full = any(kw in html for kw in full_keywords)

        status = "已满" if is_full else "✅ 有库存！可立即加入"
        current_state[code] = not is_full

        print(f"📌 {app_name} ({code}): {status}")

        # 仅【从已满变为有库存】时通知
        prev_available = previous_state.get(code, False)
        if not is_full and not prev_available:
            notify_msg += f"🚨 【{app_name}】TestFlight 有库存啦！\n🔗 {url}\n\n"

    except Exception as e:
        print(f"❌ 检查 {code} 失败: {e}")
        current_state[code] = False

save_state(current_state)

if notify_msg:
    send("TestFilght库存提醒", notify_msg + f"检测时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("✅ 已发送库存可用通知！")
else:
    print("📭 本次无新库存开放（或状态无变化）")

print("🎉 TestFilght库存监控任务执行完成")
