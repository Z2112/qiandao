# -*- coding: utf-8 -*-
"""
cron: 0 8,15 * * *
new Env('52pojie签到[大模型识别版]');
"""

"""
======================= 脚本说明 =======================
脚本名称: 52pojie 自动签到（大模型识别验证码版）
功能: 
  - 自动登录 52pojie（吾爱破解）
  - 自动识别并填写验证码（使用大模型视觉能力）
  - 支持失败重试 1 次
  - 每次执行前随机延迟 1~30 分钟（降低风控风险）
  - 支持青龙面板订阅使用

使用方式:
  1. 将本脚本上传到 GitHub 仓库
  2. 在青龙面板使用 ql repo 订阅仓库
  3. 配置下方所需的环境变量
  4. 青龙会自动识别 cron 并创建定时任务（默认早8点、下午3点各执行一次）

环境变量配置（青龙面板添加）:
  PJ52_COOKIE     : 52pojie 的 Cookie（必须）
  LLM_API_URL     : 大模型 API 地址（如 https://api.openai.com/v1）
  LLM_API_KEY     : 大模型的 API Key
  LLM_MODEL       : 使用的模型名称（如 gpt-4o、qwen-vl-plus、glm-4v 等）

依赖安装（青龙依赖管理）:
  playwright
  aiohttp

 playwright 浏览器安装（在青龙终端执行）:
  playwright install chromium

注意事项:
  - 建议使用质量较好的代理或住宅 IP，否则容易触发验证码
  - 大模型识别验证码成功率较高，但仍有可能失败（已内置重试）
  - Cookie 建议定期更新
=======================================================
"""

import os
import base64
import random
import asyncio
from playwright.async_api import async_playwright
import aiohttp
from notify import send

# ==================== 环境变量配置 ====================
PJ52_COOKIE = os.getenv("PJ52_COOKIE", "")
LLM_API_URL = os.getenv("LLM_API_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")


async def recognize_captcha(base64_image: str) -> str:
    """调用大模型识别验证码"""
    if not LLM_API_URL or not LLM_API_KEY:
        print("未配置大模型环境变量，跳过识别")
        return ""

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": LLM_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "请只返回图片中的验证码字符，不要任何解释。"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]
        }],
        "max_tokens": 10
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{LLM_API_URL}/chat/completions", json=payload, headers=headers) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"大模型识别失败: {e}")
        return ""


async def do_sign(page) -> str:
    """执行签到主流程"""
    print("正在访问签到任务页面...")
    await page.goto("https://www.52pojie.cn/home.php?mod=task&do=apply&id=2", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(5)

    content = await page.content()

    # 判断是否进入验证码验证页
    if "IP:" in content or 'type="text"' in content:
        print("检测到验证码验证页面，正在使用大模型识别...")
        img = await page.query_selector("img")
        if img:
            img_bytes = await img.screenshot()
            base64_img = base64.b64encode(img_bytes).decode()
            code = await recognize_captcha(base64_img)

            if code:
                print(f"大模型识别结果: {code}")
                await page.fill('input[type="text"]', code)
                await asyncio.sleep(0.8)

                # 点击提交按钮
                submit_btn = await page.query_selector("button, input[type='submit']")
                if submit_btn:
                    await submit_btn.click()
                await asyncio.sleep(6)
            else:
                print("验证码识别失败")
        else:
            print("未找到验证码图片")

    # 重新检查签到状态
    await page.goto("https://www.52pojie.cn/", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(3)
    final_content = await page.content()

    if "wbs.png" in final_content:
        return "签到成功"
    else:
        return "签到失败"


async def main():
    if not PJ52_COOKIE:
        print("未配置 PJ52_COOKIE 环境变量，终止执行")
        return

    # ==================== 随机延迟 1~30 分钟 ====================
    delay_minutes = random.randint(1, 30)
    print(f"随机延迟 {delay_minutes} 分钟后执行签到...")
    await asyncio.sleep(delay_minutes * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # 解析并添加 Cookie
        cookies = []
        for item in PJ52_COOKIE.split(";"):
            if "=" in item:
                key, value = item.strip().split("=", 1)
                cookies.append({"name": key, "value": value, "domain": ".52pojie.cn", "path": "/"})
        await context.add_cookies(cookies)

        page = await context.new_page()

        # 先检查是否已经签到
        await page.goto("https://www.52pojie.cn/", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        if "wbs.png" in await page.content():
            msg = "今日已签到，无需重复操作"
            print(msg)
            send("52pojie签到通知", msg)
            await browser.close()
            return

        # 执行签到（失败自动重试一次）
        result = await do_sign(page)
        if result != "签到成功":
            print("首次签到未成功，准备重试...")
            await asyncio.sleep(5)
            result = await do_sign(page)

        print(result)
        send("52pojie签到通知", result)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
