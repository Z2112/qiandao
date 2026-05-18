# -*- coding: utf-8 -*-
"""
青龙面板 - JKForum 智能版（自动判断任务状态）
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
    """获取每日任务列表及完成状态"""
    url = "https://jkforum.net/api/jkf-dailyTask-api/v1/DailyTask"
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("content", {}).get("tasks", [])
        return []
    except:
        return []


def do_sign_in(cookies):
    print("\n[1] 执行每日签到")
    url = "https://jkforum.net/api/jkf-dailysign/v1/DailySign"
    payload = {"moodStickerId": random.randint(1, 9), "message": "签到"}
    try:
        resp = requests.put(url, headers=HEADERS, cookies=cookies, json=payload, timeout=15)
        if resp.status_code == 204:
            print("    ✅ 签到成功")
            return True
        elif resp.status_code == 406:
            print("    ✅ 今天已签到（跳过）")
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
    """浏览文章 + 点赞文章 + 点赞留言"""
    print("\n[2] 执行浏览文章 + 点赞任务")
    board_id = random.choice(VIEW_BOARDS)
    articles = get_article_list(cookies, board_id=board_id, limit=40)

    if not articles:
        print("    ❌ 获取文章列表失败")
        return False

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

        # 30-60秒随机延迟
        if idx < 30:
            delay = random.randint(30, 60)
            print(f"    已处理 {idx}/30，等待 {delay} 秒...")
            time.sleep(delay)

    # 点赞留言
    for article in random.sample(articles, min(5, len(articles))):
        comments = get_comments(cookies, article.get("id"), limit=6)
        for comment in comments[:2]:
            if liked_comment < 5 and like_comment(cookies, board_id, comment.get("id")):
                liked_comment += 1

    print(f"    ✅ 浏览 {viewed} 篇，点赞文章 {liked_article} 篇，点赞留言 {liked_comment} 则")
    return True


def browse_specific_boards(cookies):
    print("\n[3] 执行逛逛特定版區")
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
    print("\n[4] 领取每日任务总奖励")
    url = "https://jkforum.net/api/jkf-dailyTask-api/v1/DailyStage"
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=15)
        if resp.status_code != 200:
            print("    ❌ 获取总奖励失败")
            return

        stages = resp.json().get("content", {}).get("stages", [])
        claimed = 0
        for stage in stages:
            if not stage.get("isCompleted"):
                stage_id = stage.get("id")
                complete_url = "https://jkforum.net/api/jkf-dailyTask-api/v1/DailyStage/CompleteStage"
                try:
                    r = requests.post(complete_url, headers=HEADERS, cookies=cookies, 
                                    json={"stageId": stage_id}, timeout=15)
                    if r.status_code in [200, 201]:
                        claimed += 1
                        print(f"    ✅ 已领取阶段奖励 (ID: {stage_id})")
                except:
                    pass
        print(f"    共领取 {claimed} 个总奖励阶段")
    except Exception as e:
        print(f"    ❌ 领取总奖励异常: {e}")


def jkforum_main():
    print("=" * 60)
    print(f"JKForum 智能脚本启动 - {datetime.now()}")
    print("=" * 60)

    if not JKFORUM_COOKIE:
        print("❌ 未设置 JKFORUM_COOKIE")
        return

    cookies = {k.strip(): v.strip() for k, v in 
               (item.split("=", 1) for item in JKFORUM_COOKIE.split(";") if "=" in item)}

    # 获取当前任务状态
    tasks = get_daily_tasks(cookies)
    task_status = {t["name"]: t.get("isCompleted", False) for t in tasks}

    print("\n当前任务状态：")
    for name, completed in task_status.items():
        status = "✅ 已完成" if completed else "❌ 未完成"
        print(f"  {name}: {status}")

    # 1. 每日签到（如果未完成）
    if not task_status.get("進行每日簽到", False):
        do_sign_in(cookies)
    else:
        print("\n[1] 每日签到已完成，跳过")

    # 2+3. 浏览 + 点赞（如果相关任务未完成）
    need_browse = not task_status.get("觀看任30篇文章", True) or \
                  not task_status.get("對三篇文章點讚", True) or \
                  not task_status.get("對三則留言點讚", True)

    if need_browse:
        do_browse_and_like_tasks(cookies)
    else:
        print("\n[2] 浏览和点赞任务已完成，跳过")

    # 4+5. 逛逛特定版區
    if not task_status.get("逛逛版區-女神焦點", False) or not task_status.get("逛逛版區-IG推特美女", False):
        browse_specific_boards(cookies)
    else:
        print("\n[3] 逛逛版區任务已完成，跳过")

    # 6. 领取总奖励
    claim_daily_stage_rewards(cookies)

    # 获取资产并推送
    user_info = get_user_info(cookies)
    if user_info and "content" in user_info:
        content = user_info["content"]
        wallet = content.get("wallet", {}).get("credits", [])
        current_assets = {TRACK_KEYS.get(item["id"], str(item["id"])): item.get("point", 0) 
                          for item in wallet if item.get("id") in TRACK_KEYS}

        last_assets = load_last_data()
        change_lines = []
        if last_assets:
            for name, current in current_assets.items():
                last = last_assets.get(name, current)
                diff = current - last
                if diff != 0:
                    change_lines.append(f"{name}: {'+' if diff > 0 else ''}{diff}")

        change_text = "\n".join(change_lines) if change_lines else "无变化"
        save_current_data(current_assets)

        output = f"""任务执行完成

【当前资产】
金币: {current_assets.get('金币', 0)}
宝石: {current_assets.get('宝石', 0)}
名声: {current_assets.get('名声', 0)}
体力: {current_assets.get('体力', 0)}

【资产变化】
{change_text}"""

        print("\n" + output)
        title = f"JKForum 签到 | {datetime.now().strftime('%m-%d %H:%M')}"
        send(title, output)


if __name__ == "__main__":
    jkforum_main()
