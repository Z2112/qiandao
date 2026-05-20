// cron: 0 8,15 * * *
// new Env('52pojie签到[大模型识别版]');
// author: Jie + Grok 修改
// version: 2.1 (多账号版)

// =============================================
// 【青龙面板使用说明】
// 1. 依赖安装（必须）：
//    - 青龙面板 → 依赖管理 → Node.js 依赖 → 新增：
//      - puppeteer-core
//      - axios
//    - 安装完成后重启青龙
//
// 2. 环境变量设置：
//    - PJ52_COOKIES       （必填，支持多账号）多个 Cookie 用 & 分割 或 换行分割
//    - LLM_API_URL        （可选）大模型接口地址（验证码识别）
//    - LLM_API_KEY        （可选）大模型 API Key
//    - LLM_MODEL          （可选）模型名称，默认 gpt-4o
//    - RANDOM_SIGNIN      （可选）true = 开启随机延迟
//    - MAX_RANDOM_DELAY   （可选）随机延迟最大秒数，默认 3600 秒
//
// 3. 多账号配置示例（PJ52_COOKIES 中填写）：
//    Cookie字符串1&Cookie字符串2&Cookie字符串3
//    或者每行一个 Cookie（推荐）：
//    Cookie字符串1
//    Cookie字符串2
//    Cookie字符串3
//
// 4. 注意事项：
//    - 已签到的账号完全不发送任何通知
//    - 只有签到成功 或 签到失败 时才会推送通知
//    - 多账号时只会发送一条汇总通知
// =============================================

const puppeteer = require('puppeteer-core');
const fs = require('fs');
const axios = require('axios');
const notify = require('./sendNotify');   // 青龙标准通知模块

const COOKIE_FILE = '/ql/data/scripts/cookies.json';

const LLM_API_URL = process.env.LLM_API_URL || '';
const LLM_API_KEY = process.env.LLM_API_KEY || '';
const LLM_MODEL = process.env.LLM_MODEL || 'gpt-4o';

// ==================== 时间格式化函数 ====================
function formatDelay(seconds) {
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (minutes > 0) return `${minutes}分钟${secs}秒`;
  return `${secs}秒`;
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

const LAUNCH_OPTIONS = {
  headless: true,
  executablePath: '/usr/bin/chromium',
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
};

// ==================== 获取所有 Cookie（支持 & 或换行分割） ====================
function getAllCookies() {
  const raw = process.env.PJ52_COOKIES || '';
  if (!raw) {
    console.error('❌ 未设置 PJ52_COOKIES 环境变量');
    return [];
  }

  const cookiesList = [raw]
    .flatMap(str => str.split('&'))
    .flatMap(str => str.split('\n'))
    .map(str => str.trim())
    .filter(str => str.length > 20);

  if (cookiesList.length === 0) {
    console.error('❌ PJ52_COOKIES 内容为空或格式错误');
    return [];
  }

  console.log(`✅ 从 PJ52_COOKIES 读取到 ${cookiesList.length} 个账号`);
  return cookiesList;
}

async function loadCookies(page, cookieInput) {
  let cookies = [];
  try {
    cookies = JSON.parse(cookieInput);
    if (!Array.isArray(cookies)) cookies = [];
  } catch (e) {
    cookies = cookieInput.split(';').map(item => {
      const [name, ...valueParts] = item.trim().split('=');
      if (!name) return null;
      return {
        name: name.trim(),
        value: valueParts.join('=').trim(),
        domain: '.52pojie.cn'
      };
    }).filter(Boolean);
  }
  if (cookies.length > 0) {
    await page.setCookie(...cookies);
    console.log(`已为当前账号注入 ${cookies.length} 个 Cookie`);
  }
}

async function getSignStatus(page) {
  await page.goto('https://www.52pojie.cn/', { waitUntil: 'networkidle2', timeout: 30000 });
  await delay(3000);
  const html = await page.content();
  if (html.includes('wbs.png')) return '已签到';
  if (html.includes('qds.png')) return '未签到';
  return '未知状态';
}

async function recognizeCaptcha(base64Image) {
  if (!LLM_API_URL || !LLM_API_KEY) return null;
  try {
    const res = await axios.post(`${LLM_API_URL}/chat/completions`, {
      model: LLM_MODEL,
      messages: [{
        role: "user",
        content: [
          { type: "text", text: "请只返回图片中的验证码字符，不要任何解释。" },
          { type: "image_url", image_url: { url: `data:image/png;base64,${base64Image}` } }
        ]
      }],
      max_tokens: 10
    }, {
      headers: { Authorization: `Bearer ${LLM_API_KEY}` }
    });
    return res.data.choices[0].message.content.trim();
  } catch (e) {
    console.log('大模型识别失败:', e.message);
    return null;
  }
}

async function doSign(page) {
  console.log('访问签到任务页...');
  await page.goto('https://www.52pojie.cn/home.php?mod=task&do=apply&id=2', {
    waitUntil: 'networkidle2',
    timeout: 30000
  });
  await delay(5000);

  const html = await page.content();
  const isVerifyPage = html.includes('IP:') || html.includes('type="text"');

  if (isVerifyPage) {
    console.log('检测到验证码页面，正在识别...');
    const img = await page.$('img');
    if (img) {
      const base64 = await img.screenshot({ encoding: 'base64' });
      const code = await recognizeCaptcha(base64);
      if (code) {
        console.log(`大模型识别结果: ${code}`);
        await page.type('input[type="text"]', code);
        await delay(800);
        const submit = await page.$('button, input[type="submit"]');
        if (submit) await submit.click();
        await delay(6000);
      } else {
        console.log('验证码识别失败');
      }
    }
  }
  return await getSignStatus(page);
}

async function processAccount(cookieInput, accountIndex) {
  console.log(`\n📌 开始处理第 ${accountIndex} 个账号`);

  let browser;
  let status = '';
  let result = '';

  try {
    browser = await puppeteer.launch(LAUNCH_OPTIONS);
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36');

    await loadCookies(page, cookieInput);

    status = await getSignStatus(page);
    console.log('当前状态:', status);

    if (status === '未签到') {
      result = await doSign(page);
      console.log('签到后状态:', result);
    } else {
      result = '今日已签到';
    }

  } catch (err) {
    result = '执行异常: ' + err.message;
    console.error(result);
  } finally {
    if (browser) {
      try { await browser.close(); } catch (e) {}
    }
  }

  return { status, result };
}

async function main() {
  console.log('=== 52pojie 签到开始（多账号 + 大模型版）===');

  if (process.env.RANDOM_SIGNIN === 'true') {
    const maxDelay = parseInt(process.env.MAX_RANDOM_DELAY) || 3600;
    const randomDelay = Math.floor(Math.random() * maxDelay) + 1;
    console.log(`随机延迟 ${formatDelay(randomDelay)} 后开始执行...`);
    await delay(randomDelay * 1000);
  } else {
    console.log('未开启随机延迟（RANDOM_SIGNIN 未设置为 true）');
  }

  const cookieList = getAllCookies();
  if (cookieList.length === 0) {
    console.error('没有可处理的 Cookie，任务结束');
    return;
  }

  const allResults = [];

  for (let i = 0; i < cookieList.length; i++) {
    const { status, result } = await processAccount(cookieList[i], i + 1);
    allResults.push(`账号${i + 1}: ${result}`);
  }

  // ==================== 最终通知 ====================
  const hasAction = allResults.some(r => r.includes('签到成功') || r.includes('执行异常') || r.includes('签到失败'));

  if (hasAction) {
    const summary = allResults.join('\n');
    const title = '52pojie 签到通知';
    const content = `多账号签到完成\n\n${summary}\n\n时间：${new Date().toLocaleString('zh-CN')}`;
    await notify.sendNotify(title, content);
    console.log('🎉 通知已发送');
  } else {
    console.log('✅ 所有账号均已签到，无需发送通知');
  }

  console.log('=== 签到结束 ===');
}

main().catch(err => {
  console.error('脚本运行出错:', err);
  process.exit(1);
});
