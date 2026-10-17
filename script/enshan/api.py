#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
恩山论坛API模块

提供恩山论坛签到相关的API接口
"""

import json
import logging
import os
import re
import shutil
from typing import Dict, Optional, List
from urllib.parse import parse_qs, unquote, urlsplit

import requests

logger = logging.getLogger(__name__)


class EnshanAPI:
    """恩山论坛API类"""

    def __init__(self, cookies: str, formhash: Optional[str] = None, user_agent: Optional[str] = None,
                 browser_fallback: bool = True):
        """
        初始化API类

        Args:
            cookies: 用户的Cookie字符串
            formhash: 表单hash值，用于验证请求（可选，自动获取）
            user_agent: 用户代理字符串，可选
            browser_fallback: 普通请求无法确认登录时，尝试已安装的Playwright浏览器
        """
        self.cookies = cookies
        self.formhash = formhash or ""
        self.browser_fallback = browser_fallback
        self._clearance_error = ""
        self._custom_user_agent = bool(user_agent)
        self.user_agent = user_agent or (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/144.0.0.0 Safari/537.36'
        )
        self.sign_url = 'https://www.right.com.cn/forum/plugin.php?id=erling_qd:action&action=sign'
        self.sign_in_page_url = 'https://www.right.com.cn/forum/erling_qd-sign_in.html'
        self.base_url = 'https://www.right.com.cn/forum'

    @staticmethod
    def _rotl8(x: int, r: int) -> int:
        """8-bit rotate left."""
        x &= 0xFF
        r &= 7
        return ((x << r) & 0xFF) | (x >> (8 - r))

    @staticmethod
    def _rotr8(x: int, r: int) -> int:
        """8-bit rotate right."""
        x &= 0xFF
        r &= 7
        return (x >> r) | ((x << (8 - r)) & 0xFF)

    @staticmethod
    def _extract_oo(html: str) -> Optional[List[int]]:
        match = re.search(r"oo\s*=\s*\[([^\]]+)\]", html)
        if not match:
            return None
        tokens = re.findall(r"0x[0-9a-fA-F]+|\d+", match.group(1))
        if not tokens:
            return None
        values = []
        for token in tokens:
            if token.lower().startswith("0x"):
                values.append(int(token, 16))
            else:
                values.append(int(token))
        return values

    @staticmethod
    def _extract_wi(html: str) -> Optional[int]:
        match = re.search(r'setTimeout\("\w+\((\d+)\)"', html)
        if match:
            return int(match.group(1))
        match = re.search(r"\b\w+\((\d+)\)", html)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _extract_loop1_params(html: str) -> Optional[Dict[str, int]]:
        pattern = (
            r"qo\s*=\s*(\d+);\s*do\{.*?oo\[qo\]=\(-oo\[qo\]\)&0xff;.*?"
            r"oo\[qo\]=\(\(\(oo\[qo\]>>(\d+)\)\|\(\(oo\[qo\]<<(\d+)\)&0xff\)\)\-(\d+)\)&0xff;.*?"
            r"\}\s*while\(--qo>=2\);"
        )
        match = re.search(pattern, html, re.S)
        if not match:
            return None
        return {
            "start": int(match.group(1)),
            "shift_r": int(match.group(2)),
            "shift_l": int(match.group(3)),
            "sub": int(match.group(4)),
        }

    @staticmethod
    def _extract_loop2_start(html: str) -> Optional[int]:
        match = re.search(
            r"qo\s*=\s*(\d+);\s*do\s*\{[^}]*?oo\[qo\]\s*=\s*\(oo\[qo\]\s*-\s*oo\[qo\s*-\s*1\]\)\s*&\s*0xff;[^}]*?\}\s*while\s*\(\s*--\s*qo\s*>=\s*3\s*\)",
            html,
            re.S,
        )
        if not match:
            return None
        return int(match.group(1))

    @staticmethod
    def _extract_loop3_params(html: str) -> Optional[Dict[str, int]]:
        block_match = re.search(
            r"qo\s*=\s*1;\s*for\s*\(.*?\)\s*\{(.*?)\}\s*po\s*=",
            html,
            re.S,
        )
        if not block_match:
            return None
        block = block_match.group(1)

        upper_match = re.search(r"qo\s*>\s*(\d+)\)\s*break", block)
        if not upper_match:
            return None
        upper = int(upper_match.group(1))

        assign_match = re.search(r"oo\[qo\]\s*=\s*(.+?);", block, re.S)
        if not assign_match:
            return None
        expr = assign_match.group(1)

        add_nums = re.findall(r"\+\s*(\d+)", expr)
        if len(add_nums) < 2:
            return None
        add1 = int(add_nums[0])
        add2 = int(add_nums[1])

        shift_nums = re.findall(r"<<\s*(\d+)|>>\s*(\d+)", expr)
        shifts = []
        for left, right in shift_nums:
            if left:
                shifts.append(int(left))
            if right:
                shifts.append(int(right))
        if len(shifts) < 2:
            return None
        rot_l = shifts[0]
        return {
            "upper": upper,
            "add1": add1,
            "add2": add2,
            "rot_l": rot_l,
        }

    @staticmethod
    def _extract_mod_skip(html: str) -> int:
        match = re.search(r"qo\s*%\s*(\d+)", html)
        if not match:
            return 7
        return int(match.group(1))

    def _decode_po(self, oo_hex: List[int], wi: int, params: Dict[str, int]) -> str:
        oo = [b & 0xFF for b in oo_hex]
        if len(oo) < 6:
            return ""

        last_index = len(oo) - 1

        loop1_start = params["loop1_start"]
        loop2_start = params["loop2_start"]
        loop3_upper = params["loop3_upper"]
        shift_r = params["shift_r"]
        shift_l = params["shift_l"]
        sub = params["sub"]
        add1 = params["add1"]
        add2 = params["add2"]
        rot_l = params["rot_l"]
        mod_skip = params["mod_skip"]

        qo = min(loop1_start, last_index - 1)
        while True:
            oo[qo] = (-oo[qo]) & 0xFF
            if (shift_r + shift_l) == 8:
                oo[qo] = (self._rotr8(oo[qo], shift_r) - sub) & 0xFF
            else:
                oo[qo] = (((oo[qo] >> shift_r) | ((oo[qo] << shift_l) & 0xFF)) - sub) & 0xFF
            qo -= 1
            if qo < 2:
                break

        qo = min(loop2_start, last_index - 2)
        while True:
            oo[qo] = (oo[qo] - oo[qo - 1]) & 0xFF
            qo -= 1
            if qo < 3:
                break

        for qo in range(1, min(loop3_upper, last_index - 1) + 1):
            x = (oo[qo] + add1) & 0xFF
            x = (x + add2) & 0xFF
            oo[qo] = self._rotl8(x, rot_l)

        po_chars = []
        for qo in range(1, last_index):
            if qo % mod_skip != 0:
                po_chars.append(chr((oo[qo] ^ (wi & 0xFF)) & 0xFF))

        return "".join(po_chars)

    @staticmethod
    def _extract_cookie_kv(decoded_js: str) -> Optional[str]:
        match = re.search(r"document\.cookie=['\"]([^'\"]+)['\"]", decoded_js)
        if not match:
            return None
        cookie_str = match.group(1).strip()
        if not cookie_str:
            return None
        return cookie_str.split(';', 1)[0].strip()

    @staticmethod
    def _upsert_cookie(base_cookies: str, new_cookie_kv: str) -> str:
        if not new_cookie_kv or '=' not in new_cookie_kv:
            return base_cookies
        new_key, new_value = new_cookie_kv.split('=', 1)
        new_key = new_key.strip()
        new_value = new_value.strip()

        parts = []
        replaced = False
        for raw in base_cookies.split(';'):
            part = raw.strip()
            if not part or '=' not in part:
                continue
            key, value = part.split('=', 1)
            key = key.strip()
            if key == new_key:
                parts.append(f"{new_key}={new_value}")
                replaced = True
            else:
                parts.append(f"{key}={value.strip()}")

        if not replaced:
            parts.append(f"{new_key}={new_value}")

        return '; '.join(parts)

    @staticmethod
    def _extract_formhash(html: str) -> Optional[str]:
        match = re.search(
            r"member\.php\?mod=logging(?:&amp;|&)action=logout(?:&amp;|&)formhash=([0-9a-fA-F]+)",
            html,
        )
        if not match:
            return None
        return match.group(1)

    def _get_clearance_headers(self) -> Dict[str, str]:
        return {
            'User-Agent': self.user_agent,
            'Accept': (
                'text/html,application/xhtml+xml,application/xml;q=0.9,'
                'image/avif,image/webp,image/apng,*/*;q=0.8'
            ),
            'Accept-Encoding': requests.utils.default_headers()['Accept-Encoding'],
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Brave";v="144"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'Upgrade-Insecure-Requests': '1',
            'Sec-GPC': '1',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Sec-Fetch-Dest': 'document',
            'Referer': self.sign_in_page_url,
            'Cookie': self.cookies
        }

    def _merge_response_cookies(self, response: requests.Response) -> None:
        for name, value in response.cookies.items():
            self.cookies = self._upsert_cookie(self.cookies, f"{name}={value}")

    def _clearance_failed(self, reason: str) -> None:
        self._clearance_error = reason
        logger.warning(reason)

    def _accept_sign_in_page(self, response: requests.Response) -> Optional[str]:
        if not 200 <= response.status_code < 300:
            return self._clearance_failed(f"签到页面返回HTTP {response.status_code}，未通过页面验证")
        formhash = self._extract_formhash(response.text)
        if not formhash:
            return self._clearance_failed("签到页面未确认登录，可能是Cookie失效或仍处于WAF验证")
        self.formhash = formhash
        self._clearance_error = ""
        return response.text

    def _refresh_clearance_cookie(self) -> Optional[str]:
        try:
            response = requests.get(
                self.sign_in_page_url,
                headers=self._get_clearance_headers(),
                timeout=30
            )
        except requests.RequestException as exc:
            return self._clearance_failed(f"获取签到页面失败（{type(exc).__name__}）")
        self._merge_response_cookies(response)

        # footer、Cookie等普通页面文本也可能包含oo；只有赋值语句才进入旧版解码器。
        if not re.search(r"\boo\s*=\s*\[", response.text):
            return self._accept_sign_in_page(response)

        oo = self._extract_oo(response.text)
        wi = self._extract_wi(response.text)
        if not oo or wi is None:
            return self._clearance_failed("WAF响应解析失败，无法提取解密参数")

        loop1 = self._extract_loop1_params(response.text)
        loop2_start = self._extract_loop2_start(response.text)
        loop3 = self._extract_loop3_params(response.text)
        if not loop1 or loop2_start is None or not loop3:
            return self._clearance_failed("WAF解密参数提取失败")

        mod_skip = self._extract_mod_skip(response.text)
        params = {
            "loop1_start": loop1["start"],
            "loop2_start": loop2_start,
            "loop3_upper": loop3["upper"],
            "shift_r": loop1["shift_r"],
            "shift_l": loop1["shift_l"],
            "sub": loop1["sub"],
            "add1": loop3["add1"],
            "add2": loop3["add2"],
            "rot_l": loop3["rot_l"],
            "mod_skip": mod_skip,
        }

        try:
            decoded_js = self._decode_po(oo, wi, params)
        except (ValueError, IndexError, ArithmeticError):
            return self._clearance_failed("WAF参数格式不受支持，无法使用旧版解码器")
        cookie_kv = self._extract_cookie_kv(decoded_js)
        if not cookie_kv:
            return self._clearance_failed("WAF解密成功但未找到cookie")

        self.cookies = self._upsert_cookie(self.cookies, cookie_kv)
        logger.info("已获取并更新 https_ydclearance cookie")

        try:
            follow = requests.get(
                self.sign_in_page_url,
                headers=self._get_clearance_headers(),
                timeout=30
            )
        except requests.RequestException as exc:
            return self._clearance_failed(f"WAF处理后获取签到页面失败（{type(exc).__name__}）")
        self._merge_response_cookies(follow)
        return self._accept_sign_in_page(follow)

    def _browser_launch_options(self) -> Dict:
        executable = (os.getenv('ENSHAN_BROWSER_PATH') or os.getenv('CHROME_PATH')
                      or shutil.which('chromium') or shutil.which('chromium-browser'))
        options = {
            'headless': True,
            'timeout': 30000,
            'args': ['--no-sandbox', '--disable-dev-shm-usage'],
        }
        if executable:
            options['executable_path'] = executable
        # Chromium不会自动采用requests使用的环境代理；也要尊重NO_PROXY。
        proxies = requests.utils.get_environ_proxies(self.sign_in_page_url)
        proxy_url = proxies.get(urlsplit(self.sign_in_page_url).scheme) or proxies.get('all')
        if proxy_url:
            parsed = urlsplit(proxy_url if '://' in proxy_url else 'http://' + proxy_url)
            if not parsed.hostname:
                raise ValueError('Invalid browser proxy configuration')
            host = f'[{parsed.hostname}]' if ':' in parsed.hostname else parsed.hostname
            server = f'{parsed.scheme}://{host}'
            if parsed.port is not None:
                server += f':{parsed.port}'
            proxy = {'server': server}
            if parsed.username is not None:
                proxy['username'] = unquote(parsed.username)
            if parsed.password is not None:
                proxy['password'] = unquote(parsed.password)
            options['proxy'] = proxy
        return options

    @staticmethod
    def _route_preflight_request(route) -> None:
        request = route.request
        query = parse_qs(urlsplit(request.url).query)
        account_action = any(value in ('sign', 'logout') for value in query.get('action', []))
        account_action = account_action or 'qiandao' in query.get('operation', [])
        if request.method not in ('GET', 'HEAD') or account_action:
            route.abort()
        else:
            route.continue_()

    def _refresh_clearance_with_browser(self) -> Optional[str]:
        """可选浏览器回退；仅访问签到页面，确认登录后同步Cookie和formhash。"""
        return self._browser_session()

    def _browser_session(self, action=None):
        """保持已验证的浏览器会话，按需在关闭之前执行调用方操作。"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return self._clearance_failed(
                "浏览器回退需要Playwright：请安装playwright和Chromium，详见script/enshan/README.md"
            )

        logger.info("普通请求未能确认登录，尝试Playwright浏览器处理签到页面")
        phase = '启动浏览器'
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(**self._browser_launch_options())
                try:
                    # 未指定UA时使用真实浏览器默认值，避免旧版伪装UA与浏览器指纹矛盾。
                    context = browser.new_context(**(
                        {'user_agent': self.user_agent} if self._custom_user_agent else {}
                    ))
                    # 预检只读：拦截写请求及签到/退出，实际签到由调用方随后提交。
                    context.route('**/*', self._route_preflight_request)
                    cookies = []
                    cookie_url = urlsplit(self.base_url)._replace(path='/', query='', fragment='').geturl()
                    for part in self.cookies.split(';'):
                        name, separator, value = part.strip().partition('=')
                        if separator and name:
                            cookies.append({'name': name, 'value': value, 'url': cookie_url})
                    context.add_cookies(cookies)
                    page = context.new_page()
                    phase = '打开签到页面'
                    page.goto(self.sign_in_page_url, wait_until='domcontentloaded', timeout=45000)
                    # 等待防护脚本跳转结束，不能只凭浏览器启动或页面HTTP 200判断成功。
                    phase = '等待登录标志'
                    page.wait_for_function(
                        """() => Array.from(document.querySelectorAll('a[href]')).some(a =>
                            a.href.includes('action=logout') && a.href.includes('formhash='))""",
                        timeout=30000,
                    )
                    html = page.content()
                    formhash = self._extract_formhash(html)
                    if not formhash:
                        return self._clearance_failed("浏览器页面未获取到有效formhash，未确认登录")
                    # 使用浏览器实际会发送的Cookie，也移除被防护脚本删除的旧值。
                    self.cookies = '; '.join(
                        f"{cookie['name']}={cookie['value']}"
                        for cookie in context.cookies([self.sign_in_page_url])
                    )
                    self.user_agent = page.evaluate('navigator.userAgent')
                    self.formhash = formhash
                    self._clearance_error = ""
                    logger.info("浏览器已确认登录并同步当前会话")
                    if action is not None:
                        phase = '浏览器内提交签到'
                        return action(context, page)
                    return html
                finally:
                    browser.close()
        except Exception as exc:
            # 不记录页面、Cookie或可能包含敏感信息的浏览器异常详情。
            return self._clearance_failed(
                f"浏览器未能确认登录（{phase}/{type(exc).__name__}）；请检查Chromium安装、站点访问及Cookie有效性"
            )

    def _submit_browser_sign_in(self, context, page) -> Dict:
        submitted = False

        def allow_one_submission(route):
            nonlocal submitted
            if route.request.method == 'POST' and not submitted:
                submitted = True
                route.continue_()
            else:
                route.abort()

        # 只放行本次明确的签到POST，其他写请求仍被预检规则拦截。
        context.route(re.compile('^' + re.escape(self.sign_url) + '$'), allow_one_submission)
        result = page.evaluate("""async ({url, formhash}) => {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 30000);
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: new URLSearchParams({formhash}).toString(),
                    signal: controller.signal
                });
                return {status: response.status, text: await response.text()};
            } finally {
                clearTimeout(timer);
            }
        }""", {'url': self.sign_url, 'formhash': self.formhash})
        return self._parse_sign_response(result['status'], result['text'])

    def _sign_in_with_browser(self) -> Dict:
        result = self._browser_session(action=self._submit_browser_sign_in)
        if isinstance(result, dict):
            return result
        return {'success': False,
                'error': f"浏览器签到失败：{self._clearance_error or '未确认接口结果'}"}

    @staticmethod
    def _parse_sign_response(status: int, text: str) -> Dict:
        if not 200 <= status < 300:
            return {'success': False, 'error': f'签到接口返回HTTP {status}，未确认签到成功'}
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            return {'success': False,
                    'error': '签到接口返回非JSON响应，可能是防护或登录页面，未确认签到成功'}
        if not isinstance(result, dict):
            return {'success': False, 'error': '签到接口返回格式异常，未确认签到成功'}
        if result.get('success') is False or result.get('status') in ('error', 'fail', 'failed'):
            return {'success': False, 'error': '签到接口返回失败状态，未确认签到成功'}
        logger.info('恩山论坛签到接口已返回成功结果')
        return {'success': True, 'result': result}

    def get_headers(self) -> Dict[str, str]:
        """
        获取请求头

        Returns:
            Dict[str, str]: 请求头字典
        """
        return {
            'User-Agent': self.user_agent,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Encoding': requests.utils.default_headers()['Accept-Encoding'],
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'sec-ch-ua-platform': '"macOS"',
            'X-Requested-With': 'XMLHttpRequest',
            'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Brave";v="144"',
            'sec-ch-ua-mobile': '?0',
            'Sec-GPC': '1',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Origin': 'https://www.right.com.cn',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Referer': self.sign_in_page_url,
            'Cookie': self.cookies
        }

    def sign_in(self) -> Dict:
        """
        执行签到

        Returns:
            Dict: 签到结果
                {
                    'success': bool,  # 是否成功
                    'result': dict,   # 成功时的结果数据
                    'error': str      # 失败时的错误信息
                }
        """
        logger.info("开始执行恩山论坛签到...")
        page = self._refresh_clearance_cookie()
        if page is None and self.browser_fallback:
            return self._sign_in_with_browser()
        if page is None or not self.formhash:
            error_msg = f"签到前页面验证失败：{self._clearance_error or '未获取到有效formhash'}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
        headers = self.get_headers()
        data = {
            'formhash': self.formhash
        }
        try:
            response = requests.post(
                self.sign_url,
                headers=headers,
                data=data,
                timeout=30
            )

            # 检查响应状态
            response.raise_for_status()

            return self._parse_sign_response(response.status_code, response.text)

        except requests.RequestException as e:
            error_msg = f"签到失败: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def get_user_info(self) -> Dict:
        """
        获取用户信息（可选功能）

        Returns:
            Dict: 用户信息
        """
        # 这里可以添加获取用户信息的逻辑
        # 目前返回空字典
        return {}
