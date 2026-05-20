// cron: 0 8,15 * * *
// new Env('52pojie签到[大模型识别版]');
// author: Jie
// version: 1.2

const puppeteer = require('puppeteer-core');
const fs = require('fs');
const axios = require('axios');
const notify = require('./sendNotify');

const COOKIE_FILE = '/ql/data/scripts/cookies.json';

const LLM_API_URL = process.env.LLM_API_URL || '';
const LLM_API_KEY = process.env.LLM_API_KEY || '';
const LLM_MODEL = process.env.LLM_MODEL || 'gpt-4o';

// ==================== 时间格式化函数 ====================
function formatDelay(seconds) {
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (minutes > 0) {
    return `${minutes}分钟${secs}秒`;
  }
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

async function loadCookies(page) {
  const envCookies = process.env.PJ52_COOKIES;
  let cookies = [];
  if (envCookies) {
    try { cookies = JSON.parse(envCookies); } catch (e) {}
  } else if (fs.existsSync(COOKIE_FILE)) {
    try { cookies = JSON.parse(fs.readFileSync(COOKIE_FILE, 'utf8')); } catch (e) {}
  }
  if (cookies.length > 0) await page.setCookie(...cookies);
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

async function main() {
  console.log('=== 52pojie 签到开始（大模型版）===');

  // ==================== 随机延迟配置（按你的要求修改） ====================
  if (process.env.RANDOM_SIGNIN === 'true') {
    const maxDelay = parseInt(process.env.MAX_RANDOM_DELAY) || 3600; // 默认最大3600秒
    const randomDelay = Math.floor(Math.random() * maxDelay) + 1;
    console.log(`随机延迟 ${formatDelay(randomDelay)} 后开始执行...`);
    await delay(randomDelay * 1000);
  } else {
    console.log('未开启随机延迟（RANDOM_SIGNIN 未设置为 true）');
  }

  let browser;
  let status = '';
  let result = '';

  try {
    browser = await puppeteer.launch(LAUNCH_OPTIONS);
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36');

    await loadCookies(page);
    status = await getSignStatus(page);
    console.log('当前状态:', status);

    if (status === '未签到') {
      result = await doSign(page);
      console.log('签到后状态:', result);
    } else {
      result = '无需重复签到';
    }

  } catch (err) {
    result = '执行异常: ' + err.message;
    console.error(result);
  } finally {
    if (browser) {
      try { await browser.close(); } catch (e) {}
    }

    const title = '52pojie 签到通知';
    const content = `签到状态：${status}\n执行结果：${result}\n时间：${new Date().toLocaleString('zh-CN')}`;
    await notify.sendNotify(title, content);
  }

  console.log('=== 签到结束 ===');
}

main().catch(err => {
  console.error('脚本运行出错:', err);
  process.exit(1);
});
