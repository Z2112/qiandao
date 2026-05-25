// =============================================
// 恩山无线论坛（right.com.cn）自动签到脚本
// 版本: 3.0 - 修复恩山币提取失败问题
// =============================================
// cron: 0 8,15 * * *
// new Env('恩山签到');

const puppeteer = require('puppeteer-core');
const notify = require('./sendNotify');

const FORUM_BASE = 'https://www.right.com.cn/forum';
const RANDOM_SIGNIN = process.env.RANDOM_SIGNIN === 'true';
const MAX_RANDOM_DELAY = parseInt(process.env.MAX_RANDOM_DELAY) || 3600;

function extractValue(html, className) {
    const regex = new RegExp(`class="${className}">\\s*(\\d+)`, 'i');
    const match = html.match(regex);
    return match ? match[1] : '?';
}

function extractEnshanCoins(html) {
    // 优先匹配 id="hcredit_2" (最准确)
    let match = html.match(/id="hcredit_2">\s*(\d+)\s*币/i);
    if (match) return match[1];

    // 匹配 “恩山币: 1453币” 或 “恩山币：1453币”
    match = html.match(/恩山币[:：]?\s*(\d+)\s*币/i);
    if (match) return match[1];

    // 通用 span 匹配
    match = html.match(/<span[^>]*>(\d+)\s*币<\/span>/i);
    if (match) return match[1];

    return '?';
}

function getAllCookies() {
    const raw = process.env.ENSHAN_COOKIE;
    if (!raw) throw new Error('未找到 ENSHAN_COOKIE 环境变量');
    return raw.split(/&|\n|\r\n/).map(s => s.trim()).filter(s => s.length > 10);
}

function parseCookies(cookieInput) {
    return cookieInput.split(';').map(c => {
        const [name, ...value] = c.trim().split('=');
        return name ? { name: name.trim(), value: value.join('=').trim(), domain: '.right.com.cn' } : null;
    }).filter(Boolean);
}

(async () => {
    console.log('🚀 【恩山无线论坛】多账号签到任务开始...');
    const allResults = [];

    if (RANDOM_SIGNIN) {
        const delay = Math.floor(Math.random() * MAX_RANDOM_DELAY) + 1;
        console.log(`⏳ 随机延迟 ${Math.floor(delay / 60)}分${delay % 60}秒...`);
        await new Promise(r => setTimeout(r, delay * 1000));
    }

    const cookieStrings = getAllCookies();

    for (let i = 0; i < cookieStrings.length; i++) {
        const cookieStr = cookieStrings[i];
        console.log(`\n📌 处理第 ${i + 1}/${cookieStrings.length} 个账号`);

        const cookies = parseCookies(cookieStr);
        const cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join('; ');

        try {
            // 轻量检查是否已签到
            const checkRes = await fetch(`${FORUM_BASE}/erling_qd-sign_in.html`, {
                headers: { cookie: cookieHeader }
            });
            const checkHtml = await checkRes.text();

            const todayPoint = extractValue(checkHtml, 'erqd-current-point');
            const continuous = extractValue(checkHtml, 'erqd-continuous-days');

            if (checkHtml.includes('disabled>已签到</button>') || checkHtml.includes('已签到</button>')) {
                // 已签到 → 获取恩山币
                const creditRes = await fetch(
                    `${FORUM_BASE}/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu`,
                    { headers: { cookie: cookieHeader } }
                );
                const creditHtml = await creditRes.text();
                const enshanCoins = extractEnshanCoins(creditHtml);

                console.log(`✅ 已签到 | 今日积分+${todayPoint} | 连续${continuous}天 | 恩山币: ${enshanCoins}`);
                allResults.push(`账号${i + 1}: 已签到 | 今日积分+${todayPoint} | 连续${continuous}天 | 恩山币: ${enshanCoins}`);
                continue;
            }

            // 未签到 → 启动浏览器点击
            console.log('🚀 启动浏览器...');
            const browser = await puppeteer.launch({
                executablePath: '/usr/bin/chromium-browser',
                headless: true,
                args: ['--no-sandbox', '--disable-setuid-sandbox']
            });

            const page = await browser.newPage();
            await page.setCookie(...cookies);
            await page.goto(`${FORUM_BASE}/erling_qd-sign_in.html`, { waitUntil: 'networkidle2' });

            const clicked = await page.evaluate(() => {
                const btn = document.getElementById('signin-btn');
                if (btn) { btn.click(); return true; }
                return false;
            });

            if (!clicked) throw new Error('未找到签到按钮');

            console.log('✅ 已点击签到按钮');
            await new Promise(r => setTimeout(r, 5000));

            console.log('🔚 关闭浏览器');
            await browser.close();

            // 签到后重新获取数据
            const resultRes = await fetch(`${FORUM_BASE}/erling_qd-sign_in.html`, {
                headers: { cookie: cookieHeader }
            });
            const resultHtml = await resultRes.text();

            const newTodayPoint = extractValue(resultHtml, 'erqd-current-point');
            const newContinuous = extractValue(resultHtml, 'erqd-continuous-days');

            // 获取恩山币
            const creditRes = await fetch(
                `${FORUM_BASE}/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu`,
                { headers: { cookie: cookieHeader } }
            );
            const creditHtml = await creditRes.text();
            const enshanCoins = extractEnshanCoins(creditHtml);

            console.log(`✅ 签到成功 | 今日积分+${newTodayPoint} | 连续${newContinuous}天 | 恩山币: ${enshanCoins}`);
            allResults.push(`账号${i + 1}: 签到成功 | 今日积分+${newTodayPoint} | 连续${newContinuous}天 | 恩山币: ${enshanCoins}`);

        } catch (err) {
            console.error(`❌ 账号${i + 1} 失败:`, err.message);
            allResults.push(`账号${i + 1}: 签到失败`);
        }
    }

    // 发送通知
    const hasAction = allResults.some(r => r.includes('签到成功') || r.includes('签到失败'));
    if (hasAction && allResults.length > 0) {
        await notify.sendNotify('恩山无线论坛签到结果',
            `【恩山多账号签到完成】\n\n${allResults.join('\n')}\n\n时间: ${new Date().toLocaleString('zh-CN')}`);
        console.log('🎉 通知已发送');
    } else {
        console.log('✅ 所有账号已签到，无需发送通知');
    }

    console.log('🔚 全部任务执行完毕');
})();