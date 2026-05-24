# -*- coding: utf-8 -*-
# cron: 0 10 * * *
# new Env('JKForum签到')

"""
================================================================================
青龙面板 - JKForum 签到脚本 (v2.6 详细注释版)
================================================================================

【v2.6 主要更新】
- 新增「总奖励领取成功/失败」通知
- 通知中会显示本次成功领取的总奖励阶段数量
- 文章间延迟调整为随机 3~5 秒
- 领取总奖励前会再次检查并尝试完成浏览点赞类任务
- 支持按需浏览和点赞（可控制数量）

【使用建议】
- 延迟已改短，建议先用 1 个账号测试
- 如运行异常，建议把延迟改回 15~30 秒
================================================================================
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


def random_delay_if_enabled():
    """随机延迟启动（防检测）"""
    if RANDOM_SIGNIN:
        delay = random.randint(1, MAX_RANDOM_DELAY)
        print(f"\n[随机延迟] RANDOM_SIGNIN 已启用，剩余 {delay//60} 分钟 {delay%60} 秒后开始执行...")
        time.sleep(delay)
        print("    ✅ 延迟结束，开始执行任务\n")


def parse_multi_cookies(cookie_env):
    """解析多账号 Cookie"""
    if not cookie_env or not cookie_env.strip():
        return []
    raw_list = cookie_env.replace('\n', '&').split('&')
    return [c.strip() for c in raw_list if c.strip()]


def parse_cookie_string(cookie_str):
    """将 Cookie 字符串转为字典"""
    if not cookie_str:
        return {}
    return {k.strip(): v.strip() for k, v in 
            (item.split("=", 1) for item in cookie_str.split(";") if "=" in item and item.strip())}


def get_member_id_from_jwt(cookies):
    """从 JWT 中提取 memberId（用于清理通知）"""
    for key in ['ap-pot', 'jkf-ap-pot']:
        token = cookies.get(key)
        if not token or '.' not in token:
            continue
        try:
            parts = token.split('.')
            payload_b64 = parts[1]
            padding = '=' * (4 - len(payload_b64) % 4) if len(payload_b64) % 4 else ''
            payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
            if 'uid' in payload:
                return int(payload['uid'])
        except:
            continue
    return None


def clear_all_notifications(cookies):
    """清理全部站内信"""
    print("\n[清理通知 - 删除所有站内信]")
    member_id = get_member_id_from_jwt(cookies)
    if not member_id:
        print("    ⚠️ 无法从 Cookie JWT 中提取 memberId，跳过清理")
        return False

    url = "https://jkforum.net/api/jkf-member-inbox/v1/Message"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://jkforum.net",
        "Referer": "https://jkforum.net/task",
        "x-signature": "pBBuSsmbqU",
        "x-signature-date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z",
    }
    payload = {"memberId": member_id, "status": 3}

    try:
        resp = requests.put(url, headers=headers, cookies=cookies, json=payload, timeout=15)
        if resp.status_code in [200, 204]:
            print(f"    ✅ 通知清理成功 (memberId={member_id})")
            return True
        else:
            print(f"    ⚠️ 清理通知返回状态码: {resp.status_code}")
            return False
    except Exception as e:
        print(f"    ❌ 清理通知请求异常: {e}")
        return False


VIEW_BOARDS = [141, 555, 374, 382, 246]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Origin": "https://jkforum.net",
    "Referer": "https://jkforum.net/",
}

TRACK_KEYS = {
    1: "名声", 2: "金币", 5: "宝石", 7: "体力", 9: "总积分"
}


def get_current_assets(cookies):
    """获取当前资产"""
    try:
        resp = requests.get("https://jkforum.net/api/legoin/v1/SignInInformation", headers=HEADERS, cookies=cookies, timeout=15)
        if resp.status_code == 200:
            wallet = resp.json().get("content", {}).get("wallet", {}).get("credits", [])
            return {TRACK_KEYS.get(item["id"], str(item["id"])): item.get("point", 0) 
                    for item in wallet if item.get("id") in TRACK_KEYS}
    except:
        pass
    return {}


def get_daily_tasks(cookies):
    """获取每日任务列表"""
    try:
        resp = requests.get("https://jkforum.net/api/jkf-dailyTask-api/v1/DailyTask", headers=HEADERS, cookies=cookies, timeout=15)
        return resp.json().get("content", {}).get("tasks", []) if resp.status_code == 200 else []
    except:
        return []


def get_daily_stages(cookies):
    """获取每日任务阶段奖励"""
    try:
        resp = requests.get("https://jkforum.net/api/jkf-dailyTask-api/v1/DailyStage", headers=HEADERS, cookies=cookies, timeout=15)
        return resp.json().get("content", {}) if resp.status_code == 200 else {}
    except:
        return {}


def should_perform_task(task):
    """判断任务是否需要执行"""
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
    """执行每日签到"""
    print("\n[每日签到]")
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
        else:
            print(f"    ⚠️ 签到异常: {resp.status_code}")
            return "failed"
    except Exception as e:
        print(f"    ❌ 签到失败: {e}")
        return "failed"


def get_article_list(cookies, board_id, limit=40):
    try:
        resp = requests.get(f"https://jkforum.net/api/jkf-forum/v1/Article/{board_id}",
                            headers=HEADERS, cookies=cookies, params={"Limit": limit}, timeout=15)
        return resp.json().get("content", {}).get("articles", []) if resp.status_code == 200 else []
    except:
        return []


def get_article_detail(cookies, article_id):
    try:
        return requests.get(f"https://jkforum.net/api/jkf-forum/v1/ArticleThread/{article_id}",
                            headers=HEADERS, cookies=cookies, timeout=10).status_code == 200
    except:
        return False


def like_article(cookies, board_id, article_id):
    try:
        return requests.put(f"https://jkforum.net/api/jkf-forum/v1/ArticleLike/{board_id}/{article_id}",
                            headers=HEADERS, cookies=cookies, timeout=10).status_code == 204
    except:
        return False


def get_comments(cookies, article_id, limit=6):
    try:
        resp = requests.get(f"https://jkforum.net/api/jkf-forum/v1/CommentThread/{article_id}",
                            headers=HEADERS, cookies=cookies, params={"Limit": limit}, timeout=10)
        return resp.json().get("content", []) if resp.status_code == 200 else []
    except:
        return []


def like_comment(cookies, board_id, comment_id):
    try:
        return requests.put(f"https://jkforum.net/api/jkf-forum/v1/CommentLike/{board_id}/{comment_id}",
                            headers=HEADERS, cookies=cookies, timeout=10).status_code == 204
    except:
        return False


def do_browse_and_like_tasks(cookies, max_article_likes=3, max_comment_likes=3, max_browse=10):
    """浏览 + 点赞任务（支持按需 + 短延迟）"""
    print(f"\n[浏览 + 点赞任务] 浏览{max_browse}篇")
    board_id = random.choice(VIEW_BOARDS)
    articles = get_article_list(cookies, board_id, max_browse + 5)
    if not articles:
        print("    ❌ 获取文章列表失败")
        return

    viewed = liked_article = liked_comment = 0
    for idx, article in enumerate(articles[:max_browse], 1):
        aid = article.get("id")
        if get_article_detail(cookies, aid):
            viewed += 1
        if liked_article < max_article_likes and like_article(cookies, board_id, aid):
            liked_article += 1
        if idx < max_browse:
            delay = random.randint(3, 5)
            print(f"    已处理 {idx}/{max_browse}，等待 {delay} 秒...")
            time.sleep(delay)

    for article in random.sample(articles, min(5, len(articles))):
        for comment in get_comments(cookies, article.get("id"), 4):
            if liked_comment < max_comment_likes and like_comment(cookies, board_id, comment.get("id")):
                liked_comment += 1

    print(f"    ✅ 浏览{viewed}篇，点赞文章{liked_article}篇，点赞留言{liked_comment}则")


def claim_daily_stage_rewards(cookies):
    """领取每日任务总奖励，返回成功领取的数量"""
    print("\n[领取每日任务总奖励]")
    stage_data = get_daily_stages(cookies)
    stages = stage_data.get("stages", [])
    uncompleted = [s for s in stages if not s.get("isCompleted", False)]

    if not uncompleted:
        print("    ✅ 总奖励已全部领取")
        return 0

    claimed = 0
    for stage in uncompleted:
        try:
            resp = requests.post("https://jkforum.net/api/jkf-dailyTask-api/v1/DailyStage/CompleteStage",
                                 headers=HEADERS, cookies=cookies, json={"stageId": stage["id"]}, timeout=15)
            if resp.status_code in [200, 201]:
                claimed += 1
                print(f"    ✅ 领取成功 stageId={stage['id']}")
        except:
            print(f"    ❌ 领取失败 stageId={stage['id']}")

    print(f"    本次共领取 {claimed} 个总奖励阶段")
    return claimed


def complete_task(cookies, task_id):
    try:
        resp = requests.post("https://jkforum.net/api/jkf-dailyTask-api/v1/DailyTask/CompleteTask",
                             headers=HEADERS, cookies=cookies, json={"taskId": task_id}, timeout=15)
        return resp.status_code == 200 and resp.json().get("code") == "200000"
    except:
        return False


def process_account(cookies, account_num, total_accounts):
    """处理单个账号"""
    print(f"\n{'='*65}")
    print(f"🚀 处理账号 {account_num}/{total_accounts}")
    print(f"{'='*65}")

    before_assets = get_current_assets(cookies)
    tasks = get_daily_tasks(cookies)
    task_status = {t["name"]: t.get("isCompleted", False) for t in tasks}

    print("\n📋 当前每日任务状态：")
    for name, completed in task_status.items():
        print(f"  {name:<22} {'✅ 已完成' if completed else '❌ 未完成'}")

    signin_status = do_sign_in(cookies) if not task_status.get("進行每日簽到", False) else "already_signed"

    LIKE_TASK_NAMES = ["對三篇文章點讚", "對三則留言點讚", "觀看任30篇文章"]
    need_browse_like = any(t["name"] in LIKE_TASK_NAMES and not t.get("isCompleted") for t in tasks)

    if need_browse_like:
        do_browse_and_like_tasks(cookies, max_article_likes=3, max_comment_likes=3, max_browse=10)

    # 领取总奖励前再次检查任务
    tasks = get_daily_tasks(cookies)
    for task in tasks:
        if task["name"] in LIKE_TASK_NAMES and not task.get("isCompleted", False):
            if should_perform_task(task) in ["claim_only", True]:
                complete_task(cookies, task["id"])

    stage_claimed = claim_daily_stage_rewards(cookies)
    clear_all_notifications(cookies)

    after_assets = get_current_assets(cookies)
    increase_lines = []
    for name in TRACK_KEYS.values():
        diff = after_assets.get(name, 0) - before_assets.get(name, 0)
        if diff != 0:
            increase_lines.append(f"{name}: +{diff}")

    print(f"\n【本次运行资产变化】")
    print("\n".join(increase_lines) if increase_lines else "  无明显变化")
    print(f"\n【当前总资产】 金币: {after_assets.get('金币', 0)}  宝石: {after_assets.get('宝石', 0)}")

    return {
        "account_num": account_num,
        "signin_status": signin_status,
        "current_assets": after_assets,
        "increase_text": "\n".join(increase_lines) if increase_lines else "无明显变化",
        "stage_claimed": stage_claimed
    }


def jkforum_main():
    print("\n" + "=" * 65)
    print(f"🚀 JKForum 签到脚本启动 (v2.6 详细注释版)")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    random_delay_if_enabled()

    if not JKFORUM_COOKIE:
        print("❌ 未设置 JKFORUM_COOKIE 环境变量")
        return

    cookies_list = parse_multi_cookies(JKFORUM_COOKIE)
    results = []
    for idx, cookie_str in enumerate(cookies_list, 1):
        cookies = parse_cookie_string(cookie_str)
        if cookies:
            res = process_account(cookies, idx, len(cookies_list))
            results.append(res)

    notify_list = [r for r in results if r["signin_status"] in ["success", "failed"]]

    if notify_list:
        notify_lines = []
        for r in notify_list:
            status = "✅ 签到成功" if r["signin_status"] == "success" else "❌ 签到失败"
            stage_info = f"总奖励领取: {r.get('stage_claimed', 0)} 个阶段" if r.get('stage_claimed', 0) > 0 else "总奖励领取: 未领取或失败"

            line = f"""【账号 {r['account_num']}】 {status}
{r['increase_text']}
{stage_info}
当前资产: 金币 {r['current_assets'].get('金币', 0)} | 宝石 {r['current_assets'].get('宝石', 0)}"""
            notify_lines.append(line)

        content = "\n\n" + "="*40 + "\n\n".join(notify_lines)
        send(f"JKForum 签到 | {datetime.now().strftime('%m-%d %H:%M')}", content)
        print("✅ 通知已发送")
    else:
        print("✅ 无需发送通知（全部已签到或跳过）")

    print("\n" + "=" * 65)
    print("✅ 脚本执行完毕")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    jkforum_main()
