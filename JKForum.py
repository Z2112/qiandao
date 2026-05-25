# -*- coding: utf-8 -*-
# cron: 0 10 * * *
# new Env('JKForum签到')

"""
================================================================================
青龙面板 - JKForum 签到脚本 (v2.5 详细日志版 - 通知仅限总奖励)
================================================================================

【通知规则】
• 仅当「领取每日任务总奖励」成功或失败时发送通知
• 其他操作（签到、浏览、点赞等）不推送
"""

import os
import json
import random
import time
import base64
import requests
from datetime import datetime, timezone

try:
    from sendNotify import send
except ImportError:
    send = lambda t, c: print("推送未启用")

JKFORUM_COOKIE = os.environ.get("JKFORUM_COOKIE", "")
RANDOM_SIGNIN = os.environ.get("RANDOM_SIGNIN", "false").lower() == "true"
MAX_RANDOM_DELAY = int(os.environ.get("MAX_RANDOM_DELAY", 3600))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Origin": "https://jkforum.net",
    "Referer": "https://jkforum.net/",
}

TRACK_KEYS = {1: "名声", 2: "金币", 5: "宝石", 7: "体力"}


def random_delay_if_enabled():
    if RANDOM_SIGNIN:
        delay = random.randint(1, MAX_RANDOM_DELAY)
        print(f"\n[随机延迟] 等待 {delay} 秒后执行...")
        time.sleep(delay)


def parse_multi_cookies(cookie_env):
    if not cookie_env or not cookie_env.strip():
        return []
    return [c.strip() for c in cookie_env.replace('\n', '&').split('&') if c.strip()]


def parse_cookie_string(cookie_str):
    if not cookie_str:
        return {}
    return {k.strip(): v.strip() for k, v in (item.split("=", 1) for item in cookie_str.split(";") if "=" in item)}


def get_member_id_from_jwt(cookies):
    for key in ['ap-pot', 'jkf-ap-pot']:
        token = cookies.get(key)
        if token and '.' in token:
            try:
                payload = json.loads(base64.urlsafe_b64decode(token.split('.')[1] + '=='))
                if 'uid' in payload:
                    return int(payload['uid'])
            except:
                pass
    return None


def clear_all_notifications(cookies):
    print("\n[步骤] 开始清理通知")
    member_id = get_member_id_from_jwt(cookies)
    if not member_id:
        return
    try:
        requests.put("https://jkforum.net/api/jkf-member-inbox/v1/Message",
                     headers=HEADERS, cookies=cookies, json={"memberId": member_id, "status": 3}, timeout=15)
        print("    ✅ 通知清理成功")
    except:
        pass


def get_user_info(cookies):
    try:
        resp = requests.get("https://jkforum.net/api/legoin/v1/SignInInformation", headers=HEADERS, cookies=cookies, timeout=15)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None


def get_current_assets(cookies):
    user_info = get_user_info(cookies)
    if not user_info or "content" not in user_info:
        return {}
    wallet = user_info["content"].get("wallet", {}).get("credits", [])
    return {TRACK_KEYS.get(item["id"], str(item["id"])): item.get("point", 0)
            for item in wallet if item.get("id") in TRACK_KEYS}


def get_daily_tasks(cookies):
    try:
        resp = requests.get("https://jkforum.net/api/jkf-dailyTask-api/v1/DailyTask", headers=HEADERS, cookies=cookies, timeout=15)
        return resp.json().get("content", {}).get("tasks", []) if resp.status_code == 200 else []
    except:
        return []


def get_task_progress(task):
    details = task.get("details", [])
    if not details:
        return 0, 1
    d = details[0]
    return d.get("progressScore", 0), d.get("goalScore", 1)


def should_perform_task(task):
    if task.get("isCompleted"):
        return False
    current, goal = get_task_progress(task)
    return "claim_only" if current >= goal else True


def do_sign_in(cookies):
    print("\n[步骤] 执行每日签到")
    try:
        resp = requests.put("https://jkforum.net/api/jkf-dailysign/v1/DailySign",
                            headers=HEADERS, cookies=cookies,
                            json={"moodStickerId": random.randint(1, 9), "message": "签到"}, timeout=15)
        if resp.status_code == 204:
            print("    ✅ 签到成功")
            return "success"
        elif resp.status_code == 406:
            print("    ✅ 今天已签到")
            return "already_signed"
        return "failed"
    except:
        return "failed"


def get_article_list(cookies, board_id, limit=40):
    try:
        resp = requests.get(f"https://jkforum.net/api/jkf-forum/v1/Article/{board_id}",
                            headers=HEADERS, cookies=cookies,
                            params={"tab": 0, "Offset": 0, "Limit": limit}, timeout=15)
        return resp.json().get("content", {}).get("articles", []) if resp.status_code == 200 else []
    except:
        return []


def get_article_detail(cookies, article_id):
    try:
        return requests.get(f"https://jkforum.net/api/jkf-forum/v1/ArticleThread/{article_id}",
                            headers=HEADERS, cookies=cookies, timeout=15).status_code == 200
    except:
        return False


def like_article(cookies, board_id, article_id):
    try:
        return requests.put(f"https://jkforum.net/api/jkf-forum/v1/ArticleLike/{board_id}/{article_id}",
                            headers=HEADERS, cookies=cookies, timeout=15).status_code == 204
    except:
        return False


def get_comments(cookies, article_id, limit=6):
    try:
        resp = requests.get(f"https://jkforum.net/api/jkf-forum/v1/CommentThread/{article_id}",
                            headers=HEADERS, cookies=cookies,
                            params={"authorOnly": "false", "sortingType": 1, "Limit": limit}, timeout=15)
        return resp.json().get("content", []) if resp.status_code == 200 else []
    except:
        return []


def like_comment(cookies, board_id, comment_id):
    try:
        return requests.put(f"https://jkforum.net/api/jkf-forum/v1/CommentLike/{board_id}/{comment_id}",
                            headers=HEADERS, cookies=cookies, timeout=15).status_code == 204
    except:
        return False


def do_browse_and_like_tasks(cookies, browse_count=0, like_article_count=3, like_comment_count=3):
    print(f"\n[步骤] 执行浏览+点赞任务")
    board_id = random.choice([141, 555, 374, 382, 246])
    articles = get_article_list(cookies, board_id, 40)
    if not articles:
        return

    viewed = liked_a = liked_c = 0
    for idx, article in enumerate(articles[:browse_count], 1):
        if get_article_detail(cookies, article.get("id")):
            viewed += 1
        if idx < browse_count:
            time.sleep(random.randint(2, 3))

    for article in random.sample(articles, min(10, len(articles))):
        if liked_a < like_article_count and like_article(cookies, board_id, article.get("id")):
            liked_a += 1

    for article in random.sample(articles, min(8, len(articles))):
        for comment in get_comments(cookies, article.get("id"), 4)[:2]:
            if liked_c < like_comment_count and like_comment(cookies, board_id, comment.get("id")):
                liked_c += 1

    print(f"    ✅ 浏览 {viewed} 篇，点赞文章 {liked_a} 篇，点赞留言 {liked_c} 则")


def browse_specific_boards(cookies):
    print("\n[步骤] 执行逛逛特定版區")
    for board_id, name in [(481, "女神焦點"), (520, "IG推特美女")]:
        try:
            resp = requests.get(f"https://jkforum.net/api/jkf-forum/v1/Board/{board_id}", headers=HEADERS, cookies=cookies, timeout=15)
            if resp.status_code == 200:
                print(f"    ✅ 已浏览 {name}")
        except:
            pass


def claim_daily_stage_rewards(cookies):
    print("\n[步骤] 开始领取每日任务总奖励")
    try:
        stages = get_daily_stages(cookies).get("stages", [])
        uncompleted = [s for s in stages if not s.get("isCompleted")]

        if not uncompleted:
            print("    ✅ 总奖励已全部领取")
            return "skipped"

        print(f"    发现 {len(uncompleted)} 个未领取的总奖励阶段")
        success_count = 0
        for stage in uncompleted:
            stage_id = stage.get("id")
            print(f"    正在尝试领取 stageId={stage_id}")
            resp = requests.post("https://jkforum.net/api/jkf-dailyTask-api/v1/DailyStage/CompleteStage",
                                 headers=HEADERS, cookies=cookies, json={"stageId": stage_id}, timeout=15)
            if resp.status_code in [200, 201]:
                print(f"    ✅ 领取成功")
                success_count += 1
            else:
                print(f"    ❌ 领取失败 (状态码: {resp.status_code})")

        return "success" if success_count > 0 else "failed"
    except Exception as e:
        print(f"    ❌ 领取总奖励异常: {e}")
        return "failed"


def get_daily_stages(cookies):
    try:
        resp = requests.get("https://jkforum.net/api/jkf-dailyTask-api/v1/DailyStage", headers=HEADERS, cookies=cookies, timeout=15)
        return resp.json().get("content", {}) if resp.status_code == 200 else {}
    except:
        return {}


def complete_task(cookies, task_id):
    try:
        resp = requests.post("https://jkforum.net/api/jkf-dailyTask-api/v1/DailyTask/CompleteTask",
                             headers=HEADERS, cookies=cookies, json={"taskId": task_id}, timeout=15)
        return resp.status_code == 200 and resp.json().get("code") == "200000"
    except:
        return False


def process_account(cookies, account_num, total_accounts):
    print(f"\n{'='*65}")
    print(f"🚀 处理账号 {account_num}/{total_accounts}")
    print(f"{'='*65}")

    before_assets = get_current_assets(cookies)
    tasks = get_daily_tasks(cookies)

    print("\n[步骤] 获取当前每日任务状态")
    for t in tasks:
        current, goal = get_task_progress(t)
        status = "✅ 已完成" if t.get("isCompleted") else f"❌ {current}/{goal}"
        print(f"  {t['name']:<22} {status}")

    signin_status = None
    need_like_article = need_like_comment = 0
    need_browse_boards = False
    stage_claim_result = "skipped"

    if not any(not t.get("isCompleted") for t in tasks):
        print("\n[结果] 所有任务已完成")
    else:
        print("\n[步骤] 开始处理未完成任务")

        if any(t["name"] == "進行每日簽到" and not t.get("isCompleted") for t in tasks):
            signin_status = do_sign_in(cookies)

        for task in tasks:
            if task.get("isCompleted"):
                continue

            current, goal = get_task_progress(task)
            name = task["name"]
            remaining = goal - current
            action = should_perform_task(task)

            print(f"\n[任务处理] {name} | 当前进度: {current}/{goal} | 剩余: {remaining}")

            if action == "claim_only":
                complete_task(cookies, task["id"])
                print(f"    → 进度已达标，直接领取")
            else:
                if name == "觀看任30篇文章":
                    do_browse_and_like_tasks(cookies, browse_count=remaining)
                elif name == "對三篇文章點讚":
                    need_like_article = remaining
                elif name == "對三則留言點讚":
                    need_like_comment = remaining
                elif "逛逛版區" in name:
                    need_browse_boards = True

        if need_like_article > 0 or need_like_comment > 0:
            do_browse_and_like_tasks(cookies, like_article_count=need_like_article, like_comment_count=need_like_comment)

        if need_browse_boards:
            browse_specific_boards(cookies)

        print("\n[步骤] 刷新任务状态并领取奖励")
        tasks = get_daily_tasks(cookies)
        for task in tasks:
            if not task.get("isCompleted") and should_perform_task(task) == "claim_only":
                if complete_task(cookies, task["id"]):
                    print(f"    ✅ 已领取: {task['name']}")

    # 领取总奖励（这里决定是否通知）
    stage_claim_result = claim_daily_stage_rewards(cookies)
    clear_all_notifications(cookies)

    after_assets = get_current_assets(cookies)
    increase = [f"{name} +{after_assets.get(name, 0) - before_assets.get(name, 0)}"
                for name in TRACK_KEYS.values()
                if after_assets.get(name, 0) - before_assets.get(name, 0) != 0]

    print(f"\n【本次运行资产变化】 {' | '.join(increase) if increase else '无变化'}")
    print(f"【当前总资产】金币: {after_assets.get('金币', 0)}  宝石: {after_assets.get('宝石', 0)}")

    return {
        "account_num": account_num,
        "stage_claim_result": stage_claim_result,   # 用于通知判断
        "current_assets": after_assets,
        "increase_text": " | ".join(increase) if increase else "无变化"
    }


def jkforum_main():
    print("\n" + "="*65)
    print(f"🚀 JKForum 签到脚本 v2.5 启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*65)

    random_delay_if_enabled()

    if not JKFORUM_COOKIE:
        print("❌ 未设置 JKFORUM_COOKIE")
        return

    results = []
    for idx, cookie_str in enumerate(parse_multi_cookies(JKFORUM_COOKIE), 1):
        cookies = parse_cookie_string(cookie_str)
        if cookies:
            results.append(process_account(cookies, idx, len(parse_multi_cookies(JKFORUM_COOKIE))))

    # ========== 仅在总奖励领取成功或失败时推送通知 ==========
    notify_list = [r for r in results if r["stage_claim_result"] in ["success", "failed"]]

    if notify_list:
        print(f"\n📢 检测到 {len(notify_list)} 个账号的总奖励领取有结果，正在发送通知...")
        notify_lines = []
        for r in notify_list:
            status = "✅ 领取成功" if r["stage_claim_result"] == "success" else "❌ 领取失败"
            assets = r["current_assets"]
            line = (
                f"【账号 {r['account_num']}】 {status}\n"
                f"金币: {assets.get('金币', 0)}   宝石: {assets.get('宝石', 0)}\n"
                f"资产变化: {r.get('increase_text', '无变化')}"
            )
            notify_lines.append(line)

        notify_content = "\n\n" + "="*40 + "\n\n".join(notify_lines)
        title = f"JKForum 总奖励领取 | {datetime.now().strftime('%m-%d %H:%M')} ({len(notify_list)}账号)"
        send(title, notify_content)
        print("✅ 通知发送完成")
    else:
        print("\n✅ 没有需要推送的总奖励领取结果，本次不发送通知")

    print("\n" + "="*65)
    print("✅ 全部账号处理完毕，脚本结束")
    print("="*65 + "\n")


if __name__ == "__main__":
    jkforum_main()
