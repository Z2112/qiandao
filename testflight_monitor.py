# cron: * * * * *
# new Env('TestFilght库存监控')

import os
import requests
import json
import sys
import time

# ==================== 青龙 notify 路径兼容 ====================
ql_dir = os.getenv('QL_DIR', '/ql')
for path in [f'{ql_dir}/scripts'， f'{ql_dir}'， '/ql/scripts']:
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
# TESTFLIGHT_URLS 支持：
# 1. 完整链接（如 https://testflight.apple.com/join/ABC123）
# 2. 仅邀请码（如 ABC123）
# 多个用 & 或换行分隔
TESTFLIGHT_URLS = os.getenv('TESTFLIGHT_URLS', '')

if not TESTFLIGHT_URLS:
    print("❌ 未设置环境变量 TESTFLIGHT_URLS，请在青龙环境变量中添加")
    send("TestFilght库存监控", "❌ 未设置环境变量 TESTFLIGHT_URLS，请检查配置")
    sys.exit(1)

# 解析链接
urls = []
for line in TESTFLIGHT_URLS.替换('&', '\n')。splitlines():
    line = line.strip()
    if line:
        if not line.startswith('http'):
            line = f'https://testflight.apple.com/join/{line}'
        urls.append(line)

headers = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

STATE_FILE = 'testflight_state.json'

# 加载上次状态（避免每次有库存都重复通知）
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

previous_state = load_state()
current_state = {}
notify_msg = ""

print("🚀 开始执行 TestFilght 库存监控...")

for url in urls:
    code = url.split('/')[-1]
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = 'utf-8'
        html = r.text.lower()  # 转为小写方便匹配

        # 尝试提取 App 名称
        app_name = "未知App"
        if '<title>' in r.text:
            title_part = r.text.split('<title>')[1]。split('</title>')[0]
            app_name = title_part.替换(' - TestFlight - Apple', '')。替换('Join the ', '')。strip()

        # 已满关键词（中英文全覆盖）
        full_keywords = [
            'this beta is full',
            "this beta isn't accepting any new testers right now",
            '此测试版已满',
            '此测试版目前不接受任何新测试者',
            '该测试版已满',
            '此 beta 版已满'
        ]
        is_full = any(kw in html for kw in full_keywords)

        status = "已满" if is_full else "✅ 有库存！可立即加入"
        current_state[code] = not is_full

        print(f"📌 {app_name} ({code}): {status}")

        # 只有【从已满 → 有库存】时才触发通知
        prev_available = previous_state.get(code, False)
        if not is_full 和 not prev_available:
            notify_msg += f"🚨 【{app_name}】TestFlight 有库存啦！\n🔗 {url}\n\n"

    except Exception as e:
        print(f"❌ 检查 {code} 失败: {e}")
        current_state[code] = False

# 保存本次状态
save_state(current_state)

# 发送通知（仅在有新库存时推送）
if notify_msg:
    send("TestFilght库存提醒", notify_msg + f"检测时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("✅ 已发送库存可用通知！")
else:
    print("📭 本次无新库存开放（或状态无变化）")

print("🎉 TestFilght库存监控任务执行完成")
