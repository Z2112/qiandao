# -*- coding: utf-8 -*-
# cron: 0 10 * * *
# new Env('JKForum签到')

import base64
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

try:
    from notify import send
except ImportError:
    send = None


def positive_env_int(name, default):
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    print(f"⚠️ {name} 必须为正整数，使用默认值 {default}")
    return default


JKFORUM_COOKIE = os.getenv("JKFORUM_COOKIE", "")
RANDOM_SIGNIN = os.getenv("RANDOM_SIGNIN", "false").lower() == "true"
MAX_RANDOM_DELAY = positive_env_int("MAX_RANDOM_DELAY", 3600)
ALWAYS_NOTIFY = os.getenv("ALWAYS_NOTIFY", "false").lower() == "true"
MAX_TASK_ROUNDS = 3
BASE_URL = "https://jkforum.net"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
}
TRACK_KEYS = {1: "名声", 2: "金币", 5: "宝石", 7: "体力"}
VIEW_BOARDS = [141, 555, 374, 382, 246]
TASK_BOARDS = {"逛逛版區-網路美女": 736, "逛逛版區-清涼寫真": 234}


class APIError(RuntimeError):
    pass


class APIClient:
    def __init__(self, cookies):
        self.cookies = cookies
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain="jkforum.net", path="/")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.session.close()

    def safe_message(self, message):
        message = str(message)
        for value in self.cookies.values():
            if value:
                message = message.replace(value, "[已隐藏]")
        return " ".join(message.split())[:200]

    def error_detail(self, resp):
        try:
            data = resp.json()
            if isinstance(data, dict):
                values = [data.get(key) for key in ("code", "message", "msg", "error")]
                detail = " | ".join(str(value) for value in values if value is not None)
                if detail:
                    return self.safe_message(detail)
        except ValueError:
            pass
        return self.safe_message(resp.text) or "无错误详情"

    def request(self, method, path, expected=(200,), **kwargs):
        # GET 可以安全重试；写操作由任务流程刷新状态后决定是否重做。
        attempts = 3 if method == "GET" else 1
        for attempt in range(1, attempts + 1):
            try:
                resp = self.session.request(
                    method, f"{BASE_URL}{path}", timeout=15, **kwargs
                )
            except requests.exceptions.SSLError as exc:
                raise APIError(f"{method} {path}: TLS 错误: {self.safe_message(exc)}") from exc
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                if attempt < attempts:
                    print(f"⚠️ {method} {path} 连接异常，准备第 {attempt + 1}/{attempts} 次请求")
                    time.sleep(2 ** attempt)
                    continue
                raise APIError(f"{method} {path}: {self.safe_message(exc)}") from exc
            except requests.exceptions.RequestException as exc:
                raise APIError(f"{method} {path}: {self.safe_message(exc)}") from exc
            if resp.status_code in expected:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < attempts:
                print(f"⚠️ {method} {path} HTTP {resp.status_code}，准备重试")
                time.sleep(2 ** attempt)
                continue
            raise APIError(f"{method} {path}: HTTP {resp.status_code} | {self.error_detail(resp)}")

    def content(self, path, **kwargs):
        resp = self.request("GET", path, **kwargs)
        try:
            data = resp.json()
        except ValueError as exc:
            raise APIError(f"{path}: 未返回有效 JSON") from exc
        if not isinstance(data, dict) or data.get("content") is None:
            raise APIError(f"{path}: 缺少 content，不能确认接口结果")
        return data["content"]


def now_text(fmt="%Y-%m-%d %H:%M:%S"):
    return datetime.now(timezone(timedelta(hours=8))).strftime(fmt)


def random_delay_if_enabled():
    if RANDOM_SIGNIN:
        delay = random.randint(1, MAX_RANDOM_DELAY)
        print(f"\n⏳ 随机延迟 {delay // 60} 分 {delay % 60} 秒后执行...")
        time.sleep(delay)


def parse_multi_cookies(cookie_env):
    return [value.strip() for value in cookie_env.replace("\n", "&").split("&") if value.strip()]


def parse_cookie_string(cookie_str):
    return {
        key.strip(): value.strip()
        for key, value in (item.split("=", 1) for item in cookie_str.split(";") if "=" in item)
        if key.strip()
    }


def get_member_id_from_jwt(cookies):
    for key in ("ap-pot", "jkf-ap-pot"):
        token = cookies.get(key, "")
        if "." not in token:
            continue
        try:
            payload = token.split(".")[1]
            data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            member_id = int(data["uid"])
            if member_id > 0:
                return member_id
        except (ValueError, KeyError, TypeError, IndexError):
            continue
    return None


def get_current_assets(client):
    content = client.content("/api/legoin/v1/SignInInformation")
    if not isinstance(content, dict) or not isinstance(content.get("wallet"), dict):
        raise APIError("资产接口缺少 wallet")
    credits = content["wallet"].get("credits")
    if not isinstance(credits, list):
        raise APIError("资产接口缺少 credits 列表")
    assets = {}
    for item in credits:
        try:
            credit_id = int(item["id"])
            point = float(item["point"])
            if not float("-inf") < point < float("inf"):
                raise ValueError("invalid point")
        except (ValueError, TypeError, KeyError):
            raise APIError("资产接口返回无效余额")
        if credit_id in TRACK_KEYS:
            assets[TRACK_KEYS[credit_id]] = int(point) if point.is_integer() else point
    if not assets:
        raise APIError("资产接口没有可识别的余额")
    return assets


def get_daily_tasks(client):
    content = client.content("/api/jkf-dailyTask-api/v1/DailyTask")
    tasks = content.get("tasks") if isinstance(content, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise APIError("每日任务列表为空或格式异常，不能判断为全部完成")
    for task in tasks:
        if not isinstance(task, dict) or not task.get("id") or not task.get("name"):
            raise APIError("每日任务缺少 id 或 name")
        get_task_progress(task)
    return tasks


def get_task_progress(task):
    details = task.get("details") or []
    if not isinstance(details, list):
        raise APIError(f"任务 {task.get('name')} 的进度格式异常")
    if not details:
        return 0, 1
    current = goal = 0
    for detail in details:
        try:
            value = max(0, int(detail.get("progressScore", 0)))
            target = max(1, int(detail.get("goalScore", 1)))
        except (AttributeError, ValueError, TypeError) as exc:
            raise APIError(f"任务 {task.get('name')} 的进度无效") from exc
        # 一个子条件超额不能抵消另一个未完成的子条件。
        current += min(value, target)
        goal += target
    return current, goal


def should_perform_task(task):
    if task.get("isCompleted"):
        return False
    current, goal = get_task_progress(task)
    return "claim_only" if current >= goal else True


def do_sign_in(client):
    print("\n📝 执行每日签到")
    resp = client.request(
        "PUT", "/api/jkf-dailysign/v1/DailySign", expected=(204, 406),
        json={"moodStickerId": random.randint(1, 9), "message": "签到"},
    )
    status = "success" if resp.status_code == 204 else "already_signed"
    print("    ✅ 签到成功" if status == "success" else "    ✅ 今日已签到")
    return status


def get_article_list(client, board_id, limit=60):
    content = client.content(
        f"/api/jkf-forum/v1/Article/{board_id}",
        params={"tab": 0, "Offset": 0, "Limit": limit},
    )
    articles = content.get("articles") if isinstance(content, dict) else None
    if not isinstance(articles, list) or any(not isinstance(article, dict) for article in articles):
        raise APIError(f"版区 {board_id} 的文章列表格式异常")
    return articles


def get_article_detail(client, article_id):
    client.request("GET", f"/api/jkf-forum/v1/ArticleThread/{article_id}")
    return True


def get_comments(client, article_id, limit=6):
    content = client.content(
        f"/api/jkf-forum/v1/CommentThread/{article_id}",
        params={"authorOnly": "false", "sortingType": 1, "Limit": limit},
    )
    if not isinstance(content, list) or any(not isinstance(comment, dict) for comment in content):
        raise APIError(f"文章 {article_id} 的留言列表格式异常")
    return content


def new_action_state():
    return {"viewed": set(), "article_likes": set(), "comment_likes": set()}


def do_browse_and_like_tasks(client, browse_count=0, like_article_count=0,
                             like_comment_count=0, state=None):
    state = state if state is not None else new_action_state()
    counts = {"viewed": 0, "article_likes": 0, "comment_likes": 0}
    targets = {"viewed": browse_count, "article_likes": like_article_count,
               "comment_likes": like_comment_count}
    print(f"\n🔄 按剩余进度执行：浏览 {browse_count}，文章点赞 {like_article_count}，留言点赞 {like_comment_count}")
    boards = list(VIEW_BOARDS)
    random.shuffle(boards)
    for board_id in boards:
        if all(counts[key] >= targets[key] for key in targets):
            break
        try:
            articles = get_article_list(client, board_id, limit=80)
        except APIError as exc:
            print(f"    ⚠️ {exc}")
            continue
        for article in articles:
            if all(counts[key] >= targets[key] for key in targets):
                break
            article_id = article.get("id")
            if not article_id:
                continue
            if article_id not in state["viewed"]:
                try:
                    get_article_detail(client, article_id)
                    state["viewed"].add(article_id)
                    counts["viewed"] += 1
                    print(f"    👀 已访问文章 {article_id}")
                    time.sleep(random.randint(2, 3))
                except APIError as exc:
                    print(f"    ⚠️ {exc}")
                    continue

            actions = ["article_likes", "comment_likes"]
            random.shuffle(actions)
            for action in actions:
                if counts[action] >= targets[action]:
                    continue
                if action == "article_likes":
                    if article_id in state[action]:
                        continue
                    # 不重复提交相同点赞，避免未知结果下再次提交造成反向操作。
                    state[action].add(article_id)
                    try:
                        client.request("PUT", f"/api/jkf-forum/v1/ArticleLike/{board_id}/{article_id}", expected=(204,))
                        counts[action] += 1
                        print(f"    👍 文章点赞成功: {article_id}")
                        time.sleep(random.randint(3, 5))
                    except APIError as exc:
                        print(f"    ⚠️ {exc}")
                else:
                    try:
                        comments = get_comments(client, article_id)
                    except APIError as exc:
                        print(f"    ⚠️ {exc}")
                        continue
                    random.shuffle(comments)
                    for comment in comments:
                        if counts[action] >= targets[action]:
                            break
                        comment_id = comment.get("id")
                        if not comment_id or comment_id in state[action]:
                            continue
                        state[action].add(comment_id)
                        try:
                            client.request("PUT", f"/api/jkf-forum/v1/CommentLike/{board_id}/{comment_id}", expected=(204,))
                            counts[action] += 1
                            print(f"    💬 留言点赞成功: {comment_id}")
                            time.sleep(random.randint(3, 5))
                        except APIError as exc:
                            print(f"    ⚠️ {exc}")
    print(f"📊 本轮实际访问文章 {counts['viewed']} 篇，文章点赞 {counts['article_likes']}，留言点赞 {counts['comment_likes']}")
    for key in targets:
        if counts[key] < targets[key]:
            print(f"    ⚠️ 本轮 {key} 不足：{counts[key]}/{targets[key]}，将以刷新后的任务进度补做")
    return counts


def browse_specific_boards(client, task_names, state):
    for name in task_names:
        board_id = TASK_BOARDS.get(name)
        if not board_id:
            print(f"    ❌ {name} 未配置目标版区 ID，不能确认完成")
            continue
        print(f"\n🌐 访问任务版区: {name} | ID: {board_id}")
        try:
            client.request("GET", f"/api/jkf-forum/v1/Board/{board_id}")
            articles = get_article_list(client, board_id, limit=1)
            if articles and articles[0].get("id"):
                article_id = articles[0]["id"]
                if article_id not in state["viewed"]:
                    get_article_detail(client, article_id)
                    state["viewed"].add(article_id)
            print("    版区和文章列表请求成功，任务结果以刷新后的进度为准")
        except APIError as exc:
            print(f"    ⚠️ {exc}")


def complete_task(client, task_id):
    resp = client.request(
        "POST", "/api/jkf-dailyTask-api/v1/DailyTask/CompleteTask", json={"taskId": task_id}
    )
    try:
        data = resp.json()
    except ValueError as exc:
        raise APIError(f"任务 {task_id} 奖励接口未返回有效 JSON") from exc
    if not isinstance(data, dict) or str(data.get("code")) != "200000":
        raise APIError(f"任务 {task_id} 奖励未确认领取: {client.error_detail(resp)}")
    return True


def claim_ready_tasks(client, tasks):
    acknowledged = False
    for task in tasks:
        if should_perform_task(task) != "claim_only":
            continue
        try:
            complete_task(client, task["id"])
            acknowledged = True
            print(f"    ✅ 奖励接口确认领取: {task['name']}")
        except APIError as exc:
            print(f"    ⚠️ {exc}")
    return acknowledged


def get_daily_stages(client):
    content = client.content("/api/jkf-dailyTask-api/v1/DailyStage")
    stages = content.get("stages") if isinstance(content, dict) else None
    if not isinstance(stages, list) or not stages or any(
        not isinstance(stage, dict) or not stage.get("id") for stage in stages
    ):
        raise APIError("阶段奖励列表为空或格式异常，不能确认领取状态")
    return stages


def claim_daily_stage_rewards(client):
    print("\n🎁 领取每日任务阶段总奖励")
    initial = set()
    verified = set()
    reasons = {}
    try:
        stages = get_daily_stages(client)
        initial = {stage["id"] for stage in stages if not stage.get("isCompleted")}
        if not initial:
            print("    ✅ 阶段总奖励已全部领取")
            return {"status": "skipped", "success": 0, "failed": 0, "errors": []}
        for attempt in range(1, MAX_TASK_ROUNDS + 1):
            pending = [stage for stage in stages if not stage.get("isCompleted")]
            if not pending:
                break
            for stage in pending:
                stage_id = stage["id"]
                initial.add(stage_id)
                try:
                    resp = client.request(
                        "POST", "/api/jkf-dailyTask-api/v1/DailyStage/CompleteStage",
                        expected=(200, 201), json={"stageId": stage_id},
                    )
                    if resp.content:
                        data = resp.json()
                        if isinstance(data, dict) and data.get("code") is not None and str(data["code"]) != "200000":
                            raise APIError(f"stageId={stage_id}: {client.error_detail(resp)}")
                    print(f"    阶段 {stage_id} 领取请求已返回，正在复核")
                except (APIError, ValueError) as exc:
                    reasons[stage_id] = client.safe_message(exc)
                    print(f"    ⚠️ stageId={stage_id}: {reasons[stage_id]}")
            time.sleep(2)
            stages = get_daily_stages(client)
            verified.update(stage["id"] for stage in stages if stage.get("isCompleted"))
        remaining = initial - verified
        errors = [
            f"阶段 {stage_id} 未确认领取: {reasons.get(stage_id, '刷新后仍未完成')}"
            for stage_id in sorted(remaining, key=str)
        ]
        print(f"    阶段总奖励确认领取 {len(initial & verified)} 个，未确认 {len(remaining)} 个")
        return {"status": "done", "success": len(initial & verified), "failed": len(remaining), "errors": errors}
    except APIError as exc:
        errors = [str(exc)]
        print(f"    ❌ 阶段总奖励复核失败: {exc}")
        return {"status": "failed", "success": len(initial & verified),
                "failed": max(1, len(initial - verified)), "errors": errors}


def clear_all_notifications(client):
    member_id = get_member_id_from_jwt(client.cookies)
    if not member_id:
        print("\nℹ️ 无法读取用户 ID，跳过站内通知清理")
        return
    try:
        client.request(
            "PUT", "/api/jkf-member-inbox/v1/Message", expected=(200, 204),
            json={"memberId": member_id, "status": 3},
        )
        print("\n🧹 站内通知清理请求成功")
    except APIError as exc:
        print(f"\n⚠️ 站内通知清理失败: {exc}")


def task_status_lines(tasks):
    lines = []
    for task in tasks:
        current, goal = get_task_progress(task)
        status = "✅ 已完成/已领取" if task.get("isCompleted") else f"❌ 未完成/未领取 {current}/{goal}"
        lines.append(f"{task['name']} | {status}")
    return lines


def perform_task_actions(client, tasks, state, signin_status, round_num):
    browse = article_likes = comment_likes = 0
    board_tasks = []
    for task in tasks:
        if should_perform_task(task) is not True:
            continue
        current, goal = get_task_progress(task)
        remaining = goal - current
        name = task["name"]
        print(f"📌 {name} | 剩余进度 {remaining}")
        if name == "進行每日簽到":
            if signin_status not in ("success", "already_signed"):
                try:
                    signin_status = do_sign_in(client)
                except APIError as exc:
                    signin_status = "failed"
                    print(f"    ⚠️ {exc}")
        elif name in ("觀看任一篇文章", "觀看任30篇文章"):
            browse = max(browse, remaining)
        elif name == "對三篇文章點讚":
            article_likes = max(article_likes, remaining)
        elif name == "對三則留言點讚":
            comment_likes = max(comment_likes, remaining)
        elif name == "瀏覽任一版區":
            board_id = VIEW_BOARDS[(round_num - 1) % len(VIEW_BOARDS)]
            try:
                client.request("GET", f"/api/jkf-forum/v1/Board/{board_id}")
                get_article_list(client, board_id, limit=1)
                print(f"    🌐 已请求版区 {board_id}，待刷新确认")
            except APIError as exc:
                print(f"    ⚠️ {exc}")
        elif name.startswith("逛逛版區"):
            board_tasks.append(name)
        else:
            print(f"    ❌ 暂不支持此任务的操作，保留为未完成: {name}")
    if browse or article_likes or comment_likes:
        do_browse_and_like_tasks(client, browse, article_likes, comment_likes, state)
    browse_specific_boards(client, board_tasks, state)
    return signin_status


def process_account(client, account_num, total_accounts):
    print(f"\n{'=' * 65}\n🚀 处理账号 {account_num}/{total_accounts}\n{'=' * 65}")
    errors = []
    try:
        before_assets = get_current_assets(client)
    except APIError as exc:
        before_assets = None
        print(f"⚠️ 执行前资产读取失败: {exc}")

    tasks = get_daily_tasks(client)
    print("\n📋 当前任务状态：\n" + "\n".join(task_status_lines(tasks)))
    signin_status = "already_signed" if any(
        task["name"] == "進行每日簽到" and task.get("isCompleted") for task in tasks
    ) else None
    state = new_action_state()
    for round_num in range(1, MAX_TASK_ROUNDS + 1):
        if all(task.get("isCompleted") for task in tasks):
            break
        print(f"\n🔄 第 {round_num}/{MAX_TASK_ROUNDS} 轮：执行任务、刷新进度、领取奖励")
        # 达标任务直接领取，绝不重复签到/点赞等操作。
        claim_ready_tasks(client, tasks)
        signin_status = perform_task_actions(client, tasks, state, signin_status, round_num)
        time.sleep(2)
        tasks = get_daily_tasks(client)
        if claim_ready_tasks(client, tasks):
            time.sleep(2)
            tasks = get_daily_tasks(client)
        print("\n📋 本轮复核：\n" + "\n".join(task_status_lines(tasks)))

    incomplete = [task for task in tasks if not task.get("isCompleted")]
    for task in incomplete:
        current, goal = get_task_progress(task)
        name = task["name"]
        reason = f"{name} 未完成/未领取 {current}/{goal}"
        if name.startswith("逛逛版區") and name not in TASK_BOARDS:
            reason += "（缺少目标版区 ID）"
        errors.append(reason)
    if signin_status == "failed":
        # 最新任务已领取则覆盖之前的请求异常，避免误报。
        if any(task["name"] == "進行每日簽到" and task.get("isCompleted") for task in tasks):
            signin_status = "already_signed"
        else:
            errors.append("每日签到请求未确认成功")

    stage_result = claim_daily_stage_rewards(client)
    errors.extend(stage_result["errors"])
    clear_all_notifications(client)

    try:
        after_assets = get_current_assets(client)
    except APIError as exc:
        after_assets = {}
        errors.append(f"最终资产读取失败: {exc}")
    if before_assets is None or not after_assets:
        increase_text = "未知（资产读取失败）"
    else:
        changes = [
            f"{name} {after_assets[name] - before_assets[name]:+g}"
            for name in TRACK_KEYS.values()
            if name in before_assets and name in after_assets and after_assets[name] != before_assets[name]
        ]
        increase_text = " | ".join(changes) if changes else "无变化"
    print(f"\n【本次运行资产变化】{increase_text}")
    print(f"[当前总资产] 金币: {after_assets.get('金币', '未知')}  宝石: {after_assets.get('宝石', '未知')}")
    print("\n📋 最终任务结果：\n" + "\n".join(task_status_lines(tasks)))
    return {
        "account_num": account_num, "signin_status": signin_status,
        "stage_result": stage_result, "current_assets": after_assets,
        "increase_text": increase_text, "task_lines": task_status_lines(tasks),
        "errors": errors, "has_fail": bool(errors),
    }


def build_summary(result):
    stage = result.get("stage_result", {})
    assets = result.get("current_assets", {})
    lines = [
        f"{'❌' if result['has_fail'] else '✅'} 账号 {result['account_num']}",
        f"阶段总奖励：确认领取 {stage.get('success', 0)} 个，未确认 {stage.get('failed', 0)} 个",
        f"金币: {assets.get('金币', '未知')} | 宝石: {assets.get('宝石', '未知')}",
        f"资产变化: {result.get('increase_text', '未知')}",
    ]
    lines.extend(result.get("task_lines", []))
    if result.get("errors"):
        lines.append("问题：" + "；".join(result["errors"]))
    return "\n".join(lines)


def jkforum_main():
    print(f"🚀 JKForum 签到脚本 v2.8 启动 - {now_text()}")
    cookie_strings = parse_multi_cookies(JKFORUM_COOKIE)
    if not cookie_strings:
        print("❌ 未设置有效的 JKFORUM_COOKIE")
        return False
    random_delay_if_enabled()
    results = []
    for idx, cookie_str in enumerate(cookie_strings, 1):
        cookies = parse_cookie_string(cookie_str)
        client = None
        try:
            if not cookies:
                raise APIError("Cookie 格式无效")
            with APIClient(cookies) as client:
                result = process_account(client, idx, len(cookie_strings))
        except Exception as exc:
            # 单个账号异常不能中断后续账号。
            detail = client.safe_message(exc) if client is not None else str(exc)
            print(f"❌ 账号 {idx} 执行异常: {detail}")
            result = {"account_num": idx, "has_fail": True, "errors": [detail]}
        results.append(result)

    summary = "\n\n" + ("\n\n" + "=" * 40 + "\n\n").join(build_summary(result) for result in results)
    print("\n📊 全部账号结果：" + summary)
    has_fail = any(result["has_fail"] for result in results)
    if ALWAYS_NOTIFY or has_fail:
        if send is None:
            print("ℹ️ 推送模块未加载，结果已打印")
        else:
            try:
                send(f"JKForum 任务汇总 | {now_text('%m-%d %H:%M')}", summary)
                print("✅ 通知发送完成" + ("（存在失败）" if has_fail else "（ALWAYS_NOTIFY=true）"))
            except Exception as exc:
                print(f"❌ 通知发送异常: {exc}")
                has_fail = True
    else:
        print("✅ 全部任务及奖励已确认完成，ALWAYS_NOTIFY=false，跳过通知")
    print("❌ 存在未完成任务或异常，详见汇总" if has_fail else "✅ 全部账号处理完成")
    return not has_fail


if __name__ == "__main__":
    sys.exit(0 if jkforum_main() else 1)
