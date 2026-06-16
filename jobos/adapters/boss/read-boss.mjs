#!/usr/bin/env node
// BOSS Zhipin read-only adapter via raw CDP protocol.
//
// Reads job listing cards from the search results page of an already-logged-in
// BOSS Zhipin session. Does NOT navigate to detail pages, click "contact HR",
// or access any personal information.
//
// Prerequisites: Chrome running with --remote-debugging-port=9222, user logged
// into BOSS Zhipin. Run ./launch-chrome.sh first.
//
// Usage: node read-boss.mjs <keyword> [city_code] [port]
//   e.g. node read-boss.mjs "AIGC" 100010000 9222
//
// Output: JSON to stdout with { url, title, items[], diagnostics{}, html }
// Items: { title, salary, company, tags[], link }
//
// Salary note: BOSS uses custom font (kanzhun-mix) to obfuscate salary digits
// (PUA codepoints U+E000-U+F8FF). We replace obfuscated digits with placeholder
// character. Units (K/yuan/day) are plain text.

import http from 'node:http';

const KEYWORD = process.argv[2];
const CITY = process.argv[3] || '100010000'; // 100010000 = nationwide
const PORT = process.argv[4] || '9222';
const INCLUDE_HTML = process.env.JOBOS_BOSS_INCLUDE_HTML !== '0';
const HTML_LIMIT = Number.parseInt(process.env.JOBOS_BOSS_HTML_LIMIT || '250000', 10);

if (!KEYWORD) {
  console.error('Usage: node read-boss.mjs <keyword> [city_code] [port]\n  e.g. node read-boss.mjs "AIGC" 100010000 9222');
  process.exit(1);
}

function pageExtractor() {
  const out = { url: location.href, title: document.title, items: [], diagnostics: {} };
  const bodyText = (document.body.innerText || '');
  const html = document.documentElement ? document.documentElement.outerHTML : '';
  if (INCLUDE_HTML) {
    out.html = html.slice(0, HTML_LIMIT);
    out.diagnostics.htmlLength = html.length;
    out.diagnostics.htmlTruncated = html.length > out.html.length;
  }

  // Anti-scraping / login / verification detection
  if (/请完成.*验证|安全验证|滑块验证|请输入验证码|验证后继续访问|拖动.*完成验证/.test(bodyText)) {
    out.diagnostics.blocked = 'Security verification detected. Solve it manually in the browser and retry.';
    out.diagnostics.pageState = 'verification_required';
  }
  if (/访问受限|异常访问|访问过于频繁|Access Denied|Forbidden|403/.test(bodyText)) {
    out.diagnostics.accessLimited = 'Access appears limited or rate-limited. Pause and retry later.';
    out.diagnostics.pageState = 'access_limited';
  }
  if (/登录后查看|立即登录|扫码登录|未登录/.test(bodyText) && bodyText.length < 1500) {
    out.diagnostics.maybeNeedLogin = 'Appears not logged in or results not loaded (page shows login prompt).';
    out.diagnostics.pageState = 'login_required';
  }

  const txt = (n) => (n ? (n.textContent || '').trim().replace(/\s+/g, ' ') : '');

  // BOSS search results: li.job-card-box = one card per job. Fallback selectors for layout changes.
  let cardEls = [...document.querySelectorAll('li.job-card-box')];
  if (!cardEls.length) cardEls = [...document.querySelectorAll('[class*="job-card-box"], [class*="job-card-wrap"]')];

  const seen = new Set();
  let obfCount = 0;
  for (const el of cardEls) {
    const nameA = el.querySelector('a.job-name, [class*="job-name"]');
    const title = txt(nameA) || txt(el.querySelector('[class*="job-title"] a, [class*="job-title"]'));
    if (!title) continue;
    // Salary: BOSS renders digits as PUA codepoints via custom font. Replace obfuscated
    // digits with placeholder, keep plain-text units (K, yuan/day, etc.).
    const salRaw = txt(el.querySelector('[class*="job-salary"], [class*="salary"]'));
    const salObfuscated = [...salRaw].some(c => c.codePointAt(0) >= 0xE000 && c.codePointAt(0) <= 0xF8FF);
    const salary = [...salRaw].map(c => (c.codePointAt(0) >= 0xE000 && c.codePointAt(0) <= 0xF8FF) ? "▯" : c).join("");
    if (salObfuscated) obfCount++;
    // Tags: experience / education / skills
    const tags = [...el.querySelectorAll('ul.tag-list li, [class*="tag-list"] li, [class*="tag"] li')]
      .map(t => txt(t)).filter(Boolean);
    // Company: footer gongsi link or company-name class
    const company = txt(el.querySelector('a[href*="gongsi"], [class*="company-name"], [class*="company"] a, [class*="company"]'));
    const href = (nameA && nameA.getAttribute('href')) || '';
    const link = href ? (href.startsWith('http') ? href : location.origin + href) : '';

    const key = link || title + '|' + salary;
    if (seen.has(key)) continue;
    seen.add(key);
    out.items.push({ title, salary, company, tags: tags.slice(0, 8), link });
  }

  out.items = out.items.slice(0, 60);
  out.diagnostics.cardCount = cardEls.length;
  if (!out.diagnostics.pageState) out.diagnostics.pageState = out.items.length ? 'normal' : 'empty';
  if (obfCount) out.diagnostics.salaryObfuscated = `${obfCount} salary values have obfuscated digits (placeholder used), units are visible. Open link for exact numbers.`;
  if (!out.items.length) {
    out.diagnostics.sampleRawText = bodyText.slice(0, 400);
    out.diagnostics.salaryNodeProbe = document.querySelectorAll('[class*="salary"]').length;
  }
  return out;
}

// ---- Minimal CDP client (HTTP tabs + single-page WebSocket commands) ----
const sleep = ms => new Promise(r => setTimeout(r, ms));

function httpJson(path, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: 'localhost', port: PORT, path, method }, res => {
      let d = ''; res.on('data', c => (d += c)); res.on('end', () => { try { resolve(JSON.parse(d)); } catch { resolve(d); } });
    });
    req.on('error', reject);
    req.end();
  });
}

// Get a page target (reuse existing, or create a new blank tab)
async function getPageTarget() {
  const list = await httpJson('/json').catch(() => []);
  const existing = Array.isArray(list) && list.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
  if (existing) return existing;
  return httpJson('/json/new', 'PUT'); // new blank tab, then navigate via Page.navigate
}

// Single WS connection for one page: send(method, params) -> Promise(result)
function openCdp(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  ws.addEventListener('message', ev => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    }
  });
  const ready = new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const mid = ++id; pending.set(mid, { resolve, reject });
    ws.send(JSON.stringify({ id: mid, method, params }));
  });
  const evaluate = async (fnOrExpr) => {
    const expression = typeof fnOrExpr === 'function' ? `(${fnOrExpr.toString()})()` : fnOrExpr;
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text || 'evaluate exception');
    return r.result?.value;
  };
  return { ready, send, evaluate, close: () => ws.close() };
}

(async () => {
  let target;
  try {
    await httpJson('/json/version'); // probe
    target = await getPageTarget();
  } catch (e) {
    console.error(`Cannot connect to Chrome debug port ${PORT}. Run ./launch-chrome.sh first and log into BOSS Zhipin.\nReason: ${e.message}`);
    process.exit(1);
  }

  const cdp = openCdp(target.webSocketDebuggerUrl);
  await cdp.ready;
  await cdp.send('Page.enable').catch(() => {});

  // Navigate to search results in the logged-in browser session
  const url = `https://www.zhipin.com/web/geek/job?query=${encodeURIComponent(KEYWORD)}&city=${CITY}`;
  await cdp.send('Page.navigate', { url });

  // SPA: poll for job cards to appear (or login wall), up to ~18s
  for (let i = 0; i < 18; i++) {
    await sleep(1000);
    const state = await cdp.evaluate(() => {
      const cards = document.querySelectorAll('li.job-card-box, [class*="job-card-box"]');
      const salFilled = [...document.querySelectorAll('[class*="job-salary"], [class*="salary"]')]
        .filter(n => (n.textContent || '').trim()).length;
      const t = document.body ? document.body.innerText : '';
      return { cards: cards.length, salFilled, login: /登录后查看|扫码登录|立即登录/.test(t) };
    }).catch(() => ({}));
    // Cards loaded with some salary values filled -> ready; or hit login wall -> stop
    if ((state.cards > 0 && state.salFilled >= Math.min(3, state.cards)) || state.login) break;
    if (i === 6) await cdp.evaluate(() => window.scrollBy(0, 1200)).catch(() => {}); // scroll to trigger lazy load
  }
  await cdp.evaluate(() => window.scrollBy(0, 1600)).catch(() => {});
  await sleep(1500);

  const data = await cdp.evaluate(pageExtractor);
  console.log(JSON.stringify(data, null, 2));
  cdp.close();
})();
