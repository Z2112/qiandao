# -*- coding: utf-8 -*-
# cron: 0 10 * * *
# new Env('JKForum签到')

"""
================================================================================
青龙面板 - JKForum 签到脚本 (多账号 v2.3 - 无本地文件实时对比版)
================================================================================

【重要更新 v2.3】
- 完全移除 jkforum_data.json 本地文件依赖
- 采用「执行前 vs 执行后」实时对比，准确显示本次运行实际增加了多少金币/宝石
- 保留原有所有功能（多账号、智能跳过、浏览点赞、清理通知等）

【环境变量配置】

1. JKFORUM_COOKIE (必填)
   - 支持多账号（& 分隔 或 换行分隔）

2. RANDOM_SIGNIN (可选)
   true  = 启用启动随机延迟（防检测，推荐）
   false = 立即执行（默认）

3. MAX_RANDOM_DELAY (可选)
   随机延迟最大秒数，默认 3600（1小时）

【通知规则（重要）】
• 仅当账号「签到成功」或「签到失败」时发送通知
• 如果账号今日「已经签到」，则跳过该账号的通知
• 全部账号已签到 → 当天完全不发通知

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

# ==================== 随机延迟配置（默认关闭） ====================
RANDOM_SIGNIN = os.environ.get("RANDOM_SIGNIN", "false").lower() == "true"
MAX_RANDOM_DELAY = int(os.environ.get("MAX_RANDOM_DELAY", 3600))


def random_delay_if_enabled():
    if RANDOM_SIGNIN:
        delay = random.randint(1, MAX_RANDOM_DELAY)
        minutes = delay // 60
        seconds = delay % 60
        print(f"\n[随机延迟] RANDOM_SIGNIN 已启用，剩余 {minutes} 分钟 {seconds} 秒后开始执行...")
        time.sleep(delay)
        print("    ✅ 延迟结束，开始执行任务\n")


def parse_multi_cookies(cookie_env):
    if not cookie_env or not cookie_env.strip():
        return []
    raw_list = cookie_env.replace('\n', '&').split('&')
    return [c.strip() for c in raw_list if c.strip()]


def parse_cookie_string(cookie_str):
    if not cookie_str:
        return {}
    return {k.strip(): v.strip() for k, v in 
            (item.split("=", 1) for item in cookie_str.split(";") if "=" in item and item.strip())}


def get_member_id_from_jwt(cookies):
    for key in ['ap-pot', 'jkf-ap-pot']:
        token = cookies.get(key)
        if not token or '.' not in token:
            continue
        try:
            parts = token.split('.')
            if len(parts) < 2:
                continue
            payload_b64 = parts[1]
            padding = '=' * (4 - len(payload_b64) % 4) if len(payload_b64) % 4 else ''
            payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
            payload = json.loads(payload_bytes)
            if 'uid' in payload:
                return int(payload['uid'])
        except Exception:
            continue
    return None


def clear_all_notifications(cookies):
    print("\n[清理通知 - 删除所有站内信]")
    member_id = get_member_id_from_jwt(cookies)
    if not member_id:
        print("    ⚠️ 无法从 Cookie JWT 中提取 memberId，跳过清理")
        return False

    url = "https://jkforum.net/api/jkf-member-inbox/v1/Message"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://jkforum.net",
        "Referer": "https://jkforum.net/task",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "x-app-version": "1.0.0.1779162684",
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


def get_user_info(cookies):
    url = "https://jkforum.net/api/legoin/v1/SignInInformation"
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=15)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None


def get_current_assets(cookies):
    """获取当前资产"""
    user_info = get_user_info(cookies)
    if not user_info or "content" not in user_info:
        return {}
    content = user_info["content"]
    wallet = content.get("wallet", {}).get("credits", [])
    return {
        TRACK_KEYS.get(item["id"], str(item["id"])): item.get("point", 0)
        for item in wallet if item.get("id") in TRACK_KEYS
    }


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
        resp = requests.post(url, headers=HEADERS, cookies=cookies, json={"stageId": stage_id}, timeout=15)
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


def process_account(cookies, account_num, total_accounts):
    """处理单个账号（v2.3 无本地文件版）"""
    print(f"\n{'='*65}")
    print(f"🚀 处理账号 {account_num}/{total_accounts}")
    print(f"{'='*65}")

    # ===== 执行前记录资产 =====
    before_assets = get_current_assets(cookies)

    tasks = get_daily_tasks(cookies)
    task_status = {t["name"]: t.get("isCompleted", False) for t in tasks}
    incomplete_tasks = [name for name, completed in task_status.items() if not completed]

    print("\n📋 当前每日任务状态：")
    print("-" * 65)
    for name, completed in task_status.items():
        status = "✅ 已完成" if completed else "❌ 未完成"
        print(f"  {name:<22} {status}")
    print("-" * 65)

    signin_status = None

    if not incomplete_tasks:
        print("\n✅ 所有每日任务已完成，无需执行操作")
    else:
        print(f"\n🔄 发现 {len(incomplete_tasks)} 个未完成任务，开始执行...")

        if not task_status.get("進行每日簽到", False):
            signin_status = do_sign_in(cookies)
        else:
            signin_status = "already_signed"

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

        if (not task_status.get("逛逛版區-女神焦點", True) or
            not task_status.get("逛逛版區-IG推特美女", True)):
            browse_specific_boards(cookies)

    claim_daily_stage_rewards(cookies)
    clear_all_notifications(cookies)

    # ===== 执行后记录资产并计算本次增加 =====
    after_assets = get_current_assets(cookies)

    increase_lines = []
    for name in TRACK_KEYS.values():
        before = before_assets.get(name, 0)
        after = after_assets.get(name, 0)
        diff = after - before
        if diff != 0:
            increase_lines.append(f"{name}: {'+' if diff > 0 else ''}{diff}")

    increase_text = "\n".join(increase_lines) if increase_lines else "本次运行无资产变化"

    print(f"\n【本次运行资产变化】")
    if increase_lines:
        for line in increase_lines:
            print(f"  {line}")
    else:
        print("  本次运行无资产变化")

    print(f"\n【账号 {account_num} 当前总资产】")
    print(f"  金币: {after_assets.get('金币', 0):>8}    宝石: {after_assets.get('宝石', 0):>8}")
    print(f"  名声: {after_assets.get('名声', 0):>8}    体力: {after_assets.get('体力', 0):>8}")

    return {
        "account_num": account_num,
        "signin_status": signin_status or "skipped",
        "current_assets": after_assets,
        "increase_text": increase_text
    }


def jkforum_main():
    print("\n" + "=" * 65)
    print(f"🚀 JKForum 多账号智能脚本启动")
    print(f"⏰ 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    random_delay_if_enabled()

    if not JKFORUM_COOKIE:
        print("❌ 未设置 JKFORUM_COOKIE 环境变量")
        return

    cookies_list = parse_multi_cookies(JKFORUM_COOKIE)
    if not cookies_list:
        print("❌ 未解析到有效 Cookie，请检查环境变量格式")
        return

    print(f"📌 共检测到 {len(cookies_list)} 个账号，开始顺序处理...\n")

    results = []
    for idx, cookie_str in enumerate(cookies_list, 1):
        cookies = parse_cookie_string(cookie_str)
        if not cookies:
            print(f"账号 {idx}: Cookie 格式无效，跳过该账号\n")
            continue
        res = process_account(cookies, idx, len(cookies_list))
        results.append(res)

    notify_list = [r for r in results if r["signin_status"] in ["success", "failed"]]

    if notify_list:
        print(f"\n📢 检测到 {len(notify_list)} 个账号需要通知，正在发送...")
        notify_lines = []
        for r in notify_list:
            status_emoji = "✅" if r["signin_status"] == "success" else "❌"
            status_text = "签到成功" if r["signin_status"] == "success" else "签到失败/异常"
            assets = r["current_assets"]
            increase = r.get("increase_text", "无变化")

            line = (
                f"【账号 {r['account_num']}】 {status_emoji} {status_text}\n"
                f"金币: {assets.get('金币', 0)}   宝石: {assets.get('宝石', 0)}\n"
                f"名声: {assets.get('名声', 0)}   体力: {assets.get('体力', 0)}\n"
                f"本次增加: {increase if increase != '本次运行无资产变化' else '无明显变化'}"
            )
            notify_lines.append(line)

        notify_content = "\n\n" + "="*40 + "\n\n".join(notify_lines)
        title = f"JKForum 签到 | {datetime.now().strftime('%m-%d %H:%M')} ({len(notify_list)}账号)"
        send(title, notify_content)
        print("✅ 通知发送完成")
    else:
        print("\n✅ 所有账号今日已签到或无需操作，本次不发送通知（符合规则）")

    print("\n" + "=" * 65)
    print("✅ 全部账号处理完毕，脚本结束")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    jkforum_main()
