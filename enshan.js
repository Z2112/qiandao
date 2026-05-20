// =============================================
// 恩山无线论坛（right.com.cn）自动签到脚本
// 版本: 1.7 (纯 API fetch 判断已签到 + 仅未签到时才启动浏览器)
// 作者: 原脚本作者 + Grok 修改
// 运行环境: 青龙面板 / Node.js + Puppeteer
// =============================================
// cron: 0 8,15 * * *
// new Env('恩山签到');

const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');
const notify = require('./sendNotify');

// ====================== 配置 ======================
const COOKIES_ENV = process.env.ENSHAN_COOKIE;
const RANDOM_SIGNIN = process.env.RANDOM_SIGNIN === 'true';
const MAX_RANDOM_DELAY = parseInt(process.env.MAX_RANDOM_DELAY) || 1800;
const FORUM_BASE = 'https://www.right.com.cn/forum';

// ====================== Cookie 解析 ======================
function parseCookies(cookieInput) {
    if (!cookieInput) throw new Error('ENSHAN_COOKIE 环境变量为空！');
    try {
        const parsed = JSON.parse(cookieInput);
        if (Array.isArray(parsed)) {
            console.log('✅ 已成功解析 JSON 格式 Cookie');
            return parsed;
        }
    } catch (e) {
        console.log('ℹ️  非 JSON 格式，尝试解析字符串 Cookie...');
    }
    const cookies = cookieInput.split(';').map(cookie => {
        const [name, ...valueParts] = cookie.trim().split('=');
        if (!name) return null;
        return {
            name: name.trim(),
            value: valueParts.join('=').trim(),
            domain: '.right.com.cn'
        };
    }).filter(Boolean);
    console.log(`✅ 已解析 ${cookies.length} 个 Cookie`);
    return cookies;
}

// ====================== 提取恩山币函数 ======================
function extractEnshanCoins(text) {
    if (!text) return 0;
    let match = text.match(/id="hcredit_2">(\d+)币/);
    if (match && match[1]) return parseInt(match[1]);
    match = text.match(/恩山币:\s*<span[^>]*>(\d+)币/);
    if (match && match[1]) return parseInt(match[1]);
    match = text.match(/恩山币:\s*(\d+)币/);
    return match && match[1] ? parseInt(match[1]) : 0;
}

// ====================== 主函数 ======================
(async () => {
    console.log('🚀 【恩山无线论坛】签到任务开始...');

    if (RANDOM_SIGNIN) {
        const delay = Math.floor(Math.random() * MAX_RANDOM_DELAY) + 1;
        console.log(`⏳ 随机延迟 ${delay} 秒（防风控）...`);
        await new Promise(r => setTimeout(r, delay * 1000));
    }

    const cookies = parseCookies(COOKIES_ENV);
    const scriptDir = __dirname;
    console.log(`📂 脚本运行目录: ${scriptDir}`);

    // ====================== 【纯 API 判断】签到前状态检查 ======================
    console.log('🔍 【纯 API 判断】正在访问签到页面检查是否已签到...');
    
    const cookieStr = cookies.map(c => `${c.name}=${c.value}`).join('; ');

    // 使用你提供的完整 fetch 请求
    const checkResponse = await fetch(`${FORUM_BASE}/erling_qd-sign_in.html`, {
        headers: {
            "cache-control": "max-age=0",
            "sec-ch-ua": "\"Not;A=Brand\";v=\"8\", \"Chromium\";v=\"150\", \"Google Chrome\";v=\"150\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "navigate",
            "sec-fetch-user": "?1",
            "sec-fetch-dest": "document",
            "referer": "https://www.right.com.cn/forum/forum-169-1.html",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9",
            "priority": "u=0, i",
            "cookie": cookieStr
        },
        method: "GET"
    });

    const checkText = await checkResponse.text();

    // 判断是否已签到
    if (checkText.includes('disabled>已签到</button>') || checkText.includes('已签到</button>')) {
        console.log('✅ 【纯 API 判断】已检测到【已签到】状态，直接结束任务（未启动浏览器）');
        const msg = `【恩山无线论坛】今日已签到\n无需重复签到\n时间: ${new Date().toLocaleString('zh-CN')}`;
        await notify.sendNotify('恩山无线论坛签到', msg);
        return;   // 直接结束，不启动浏览器
    } else {
        console.log('🔄 【纯 API 判断】未签到，继续执行签到流程...');
    }

    // ====================== 仅未签到时才启动浏览器 ======================
    let browser;
    try {
        console.log('🌐 启动浏览器并注入 Cookie...');
        browser = await puppeteer.launch({
            executablePath: '/usr/bin/chromium-browser',
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
        });

        const page = await browser.newPage();
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36');
        await page.setCookie(...cookies);

        // ====================== 步骤1：签到前获取恩山币 ======================
        console.log('📊 【步骤1】正在获取签到前恩山币...');
        await page.goto(`${FORUM_BASE}/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu`, { waitUntil: 'networkidle2' });

        const beforeText = await page.evaluate(() => document.body.innerText || '');
        const beforeCoins = extractEnshanCoins(beforeText);
        console.log(`💰 【签到前】恩山币数量: ${beforeCoins} 币`);

        // ====================== 步骤2：执行签到 ======================
        console.log('🔄 【步骤2】正在前往签到页面并点击签到...');
        await page.goto(`${FORUM_BASE}/erling_qd-sign_in.html`, { waitUntil: 'networkidle2' });

        const signed = await page.evaluate(() => {
            const btn = document.getElementById('signin-btn');
            if (btn) {
                btn.click();
                return true;
            }
            return false;
        });

        if (!signed) throw new Error('❌ 未找到签到按钮（#signin-btn）');

        console.log('✅ 已成功点击签到按钮，等待签到结果...');
        await new Promise(resolve => setTimeout(resolve, 4000));

        // ====================== 步骤3：签到后获取恩山币 ======================
        console.log('📊 【步骤3】正在获取签到后恩山币...');
        await page.goto(`${FORUM_BASE}/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu`, { waitUntil: 'networkidle2' });

        const afterText = await page.evaluate(() => document.body.innerText || '');
        
        const afterFile = path.join(scriptDir, 'enshan_credit_after.txt');
        fs.writeFileSync(afterFile, afterText, 'utf8');
        console.log(`📄 签到后原始文本已保存 → ${afterFile}`);

        const afterCoins = extractEnshanCoins(afterText);
        const increase = afterCoins - beforeCoins;
        console.log(`💰 【签到后】恩山币数量: ${afterCoins} 币（本次增加 ${increase} 币）`);

        // ====================== 通知 ======================
        const msg = `【恩山无线论坛签到成功】\n\n签到前: ${beforeCoins} 币\n签到后: ${afterCoins} 币\n本次增加: ${increase} 币\n时间: ${new Date().toLocaleString('zh-CN')}`;
        await notify.sendNotify('恩山无线论坛签到', msg);
        console.log('🎉 签到任务全部完成！通知已发送');

    } catch (err) {
        console.error('❌ 签到失败:', err.message);
        await notify.sendNotify('恩山无线论坛签到', `❌ 签到失败\n原因: ${err.message}`);
    } finally {
        if (browser) await browser.close();
        console.log('🔚 浏览器已关闭，任务结束');
    }
})();
