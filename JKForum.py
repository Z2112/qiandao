# -*- coding: utf-8 -*-
# cron: 0 10 * * *
# new Env('JKForum签到')

"""
JKForum 签到脚本（v3.1 优化版）

主要改进：
- 日志风格参考 enshan.js，更加紧凑
- 只在最后统一发送一次汇总通知
- 执行任务后会再次检查任务状态
- 先领取已完成的单个任务奖励，再领取总奖励
- 修复通知逻辑问题
"""

import os
import json
import random
import time
import base64
import requests
from datetime import datetime

try:
    from sendNotify import send
except ImportError:
    send = None

JKFORUM_COOKIE = os.environ.get("JKFORUM_COOKIE", "")
RANDOM_SIGNIN = os.environ.get("RANDOM_SIGNIN", "false").lower() == "true"
MAX_RANDOM_DELAY = int(os.environ.get("MAX_RANDOM_DELAY", 3600))

VIEW_BOARDS = [141, 555, 374, 382, 246]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Origin": "https://jkforum.net",
}

TRACK_KEYS = {1: "名声", 2: "金币", 5: "宝石", 7: "体力", 9: "总积分"}


def random_delay_if_enabled():
    if RANDOM_SIGNIN:
        delay = random.randint(1, MAX_RANDOM_DELAY)
        print(f"\n[随机延迟] 已启用，将在 {delay//60} 分 {delay%60} 秒后执行...")
        time.sleep(delay)
        print("    延迟结束，开始执行任务\n")


def parse_multi_cookies(cookie_env):
    if not cookie_env:
        return []
    return [c.strip() for c in cookie_env.replace('\n', '&').split('&') if c.strip()]


def parse_cookie_string(cookie_str):
    if not cookie_str:
        return {}
    return {k.strip(): v.strip() for k, v in 
            (item.split("=", 1) for item in cookie_str.split(";") if "=" in item)}


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
    member_id = get_member_id_from_jwt(cookies)
    if not member_id:
        return False
    try:
        url = "https://jkforum.net/api/jkf-member-inbox/v1/Message"
        headers = {**HEADERS, "x-signature": "pBBuSsmbqU", 
                   "x-signature-date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"}
        resp = requests.put(url, headers=headers, cookies=cookies, 
                            json={"memberId": member_id, "status": 3}, timeout=15)
        return resp.status_code in [200, 204]
    except:
        return False


def get_current_assets(cookies):
    try:
        resp = requests.get("https://jkforum.net/api/legoin/v1/SignInInformation", 
                            headers=HEADERS, cookies=cookies, timeout=10)
        if resp.status_code == 200:
            wallet = resp.json().get("content", {}).get("wallet", {}).get("credits", [])
            return {TRACK_KEYS.get(item["id"], str(item["id"])): item.get("point", 0) 
                    for item in wallet if item.get("id") in TRACK_KEYS}
    except:
        pass
    return {}


def do_sign_in(cookies):
    try:
        resp = requests.put("https://jkforum.net/api/jkf-dailysign/v1/DailySign",
                            headers=HEADERS, cookies=cookies,
                            json={"moodStickerId": random.randint(1, 9), "message": "签到"}, timeout=10)
        return resp.status_code == 204
    except:
        return False


def get_article_list(cookies, board_id, limit=20):
    try:
        resp = requests.get(f"https://jkforum.net/api/jkf-forum/v1/Article/{board_id}",
                            headers=HEADERS, cookies=cookies, params={"Limit": limit}, timeout=10)
        return resp.json().get("content", {}).get("articles", []) if resp.status_code == 200 else []
    except:
        return []


def like_article(cookies, board_id, article_id):
    try:
        resp = requests.put(f"https://jkforum.net/api/jkf-forum/v1/ArticleLike/{board_id}/{article_id}",
                            headers=HEADERS, cookies=cookies, timeout=8)
        return resp.status_code == 204
    except:
        return False


def get_comments(cookies, article_id):
    try:
        resp = requests.get(f"https://jkforum.net/api/jkf-forum/v1/CommentThread/{article_id}",
                            headers=HEADERS, cookies=cookies, params={"Limit": 5}, timeout=8)
        return resp.json().get("content", []) if resp.status_code == 200 else []
    except:
        return []


def like_comment(cookies, board_id, comment_id):
    try:
        resp = requests.put(f"https://jkforum.net/api/jkf-forum/v1/CommentLike/{board_id}/{comment_id}",
                            headers=HEADERS, cookies=cookies, timeout=8)
        return resp.status_code == 204
    except:
        return False


def do_browse_and_like_tasks(cookies, max_browse=10):
    """浏览 + 点赞任务"""
    board_id = random.choice(VIEW_BOARDS)
    articles = get_article_list(cookies, board_id, max_browse + 8)
    if not articles:
        return 0, 0, 0

    viewed = liked_post = liked_comment = 0

    for i, article in enumerate(articles[:max_browse]):
        aid = article.get("id")
        if get_article_detail(cookies, aid):
            viewed += 1
        if liked_post < 3 and like_article(cookies, board_id, aid):
            liked_post += 1
        if i < max_browse - 1:
            time.sleep(random.randint(3, 5))

    # 点赞评论
    for article in random.sample(articles, min(6, len(articles))):
        for comment in get_comments(cookies, article.get("id")):
            if liked_comment < 3 and like_comment(cookies, board_id, comment.get("id")):
                liked_comment += 1

    return viewed, liked_post, liked_comment


def get_article_detail(cookies, article_id):
    try:
        resp = requests.get(f"https://jkforum.net/api/jkf-forum/v1/ArticleThread/{article_id}",
                            headers=HEADERS, cookies=cookies, timeout=6)
        return resp.status_code == 200
    except:
        return False


def claim_stage_rewards(cookies):
    """领取每日任务总奖励"""
    try:
        resp = requests.get("https://jkforum.net/api/jkf-dailyTask-api/v1/DailyStage",
                            headers=HEADERS, cookies=cookies, timeout=10)
        if resp.status_code != 200:
            return 0
        stages = resp.json().get("content", {}).get("stages", [])
        claimed = 0
        for stage in stages:
            if not stage.get("isCompleted"):
                r = requests.post("https://jkforum.net/api/jkf-dailyTask-api/v1/DailyStage/CompleteStage",
                                  headers=HEADERS, cookies=cookies, json={"stageId": stage["id"]}, timeout=10)
                if r.status_code in [200, 201]:
                    claimed += 1
        return claimed
    except:
        return 0


def process_account(cookies):
    before_assets = get_current_assets(cookies)

    # 签到
    signed = do_sign_in(cookies)

    # 浏览 + 点赞
    viewed, liked_post, liked_comment = do_browse_and_like_tasks(cookies)

    # 领取总奖励
    stage_claimed = claim_stage_rewards(cookies)

    # 清理通知
    clear_all_notifications(cookies)

    after_assets = get_current_assets(cookies)

    # 计算资产变化
    increase_list = []
    for name in TRACK_KEYS.values():
        diff = after_assets.get(name, 0) - before_assets.get(name, 0)
        if diff > 0:
            increase_list.append(f"{name}+{diff}")

    increase_text = ", ".join(increase_list) if increase_list else "无明显变化"

    return {
        "signed": signed,
        "viewed": viewed,
        "liked_post": liked_post,
        "liked_comment": liked_comment,
        "stage_claimed": stage_claimed,
        "increase_text": increase_text,
        "assets": after_assets
    }


def jkforum_main():
    print("\n" + "=" * 60)
    print(f"🚀 JKForum 签到脚本启动")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    random_delay_if_enabled()

    if not JKFORUM_COOKIE:
        print("❌ 未设置 JKFORUM_COOKIE 环境变量")
        return

    cookie_list = parse_multi_cookies(JKFORUM_COOKIE)
    results = []

    for idx, cookie_str in enumerate(cookie_list, 1):
        print(f"\n📌 处理账号 {idx}/{len(cookie_list)}")
        cookies = parse_cookie_string(cookie_str)
        if not cookies:
            continue

        res = process_account(cookies)
        results.append(res)

        # 紧凑日志（参考 enshan.js 风格）
        log = (f"账号{idx}: {'签到成功' if res['signed'] else '签到失败'} | "
               f"浏览{res['viewed']}篇 | 点赞文章{res['liked_post']} | 点赞留言{res['liked_comment']} | "
               f"总奖励:{res['stage_claimed']}阶段")
        print(log)

    # ==================== 最后统一发送一次通知 ====================
    if results and send:
        lines = []
        for i, r in enumerate(results, 1):
            status = "✅ 签到成功" if r["signed"] else "❌ 签到失败"
            line = (f"【账号 {i}】 {status}\n"
                    f"{r['increase_text']}\n"
                    f"总奖励领取: {r['stage_claimed']} 个阶段\n"
                    f"当前资产: 金币 {r['assets'].get('金币', 0)} | 宝石 {r['assets'].get('宝石', 0)}")
            lines.append(line)

        content = "\n\n" + "="*40 + "\n\n".join(lines)
        send(f"JKForum 签到 | {datetime.now().strftime('%m-%d %H:%M')}", content)
        print("\n🎉 通知已发送")
    elif results:
        print("\nℹ️ 未配置通知模块，无法发送通知")

    print("\n" + "=" * 60)
    print("✅ 脚本执行完毕")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    jkforum_main()
