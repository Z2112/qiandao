// =============================================
// 恩山无线论坛（right.com.cn）自动签到脚本
// 版本: 2.3 (仅使用 ENSHAN_COOKIE，支持 & 或换行符分割多账号)
// 作者: 原脚本作者 + Grok 修改
// 运行环境: 青龙面板 / Node.js + Puppeteer
// =============================================
// cron: 0 8,15 * * *
// new Env('恩山签到');
// # 随机化配置（可选） RANDOM_SIGNIN=true MAX_RANDOM_DELAY=3600

/**
 * 【青龙面板使用说明】
 * 
 * 1. 依赖安装（必须）：
 *    - 青龙面板 → 依赖管理 → Node.js 依赖 → 新增
 *    - 依赖名称：puppeteer-core
 *    - 安装完成后重启青龙
 * 
 * 2. 环境变量设置：
 *    - ENSHAN_COOKIE      （必填，支持多账号）单个环境变量，多个 Cookie 用 & 或 换行符 分割
 *    - RANDOM_SIGNIN      （可选）true = 开启随机延迟
 *    - MAX_RANDOM_DELAY   （可选）最大延迟秒数，默认3600秒
 * 
 * 3. 多账号配置示例（在青龙环境变量 ENSHAN_COOKIE 中填写）：
 *    Cookie1字符串&Cookie2字符串&Cookie3字符串
 *    或者每行一个 Cookie（青龙支持换行）：
 *    Cookie1字符串
 *    Cookie2字符串
 *    Cookie3字符串
 * 
 * 4. 注意事项：
 *    - 已签到的账号不会发送任何通知
 *    - 只有签到成功或签到失败时才会推送通知
 *    - 多账号时只会发送一条汇总通知
 */

const puppeteer = require('puppeteer-core');
const notify = require('./sendNotify');

// ====================== 配置 ======================
const FORUM_BASE = 'https://www.right.com.cn/forum';
const RANDOM_SIGNIN = process.env.RANDOM_SIGNIN === 'true';
const MAX_RANDOM_DELAY = parseInt(process.env.MAX_RANDOM_DELAY) || 3600;

// ====================== 获取所有 Cookie（仅使用 ENSHAN_COOKIE，支持 & 和换行分割） ======================
function getAllCookies() {
    const raw = process.env.ENSHAN_COOKIE;
    if (!raw) {
        throw new Error('未找到 ENSHAN_COOKIE 环境变量，请设置该变量（支持 & 或换行分割多个 Cookie）');
    }

    // 支持 & 分割 和 换行符 分割，同时去除空白
    const cookiesList = raw
        .split(/&|\n|\r\n/)          // 支持 & 和 各种换行
        .map(str => str.trim())
        .filter(str => str.length > 10); // 过滤空字符串和明显无效的短字符串

    if (cookiesList.length === 0) {
        throw new Error('ENSHAN_COOKIE 内容为空或格式错误');
    }

    console.log(`✅ 从 ENSHAN_COOKIE 读取到 ${cookiesList.length} 个账号`);
    return cookiesList;
}

// ====================== Cookie 解析 ======================
function parseCookies(cookieInput) {
    const cookies = cookieInput.split(';').map(cookie => {
        const [name, ...valueParts] = cookie.trim().split('=');
        if (!name) return null;
        return {
            name: name.trim(),
            value: valueParts.join('=').trim(),
            domain: '.right.com.cn'
        };
    }).filter(Boolean);

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
    console.log('🚀 【恩山无线论坛】多账号签到任务开始...');

    let allResults = [];

    // ====================== 随机延迟 ======================
    if (RANDOM_SIGNIN) {
        const delay = Math.floor(Math.random() * MAX_RANDOM_DELAY) + 1;
        const minutes = Math.floor(delay / 60);
        const seconds = delay % 60;
        console.log(`⏳ 将等待 ${minutes} 分钟 ${seconds} 秒后开始执行...`);
        await new Promise(r => setTimeout(r, delay * 1000));
    } else {
        console.log('ℹ️  RANDOM_SIGNIN 未开启，跳过随机延迟（默认行为）');
    }

    const cookieStrings = getAllCookies();

    for (let i = 0; i < cookieStrings.length; i++) {
        const cookieStr = cookieStrings[i];
        console.log(`\n📌 开始处理第 ${i+1}/${cookieStrings.length} 个账号`);

        const cookies = parseCookies(cookieStr);

        // ====================== 纯 API 判断是否已签到 ======================
        console.log('🔍 【纯 API 判断】检查签到状态...');
        const checkCookieStr = cookies.map(c => `${c.name}=${c.value}`).join('; ');

        try {
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
                    "cookie": checkCookieStr
                },
                method: "GET"
            });

            const checkText = await checkResponse.text();

            if (checkText.includes('disabled>已签到</button>') || checkText.includes('已签到</button>')) {
                console.log('✅ 该账号今日已签到（不发送通知）');
                allResults.push(`账号${i+1}: 已签到`);
                continue;
            }

            console.log('🔄 该账号未签到，开始执行签到...');

            // ====================== 未签到 → 启动浏览器执行签到 ======================
            let browser = await puppeteer.launch({
                executablePath: '/usr/bin/chromium-browser',
                headless: true,
                args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
            });

            const page = await browser.newPage();
            await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36');
            await page.setCookie(...cookies);

            // 签到前恩山币
            await page.goto(`${FORUM_BASE}/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu`, { waitUntil: 'networkidle2' });
            const beforeText = await page.evaluate(() => document.body.innerText || '');
            const beforeCoins = extractEnshanCoins(beforeText);

            // 执行签到
            await page.goto(`${FORUM_BASE}/erling_qd-sign_in.html`, { waitUntil: 'networkidle2' });
            const signed = await page.evaluate(() => {
                const btn = document.getElementById('signin-btn');
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            });

            if (!signed) throw new Error('未找到签到按钮（#signin-btn）');

            console.log('✅ 已点击签到按钮，等待结果...');
            await new Promise(resolve => setTimeout(resolve, 4000));

            // 签到后恩山币
            await page.goto(`${FORUM_BASE}/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu`, { waitUntil: 'networkidle2' });
            const afterText = await page.evaluate(() => document.body.innerText || '');
            const afterCoins = extractEnshanCoins(afterText);
            const increase = afterCoins - beforeCoins;

            console.log(`💰 签到成功！本次增加 ${increase} 币`);

            allResults.push(`账号${i+1}: 签到成功（+${increase}币）`);

            await browser.close();

        } catch (err) {
            console.error(`❌ 账号${i+1} 签到失败:`, err.message);
            allResults.push(`账号${i+1}: 签到失败`);
        }
    }

    // ====================== 最终通知（仅在有成功或失败时发送） ======================
    if (allResults.length > 0) {
        const summary = allResults.join('\n');
        const hasAction = allResults.some(r => r.includes('签到成功') || r.includes('签到失败'));

        if (hasAction) {
            await notify.sendNotify('恩山无线论坛签到结果', `【恩山多账号签到完成】\n\n${summary}\n\n时间: ${new Date().toLocaleString('zh-CN')}`);
            console.log('🎉 多账号签到完成，通知已发送');
        } else {
            console.log('✅ 所有账号均已签到，无需发送通知');
        }
    }

    console.log('🔚 全部任务执行完毕');
})();
