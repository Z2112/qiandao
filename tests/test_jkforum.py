import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location('jkforum_under_test', Path(__file__).resolve().parents[1] / 'JKForum.py')
jkf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jkf)


def task(progress, completed=False):
    return {'id': 'like-task', 'name': '對三篇文章點讚', 'isCompleted': completed,
            'details': [{'progressScore': progress, 'goalScore': 3}]}


def stage(progress, completed=False):
    return {'id': '370081911275560', 'isCompleted': completed,
            'details': [{'progressScore': progress, 'goalScore': 3}]}


class JKForumTests(unittest.TestCase):
    def setUp(self):
        self.log = io.StringIO()
        self.output = contextlib.redirect_stdout(self.log)
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.sleep = patch.object(jkf.time, 'sleep').start()
        self.addCleanup(patch.stopall)
        patch.object(jkf.random, 'shuffle', side_effect=lambda values: None).start()
        patch.object(jkf, 'VIEW_BOARDS', [141]).start()
        self.client = Mock()
        self.client.safe_message.side_effect = str

    def articles(self, rows):
        patch.object(jkf, 'get_article_list', return_value=rows).start()
        patch.object(jkf, 'get_article_detail', return_value=True).start()

    def test_http_204_without_progress_uses_another_article(self):
        self.articles([{'id': 'old-like'}, {'id': 'new-like'}, {'id': 'extra'}])
        patch.object(jkf, 'get_daily_tasks', side_effect=[[task(2)], [task(2)], [task(3)]]).start()
        jkf.do_browse_and_like_tasks(self.client, like_article_count=1)
        puts = [call.args[1] for call in self.client.request.call_args_list if call.args[0] == 'PUT']
        self.assertEqual(puts, ['/api/jkf-forum/v1/ArticleLike/141/old-like',
                                '/api/jkf-forum/v1/ArticleLike/141/new-like'])

    def test_delayed_progress_is_read_before_another_write(self):
        self.articles([{'id': 'one'}, {'id': 'extra'}])
        refresh = patch.object(jkf, 'get_daily_tasks', side_effect=[[task(2)], [task(3)]]).start()
        jkf.do_browse_and_like_tasks(self.client, like_article_count=1)
        self.assertEqual(refresh.call_count, 2)
        self.assertEqual(self.client.request.call_count, 1)

    def test_known_liked_articles_are_not_toggled(self):
        self.articles([{'id': 'already', 'isLiked': True}, {'id': 'new', 'isLiked': False}])
        patch.object(jkf, 'get_daily_tasks', return_value=[task(3)]).start()
        jkf.do_browse_and_like_tasks(self.client, like_article_count=1)
        self.assertEqual(self.client.request.call_args.args[1], '/api/jkf-forum/v1/ArticleLike/141/new')

    def test_detail_like_flag_prevents_toggling_when_list_omits_it(self):
        self.articles([{'id': 'already'}, {'id': 'new'}])
        jkf.get_article_detail.side_effect = [{'isLiked': True}, {'isLiked': False}]
        patch.object(jkf, 'get_daily_tasks', return_value=[task(3)]).start()
        jkf.do_browse_and_like_tasks(self.client, like_article_count=1)
        self.assertEqual(self.client.request.call_count, 1)
        self.assertTrue(self.client.request.call_args.args[1].endswith('/new'))

    def test_no_progress_has_a_bounded_number_of_like_attempts(self):
        self.articles([{'id': str(i)} for i in range(50)])
        patch.object(jkf, 'get_daily_tasks', return_value=[task(2)]).start()
        jkf.do_browse_and_like_tasks(self.client, like_article_count=1)
        self.assertEqual(self.client.request.call_count, 3)

    def test_comment_likes_also_require_server_progress(self):
        self.articles([{'id': 'article'}])
        patch.object(jkf, 'get_comments', return_value=[{'id': 'old'}, {'id': 'new'}]).start()
        def comment_task(progress):
            result = task(progress)
            result['name'] = '對三則留言點讚'
            return result
        patch.object(jkf, 'get_daily_tasks', side_effect=[
            [comment_task(2)], [comment_task(2)], [comment_task(3)],
        ]).start()
        jkf.do_browse_and_like_tasks(self.client, like_comment_count=1)
        self.assertEqual(self.client.request.call_count, 2)

    def test_failed_progress_read_stops_more_likes(self):
        self.articles([{'id': 'one'}, {'id': 'extra'}])
        refresh = patch.object(jkf, 'get_daily_tasks', side_effect=jkf.APIError('progress unavailable')).start()
        jkf.do_browse_and_like_tasks(self.client, like_article_count=1)
        refresh.assert_called_once()
        self.assertEqual(self.client.request.call_count, 1)

    def test_unknown_write_result_is_not_repeated_and_is_read_back(self):
        self.articles([{'id': 'one'}, {'id': 'one'}, {'id': 'extra'}])
        self.client.request.side_effect = jkf.APIError('response lost')
        refresh = patch.object(jkf, 'get_daily_tasks', return_value=[task(3)]).start()
        jkf.do_browse_and_like_tasks(self.client, like_article_count=1)
        self.assertGreater(refresh.call_count, 0)
        self.assertEqual(self.client.request.call_count, 1)

    def test_stage_below_threshold_is_not_posted(self):
        patch.object(jkf, 'get_daily_stages', return_value=[stage(2)]).start()
        patch.object(jkf, 'get_daily_tasks', return_value=[task(2)]).start()
        result = jkf.claim_daily_stage_rewards(self.client)
        self.client.request.assert_not_called()
        self.assertEqual(result.get('pending'), 1)
        self.assertEqual(result['failed'], 0)

    def test_unknown_stage_conditions_still_allow_available_lower_reward(self):
        patch.object(jkf, 'get_daily_stages', side_effect=[
            [{'id': 'unknown', 'isCompleted': False}],
            [{'id': 'unknown', 'isCompleted': True}],
        ]).start()
        self.client.request.return_value.content = b'{"code":"201000"}'
        self.client.request.return_value.json.return_value = {'code': '201000', 'message': 'Success Created.'}
        result = jkf.claim_daily_stage_rewards(self.client)
        self.assertEqual(self.client.request.call_count, 1)
        self.assertEqual(result['success'], 1)
        self.assertEqual(result['failed'], 0)
        self.assertNotIn('⚠️', self.log.getvalue())

    def test_stage_400_is_not_posted_three_times(self):
        patch.object(jkf, 'get_daily_stages', return_value=[stage(3)]).start()
        patch.object(jkf, 'get_daily_tasks', return_value=[task(3, completed=True)]).start()
        self.client.request.side_effect = jkf.APIError('HTTP 400 | 400000')
        result = jkf.claim_daily_stage_rewards(self.client)
        self.assertEqual(self.client.request.call_count, 1)
        self.assertEqual(result['failed'], 1)
        self.assertIn('400000', result['errors'][0])

    def test_stage_claim_response_requires_readback(self):
        patch.object(jkf, 'get_daily_stages', side_effect=[[stage(3)], [stage(3, completed=True)]]).start()
        patch.object(jkf, 'get_daily_tasks', return_value=[task(3, completed=True)]).start()
        self.client.request.return_value.content = b''
        result = jkf.claim_daily_stage_rewards(self.client)
        self.assertEqual(result['success'], 1)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(self.client.request.call_count, 1)

    def test_reported_two_created_stages_and_one_400_are_counted_correctly(self):
        before = [{'id': str(i), 'isCompleted': False} for i in range(3)]
        after = [{'id': str(i), 'isCompleted': i < 2} for i in range(3)]
        patch.object(jkf, 'get_daily_stages', side_effect=[before, after, after, after]).start()
        created = Mock(content=b'{"code":"201000"}')
        created.json.return_value = {'code': '201000', 'message': 'Success Created.'}
        self.client.request.side_effect = [created, created, jkf.APIError('HTTP 400 | 400000')]
        result = jkf.claim_daily_stage_rewards(self.client)
        self.assertEqual(self.client.request.call_count, 3)
        self.assertEqual(result['success'], 2)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(self.log.getvalue().count('⚠️'), 1)

    def test_full_account_finishes_remaining_like_task_and_claims_rewards(self):
        state = {'likes': [], 'task_claimed': False, 'stage_claimed': False}
        self.client.cookies = {}

        def content(path, **kwargs):
            if path.endswith('/SignInInformation'):
                return {'wallet': {'credits': [{'id': 2, 'point': 100}]}}
            if path.endswith('/DailyTask'):
                return {'tasks': [task(3 if 'new' in state['likes'] else 2, state['task_claimed'])]}
            if path.endswith('/DailyStage'):
                return {'stages': [stage(3 if state['task_claimed'] else 2, state['stage_claimed'])]}
            if '/Article/' in path:
                return {'articles': [{'id': 'old'}, {'id': 'new'}, {'id': 'extra'}]}
            raise AssertionError(path)

        def request(method, path, **kwargs):
            result = Mock()
            result.content = b'{"code":"200000"}'
            result.json.return_value = {'code': '200000'}
            if '/ArticleLike/' in path:
                state['likes'].append(path.rsplit('/', 1)[-1])
            elif path.endswith('/CompleteTask'):
                self.assertIn('new', state['likes'])
                state['task_claimed'] = True
            elif path.endswith('/CompleteStage'):
                self.assertTrue(state['task_claimed'])
                state['stage_claimed'] = True
                result.json.return_value = {'code': '201000', 'message': 'Success Created.'}
            elif '/ArticleThread/' in path:
                result.json.return_value = {'content': {}}
            else:
                raise AssertionError(path)
            return result

        self.client.content.side_effect = content
        self.client.request.side_effect = request
        result = jkf.process_account(self.client, 1, 1)
        self.assertEqual(state['likes'], ['old', 'new'])
        self.assertTrue(state['task_claimed'])
        self.assertTrue(state['stage_claimed'])
        self.assertFalse(result['has_fail'])
        self.assertEqual(result['stage_result']['success'], 1)
        self.assertIn('✅ 已完成/已领取', result['task_lines'][0])


if __name__ == '__main__':
    unittest.main()
