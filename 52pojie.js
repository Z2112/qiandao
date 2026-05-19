const puppeteer = require('puppeteer-core');
const fs = require('fs');
const notify = require('./sendNotify');

// ==================== 配置 ====================
const COOKIE_FILE = '/ql/data/scripts/cookies.json';

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

const LAUNCH_OPTIONS = {
  headless: true,
  executablePath: '/usr/bin/chromium',
  args: [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu'
  ]
};

// 加载 Cookie（优先环境变量）
async function loadCookies(page) {
  let cookies = [];
  const envCookies = process.env.PJ52_COOKIES;

  if (envCookies) {
    try {
      cookies = JSON.parse(envCookies);
      console.log('✅ 从环境变量加载 Cookie');
    } catch (e) {
      console.log('❌ 环境变量 Cookie 解析失败');
    }
  } else if (fs.existsSync(COOKIE_FILE)) {
    try {
      cookies = JSON.parse(fs.readFileSync(COOKIE_FILE, 'utf8'));
      console.log('✅ 从文件加载 Cookie');
    } catch (e) {
      console.log('❌ Cookie 文件解析失败');
    }
  }

  if (cookies.length > 0) {
    await page.setCookie(...cookies);
  }
}

// 检查签到状态
async function checkSignStatus(page) {
  await delay(3000);
  const html = await page.content();
  if (html.includes('wbs.png')) return '已签到';
  if (html.includes('qds.png')) return '未签到';
  return '未知状态';
}

// 执行签到
async function doSign(page) {
  await page.goto('https://www.52pojie.cn/home.php?mod=task&do=apply&id=2', {
    waitUntil: 'networkidle2',
    timeout: 30000
  });
  await delay(3000);
  const html = await page.content();

  if (html.includes('恭喜') || html.includes('签到成功')) return '签到成功';
  if (html.includes('已完成') || html.includes('不是进行中的任务')) return '今日已签到';
  return '签到状态未知';
}

// 主函数
async function main() {
  console.log('=== 52pojie 签到开始 ===');

  const browser = await puppeteer.launch(LAUNCH_OPTIONS);
  const page = await browser.newPage();

  await page.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
  );

  await loadCookies(page);
  await page.goto('https://www.52pojie.cn/', { waitUntil: 'networkidle2', timeout: 30000 });

  const status = await checkSignStatus(page);
  console.log('当前状态:', status);

  let result = '';
  if (status === '未签到') {
    result = await doSign(page);
  } else {
    result = '无需重复签到';
  }
  console.log('执行结果:', result);

  await browser.close();

  // 发送通知
  const title = '52pojie 签到通知';
  const content = 
    `签到状态：${status}\n` +
    `执行结果：${result}\n` +
    `时间：${new Date().toLocaleString('zh-CN')}`;

  await notify.sendNotify(title, content);
  console.log('=== 签到结束 ===');
}

main().catch(err => {
  console.error('脚本出错:', err);
  process.exit(1);
});
