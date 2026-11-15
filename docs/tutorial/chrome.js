/* Draw the frame around the screen recording: one PNG for each state, and a list ffmpeg can play. */
const { chromium } = require('playwright'); const fs = require('fs');
const D = __dirname, ep = process.argv[2]; const plan = JSON.parse(fs.readFileSync(`${D}/plan-${ep}.json`));
const BEAT = 0.3;
(async () => {
  const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 })).newPage();
  await p.goto('file://' + D + '/chrome.html'); await p.evaluate(pl => load(pl), plan);
  const dir = `${D}/chrome-${ep}`; fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir);
  const segs = []; // [start, end, state]
  plan.scenes.forEach((s, i) => {
    let u = 0; const push = (to, st) => { if (to > u + 1e-6) { segs.push([s.start + u, s.start + to, { scene: i, ...st }]); u = to; } };
    s.lines.forEach((l, j) => {
      push(l.start, { caption: j ? s.lines[j - 1].text : '', speaking: false, beat: 0 });
      push(l.start + l.dur, { caption: l.text, speaking: true, beat: 0 });
    });
    push(s.dur, { caption: s.lines[s.lines.length - 1].text, speaking: false, beat: 0 });
  });
  const seen = new Map(); let list = '';
  for (const [a, z, st] of segs) {
    const key = JSON.stringify(st); let name = seen.get(key);
    if (!name) { name = `s${String(seen.size).padStart(4, '0')}.png`; seen.set(key, name); await p.evaluate(s => show(s), st); await p.screenshot({ path: `${dir}/${name}`, omitBackground: true }); }
    list += `file '${dir}/${name}'\nduration ${(z - a).toFixed(4)}\n`;
  }
  list += `file '${dir}/${seen.get(JSON.stringify(segs[segs.length - 1][2]))}'\n`;
  fs.writeFileSync(`${D}/chrome-${ep}.txt`, list); console.log(ep, 'states', seen.size, 'segments', segs.length);
  await b.close();
})();
