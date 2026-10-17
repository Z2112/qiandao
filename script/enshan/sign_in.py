#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new Env('恩山论坛签到');
cron: 1 1 1 1 1
"""

"""
恩山论坛自动签到脚本

功能：
1. 优先从ENSHAN_COOKIE读取账号，兼容token.json账号配置
2. 支持多账号管理
3. 自动执行签到并推送通知

Author: ZaiZaiCat
Date: 2025-01-20
"""

import json
import logging
import os
import sys
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径，以兼容青龙的notify模块。
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from notify import send as _ql_send
except ImportError:
    _ql_send = None

# 导入API模块（当前目录）
from api import EnshanAPI

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def send_notification(title, content):
    if _ql_send is None:
        logger.info('notify模块未加载，结果已输出，跳过外部推送')
        return False
    _ql_send(title, content)
    return True


class EnshanSignInManager:
    """恩山论坛签到管理器"""

    def __init__(self, config_path: str = None):
        """
        初始化签到管理器

        Args:
            config_path: 显式指定时读取该文件；默认优先使用ENSHAN_COOKIE，再读取config/token.json
        """
        self._explicit_config_path = config_path is not None
        if config_path is None:
            config_path = project_root / "config" / "token.json"
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self.site_name = "恩山论坛"
        self.accounts = []
        self.load_config()

    def load_config(self) -> None:
        """加载配置文件"""
        raw = os.getenv('ENSHAN_COOKIE', '')
        if not self._explicit_config_path and raw.strip():
            values = [value.strip() for value in raw.replace('&', '\n').splitlines() if value.strip()]
            self.accounts = []
            for index, value in enumerate(values, 1):
                if value.lower().startswith('cookie:'):
                    value = value.split(':', 1)[1].strip()
                self.accounts.append({'account_name': f'账号{index}', 'cookies': value})
            logger.info('从ENSHAN_COOKIE加载%d个账号', len(self.accounts))
            return
        try:
            logger.info(f"正在读取配置文件: {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 获取恩山论坛的配置
            enshan_config = config.get('enshan', {})
            self.accounts = enshan_config.get('accounts', [])

            if not self.accounts:
                logger.warning("配置文件中没有找到恩山论坛账号信息")
            else:
                logger.info(f"成功加载 {len(self.accounts)} 个账号配置")

        except FileNotFoundError:
            logger.error(f"配置文件不存在: {self.config_path}；请设置ENSHAN_COOKIE或提供账号配置")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"配置文件JSON格式错误: {e}")
            raise
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise

    def sign_in_single_account(self, account: Dict[str, Any]) -> Dict[str, Any]:
        """
        单个账号签到

        Args:
            account: 账号配置信息

        Returns:
            Dict: 签到结果
        """
        account_name = account.get('account_name', '未命名账号')
        cookies = account.get('cookies', '')
        formhash = account.get('formhash', '')
        user_agent = account.get('user_agent')
        browser_fallback = account.get('browser_fallback', True)

        logger.info(f"开始执行账号 [{account_name}] 的签到...")

        if not cookies:
            error_msg = "cookies为空"
            logger.error(f"账号 [{account_name}] {error_msg}")
            return {
                'account_name': account_name,
                'success': False,
                'error': error_msg
            }

        try:
            # 创建API实例并执行签到
            api = EnshanAPI(cookies, formhash, user_agent, browser_fallback=browser_fallback)
            result = api.sign_in()

            # 添加账号名称到结果中
            result['account_name'] = account_name

            if result.get('success'):
                logger.info(f"账号 [{account_name}] 签到成功")
            else:
                logger.error(f"账号 [{account_name}] 签到失败: {result.get('error', '未知错误')}")

            return result

        except Exception as e:
            error_msg = f"签到异常: {str(e)}"
            logger.error(f"账号 [{account_name}] {error_msg}", exc_info=True)
            return {
                'account_name': account_name,
                'success': False,
                'error': error_msg
            }

    def sign_in_all_accounts(self) -> List[Dict[str, Any]]:
        """
        所有账号签到

        Returns:
            List[Dict]: 所有账号的签到结果列表
        """
        if not self.accounts:
            logger.warning("没有可签到的账号")
            return []

        results = []
        for i, account in enumerate(self.accounts, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"正在处理第 {i}/{len(self.accounts)} 个账号")
            logger.info(f"{'='*60}")

            result = self.sign_in_single_account(account)
            results.append(result)

        return results

    def send_notification(self, results: List[Dict[str, Any]], start_time: datetime, end_time: datetime) -> None:
        """
        发送签到结果通知

        Args:
            results: 签到结果列表
            start_time: 任务开始时间
            end_time: 任务结束时间
        """
        try:
            duration = (end_time - start_time).total_seconds()

            # 统计结果
            total_count = len(results)
            success_count = sum(1 for r in results if r.get('success'))
            failed_count = total_count - success_count

            # 构建通知标题
            if failed_count == 0:
                title = f"{self.site_name}签到成功 ✅"
            elif success_count == 0:
                title = f"{self.site_name}签到失败 ❌"
            else:
                title = f"{self.site_name}签到部分成功 ⚠️"

            # 构建通知内容
            content_parts = [f"📊 执行统计:"]

            if success_count > 0:
                content_parts.append(f"✅ 成功: {success_count} 个账号")
            if failed_count > 0:
                content_parts.append(f"❌ 失败: {failed_count} 个账号")

            content_parts.append(f"📈 总计: {total_count} 个账号")
            content_parts.append("")  # 空行

            # 添加详细信息
            content_parts.append("📝 详情:")
            for result in results:
                account_name = result.get('account_name', '未知账号')
                if result.get('success'):
                    api_result = result.get('result', {})

                    # 解析签到返回的数据
                    if 'credit' in api_result:
                        content_parts.append(f"  ✅ [{account_name}] 获得积分: {api_result.get('credit')}")
                    elif 'message' in api_result:
                        message = api_result.get('message', '签到成功')
                        # 限制消息长度
                        if len(message) > 50:
                            message = message[:50] + "..."
                        content_parts.append(f"  ✅ [{account_name}] {message}")
                    else:
                        content_parts.append(f"  ✅ [{account_name}] 签到成功")
                else:
                    error = result.get('error', '未知错误')
                    # 限制错误消息长度
                    if len(error) > 50:
                        error = error[:50] + "..."
                    content_parts.append(f"  ❌ [{account_name}] {error}")

            # 添加执行信息
            content_parts.append("")  # 空行
            content_parts.append(f"⏱️ 执行耗时: {int(duration)}秒")
            content_parts.append(f"🕐 完成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

            content = "\n".join(content_parts)

            # 发送通知
            sent = send_notification(
                title=title,
                content=content,
            )
            if sent:
                logger.info(f"✅ {self.site_name}签到推送发送成功")

        except Exception as e:
            logger.error(f"❌ {self.site_name}推送通知失败: {str(e)}", exc_info=True)


def main():
    """主函数"""
    # 记录开始时间
    start_time = datetime.now()
    print(f"\n{'='*60}")
    print(f"## 恩山论坛签到任务开始")
    print(f"## 开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    logger.info("="*60)
    logger.info(f"恩山论坛签到任务开始执行 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)

    try:
        # 创建签到管理器
        manager = EnshanSignInManager()

        # 执行所有账号签到
        results = manager.sign_in_all_accounts()

        # 记录结束时间
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"\n{'='*60}")
        print(f"## 恩山论坛签到任务完成")
        print(f"## 结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"## 执行耗时: {int(duration)} 秒")
        print(f"{'='*60}\n")

        logger.info("="*60)
        logger.info(f"恩山论坛签到任务执行完成 - {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"执行耗时: {int(duration)} 秒")
        logger.info("="*60)

        # 发送推送通知
        if results:
            manager.send_notification(results, start_time, end_time)

        # 统计结果
        total_count = len(results)
        success_count = sum(1 for r in results if r.get('success'))
        failed_count = total_count - success_count

        # 打印总结
        print(f"📊 签到总结:")
        print(f"   ✅ 成功: {success_count} 个账号")
        print(f"   ❌ 失败: {failed_count} 个账号")
        print(f"   📈 总计: {total_count} 个账号\n")

        # 根据结果返回退出码
        if failed_count > 0:
            return 1 if success_count == 0 else 2  # 1=全部失败, 2=部分失败
        return 0  # 全部成功

    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.error(f"签到任务执行异常: {str(e)}", exc_info=True)

        print(f"\n{'='*60}")
        print(f"## ❌ 签到任务执行异常")
        print(f"## 错误信息: {str(e)}")
        print(f"## 结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"## 执行耗时: {int(duration)} 秒")
        print(f"{'='*60}\n")

        # 发送错误通知
        try:
            send_notification(
                title=f"恩山论坛签到任务异常 ❌",
                content=(
                    f"❌ 任务执行异常\n"
                    f"💬 错误信息: {str(e)}\n"
                    f"⏱️ 执行耗时: {int(duration)}秒\n"
                    f"🕐 完成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}"
                ),
            )
        except:
            pass

        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
