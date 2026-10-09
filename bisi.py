# -*- coding: utf-8 -*-
# cron: 0 10 * * *
# new Env('比思论坛签到')
# 默认同步 Cookie 到青龙；BISI_SYNC_COOKIE=false 可关闭写回。
# 优先使用任务执行器注入的 QLAPI。
# 无内置接口时：配置 QL_CLIENT_ID、QL_CLIENT_SECRET（应用需环境变量权限）。
# QL_URL 默认 http://127.0.0.1:5700，也支持已有 QL_ACCESS_TOKEN。

import builtins
import html
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

try:
    from notify import send
except ImportError:
    send = None

BASE_URL = "http://hkcdn4.space"
HOST = urlparse(BASE_URL).hostname
SIGN_URL = f"{BASE_URL}/plugin.php?id=dsu_paulsign:sign"
POST_URL = f"{SIGN_URL}&operation=qiandao&infloat=1"
CREDIT_URL = f"{BASE_URL}/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class BisiError(RuntimeError):
    pass


class CookieSyncError(RuntimeError):
    pass


def parse_cookie(cookie):
    cookie = cookie.strip()
    for left, right in (('"', '"'), ("'", "'"), ("“", "”")):
        if cookie.startswith(left) and cookie.endswith(right):
            cookie = cookie[1:-1].strip()
            break
    values = {}
    for part in cookie.split(";"):
        if "=" in part:
            name, value = part.split("=", 1)
            if name.strip():
                values[name.strip()] = value.strip()
    return values


def get_all_cookies(raw=None):
    if raw is None:
        raw = os.getenv("BISI_COOKIE", "")
    cookies = [value.strip() for value in re.split(r"[&\r\n]+", raw) if value.strip()]
    if not cookies:
        raise BisiError("未设置有效的 BISI_COOKIE 环境变量")
    return cookies


def plain_text(value):
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", value, flags=re.I | re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def page_title(page):
    match = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
    return plain_text(match.group(1)) if match else "无页面标题"


def today():
    return datetime.now(timezone(timedelta(hours=8))).date()


class FormhashParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.formhash = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "input":
            return
        values = dict(attrs)
        token = values.get("value") or ""
        if (values.get("name") or "").lower() == "formhash" and re.fullmatch(r"[0-9a-f]{8}", token, re.I):
            self.formhash = token


def extract_formhash(page):
    parser = FormhashParser()
    parser.feed(page)
    if parser.formhash:
        return parser.formhash
    match = re.search(r"\bformhash=([0-9a-f]{8})(?![0-9a-f])", html.unescape(page), re.I)
    return match.group(1) if match else None


def get_sign_stats(page):
    text = plain_text(page)
    stats = {}
    patterns = {
        "累计签到": r"累[計计]已[簽签]到\s*[:：]?\s*(\d+)\s*天",
        "本月签到": r"本月已累[計计][簽签]到\s*[:：]?\s*(\d+)\s*天",
        "上次签到": r"上次[簽签]到[時时][間间]\s*[:：]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
        "上次奖励": r"上次[獲获]得的[獎奖][勵励][為为]\s*[:：]?\s*金[錢钱]\s*(\d+)",
    }
    for name, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            stats[name] = match.group(1)
    return stats


def has_signed_today(page):
    stats = get_sign_stats(page)
    if stats.get("上次签到"):
        parts = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", stats["上次签到"])
        try:
            if datetime(*(int(value) for value in parts.groups())).date() == today():
                return True
        except (ValueError, AttributeError):
            pass
    text = plain_text(page)
    # 这句话还可能表示签到尚未开放，不能单凭它报“今日已签到”。
    for ambiguous in ("您今天已經簽到過了或者簽到時間還未開始", "您今天已经签到过了或者签到时间还未开始"):
        text = text.replace(ambiguous, "")
    return bool(re.search(r"您今天已[經经][簽签]到[過过]了|今日已[簽签]到|今天已[經经][簽签]到", text))


class BisiClient:
    def __init__(self, cookie):
        self.original_cookie = cookie
        self.original_values = parse_cookie(cookie)
        if not self.original_values or not any(name.endswith("_auth") and value for name, value in self.original_values.items()):
            raise BisiError("Cookie 缺少登录 auth 字段")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Referer": f"{BASE_URL}/"})
        for name, value in self.original_values.items():
            self.session.cookies.set(name, value, domain=HOST, path="/")
        self.authenticated = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.session.close()

    def redact(self, message):
        text = str(message)
        secrets = list(self.original_values.values()) + [cookie.value for cookie in self.session.cookies]
        for value in secrets:
            if len(value) > 4:
                text = text.replace(value, "[已隐藏]")
        return " ".join(text.split())[:240]

    def loaded_get(self, url):
        for attempt in range(1, 4):
            try:
                resp = self.session.get(url, timeout=15, allow_redirects=False)
            except requests.exceptions.SSLError as exc:
                raise BisiError(f"网站 TLS 连接异常: {self.redact(exc)}") from exc
            except requests.exceptions.RequestException as exc:
                if attempt == 3:
                    raise BisiError(f"网站请求异常: {self.redact(exc)}") from exc
                print(f"⚠️ 网站请求异常，2 秒后重试（{attempt + 1}/3）")
                time.sleep(2)
                continue
            if resp.status_code != 200:
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(2)
                    continue
                raise BisiError(f"网站返回 HTTP {resp.status_code}，未获得正常页面")
            resp.encoding = "utf-8"
            title = page_title(resp.text)
            if title in ("页面重载开启", "頁面重載開啟"):
                if attempt == 3:
                    raise BisiError("网站连续返回重载提示页，无法进入正常页面")
                print(f"🔄 网站要求重载，已接收新 Cookie，2 秒后重新访问（{attempt + 1}/3）")
                time.sleep(2)
                continue
            return resp.text

    def sign_page(self):
        self.authenticated = False
        page = self.loaded_get(SIGN_URL)
        uid = re.search(r"""discuz_uid\s*=\s*['"](\d+)['"]""", page)
        if not uid or int(uid.group(1)) <= 0:
            raise BisiError(f"签到页未确认登录，请检查 Cookie | 页面: {self.redact(page_title(page))}")
        self.authenticated = True
        return page

    def current_money(self):
        page = self.loaded_get(CREDIT_URL)
        match = re.search(r"""<span[^>]*id\s*=\s*["']hcredit_2["'][^>]*>(.*?)</span>""", page, re.I | re.S)
        return plain_text(match.group(1)) if match else None

    def export_cookie(self):
        # 使用当前实际请求会携带的 Cookie，包含更新值并排除已删除/过期项。
        prepared = self.session.prepare_request(requests.Request("GET", SIGN_URL))
        values = parse_cookie(prepared.headers.get("Cookie", ""))
        if not any(name.endswith("_auth") and value for name, value in values.items()):
            raise BisiError("当前会话缺少登录 Cookie，保留面板原值")
        return "; ".join(f"{name}={value}" for name, value in values.items())


def sign_account(client, index):
    page = client.sign_page()
    if has_signed_today(page):
        status = "今日已签到"
    else:
        token = extract_formhash(page)
        if not token:
            if re.search(r"[簽签]到[時时][間间][還还]未[開开]始", plain_text(page)):
                raise BisiError("网站提示已签到或签到时间未开始，但未确认今日签到")
            raise BisiError(f"正常登录页中未找到 formhash | 页面: {client.redact(page_title(page))}")
        post_error = None
        try:
            resp = client.session.post(
                POST_URL, data={"formhash": token, "qdxq": "fd"}, timeout=15, allow_redirects=False
            )
            resp.encoding = "utf-8"
            if resp.status_code != 200:
                post_error = f"签到提交返回 HTTP {resp.status_code}"
            else:
                post_error = client.redact(plain_text(resp.text))[:160]
        except requests.exceptions.RequestException as exc:
            # 请求超时也可能已经处理成功，先复核，避免重复提交。
            post_error = f"签到提交请求异常: {client.redact(exc)}"
        for attempt in range(3):
            time.sleep(2)
            page = client.sign_page()
            if has_signed_today(page):
                break
        else:
            raise BisiError(f"提交后未确认今日签到成功 | 网站提示: {post_error or '无明确提示'}")
        status = "签到成功"
    stats = get_sign_stats(page)
    money_warning = None
    try:
        money = client.current_money()
        if money is None:
            money_warning = "当前金钱未解析到"
    except BisiError as exc:
        money = None
        money_warning = str(exc)
    parts = [
        f"✅ {status}", f"账号{index}",
        f"本月{stats.get('本月签到', '?')}天", f"累计{stats.get('累计签到', '?')}天",
    ]
    if stats.get("上次奖励"):
        label = "上次奖励为" if status == "今日已签到" else "奖励为"
        parts.append(f"{label}: {stats['上次奖励']}")
    parts.append(f"当前金钱: {money if money is not None else '未知'}")
    if money_warning:
        parts.append(f"⚠️ {money_warning}")
    return " | ".join(parts)


def check_ql_result(result):
    if not isinstance(result, dict) or str(result.get("code")) != "200":
        code = result.get("code", "未知") if isinstance(result, dict) else "格式异常"
        raise CookieSyncError(f"青龙接口未确认成功（业务 code={code}）")
    return result.get("data")


class BuiltinQinglong:
    def __init__(self, api):
        self.api = api

    def list_envs(self):
        try:
            return check_ql_result(self.api.getEnvs({"searchValue": "BISI_COOKIE"}))
        except CookieSyncError:
            raise
        except Exception as exc:
            raise CookieSyncError(f"青龙内置查询接口异常（{type(exc).__name__}）") from exc

    def update_env(self, item, value):
        payload = {key: item[key] for key in ("id", "name", "remarks", "status", "position") if key in item}
        payload["value"] = value
        try:
            check_ql_result(self.api.updateEnv({"env": payload}))
        except CookieSyncError:
            raise
        except Exception as exc:
            raise CookieSyncError(f"青龙内置更新接口异常（{type(exc).__name__}）") from exc


class OpenQinglong:
    def __init__(self, base_url, client_id="", client_secret="", access_token=""):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token

    def request(self, method, path, **kwargs):
        headers = {"Authorization": f"Bearer {self.access_token}"} if self.access_token else {}
        try:
            resp = requests.request(
                method, f"{self.base_url}/open{path}", headers=headers,
                timeout=15, allow_redirects=False, **kwargs
            )
            if resp.status_code != 200:
                raise CookieSyncError(f"青龙开放接口返回 HTTP {resp.status_code}")
            return check_ql_result(resp.json())
        except (requests.exceptions.RequestException, ValueError) as exc:
            # 不打印异常 URL/响应，避免暴露查询参数中的应用密钥或变量值。
            raise CookieSyncError(f"青龙开放接口连接或响应异常（{type(exc).__name__}）") from exc

    def authenticate(self):
        if not self.access_token:
            data = self.request("GET", "/auth/token", params={
                "client_id": self.client_id, "client_secret": self.client_secret,
            })
            if not isinstance(data, dict) or not data.get("token"):
                raise CookieSyncError("青龙未返回有效应用 token")
            self.access_token = data["token"]

    def list_envs(self):
        self.authenticate()
        return self.request("GET", "/envs", params={"searchValue": "BISI_COOKIE"})

    def update_env(self, item, value):
        payload = {key: item[key] for key in ("id", "name", "remarks", "labels") if key in item}
        payload["value"] = value
        self.request("PUT", "/envs", json=payload)


def get_qinglong():
    api = globals().get("QLAPI") or getattr(builtins, "QLAPI", None)
    if api is not None and hasattr(api, "getEnvs") and hasattr(api, "updateEnv"):
        return BuiltinQinglong(api)
    token = os.getenv("QL_ACCESS_TOKEN", "").strip()
    client_id = os.getenv("QL_CLIENT_ID", "").strip()
    client_secret = os.getenv("QL_CLIENT_SECRET", "").strip()
    if token or (client_id and client_secret):
        return OpenQinglong(os.getenv("QL_URL", "http://127.0.0.1:5700"), client_id, client_secret, token)
    return None


def panel_envs(panel):
    rows = panel.list_envs()
    if not isinstance(rows, list):
        raise CookieSyncError("青龙环境变量列表格式异常")
    return [
        row for row in rows if isinstance(row, dict) and row.get("name") == "BISI_COOKIE"
        and str(row.get("status", 0)) != "1"
    ]


def sync_cookie(panel, original, updated):
    original_values = parse_cookie(original)
    if original_values == parse_cookie(updated):
        return "未变化"
    matches = []
    for row in panel_envs(panel):
        value = row.get("value")
        if not isinstance(value, str):
            continue
        parts = re.split(r"([&\r\n]+)", value)
        for index in range(0, len(parts), 2):
            if parse_cookie(parts[index]) == original_values:
                matches.append((row, parts, index))
    if len(matches) != 1:
        raise CookieSyncError("未唯一匹配面板原 Cookie，可能已被修改或存在重复配置，保留原值")
    row, parts, index = matches[0]
    if row.get("id") is None:
        raise CookieSyncError("面板变量缺少 id，请检查青龙版本")
    old_value = row["value"]
    # 写入前再读取一次，减少覆盖同时发生的手工修改。
    latest = [item for item in panel_envs(panel) if item.get("id") == row["id"]]
    if len(latest) != 1 or latest[0].get("value") != old_value:
        raise CookieSyncError("面板 Cookie 在运行期间已变化，保留最新面板配置")
    fragment = parts[index]
    leading = fragment[:len(fragment) - len(fragment.lstrip())]
    trailing = fragment[len(fragment.rstrip()):]
    parts[index] = leading + updated + trailing
    new_value = "".join(parts)
    try:
        panel.update_env(latest[0], new_value)
    except CookieSyncError:
        # 写入超时有可能已成功；只读复核，不盲目重复写入。
        current = [item for item in panel_envs(panel) if item.get("id") == row["id"]]
        if len(current) == 1 and current[0].get("value") == new_value:
            return "已更新"
        raise
    current = [item for item in panel_envs(panel) if item.get("id") == row["id"]]
    if len(current) != 1 or current[0].get("value") != new_value:
        raise CookieSyncError("写回后未确认面板值已更新")
    return "已更新"


def main():
    print("【比思论坛签到】多账号任务开始...")
    try:
        cookies = get_all_cookies()
    except BisiError as exc:
        print(f"❌ {exc}")
        return False
    if os.getenv("RANDOM_SIGNIN", "false").lower() == "true":
        try:
            max_delay = int(os.getenv("MAX_RANDOM_DELAY", "3600"))
            if max_delay <= 0:
                raise ValueError()
        except ValueError:
            max_delay = 3600
            print("⚠️ MAX_RANDOM_DELAY 无效，使用 3600 秒")
        delay = random.randint(1, max_delay)
        print(f"⏳ 随机延迟 {delay} 秒...")
        time.sleep(delay)
    results = []
    updates = []
    has_fail = False
    sync_enabled = os.getenv("BISI_SYNC_COOKIE", "true").lower() == "true"
    for index, cookie in enumerate(cookies, 1):
        print(f"\n📌 开始处理第 {index}/{len(cookies)} 个账号")
        client = None
        try:
            with BisiClient(cookie) as client:
                try:
                    line = sign_account(client, index)
                except Exception as exc:
                    has_fail = True
                    line = f"❌ 签到失败 | 账号{index} | {client.redact(exc)}"
                if sync_enabled and client.authenticated:
                    try:
                        updates.append((index, cookie, client.export_cookie()))
                    except BisiError as exc:
                        has_fail = True
                        line += f" | ⚠️ Cookie未同步: {exc}"
        except Exception as exc:
            has_fail = True
            detail = client.redact(exc) if client is not None else "Cookie格式无效或会话创建失败"
            line = f"❌ 签到失败 | 账号{index} | {detail}"
        print(line)
        results.append(line)

    if sync_enabled and updates:
        panel = get_qinglong()
        for index, original, updated in updates:
            try:
                if parse_cookie(original) == parse_cookie(updated):
                    print(f"ℹ️ 账号{index} Cookie未变化，无需写回")
                    continue
                if panel is None:
                    raise CookieSyncError("未注入QLAPI；请配置QL_CLIENT_ID/QL_CLIENT_SECRET及QL_URL")
                status = sync_cookie(panel, original, updated)
                print(f"✅ 账号{index} Cookie同步青龙：{status}")
            except CookieSyncError as exc:
                has_fail = True
                warning = f"⚠️ Cookie同步失败 | 账号{index} | {exc}（本次签到结果不受影响）"
                print(warning)
                results.append(warning)
    elif not sync_enabled:
        print("ℹ️ BISI_SYNC_COOKIE=false，仅在本次会话中更新Cookie")

    print("\n【比思论坛签到】结果汇总：\n" + "\n".join(results))
    always_notify = os.getenv("ALWAYS_NOTIFY", "false").lower() == "true"
    if always_notify or has_fail:
        if send is None:
            print("ℹ️ 推送模块未加载，结果已打印")
        else:
            try:
                send("比思论坛签到", "\n".join(results))
                print("🎉 通知已发送" + ("（存在失败）" if has_fail else "（ALWAYS_NOTIFY=true）"))
            except Exception:
                print("❌ 推送通知异常，请检查通知配置")
                has_fail = True
    else:
        print("✅ 全部签到成功/已签到，ALWAYS_NOTIFY=false，跳过通知")
    print("【比思论坛签到】任务执行完毕")
    return not has_fail


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
