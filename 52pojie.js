// cron: 0 8,15 * * *
// new Env('52pojie签到[大模型识别版]');

const puppeteer = require('puppeteer-core');
const axios = require('axios');
const notify = require('./sendNotify');

const LLM_API_URL = process.env.LLM_API_URL || '';
const LLM_API_KEY = process.env.LLM_API_KEY || '';
const LLM_MODEL = process.env.LLM_MODEL || 'gpt-4o';

const LAUNCH_OPTIONS = {
  headless: true,
  executablePath: '/usr/bin/chromium',
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
};

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function getAllCookies() {
  const raw = process.env.PJ52_COOKIES || '';
  if (!raw) return [];
  return raw.split(/&|\n/).map(s => s.trim()).filter(s => s.length > 20);
}

// ==================== 轻量API检查签到状态 ====================
async function checkSignStatus(cookie) {
  try {
    const resp = await axios.get('https://www.52pojie.cn/forum.php', {
      headers: {
        Cookie: cookie,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      },
      timeout: 15000
    });
    const html = resp.data;

    if (html.includes('wbs.png') || html.includes('已签到') || html.includes('签到成功')) {
      return '已签到';
    }
    if (html.includes('qds.png') || html.includes('每日签到') || html.includes('签到')) {
      return '未签到';
    }
    return '未知';
  } catch (e) {
    console.log('⚠️ 状态检查失败:', e.message);
    return '未知';
  }
}

// ==================== 纯API获取吾爱币 ====================
async function getMyCreditsAPI(cookie) {
  try {
    const resp = await axios.get(
      'https://www.52pojie.cn/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu',
      {
        headers: {
          Cookie: cookie,
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        },
        timeout: 15000
      }
    );
    const html = resp.data;
    const match = html.match(/>([\d,]+)CB<\/span>/);
    return match ? match[1].replace(/,/g, '') : null;
  } catch (e) {
    console.log('⚠️ 获取吾爱币失败:', e.message);
    return null;
  }
}

async function loadCookies(page, cookieInput) {
  let cookies = [];
  try {
    cookies = JSON.parse(cookieInput);
  } catch {
    cookies = cookieInput.split(';').map(item => {
      const [name, ...value] = item.trim().split('=');
      return name ? { name: name.trim(), value: value.join('=').trim(), domain: '.52pojie.cn' } : null;
    }).filter(Boolean);
  }
  if (cookies.length > 0) await page.setCookie(...cookies);
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
    }, { headers: { Authorization: `Bearer ${LLM_API_KEY}` } });

    if (res.data?.usage) {
      const u = res.data.usage;
      console.log(`🔥 大模型 tokens 消耗 → prompt:${u.prompt_tokens} | completion:${u.completion_tokens} | total:${u.total_tokens}`);
    }
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
  await delay(4000);

  let html = await page.content();
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
        await delay(600);
        const submit = await page.$('button, input[type="submit"]');
        if (submit) await submit.click();
        await delay(6000);

        html = await page.content();
        if (html.includes('签到成功') || html.includes('获得') || html.includes('任务已完成')) {
          return { status: 'success', message: '签到成功' };
        }
      }
    }
    return { status: 'fail', message: '验证码识别或提交失败' };
  }

  return { status: 'success', message: '签到成功' };
}

async function processAccount(cookieInput, accountIndex) {
  console.log(`\n📌 开始处理第 ${accountIndex} 个账号`);

  const status = await checkSignStatus(cookieInput);
  console.log(`当前状态: ${status}`);

  if (status === '已签到') {
    const credits = await getMyCreditsAPI(cookieInput);
    return `✅ 今日已签到 | 吾爱币: ${credits || '未知'}`;
  }

  // ==================== 未签到 → 执行签到 ====================
  console.log('🌐 浏览器已启动');
  let browser;
  let finalResult = '';

  try {
    browser = await puppeteer.launch(LAUNCH_OPTIONS);
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36');

    await loadCookies(page, cookieInput);

    // 签到前获取吾爱币
    const oldCredits = await getMyCreditsAPI(cookieInput);
    console.log(`签到前吾爱币: ${oldCredits || '未知'}`);

    const signResult = await doSign(page);

    if (signResult.status === 'success') {
      await delay(3000);

      // 签到后获取吾爱币
      const newCredits = await getMyCreditsAPI(cookieInput);
      console.log(`签到后吾爱币: ${newCredits || '未知'}`);

      let rewardText = '';
      if (oldCredits && newCredits) {
        const diff = parseInt(newCredits) - parseInt(oldCredits);
        if (diff > 0) rewardText = `，本次获得 ${diff} 吾爱币`;
      }

      finalResult = `✅ 签到成功${rewardText}，当前总共 ${newCredits || '未知'} 吾爱币`;
    } else {
      finalResult = `❌ ${signResult.message}`;
    }
  } catch (err) {
    finalResult = `执行异常: ${err.message}`;
  } finally {
    if (browser) {
      await browser.close();
      console.log('🔚 浏览器已关闭');
    }
  }

  return finalResult;
}

async function main() {
  console.log('=== 52pojie 签到开始（多账号 + 大模型版）===');

  if (process.env.RANDOM_SIGNIN === 'true') {
    const maxDelay = parseInt(process.env.MAX_RANDOM_DELAY) || 3600;
    const randomDelay = Math.floor(Math.random() * maxDelay) + 1;
    console.log(`随机延迟 ${randomDelay} 秒后开始执行...`);
    await delay(randomDelay * 1000);
  } else {
    console.log('未开启随机延迟（RANDOM_SIGNIN 未设置为 true）');
  }

  const cookieList = getAllCookies();
  if (cookieList.length === 0) return;

  const allResults = [];

  for (let i = 0; i < cookieList.length; i++) {
    const result = await processAccount(cookieList[i], i + 1);
    allResults.push(`账号${i + 1}: ${result}`);
  }

  // 无论是否已签到，都打印详细结果
  console.log("\n" + allResults.join('\n'));

  const hasAction = allResults.some(r => r.includes('签到成功') || r.includes('执行异常'));

  if (hasAction) {
    const summary = allResults.join('\n');
    await notify.sendNotify('52pojie 签到通知', `多账号签到完成\n\n${summary}\n\n时间：${new Date().toLocaleString('zh-CN')}`);
    console.log('🎉 通知已发送');
  } else {
    console.log('✅ 所有账号均已签到，无需发送通知');
  }

  console.log('=== 签到结束 ===');
}

main().catch(console.error);