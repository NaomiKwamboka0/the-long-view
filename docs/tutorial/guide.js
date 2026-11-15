/* Film the drawn guide for one episode: guide-<ep>.mp4 (264 x 652, 30 frames a second). */
const { chromium } = require('playwright'); const fs = require('fs'); const { spawn, execFileSync } = require('child_process');
const D = __dirname, ep = process.argv[2], FPS = 30, PARTS = 4;
const plan = JSON.parse(fs.readFileSync(`${D}/plan-${ep}.json`)), env = JSON.parse(fs.readFileSync(`${D}/env-${ep}.json`));
(async () => {
  const b = await chromium.launch(); const n = Math.round(plan.total * FPS), per = Math.ceil(n / PARTS);
  await Promise.all([...Array(PARTS)].map(async (_, k) => {
    const p = await (await b.newContext({ viewport: { width: 264, height: 652 }, deviceScaleFactor: 1 })).newPage();
    await p.goto('file://' + D + '/guide.html'); await p.evaluate(([a, c]) => load(a, c), [plan, env]);
    const out = `${D}/guide-${ep}-${k}.mp4`;
    const ff = spawn('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-crf', '16', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', out]);
    const done = new Promise((ok, bad) => ff.on('close', c => c === 0 ? ok() : bad(new Error('ffmpeg ' + c))));
    for (let f = k * per; f < Math.min(n, (k + 1) * per); f++) { await p.evaluate(t => setT(t), f / FPS); const buf = await p.screenshot({ type: 'jpeg', quality: 93 }); if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r)); }
    ff.stdin.end(); await done;
  }));
  fs.writeFileSync(`${D}/guide-${ep}.txt`, [...Array(PARTS)].map((_, k) => `file '${D}/guide-${ep}-${k}.mp4'`).join('\n'));
  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', `${D}/guide-${ep}.txt`, '-c', 'copy', `${D}/guide-${ep}.mp4`]);
  console.log('guide', ep, n); await b.close();
})();
