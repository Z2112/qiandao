# -*- coding: utf-8 -*-
# cron: 0 8,15 * * *
# new Env('52pojie签到[Python Playwright版]')
# Supported runtime: Windows, Debian or Ubuntu; see docs/52pojie-playwright.md.

import asyncio
import base64
import html
import json
import os
import random
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import requests

try:
    from notify import send
except ImportError:
    send = None

BASE_URL = "https://www.52pojie.cn"
FORUM_URL = f"{BASE_URL}/forum.php"
SIGN_URL = f"{BASE_URL}/home.php?mod=task&do=apply&id=2"
CREDIT_URL = f"{BASE_URL}/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu"
MAX_ATTEMPTS = 3
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"


class SignError(RuntimeError):
    pass


def positive_int(name, default):
    try:
        value = int(os.getenv(name, str(default)))
        if value > 0:
            return value
    except ValueError:
        pass
    print(f"⚠️ {name} 无效，使用 {default}")
    return default


def enabled(name, default="false"):
    return os.getenv(name, default).strip().lower() == "true"


def cookie_batches(raw):
    if not raw.strip():
        raise SignError("未设置 PJ52_COOKIES")
    try:
        parsed = json.loads(raw)
    except ValueError:
        return [part.strip() for part in re.split(r"[&\r\n]+", raw) if part.strip()]
    if isinstance(parsed, list) and parsed and not all(isinstance(item, dict) and "name" in item for item in parsed):
        return parsed
    return [parsed]


def normalize_cookies(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = [
                {"name": name.strip(), "value": value.strip()}
                for name, value in (part.split("=", 1) for part in raw.split(";") if "=" in part)
            ]
    if isinstance(raw, dict):
        raw = [raw] if "name" in raw else [{"name": key, "value": value} for key, value in raw.items()]
    if not isinstance(raw, list) or not raw:
        raise SignError("Cookie 格式无效")
    cookies = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("name") or not isinstance(item.get("value"), str):
            raise SignError("Cookie 项缺少有效 name/value")
        domain = str(item.get("domain") or urlparse(item.get("url", BASE_URL)).hostname or ".52pojie.cn")
        if domain.lstrip(".") != "52pojie.cn" and not domain.lstrip(".").endswith(".52pojie.cn"):
            raise SignError("Cookie 域名不是 52pojie.cn")
        cookie = {
            "name": str(item["name"]), "value": item["value"],
            "domain": domain, "path": item.get("path") or "/",
        }
        for key in ("httpOnly", "secure"):
            if isinstance(item.get(key), bool):
                cookie[key] = item[key]
        expires = item.get("expires", item.get("expirationDate"))
        if isinstance(expires, (int, float)) and expires > 0:
            cookie["expires"] = expires
        same_site = str(item.get("sameSite", "")).lower()
        if same_site in ("strict", "lax", "none", "no_restriction"):
            cookie["sameSite"] = {"strict": "Strict", "lax": "Lax", "none": "None", "no_restriction": "None"}[same_site]
        cookies.append(cookie)
    return cookies


def plain_text(page):
    page = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", page, flags=re.I | re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def is_waf_page(page):
    return "/wzws-waf-cgi/" in page or "Please enable JavaScript and refresh the page" in page


class SignIconParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.icons = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a":
            query = parse_qs(urlparse(html.unescape(values.get("href") or "")).query)
            self.links.append(query.get("mod") == ["task"] and query.get("id") == ["2"])
        if tag == "img" and any(self.links):
            source = values.get("src") or ""
            if re.search(r"(?:^|/)wbs\.png(?:[?#]|$)", source):
                self.icons.append("已签到")
            if re.search(r"(?:^|/)qds\.png(?:[?#]|$)", source):
                self.icons.append("未签到")

    def handle_endtag(self, tag):
        if tag == "a" and self.links:
            self.links.pop()


def classify_status(page):
    if is_waf_page(page):
        return "未知"
    uid = re.search(r"""discuz_uid\s*=\s*['"]?(\d+)""", page)
    if uid and int(uid.group(1)) == 0:
        return "Cookie失效"
    if not uid or int(uid.group(1)) <= 0:
        return "未知"
    parser = SignIconParser()
    parser.feed(page)
    if "已签到" in parser.icons:
        return "已签到"
    if "未签到" in parser.icons:
        return "未签到"
    signed = bool(re.search(r"""src\s*=\s*['"][^'"]*/wbs\.png(?:[?'"]|$)""", page))
    unsigned = bool(re.search(r"""src\s*=\s*['"][^'"]*/qds\.png(?:[?'"]|$)""", page))
    if signed != unsigned:
        return "已签到" if signed else "未签到"
    return "未知"


class Account:
    def __init__(self, raw):
        self.cookies = normalize_cookies(raw)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = DEFAULT_UA
        self.merge_cookies(self.cookies)

    def merge_cookies(self, cookies):
        for cookie in cookies:
            domain = str(cookie.get("domain", ".52pojie.cn"))
            if domain.lstrip(".") == "52pojie.cn" or domain.lstrip(".").endswith(".52pojie.cn"):
                kwargs = {}
                if cookie.get("expires", -1) > 0:
                    kwargs["expires"] = int(cookie["expires"])
                self.session.cookies.set(cookie["name"], cookie["value"], domain=domain, path=cookie.get("path", "/"), **kwargs)
        self.cookies = cookies

    def redact(self, error):
        text = str(error)
        secrets = [cookie.value for cookie in self.session.cookies] + [os.getenv("LLM_API_KEY", "")]
        for value in secrets:
            if len(value) > 4:
                text = text.replace(value, "[已隐藏]")
        return " ".join(text.split())[:300]

    def get(self, url):
        response = self.session.get(url, timeout=15)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text

    async def status(self):
        try:
            return classify_status(await asyncio.to_thread(self.get, FORUM_URL))
        except requests.RequestException as error:
            print(f"⚠️ 状态检查异常: {self.redact(error)}")
            return "未知"

    async def credits(self):
        try:
            page = await asyncio.to_thread(self.get, CREDIT_URL)
            match = re.search(r">\s*([\d,]+)\s*CB\s*</span>", page, re.I)
            return int(match.group(1).replace(",", "")) if match else None
        except requests.RequestException as error:
            print(f"⚠️ 吾爱币读取异常: {self.redact(error)}")
            return None

    def close(self):
        self.session.close()


async def stage(name, awaitable, seconds=30):
    print(f"  → {name}")
    try:
        return await asyncio.wait_for(awaitable, timeout=seconds)
    except asyncio.TimeoutError as error:
        raise SignError(f"{name}超时；浏览器或任务页脚本未响应") from error


async def capture_page(page):
    return await stage("读取页面内容", page.content(), positive_int("PJ52_CONTENT_TIMEOUT", 20))


async def wait_for_site(page):
    for _ in range(6):
        content = await capture_page(page)
        if not is_waf_page(content):
            return content
        print("  检测到 WZWS 防护页，等待网站验证完成...")
        await asyncio.sleep(2)
    raise SignError("WZWS 网站验证未完成，不能确认签到")


def neutralize_challenge(source):
    return source.replace("'while\\x20(true)\\x20{}'", "'return'").replace("'debu'+'gger'", "'return'")


async def install_challenge_route(page, state):
    async def handle(route):
        request = route.request
        if request.resource_type != "document" or "52pojie.cn" not in request.url:
            await route.continue_()
            return
        try:
            fetched = await route.fetch()
            body = await fetched.body()
        except Exception as error:
            print(f"  读取文档响应失败: {type(error).__name__}")
            await route.continue_()
            return
        if b"waf_zw_verify" not in body:
            await route.fulfill(response=fetched)
            return
        state["challenge"] = True
        print("  已跳过防护页调试陷阱")
        await route.fulfill(response=fetched, body=neutralize_challenge(body.decode("utf-8", "replace")))

    def on_response(response):
        if state["verify"] is None and "/waf_zw_verify" in response.url:
            state["verify"] = response
            return
        if state["verify"] is not None and state["redirect"] is None and response.request.resource_type == "document":
            state["redirect"] = response

    page.on("response", on_response)
    await page.route("**/*", handle)


async def finish_challenge(state):
    print("  检测到 WZWS 防护页，等待浏览器完成验证...")
    for ticks in range(240):
        if state["verify"] is not None:
            break
        await asyncio.sleep(0.5)
        if ticks and ticks % 30 == 0:
            print(f"  仍在等待防护校验，已等待 {ticks // 2} 秒...")
    verify = state["verify"]
    if verify is None:
        raise SignError("WZWS 网站验证未完成，不能确认签到")
    print(f"  防护校验响应 HTTP {verify.status}")
    if verify.status != 200:
        raise SignError(f"WZWS 校验返回 HTTP {verify.status}")
    for _ in range(60):
        if state["redirect"] is not None:
            break
        await asyncio.sleep(0.5)
    redirect = state["redirect"]
    if redirect is None:
        raise SignError("WZWS 校验已通过，但页面没有跳转")
    print(f"  验证后页面响应 HTTP {redirect.status}")
    content = await redirect.text()
    if is_waf_page(content):
        raise SignError("WZWS 网站验证未完成，不能确认签到")
    return content


async def open_through_waf(page, url, label, state):
    print(f"  {label}")
    state["challenge"] = False
    state["verify"] = None
    state["redirect"] = None
    response = await stage(label, page.goto(url, wait_until="domcontentloaded", timeout=60000), 65)
    if response is not None:
        print(f"  网站响应 HTTP {response.status}")
        if response.status >= 400:
            raise SignError(f"页面返回 HTTP {response.status}")
    if state["challenge"]:
        return await finish_challenge(state)
    if response is not None:
        try:
            content = await response.text()
        except Exception as error:
            print(f"  读取原始响应失败: {type(error).__name__}")
            content = ""
        if content and not is_waf_page(content):
            return content
    return await wait_for_site(page)


async def find_captcha(page, content):
    if not re.search(r"IP:|验证码|驗證碼|captcha|seccode", content, re.I):
        return None
    inputs = page.locator('input[type="text"], input:not([type])')
    for index in range(min(await inputs.count(), 15)):
        field = inputs.nth(index)
        if not await field.is_visible():
            continue
        name = (await field.get_attribute("name") or await field.get_attribute("id") or "").lower()
        if name in ("srchtxt", "search", "q", "username", "password", "email"):
            continue
        form = field.locator("xpath=ancestor::form[1]")
        scope = form if await form.count() else page
        images = scope.locator('img[src*="captcha" i], img[src*="verify" i], img[src*="seccode" i], img[id*="captcha" i]')
        if not await images.count():
            candidates = scope.locator("img")
            if await candidates.count() == 1:
                images = candidates
        if not await images.count() or not await images.first.is_visible():
            continue
        submit = scope.locator('button[type="submit"], input[type="submit"]')
        if not await submit.count():
            submit = scope.locator("button")
        if await submit.count() and await submit.first.is_visible():
            return images.first, field, submit.first
    return None


def recognize_captcha(image):
    base_url = os.getenv("LLM_API_URL", "").rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "")
    if not base_url or not api_key:
        raise SignError("验证码页面需要 LLM_API_URL 和 LLM_API_KEY")
    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    payload = {
        "model": os.getenv("LLM_MODEL", "gpt-4o"),
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "请只返回图片中的验证码字符，不要解释或标点。"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(image).decode()}},
        ]}],
        "max_tokens": 32,
    }
    try:
        response = requests.post(endpoint, json=payload, headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
        response.raise_for_status()
        data = response.json()
        answer = data["choices"][0]["message"]["content"].strip().strip("\"'" + chr(96))
        answer = re.sub(r"\s+", "", answer)
        if not re.fullmatch(r"[A-Za-z0-9]{3,10}", answer):
            raise ValueError("invalid captcha characters")
        usage = data.get("usage") or {}
        print(f"  🔥 模型 tokens: {usage.get('total_tokens', '未知')}")
        return answer
    except (requests.RequestException, KeyError, ValueError, TypeError, IndexError, AttributeError) as error:
        raise SignError(f"大模型识别未返回可用验证码（{type(error).__name__}）") from error


def launch_options():
    options = {"headless": True, "timeout": 30000}
    browser_name = os.getenv("PJ52_BROWSER", "chromium").strip().lower()
    if sys.platform.startswith("linux") and browser_name == "chromium":
        options["args"] = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
    path = os.getenv("PLAYWRIGHT_BROWSER_PATH", os.getenv("CHROME_PATH", "") if browser_name == "chromium" else "").strip()
    if path:
        options["executable_path"] = path
    return options


async def browser_attempt(playwright, account):
    browser = context = None
    try:
        endpoint = os.getenv("PLAYWRIGHT_WS_ENDPOINT", "").strip()
        browser_name = os.getenv("PJ52_BROWSER", "chromium").strip().lower()
        if browser_name not in ("chromium", "firefox", "webkit"):
            raise SignError("PJ52_BROWSER 只能是 chromium、firefox 或 webkit")
        browser_type = getattr(playwright, browser_name)
        browser = await stage("启动 Playwright 浏览器", browser_type.connect(endpoint) if endpoint else browser_type.launch(**launch_options()), 40)
        context = await stage("创建账号浏览器会话", browser.new_context())
        context.set_default_timeout(15000)
        context.set_default_navigation_timeout(60000)
        await stage("载入 Cookie", context.add_cookies(account.cookies))
        page = await stage("创建页面", context.new_page())
        challenge = {"challenge": False, "verify": None, "redirect": None}
        await install_challenge_route(page, challenge)
        await open_through_waf(page, FORUM_URL, "打开论坛首页", challenge)
        content = await open_through_waf(page, SIGN_URL, "打开签到任务页", challenge)
        pair = await stage("检查验证码表单", find_captcha(page, content), 20)
        if pair is not None:
            image, field, submit = pair
            print("  检测到验证码，调用大模型识别...")
            png = await stage("截取验证码图片", image.screenshot(timeout=15000), 20)
            code = await asyncio.to_thread(recognize_captcha, png)
            await stage("填写验证码", field.fill(code, timeout=15000), 20)
            await stage("提交验证表单", submit.click(timeout=15000), 20)
            await asyncio.sleep(3)
            content = await wait_for_site(page)
        await stage("同步浏览器会话 Cookie", synchronize_context(context, account), 10)
        status = await account.status()
        if status == "已签到":
            return True
        visible = plain_text(content)
        if re.search(r"签到成功|任务已(?:成功)?完成|任务已经(?:成功)?完成", visible):
            return True
        if status == "Cookie失效":
            raise SignError("Cookie 已失效，请重新登录获取")
        raise SignError("任务页未显示成功，接口复核也未确认已签到")
    finally:
        if context is not None:
            try:
                await asyncio.wait_for(synchronize_context(context, account), 5)
            except Exception:
                pass
            try:
                await asyncio.wait_for(context.close(), 8)
            except Exception:
                print("⚠️ 浏览器会话关闭超时，将关闭本次浏览器")
        if browser is not None:
            try:
                await asyncio.wait_for(browser.close(), 8)
            except Exception:
                print("⚠️ 浏览器关闭未确认，由 Playwright 驱动结束时清理")


async def synchronize_context(context, account):
    account.merge_cookies(await context.cookies([BASE_URL]))


@dataclass
class Result:
    line: str
    failed: bool = False


async def process_account(raw, index, playwright_factory=None):
    account = None
    try:
        account = Account(raw)
        status = await account.status()
        print(f"\n📌 账号{index} | 当前状态: {status}")
        if status == "Cookie失效":
            raise SignError("Cookie 已失效，请重新登录获取")
        before = await account.credits()
        if status == "已签到":
            return Result(f"✅ 今日已签到 | 账号{index} | 吾爱币: {before if before is not None else '未知'}")
        if playwright_factory is None:
            try:
                from playwright.async_api import async_playwright
            except ImportError as error:
                raise SignError("未安装 playwright；请在受支持的运行环境安装依赖及浏览器") from error
            playwright_factory = async_playwright
        last_error = "未执行签到"
        async with playwright_factory() as playwright:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                print(f"\n🔄 签到尝试 {attempt}/{MAX_ATTEMPTS}")
                success = False
                try:
                    success = await browser_attempt(playwright, account)
                except Exception as error:
                    last_error = account.redact(error)
                    print(f"⚠️ 本次尝试失败: {last_error}")
                if not success:
                    success = await account.status() == "已签到"
                if success:
                    after = await account.credits()
                    reward = f" | 本次获得 {after - before} 吾爱币" if before is not None and after is not None and after > before else ""
                    return Result(f"✅ 签到成功 | 账号{index}{reward} | 当前吾爱币: {after if after is not None else '未知'}")
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(2)
        raise SignError(f"{last_error}（已尝试 {MAX_ATTEMPTS} 次）")
    except Exception as error:
        detail = account.redact(error) if account is not None else "Cookie 格式无效"
        return Result(f"❌ 签到失败 | 账号{index} | {detail}", True)
    finally:
        if account is not None:
            account.close()


async def main():
    print("=== 52pojie 签到开始（Python + Playwright）===")
    try:
        accounts = cookie_batches(os.getenv("PJ52_COOKIES", ""))
    except SignError as error:
        print(f"❌ {error}")
        return False
    if enabled("RANDOM_SIGNIN"):
        delay = random.randint(1, positive_int("MAX_RANDOM_DELAY", 3600))
        print(f"⏳ 随机延迟 {delay} 秒...")
        await asyncio.sleep(delay)
    results = []
    for index, raw in enumerate(accounts, 1):
        results.append(await process_account(raw, index))
    summary = "\n".join(result.line for result in results)
    print("\n" + summary)
    has_fail = any(result.failed for result in results)
    if enabled("PJ52_DEBUG_NO_NOTIFY"):
        print("ℹ️ 本次调试未发送通知")
    elif enabled("ALWAYS_NOTIFY") or has_fail:
        if send is None:
            print("ℹ️ notify 模块未加载，结果已打印")
        else:
            try:
                timestamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                await asyncio.to_thread(send, "52pojie 签到通知", f"{summary}\n\n时间：{timestamp}")
                print("🎉 通知已发送")
            except Exception:
                print("❌ 推送通知异常，请检查通知配置")
                has_fail = True
    else:
        print("✅ 全部签到成功/已签到，ALWAYS_NOTIFY=false，跳过通知")
    print("=== 签到结束 ===")
    return not has_fail


if __name__ == "__main__":
    for output in (sys.stdout, sys.stderr):
        if hasattr(output, "reconfigure"):
            output.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(0 if asyncio.run(main()) else 1)
