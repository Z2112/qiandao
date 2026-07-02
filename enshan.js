// =============================================
// 恩山无线论坛（right.com.cn）自动签到脚本
// 版本: 3.3 - 修复「已签到」按钮误判为未找到签到按钮
// =============================================
// cron: 0 8,15 * * *
// new Env('恩山签到');

const puppeteer = require('puppeteer-core');
const notify = require('./sendNotify');

const FORUM_BASE = 'https://www.right.com.cn/forum';
const SIGN_URL = `${FORUM_BASE}/erling_qd-sign_in.html`;
const CREDIT_URL = `${FORUM_BASE}/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu`;
const RANDOM_SIGNIN = process.env.RANDOM_SIGNIN === 'true';
const MAX_RANDOM_DELAY = parseInt(process.env.MAX_RANDOM_DELAY) || 3600;
// ALWAYS_NOTIFY=true：成功/失败都发通知；false：仅失败时发通知
const ALWAYS_NOTIFY = String(process.env.ALWAYS_NOTIFY || '').toLowerCase() === 'true';

function extractValue(html, className) {
    const regex = new RegExp(`class="${className}">\\s*(\\d+)`, 'i');
    const match = html.match(regex);
    return match ? match[1] : '?';
}

function extractEnshanCoins(html) {
    let match = html.match(/id="hcredit_2">\s*(\d+)\s*币/i);
    if (match) return match[1];

    match = html.match(/恩山币[:：]?\s*(\d+)\s*币/i);
    if (match) return match[1];

    match = html.match(/<span[^>]*>(\d+)\s*币<\/span>/i);
    if (match) return match[1];

    return '?';
}

/** 宽松判断页面是否已签到（兼容 disabled 属性顺序、空格、文案差异） */
function isAlreadySignedHtml(html) {
    if (!html) return false;

    // 按钮文案为「已签到」
    if (/已签到\s*<\/(?:button|a|span|div)/i.test(html)) return true;
    if (/<(?:button|a|input)[^>]*>\s*已签到\s*</i.test(html)) return true;
    if (/value\s*=\s*["']已签到["']/i.test(html)) return true;

    // signin-btn 已禁用 / 文案已变更
    if (/id\s*=\s*["']signin-btn["'][^>]*(?:disabled|已签到)/i.test(html)) return true;
    if (/id\s*=\s*["']signin-btn["'][^>]*>\s*已签到/i.test(html)) return true;

    // 页面提示
    if (/今天已经签到|今日已签到|您今天已经签到|已经签到过了/.test(html)) return true;

    // 常见：disabled + 已签到（属性顺序不定）
    if (/disabled[\s\S]{0,80}已签到|已签到[\s\S]{0,80}disabled/i.test(html)) return true;

    return false;
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

async function fetchHtml(url, cookieHeader) {
    const res = await fetch(url, {
        headers: {
            cookie: cookieHeader,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    });
    return res.text();
}

async function buildResultLine(statusText, accountIndex, cookieHeader, htmlHint) {
    let html = htmlHint || '';
    try {
        if (!html) html = await fetchHtml(SIGN_URL, cookieHeader);
    } catch (_) { /* ignore */ }

    const todayPoint = extractValue(html, 'erqd-current-point');
    const continuous = extractValue(html, 'erqd-continuous-days');

    let enshanCoins = '?';
    try {
        const creditHtml = await fetchHtml(CREDIT_URL, cookieHeader);
        enshanCoins = extractEnshanCoins(creditHtml);
    } catch (_) { /* ignore */ }

    return `✅ ${statusText} | 账号${accountIndex} | 今日积分+${todayPoint} | 连续${continuous}天 | 恩山币: ${enshanCoins}`;
}

/**
 * 在浏览器页面中尝试签到：
 * - already：页面已是「已签到」
 * - clicked：已点击签到按钮
 * - not_found：既无已签到也无签到按钮
 */
async function trySignOnPage(page) {
    // 等页面/插件脚本渲染按钮
    await new Promise(r => setTimeout(r, 2000));
    await page.waitForSelector('#signin-btn, button, .btn', { timeout: 8000 }).catch(() => {});

    return page.evaluate(() => {
        const textOf = (el) => ((el && (el.innerText || el.textContent || el.value || '')) || '').replace(/\s+/g, ' ').trim();

        const candidates = Array.from(document.querySelectorAll(
            'button, a, input[type="button"], input[type="submit"], span, div'
        ));

        // 1) 已签到：按钮/文案显示「已签到」
        const signedEl = candidates.find((el) => {
            const t = textOf(el);
            return t === '已签到' || /^已签到/.test(t) || t.includes('今日已签到') || t.includes('今天已经签到');
        });
        if (signedEl) return { status: 'already', reason: '页面显示已签到' };

        const bodyText = textOf(document.body);
        if (/今天已经签到|今日已签到|您今天已经签到|已经签到过了/.test(bodyText)) {
            return { status: 'already', reason: '页面文案已签到' };
        }

        // 2) 可点击签到按钮
        const byId = document.getElementById('signin-btn');
        const signButtons = [];
        if (byId) signButtons.push(byId);
        for (const el of candidates) {
            const t = textOf(el);
            if (!t) continue;
            // 必须含「签到」，且不是「已签到」
            if (t.includes('签到') && !t.includes('已签到')) signButtons.push(el);
        }

        for (const btn of signButtons) {
            if (btn.disabled || btn.getAttribute('disabled') !== null) {
                // 禁用且与签到相关 → 多半已签
                const t = textOf(btn);
                if (t.includes('已签到') || t.includes('签到')) {
                    return { status: 'already', reason: '签到按钮已禁用' };
                }
                continue;
            }
            btn.click();
            return { status: 'clicked', reason: textOf(btn) || btn.id || 'unknown' };
        }

        return { status: 'not_found', reason: '未找到可点击的签到按钮，且未检测到已签到' };
    });
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
        const accountIndex = i + 1;
        console.log(`\n📌 处理第 ${accountIndex}/${cookieStrings.length} 个账号`);

        const cookies = parseCookies(cookieStr);
        const cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join('; ');

        try {
            // ---------- 轻量预检 ----------
            let checkHtml = '';
            try {
                checkHtml = await fetchHtml(SIGN_URL, cookieHeader);
            } catch (e) {
                console.log(`⚠️ 预检请求失败，将改用浏览器: ${e.message}`);
            }

            if (checkHtml && isAlreadySignedHtml(checkHtml)) {
                const line = await buildResultLine('今日已签到', accountIndex, cookieHeader, checkHtml);
                console.log(line);
                allResults.push(line);
                continue;
            }

            // ---------- 浏览器签到 ----------
            console.log('🚀 启动浏览器...');
            let browser;
            let signOutcome = null;

            try {
                browser = await puppeteer.launch({
                    executablePath: process.env.CHROME_PATH || '/usr/bin/chromium-browser',
                    headless: true,
                    args: [
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage'
                    ]
                });

                const page = await browser.newPage();
                await page.setUserAgent(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                );
                await page.setCookie(...cookies);
                await page.goto(SIGN_URL, {
                    waitUntil: 'networkidle2',
                    timeout: 45000
                }).catch(async () => {
                    await page.goto(SIGN_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
                });

                signOutcome = await trySignOnPage(page);
                console.log(`📋 页面签到判定: ${signOutcome.status} (${signOutcome.reason || ''})`);

                if (signOutcome.status === 'clicked') {
                    console.log('✅ 已点击签到按钮');
                    await page.waitForNavigation({
                        waitUntil: 'domcontentloaded',
                        timeout: 10000
                    }).catch(() => {});
                    // 点击后稍等，再确认是否变为已签到
                    await new Promise(r => setTimeout(r, 2000));
                    const afterHtml = await page.content();
                    if (isAlreadySignedHtml(afterHtml)) {
                        signOutcome = { status: 'success', reason: '点击后已变为已签到' };
                    } else {
                        // 再扫一次按钮状态
                        const recheck = await trySignOnPage(page);
                        if (recheck.status === 'already') {
                            signOutcome = { status: 'success', reason: '点击后页面显示已签到' };
                        } else {
                            signOutcome = { status: 'success', reason: '已点击签到' };
                        }
                    }
                } else if (signOutcome.status === 'already') {
                    // 浏览器确认已签到
                } else {
                    // not_found：用完整 HTML 再判一次，避免误报
                    const pageHtml = await page.content();
                    if (isAlreadySignedHtml(pageHtml)) {
                        signOutcome = { status: 'already', reason: 'HTML 复核为已签到' };
                    }
                }

                console.log('🔚 关闭浏览器');
            } catch (err) {
                console.error(`❌ 账号${accountIndex} 浏览器阶段失败:`, err.message);
                allResults.push(`❌ 签到失败 | 账号${accountIndex} | ${err.message}`);
                signOutcome = null;
            } finally {
                if (browser) {
                    await browser.close().catch(() => {});
                }
            }

            if (allResults.some(r => r.includes(`账号${accountIndex}`))) {
                continue;
            }

            if (!signOutcome || signOutcome.status === 'not_found') {
                // 浏览器失败后最后再用接口复核一次
                try {
                    const finalHtml = await fetchHtml(SIGN_URL, cookieHeader);
                    if (isAlreadySignedHtml(finalHtml)) {
                        const line = await buildResultLine('今日已签到', accountIndex, cookieHeader, finalHtml);
                        console.log(line);
                        allResults.push(line);
                        continue;
                    }
                } catch (_) { /* ignore */ }

                allResults.push(`❌ 签到失败 | 账号${accountIndex} | ${signOutcome?.reason || '未找到签到按钮'}`);
                continue;
            }

            if (signOutcome.status === 'already') {
                const line = await buildResultLine('今日已签到', accountIndex, cookieHeader);
                console.log(line);
                allResults.push(line);
            } else {
                // success / clicked
                const line = await buildResultLine('签到成功', accountIndex, cookieHeader);
                console.log(line);
                allResults.push(line);
            }

        } catch (err) {
            console.error(`❌ 账号${accountIndex} 失败:`, err.message);
            if (!allResults.some(r => r.includes(`账号${accountIndex}`))) {
                allResults.push(`❌ 签到失败 | 账号${accountIndex} | ${err.message}`);
            }
        }
    }

    const hasFail = allResults.some(r => r.includes('签到失败') || r.includes('❌'));
    if (allResults.length > 0 && (ALWAYS_NOTIFY || hasFail)) {
        await notify.sendNotify('恩山无线论坛签到结果',
            `【恩山多账号签到完成】\n\n${allResults.join('\n')}\n\n时间: ${new Date().toLocaleString('zh-CN')}`);
        console.log(ALWAYS_NOTIFY
            ? '🎉 通知已发送（ALWAYS_NOTIFY=true，成功与否均通知）'
            : '🎉 通知已发送（存在签到失败）');
    } else {
        console.log('✅ 全部签到成功/已签到，ALWAYS_NOTIFY=false，跳过通知');
    }

    console.log('🔚 全部任务执行完毕');
})();
