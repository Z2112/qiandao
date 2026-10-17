import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import requests


MODULE_PATH = Path(__file__).resolve().parents[1] / 'script' / 'enshan' / 'api.py'
SPEC = importlib.util.spec_from_file_location('enshan_api_under_test', MODULE_PATH)
api_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api_module)
EnshanAPI = api_module.EnshanAPI

SIGNED_IN_PAGE = '<footer>foo</footer><a href="member.php?mod=logging&amp;action=logout&amp;formhash=abcdef12">退出</a>'


def response(body, status=200):
    result = requests.Response()
    result.status_code = status
    result.url = 'https://www.right.com.cn/forum/erling_qd-sign_in.html'
    result.encoding = 'utf-8'
    result._content = body.encode()
    return result


class EnshanAPITests(unittest.TestCase):
    def setUp(self):
        self.api = EnshanAPI('auth=local-test', formhash='oldhash')

    @patch.object(api_module.requests, 'get')
    def test_normal_html_containing_oo_is_not_a_challenge(self, get):
        get.return_value = response(SIGNED_IN_PAGE)
        self.assertEqual(self.api._refresh_clearance_cookie(), SIGNED_IN_PAGE)
        self.assertEqual(self.api.formhash, 'abcdef12')

    @patch.object(api_module.requests, 'get')
    def test_http_503_is_not_a_successful_clearance(self, get):
        get.return_value = response('<h1>Service Unavailable</h1>', 503)
        self.assertIsNone(self.api._refresh_clearance_cookie())

    @patch.object(api_module.requests, 'get')
    def test_login_page_does_not_reuse_configured_formhash(self, get):
        get.return_value = response('<form action="member.php?mod=logging&amp;action=login"></form>')
        self.assertIsNone(self.api._refresh_clearance_cookie())

    @patch.object(api_module.requests, 'post')
    @patch.object(EnshanAPI, '_sign_in_with_browser')
    @patch.object(EnshanAPI, '_refresh_clearance_cookie', return_value=None)
    def test_browser_fallback_can_be_disabled(self, refresh, browser, post):
        self.api.browser_fallback = False
        self.assertFalse(self.api.sign_in()['success'])
        browser.assert_not_called()
        post.assert_not_called()

    def test_missing_optional_browser_dependency_reports_failure(self):
        with patch.dict('sys.modules', {'playwright.sync_api': None}):
            self.assertIsNone(self.api._refresh_clearance_with_browser())
        self.assertIn('Playwright', self.api._clearance_error)

    def test_browser_inherits_https_proxy_without_credentials_in_server_url(self):
        with patch.object(api_module.requests.utils, 'get_environ_proxies', return_value={
            'https': 'http://example-user:example-pass@proxy.example:8080',
        }):
            options = self.api._browser_launch_options()
        self.assertEqual(options['proxy']['server'], 'http://proxy.example:8080')
        self.assertEqual(options['proxy']['username'], 'example-user')
        self.assertEqual(options['proxy']['password'], 'example-pass')

    def test_browser_honors_no_proxy_for_local_requests(self):
        self.api.sign_in_page_url = 'http://127.0.0.1:8765/forum'
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://proxy.example:8080',
                                     'NO_PROXY': '127.0.0.1'}, clear=True):
            self.assertNotIn('proxy', self.api._browser_launch_options())

    def test_browser_preflight_blocks_post_and_get_account_actions(self):
        for method, query in [('POST', ''), ('GET', '?action=sign'), ('GET', '?action=logout')]:
            with self.subTest(method=method, query=query):
                route = Mock()
                route.request.method = method
                route.request.url = self.api.sign_in_page_url + query
                self.api._route_preflight_request(route)
                route.abort.assert_called_once()
                route.continue_.assert_not_called()

    @patch.object(api_module.requests, 'post')
    @patch.object(EnshanAPI, '_sign_in_with_browser', return_value={'success': False}, create=True)
    @patch.object(EnshanAPI, '_refresh_clearance_cookie', return_value=None)
    def test_failed_clearance_does_not_post_with_stale_formhash(self, refresh, browser, post):
        result = self.api.sign_in()
        self.assertFalse(result['success'])
        post.assert_not_called()

    @patch.object(api_module.requests, 'post')
    @patch.object(api_module.requests, 'get')
    def test_html_error_page_is_not_reported_as_success(self, get, post):
        get.return_value = response(SIGNED_IN_PAGE)
        post.return_value = response('<html><h1>Access denied</h1></html>')
        self.assertFalse(self.api.sign_in()['success'])

    def test_only_advertises_available_compression_decoders(self):
        for headers in [self.api.get_headers(), self.api._get_clearance_headers()]:
            self.assertEqual(headers['Accept-Encoding'], requests.utils.default_headers()['Accept-Encoding'])

    @patch.object(api_module.requests, 'post')
    @patch.object(EnshanAPI, '_sign_in_with_browser')
    @patch.object(EnshanAPI, '_refresh_clearance_cookie', return_value=None)
    def test_browser_recovery_does_not_submit_through_requests(self, refresh, browser, post):
        browser.return_value = {'success': True, 'result': {'credit': 1}}
        self.assertTrue(self.api.sign_in()['success'])
        browser.assert_called_once()
        post.assert_not_called()

    @patch.object(api_module.requests, 'post')
    @patch.object(api_module.requests, 'get')
    def test_http_503_from_post_is_not_retried(self, get, post):
        get.return_value = response(SIGNED_IN_PAGE)
        post.return_value = response('Service Unavailable', 503)
        self.assertFalse(self.api.sign_in()['success'])
        self.assertEqual(post.call_count, 1)


@unittest.skipUnless(os.getenv('ENSHAN_RUN_BROWSER_TESTS') == '1', 'optional real Chromium test')
class BrowserIntegrationTests(unittest.TestCase):
    def test_sign_in_posts_once_inside_verified_browser_session(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import parse_qs
        import threading

        submissions = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if 'local_clearance=ok' in self.headers.get('Cookie', ''):
                    body = SIGNED_IN_PAGE
                else:
                    body = '<script>document.cookie="local_clearance=ok; path=/";location.reload();</script>'
                data = body.encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0'))).decode()
                submissions.append((self.path, self.headers.get('Cookie', ''), parse_qs(body)))
                allowed = ('local_clearance=ok' in self.headers.get('Cookie', '')
                           and parse_qs(body).get('formhash') == ['abcdef12'])
                data = b'{"status":"success","credit":1}' if allowed else b'{}'
                self.send_response(200 if allowed else 503)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = EnshanAPI('auth=local-test', formhash='oldhash')
            client.base_url = f'http://127.0.0.1:{server.server_port}/forum'
            client.sign_in_page_url = client.base_url + '/erling_qd-sign_in.html'
            client.sign_url = client.base_url + '/plugin.php?id=erling_qd:action&action=sign'
            with patch.object(api_module.requests, 'post', side_effect=AssertionError('Must use browser')):
                result = client.sign_in()
            self.assertTrue(result['success'], result)
            self.assertEqual(result['result']['credit'], 1)
            self.assertEqual(len(submissions), 1)
            self.assertIn('auth=local-test', submissions[0][1])
            self.assertIn('local_clearance=ok', submissions[0][1])
            self.assertEqual(submissions[0][2], {'formhash': ['abcdef12']})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_javascript_cookie_and_redirect_are_preserved(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading

        observed_agents = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                observed_agents.append(self.headers.get('User-Agent'))
                if 'local_clearance=ok' in self.headers.get('Cookie', ''):
                    body = SIGNED_IN_PAGE
                else:
                    body = ('<script>document.cookie="local_clearance=ok; path=/";'
                            'document.cookie="old_clearance=; max-age=0; path=/";'
                            'location.reload();</script>')
                data = body.encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = EnshanAPI('auth=local-test; old_clearance=stale', formhash='oldhash')
            client.base_url = f'http://127.0.0.1:{server.server_port}/forum'
            client.sign_in_page_url = client.base_url + '/erling_qd-sign_in.html'
            self.assertIsNotNone(client._refresh_clearance_with_browser())
            self.assertEqual(client.formhash, 'abcdef12')
            self.assertIn('auth=local-test', client.cookies)
            self.assertIn('local_clearance=ok', client.cookies)
            self.assertNotIn('old_clearance', client.cookies)
            self.assertEqual(client.user_agent, observed_agents[-1])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
