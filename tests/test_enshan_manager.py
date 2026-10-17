import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
api_spec = importlib.util.spec_from_file_location('enshan_manager_test_api', ROOT / 'script/enshan/api.py')
api = importlib.util.module_from_spec(api_spec)
api_spec.loader.exec_module(api)
manager_spec = importlib.util.spec_from_file_location('enshan_manager_under_test', ROOT / 'script/enshan/sign_in.py')
manager = importlib.util.module_from_spec(manager_spec)
with patch.dict(sys.modules, {'api': api}), patch.object(sys, 'path', list(sys.path)):
    manager_spec.loader.exec_module(manager)


class EnshanManagerTests(unittest.TestCase):
    def test_environment_accounts_do_not_require_original_project_config(self):
        with patch.dict(os.environ, {'ENSHAN_COOKIE': 'auth=local-one&Cookie: auth=local-two'}):
            with patch('builtins.open', side_effect=AssertionError('No config file needed')):
                instance = manager.EnshanSignInManager()
        self.assertEqual([item['cookies'] for item in instance.accounts],
                         ['auth=local-one', 'auth=local-two'])

    def test_explicit_config_path_keeps_file_based_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'token.json'
            path.write_text(json.dumps({'enshan': {'accounts': [
                {'account_name': 'fixture', 'cookies': 'auth=file-fixture'},
            ]}}))
            with patch.dict(os.environ, {'ENSHAN_COOKIE': 'auth=environment-fixture'}):
                instance = manager.EnshanSignInManager(str(path))
        self.assertEqual(instance.accounts[0]['cookies'], 'auth=file-fixture')

    def test_missing_optional_notify_module_does_not_claim_delivery(self):
        with patch.object(manager, '_ql_send', None):
            self.assertFalse(manager.send_notification('local-test', 'local-result'))


if __name__ == '__main__':
    unittest.main()
