/* Record Hatua really being used, in step with the voice. Needs the practice school on port 8799.
     node record.js teachers | parents [--dry]
   Writes screen-<ep>.mp4 (960 x 600), which starts at the same moment as the voice. */
const { chromium } = require('playwright'); const fs = require('fs'); const { execFileSync } = require('child_process');
const D = __dirname, ep = process.argv[2]; const plan = JSON.parse(fs.readFileSync(`${D}/plan-${ep}.json`));
const U = 'http://127.0.0.1:8799/'; const W = 960, H = 600;
const FAST = process.argv.includes('--fast');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const CURSOR = () => {
  const make = () => {
    if (document.getElementById('hatua-cursor') || !document.body) return;
    const c = document.createElement('div'); c.id = 'hatua-cursor';
    c.style.cssText = 'position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;pointer-events:none;transform:translate(480px,420px);will-change:transform';
    c.innerHTML = '<svg width="26" height="26" viewBox="0 0 26 26"><path d="M4 2 L4 21 L9.2 16.4 L12.6 24 L16 22.5 L12.7 15 L19.5 15 Z" fill="#111" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/></svg><span style="position:absolute;left:-13px;top:-13px;width:34px;height:34px;border-radius:50%;border:3px solid #e9a23b;opacity:0;transform:scale(.4)"></span>';
    document.body.appendChild(c);
    const host = () => { const d = document.querySelector('dialog[open]') || document.body; if (c.parentNode !== d) d.appendChild(c); };
    addEventListener('mousemove', e => { host(); c.style.transform = `translate(${e.clientX}px,${e.clientY}px)`; }, true);
    addEventListener('mousedown', () => { const r = c.lastChild; r.style.transition = 'none'; r.style.opacity = '1'; r.style.transform = 'scale(.4)';
      requestAnimationFrame(() => { r.style.transition = 'all .45s ease-out'; r.style.opacity = '0'; r.style.transform = 'scale(1.5)'; }); }, true);
    new MutationObserver(host).observe(document.documentElement, { subtree: true, attributes: true, attributeFilter: ['open'] });
  };
  if (document.body) make(); else addEventListener('DOMContentLoaded', make);
};
(async () => {
  const b = await chromium.launch();
  // What must already be true before the film starts.
  if (ep === 'parents') {
    const q = await (await b.newContext({ viewport: { width: 1180, height: 820 } })).newPage();
    await q.goto(U); await q.fill('#si-id', 'M-6001'); await q.fill('#si-pin', '246810'); await q.click('#si-go');
    await q.waitForSelector('#privacy:not([hidden])'); await q.check('#pv-ok'); await q.click('#pv-go'); await q.waitForSelector('#who b');
    await q.evaluate(async () => {
      await api('account/whatsapp', { method: 'POST', json: { phone: '0700 000 000', agreed: true } });
      await api('drive/decide', { method: 'POST', json: { path: 'Grade 6/2026 Term 3/Grade 6 Term 3 2026 results.xlsx', decision: 'approve' } });
      const c = (await api('learner/HT-0603/comment', { method: 'POST', json: {} })).comment;
      await api(`comment/${c.comment_id}/rate`, { method: 'POST', json: { rating: 'up' } });
    });
    await q.context().close();
  }
  const ctx = await b.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, colorScheme: 'light' });
  await ctx.route(/wa\.me/, r => r.fulfill({ status: 200, contentType: 'text/html', body: '<title>WhatsApp</title><p>WhatsApp</p>' }));
  await ctx.addInitScript(CURSOR); const p = await ctx.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  await p.goto(U); await p.waitForSelector('#si-id'); await sleep(600);
  let pos = [480, 420]; await p.mouse.move(...pos);
  const M = {
    async move(x, y, ms = 650) { const [x0, y0] = pos, n = Math.max(8, Math.round(ms / 16));
      for (let i = 1; i <= n; i++) { const k = i / n, e = k * k * (3 - 2 * k); await p.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e); await sleep(14); } pos = [x, y]; },
    async box(sel, nth = 0) { const l = p.locator(sel).nth(nth); await l.waitFor({ state: 'visible', timeout: 8000 });
      const moved = await l.evaluate(el => { const r = el.getBoundingClientRect(); if (r.top < 70 || r.bottom > innerHeight - 40) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); return true; } return false; }); await sleep(moved ? 500 : 120);
      return l.boundingBox(); },
    async to(sel, nth = 0, fx = 0.5, fy = 0.5) { const r = await this.box(sel, nth); await this.move(r.x + r.width * fx, r.y + r.height * fy); },
    async click(sel, nth = 0, fx = 0.5) { await this.to(sel, nth, fx); await sleep(180); await p.mouse.down(); await sleep(70); await p.mouse.up(); await sleep(250); },
    async type(sel, text, delay = 85) { await this.click(sel); await p.keyboard.type(text, { delay }); await sleep(200); },
    async show(sel, nth = 0) { const l = p.locator(sel).nth(nth); await l.waitFor({ state: 'visible', timeout: 8000 }); await l.evaluate(el => el.scrollIntoView({ behavior: 'smooth', block: 'center' })); await sleep(700); },
    async top() { await p.evaluate(() => scrollTo({ top: 0, behavior: 'smooth' })); await sleep(600); },
  };
  const ACTS = {
    teachers: {
      signin: [async () => { await M.to('#si-role [data-role=teacher]'); }, async () => { await M.click('#si-role [data-role=teacher]'); },
        async () => { await M.type('#si-id', 'M-6001'); await M.type('#si-pin', '246810'); await M.click('#si-go'); await p.waitForSelector('#privacy:not([hidden])'); }],
      privacy: [async () => { await M.to('#pv-title', 0, 0.3); }, async () => { await M.to('#pv-body', 0, 0.4, 0.3); await p.evaluate(() => document.getElementById('pv-body').scrollTo({ top: 400, behavior: 'smooth' })); },
        async () => { await M.click('#pv-ok'); await sleep(300); await M.click('#pv-go'); await p.waitForSelector('#who b'); }],
      today: [async () => { await M.move(300, 150, 500); }, async () => { await M.to('[data-tab=today]'); }, async () => { await M.to('.card.task'); await M.to('.card.task [data-go-drive]'); }],
      approve: [async () => { await M.click('.card.task [data-go-drive]'); await sleep(500); await M.click('[data-preview]'); await p.waitForSelector('.preview'); },
        async () => { await M.show('.preview'); await M.to('.preview', 0, 0.3, 0.35); }, async () => { await M.click('[data-decide=approve]'); }, async () => { await sleep(1900); await p.evaluate(() => { document.getElementById('toast').hidden = true; }); await M.top(); }],
      watch: [async () => { await M.click('[data-tab=today]'); },
        async () => { await M.to('.card.watch, .alert-line', 0, 0.4); }, async () => { await M.click('[data-open]'); await p.waitForSelector('#msg-parent'); }],
      longview: [async () => { await M.show('table.long'); await M.to('table.long', 0, 0.2, 0.2); }, async () => { await M.to('table.long', 0, 0.7, 0.5); },
        async () => { await M.click('table.long td button', 12); await p.waitForSelector('#dlg[open]'); await sleep(2600); await M.click('#dlg-x'); }],
      comment: [async () => { await M.click('#cm-write'); await p.waitForSelector('#cm-up'); }, async () => { await M.show('.comment'); await M.to('.comment', 0, 0.4, 0.3); },
        async () => { await sleep(1600); await M.click('#cm-up'); await sleep(700); await M.click('#cm-use'); }],
      whatsapp: [async () => { await p.evaluate(() => { document.getElementById('toast').hidden = true; }); await M.top(); await M.click('#msg-parent'); await p.waitForSelector('#pm-text'); },
        async () => { await M.to('#pm-text', 0, 0.5, 0.4); await M.click('[data-style=shorter]'); await sleep(900); await M.to('#pm-text', 0, 0.5, 0.4); },
        async () => { await M.show('#pm-to'); await M.to('#pm-to', 0, 0.4); await sleep(400); await M.type('#pm-phone', '0712 345 678', 100); await M.click('#pm-save'); },
        async () => { await M.to('#pm-who', 0, 0.4); await sleep(900); await M.click('#pm-ok'); await sleep(300); await M.click('#pm-wa'); await p.waitForSelector('.sent.ok'); await p.bringToFront(); },
        async () => { await M.to('.sent.ok', 0, 0.3); await sleep(1200); await M.click('#pm-sent'); }],
      access: [async () => { await M.show('#pa-add'); await M.to('#pa-add'); },
        async () => { await M.click('#pa-add'); await M.type('#pa-name', 'Grace Wanjiku', 95); },
        async () => { await M.click('#pa-go'); await p.waitForSelector('.slip'); await M.to('.slip', 0, 0.6, 0.55); await sleep(1500); await M.to('#sl-print'); }],
      assistant: [async () => { await M.click('#sl-done'); await M.click('#ask-launch'); await M.type('#ask-q', 'How is Kamau doing?', 35); },
        async () => { await M.click('#ask-send'); await sleep(900); await M.click('.msg.bot .chips.live .chip', 1); },
        async () => { await p.waitForSelector('[data-next]'); await M.to('[data-next]', 0); }, async () => { await sleep(600); await M.click('#ask-min'); }],
      look: [async () => { await M.click('#account'); await p.waitForSelector('#wn-form'); await M.show('#wn-form'); await M.type('#wn-phone', '0700 000 000', 90); },
        async () => { await M.click('.dlg [data-look-pick=dark]'); await sleep(900); await M.click('.dlg [data-look-pick=light]'); },
        async () => { await M.click('#dlg-x'); await M.to('#video-guide'); await sleep(250); await M.to('#app header a.btn'); }],
    },
    parents: {
      slip: [async () => { await M.move(480, 300, 500); }, async () => { await M.to('#si-id'); }, async () => { await M.to('#si-facts'); }],
      signin: [async () => { await M.top(); await M.click('#si-role [data-role=parent]'); }, async () => { await M.type('#si-id', 'P-100003'); await M.type('#si-pin', '246810'); }, async () => { await M.click('#si-go'); await p.waitForSelector('#np-form:not([hidden])'); }],
      pin: [async () => { await M.to('#np-hello'); }, async () => { await M.type('#np-new', 'mwangi73', 120); await M.type('#np-again', 'mwangi73', 120); }, async () => { await M.click('#np-go'); await p.waitForSelector('#privacy:not([hidden])'); }],
      privacy: [async () => { await M.to('#pv-title', 0, 0.3); }, async () => { await M.to('#pv-body', 0, 0.4, 0.3); await p.evaluate(() => document.getElementById('pv-body').scrollTo({ top: 400, behavior: 'smooth' })); },
        async () => { await M.click('#pv-ok'); await sleep(300); await M.click('#pv-go'); await p.waitForSelector('#child .area'); await p.evaluate(() => { document.getElementById('toast').hidden = true; }); }],
      child: [async () => { await M.to('#child .learner-head', 0, 0.3); }, async () => { await M.to('#child .areas', 0, 0.3, 0.3); await M.to('#child .areas', 0, 0.7, 0.6, 900); },
        async () => { await M.click('#child .area button[data-ev]', 3); await p.waitForSelector('#dlg[open]'); await sleep(2600); await M.click('#dlg-x'); }],
      days: [async () => { await M.show('#child .days'); await M.to('#child .days'); }, async () => { await M.to('#child section:has(h3:text-is("From the class teacher"))', 0, 0.4, 0.6); }, async () => { await sleep(300); }],
      message: [async () => { await M.show('#msg-teacher'); await M.click('#msg-teacher'); await p.waitForSelector('#pm-text'); },
        async () => { await M.click('#pm-text'); await p.keyboard.press('End'); await p.keyboard.type('Can we talk about his Mathematics this week?', { delay: 45 }); await M.click('[data-style=warmer]'); },
        async () => { await sleep(500); await M.to('.who-card', 0, 0.3); await sleep(700); await M.click('#pm-ok'); await sleep(300); await M.click('#pm-wa'); await p.waitForSelector('.sent.ok'); await p.bringToFront(); },
        async () => { await M.to('.sent.ok', 0, 0.3); await sleep(800); await M.click('#dlg-x'); }],
      pathways: [async () => { const h = p.locator('#child h3', { hasText: /pathway/i }).first(); await h.evaluate(el => el.scrollIntoView({ behavior: 'smooth', block: 'center' })); await sleep(700); const r = await h.boundingBox(); await M.move(r.x + 120, r.y + 14); },
        async () => { const r = await p.locator('#child h3', { hasText: /pathway/i }).first().boundingBox(); await M.move(r.x + 260, r.y + 70, 900); }],
      assistant: [async () => { await M.top(); await M.click('#ask-launch'); }, async () => { await M.type('#ask-q', 'How is Kamau doing in Mathematics?', 45); await M.click('#ask-send'); },
        async () => { await sleep(500); await M.click('.msg.bot .chips.live .chip', 0); },
        async () => { await p.waitForSelector('[data-next]'); await M.to('[data-next]', 0); await sleep(900); await M.click('#ask-min'); }],
      signout: [async () => { await M.to('#f-signout'); await sleep(600); await M.click('#f-signout'); }, async () => { await p.waitForSelector('#si-id'); await M.move(480, 330); }],
    },
  }[ep];
  if (ep === 'parents') ACTS.pathways; // (kept for clarity: Kamau is in Grade 6, so pathway ideas are still closed)
  // Start filming.
  const frames = []; const cdp = await ctx.newCDPSession(p);
  cdp.on('Page.screencastFrame', f => { frames.push([f.metadata.timestamp, Buffer.from(f.data, 'base64')]); cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {}); });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 93, everyNthFrame: 1 });
  await M.move(481, 421, 100); await sleep(300);
  const t0 = Date.now() / 1000; const now = () => Date.now() / 1000 - t0; const late = [];
  for (const s of plan.scenes) {
    const acts = ACTS[s.id] || [];
    for (let i = 0; i < s.lines.length; i++) {
      const at = s.start + s.lines[i].start - 0.15; if (FAST) {} else if (now() < at) await sleep((at - now()) * 1000); else if (now() - at > 0.4) late.push([s.id, i, +(now() - at).toFixed(2)]);
      const a0 = now(); if (acts[i]) { try { await acts[i](); const room = (i + 1 < s.lines.length ? s.lines[i + 1].start : s.dur) - s.lines[i].start; if (FAST) console.log(s.id, i, 'took', (now() - a0).toFixed(1), 'room', room.toFixed(1), now() - a0 > room ? '<<< TOO LONG' : ''); } catch (e) { console.log('ACT FAILED', s.id, i, e.message.split('\n')[0]); if (!process.argv.includes('--dry')) throw e; } }
    }
    const end = s.start + s.dur; if (now() > end + 0.3) late.push([s.id, 'end', +(now() - end).toFixed(2)]);
  }
  if (!FAST && now() < plan.total) await sleep((plan.total - now()) * 1000);
  if (FAST) { await b.close(); return; }
  await cdp.send('Page.stopScreencast'); await sleep(200);
  console.log(ep, 'frames', frames.length, 'late', JSON.stringify(late), 'errors', errs);
  // Frames arrive only when the picture changes, so each is shown until the next one.
  const dir = `${D}/frames-${ep}`; fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir);
  const use = frames.filter(([t]) => t >= t0 - 0.5); let list = '';
  use.forEach(([t, buf], i) => { const f = `${dir}/f${String(i).padStart(5, '0')}.jpg`; fs.writeFileSync(f, buf);
    const a = Math.max(0, t - t0), z = i + 1 < use.length ? Math.max(0, use[i + 1][0] - t0) : plan.total; if (z > a) list += `file '${f}'\nduration ${(z - a).toFixed(4)}\n`; });
  list += `file '${dir}/f${String(use.length - 1).padStart(5, '0')}.jpg'\n`; fs.writeFileSync(`${D}/frames-${ep}.txt`, list);
  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', `${D}/frames-${ep}.txt`, '-vf', `fps=30,scale=${W}:${H},format=yuv420p`, '-c:v', 'libx264', '-crf', '16', '-preset', 'veryfast', '-t', String(plan.total), `${D}/screen-${ep}.part.mp4`]);
  fs.renameSync(`${D}/screen-${ep}.part.mp4`, `${D}/screen-${ep}.mp4`);
  await b.close();
})().catch(e => { console.error('FAILED', e.message); process.exit(1); });
