# -*- coding: utf-8 -*-
# cron: 0 10 * * *

"""
青龙面板 - JKForum 最终智能版（支持随机延迟）
环境变量：
  RANDOM_SIGNIN=true          # 是否启用随机延迟
  MAX_RANDOM_DELAY=3600       # 最大随机延迟秒数（默认3600秒）
"""

import os
import json
import random
import time
import requests
from datetime import datetime

try:
    from sendNotify import send
except ImportError:
    send = lambda t, c: print("推送未启用")

JKFORUM_COOKIE = os.environ.get("JKFORUM_COOKIE", "")
DATA_FILE = "jkforum_data.json"

# ==================== 随机延迟配置 ====================
RANDOM_SIGNIN = os.environ.get("RANDOM_SIGNIN", "false").lower() == "true"
MAX_RANDOM_DELAY = int(os.environ.get("MAX_RANDOM_DELAY", 3600))

VIEW_BOARDS = [141, 555, 374, 382, 246]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Origin": "https://jkforum.net",
    "Referer": "https://jkforum.net/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

TRACK_KEYS = {
    1: "名声", 2: "金币", 5: "宝石", 7: "体力", 9: "总积分"
}


def random_delay_if_enabled():
    """根据环境变量决定是否执行随机延迟"""
    if RANDOM_SIGNIN:
        delay = random.randint(1, MAX_RANDOM_DELAY)
        minutes = delay // 60
        seconds = delay % 60
        
        print(f"\n[随机延迟] RANDOM_SIGNIN 已启用，剩余 {minutes} 分钟 {seconds} 秒后开始执行...")
        time.sleep(delay)
        print("    ✅ 延迟结束，开始执行任务\n")

def load_last_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_current_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user_info(cookies):
    url = "https://jkforum.net/api/legoin/v1/SignInInformation"
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=15)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None


def get_daily_tasks(cookies):
    url = "https://jkforum.net/api/jkf-dailyTask-api/v1/DailyTask"
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("content", {}).get("tasks", [])
        return []
    except:
        return []


def get_daily_stages(cookies):
    url = "https://jkforum.net/api/jkf-dailyTask-api/v1/DailyStage"
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("content", {})
        return {}
    except:
        return {}


def should_perform_task(task):
    if task.get("isCompleted"):
        return False
    details = task.get("details", [])
    if not details:
        return True
    detail = details[0]
    if detail.get("progressScore", 0) >= detail.get("goalScore", 0):
        return "claim_only"
    return True


def do_sign_in(cookies):
    print("\n[每日签到]")
    url = "https://jkforum.net/api/jkf-dailysign/v1/DailySign"
    payload = {"moodStickerId": random.randint(1, 9), "message": "签到"}
    try:
        resp = requests.put(url, headers=HEADERS, cookies=cookies, json=payload, timeout=15)
        if resp.status_code == 204:
            print("    ✅ 签到成功")
            return True
        elif resp.status_code == 406:
            print("    ✅ 今天已签到")
            return True
        else:
            print(f"    ⚠️ 签到异常: {resp.status_code}")
            return False
    except Exception as e:
        print(f"    ❌ 签到失败: {e}")
        return False


def get_article_list(cookies, board_id, limit=40):
    url = f"https://jkforum.net/api/jkf-forum/v1/Article/{board_id}"
    params = {"tab": 0, "isQueryPin": "true", "Offset": 0, "Limit": limit}
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("content", {}).get("articles", [])
        return []
    except:
        return []


def get_article_detail(cookies, article_id):
    url = f"https://jkforum.net/api/jkf-forum/v1/ArticleThread/{article_id}"
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=15)
        return resp.status_code == 200
    except:
        return False


def like_article(cookies, board_id, article_id):
    url = f"https://jkforum.net/api/jkf-forum/v1/ArticleLike/{board_id}/{article_id}"
    try:
        resp = requests.put(url, headers=HEADERS, cookies=cookies, timeout=15)
        return resp.status_code == 204
    except:
        return False


def get_comments(cookies, article_id, limit=8):
    url = f"https://jkforum.net/api/jkf-forum/v1/CommentThread/{article_id}"
    params = {"authorOnly": "false", "sortingType": 1, "Offset": 0, "Limit": limit}
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("content", [])
        return []
    except:
        return []


def like_comment(cookies, board_id, comment_id):
    url = f"https://jkforum.net/api/jkf-forum/v1/CommentLike/{board_id}/{comment_id}"
    try:
        resp = requests.put(url, headers=HEADERS, cookies=cookies, timeout=15)
        return resp.status_code == 204
    except:
        return False


def do_browse_and_like_tasks(cookies):
    print("\n[浏览 + 点赞任务]")
    board_id = random.choice(VIEW_BOARDS)
    articles = get_article_list(cookies, board_id=board_id, limit=40)

    if not articles:
        print("    ❌ 获取文章列表失败")
        return

    viewed = 0
    liked_article = 0
    liked_comment = 0

    for idx, article in enumerate(articles[:30], 1):
        article_id = article.get("id")
        if not article_id:
            continue

        if get_article_detail(cookies, article_id):
            viewed += 1

        if liked_article < 5 and like_article(cookies, board_id, article_id):
            liked_article += 1

        if idx < 30:
            delay = random.randint(30, 60)
            print(f"    已处理 {idx}/30，等待 {delay} 秒...")
            time.sleep(delay)

    for article in random.sample(articles, min(5, len(articles))):
        comments = get_comments(cookies, article.get("id"), limit=6)
        for comment in comments[:2]:
            if liked_comment < 5 and like_comment(cookies, board_id, comment.get("id")):
                liked_comment += 1

    print(f"    ✅ 浏览 {viewed} 篇，点赞文章 {liked_article} 篇，点赞留言 {liked_comment} 则")


def browse_specific_boards(cookies):
    print("\n[逛逛特定版區]")
    for board_id, name in [(481, "女神焦點"), (520, "IG推特美女")]:
        url = f"https://jkforum.net/api/jkf-forum/v1/Board/{board_id}"
        try:
            resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=15)
            if resp.status_code == 200:
                title = resp.json().get("content", {}).get("title", name)
                print(f"    ✅ 已浏览 {title}")
            else:
                print(f"    ❌ 浏览 {name} 失败")
        except Exception as e:
            print(f"    ❌ 浏览 {name} 异常: {e}")


def claim_daily_stage_rewards(cookies):
    print("\n[领取每日任务总奖励]")
    stage_data = get_daily_stages(cookies)
    stages = stage_data.get("stages", [])

    if not stages:
        print("    未获取到总奖励阶段")
        return

    uncompleted = [s for s in stages if not s.get("isCompleted", False)]

    if not uncompleted:
        print("    ✅ 总奖励已全部领取，跳过")
        return

    print(f"    发现 {len(uncompleted)} 个未领取的总奖励阶段")

    claimed = 0
    for stage in uncompleted:
        stage_id = stage.get("id")
        print(f"    尝试领取 stageId={stage_id}")
        if complete_daily_stage(cookies, stage_id):
            claimed += 1
            print(f"    ✅ 领取成功 stageId={stage_id}")
        else:
            print(f"    ❌ 领取失败 stageId={stage_id}")

    print(f"    本次共领取 {claimed} 个总奖励阶段")


def complete_daily_stage(cookies, stage_id):
    url = "https://jkforum.net/api/jkf-dailyTask-api/v1/DailyStage/CompleteStage"
    try:
        resp = requests.post(url, headers=HEADERS, cookies=cookies, 
                           json={"stageId": stage_id}, timeout=15)
        return resp.status_code in [200, 201]
    except:
        return False


def complete_task(cookies, task_id):
    url = "https://jkforum.net/api/jkf-dailyTask-api/v1/DailyTask/CompleteTask"
    try:
        resp = requests.post(url, headers=HEADERS, cookies=cookies, json={"taskId": task_id}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("code") == "200000"
        return False
    except:
        return False


def jkforum_main():
    print("\n" + "=" * 65)
    print(f"🚀 JKForum 智能脚本启动")
    print(f"⏰ 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    # 随机延迟（如果启用）
    random_delay_if_enabled()

    if not JKFORUM_COOKIE:
        print("❌ 未设置 JKFORUM_COOKIE 环境变量")
        return

    cookies = {k.strip(): v.strip() for k, v in 
               (item.split("=", 1) for item in JKFORUM_COOKIE.split(";") if "=" in item)}

    tasks = get_daily_tasks(cookies)
    task_status = {t["name"]: t.get("isCompleted", False) for t in tasks}
    incomplete_tasks = [name for name, completed in task_status.items() if not completed]

    print("\n📋 当前每日任务状态：")
    print("-" * 65)
    for name, completed in task_status.items():
        status = "✅ 已完成" if completed else "❌ 未完成"
        print(f"  {name:<22} {status}")
    print("-" * 65)

    if not incomplete_tasks:
        print("\n✅ 所有每日任务已完成，无需执行操作")
    else:
        print(f"\n🔄 发现 {len(incomplete_tasks)} 个未完成任务，开始执行...")

        # 每日签到
        if not task_status.get("進行每日簽到", False):
            do_sign_in(cookies)

        # 全任务进度判断
        need_browse_like = False

        for task in tasks:
            task_name = task["name"]
            action = should_perform_task(task)

            if action == "claim_only":
                complete_task(cookies, task["id"])
                print(f"    [{task_name}] 进度已达标，已调用完成接口")
            elif action is True:
                if task_name in ["觀看任30篇文章", "對三篇文章點讚", "對三則留言點讚"]:
                    need_browse_like = True

        if need_browse_like:
            do_browse_and_like_tasks(cookies)

        # 逛逛特定版區
        if (not task_status.get("逛逛版區-女神焦點", True) or
            not task_status.get("逛逛版區-IG推特美女", True)):
            browse_specific_boards(cookies)

    claim_daily_stage_rewards(cookies)

    # 获取资产
    user_info = get_user_info(cookies)
    current_assets = {}
    change_text = "无变化"

    if user_info and "content" in user_info:
        content = user_info["content"]
        wallet = content.get("wallet", {}).get("credits", [])
        current_assets = {TRACK_KEYS.get(item["id"], str(item["id"])): item.get("point", 0) 
                          for item in wallet if item.get("id") in TRACK_KEYS}

        last_assets = load_last_data()
        if last_assets:
            change_lines = []
            for name, current in current_assets.items():
                last = last_assets.get(name, current)
                diff = current - last
                if diff != 0:
                    change_lines.append(f"{name}: {'+' if diff > 0 else ''}{diff}")
            change_text = "\n".join(change_lines) if change_lines else "无变化"

        save_current_data(current_assets)

    print("\n" + "=" * 65)
    print("📊 执行结果汇总")
    print("=" * 65)
    print(f"""
【当前资产】
  金币   : {current_assets.get('金币', 0)}
  宝石   : {current_assets.get('宝石', 0)}
  名声   : {current_assets.get('名声', 0)}
  体力   : {current_assets.get('体力', 0)}

【资产变化】
{change_text if change_text != '无变化' else '  无变化'}
""")
    print("=" * 65)
    print("✅ 脚本执行完成")
    print("=" * 65 + "\n")

    output = f"""任务执行完成

【当前资产】
金币: {current_assets.get('金币', 0)}
宝石: {current_assets.get('宝石', 0)}
名声: {current_assets.get('名声', 0)}
体力: {current_assets.get('体力', 0)}

【资产变化】
{change_text}"""

    title = f"JKForum 签到 | {datetime.now().strftime('%m-%d %H:%M')}"
    send(title, output)


if __name__ == "__main__":
    jkforum_main()
