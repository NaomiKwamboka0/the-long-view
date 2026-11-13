/* Hostile text escaping checks for ui/portal.html (WP1.4) */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM, VirtualConsole } = require('jsdom');

const portalHtml = fs.readFileSync('ui/portal.html', 'utf8');

const HOSTILE_IMG = '<img src=x onerror="window.__x=1">';
const HOSTILE_SCRIPT = '"><script>window.__x=1</script>';
const HOSTILE_FILE = `test_${HOSTILE_IMG}_${HOSTILE_SCRIPT}.csv`;

function createPortalDom() {
  const virtualConsole = new VirtualConsole();
  const dom = new JSDOM(portalHtml, {
    url: 'http://127.0.0.1:8765/',
    runScripts: 'dangerously',
    virtualConsole,
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false });
      w.confirm = () => true;
      w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
      w.HTMLDialogElement.prototype.close = function () { this.open = false; };
    }
  });
  return dom;
}

console.log('Running portal XSS audit checks...');

const dom = createPortalDom();
const w = dom.window;
const esc = w.eval('esc');
const renderAnswer = w.eval('renderAnswer');
const askAdd = w.eval('askAdd');

// 1. Check esc function directly
assert.equal(esc(HOSTILE_IMG).includes('<'), false);
assert.equal(esc(HOSTILE_SCRIPT).includes('<'), false);
assert.equal(esc(HOSTILE_FILE).includes('<'), false);
assert.equal(w.__x, undefined);

// 2. Check renderAnswer
const renderedAnswer = renderAnswer(`Here is an answer with ${HOSTILE_IMG} and ${HOSTILE_SCRIPT} [R-0001]`);
assert.equal(renderedAnswer.includes('<img'), false);
assert.equal(renderedAnswer.includes('<script'), false);
const testBox = w.document.createElement('div');
testBox.innerHTML = renderedAnswer;
assert.equal(testBox.querySelector('img'), null);
assert.equal(testBox.querySelector('script'), null);
assert.equal(w.__x, undefined);

// 3. Check askAdd
askAdd('bot', renderedAnswer, 'Qwen model');
assert.equal(w.document.querySelector('img'), null);
assert.equal(w.__x, undefined);

// 4. Check drive rendering with hostile file name
w.eval(`
DRIVE = [{
  folder: ${JSON.stringify(HOSTILE_IMG)},
  terms: [{
    label: 'Term 3',
    files: [{
      path: 'Grade 9/2026 Term 3/' + ${JSON.stringify(HOSTILE_FILE)},
      name: ${JSON.stringify(HOSTILE_FILE)},
      status: 'waiting',
      modified: '2026-11-06T12:00:00'
    }]
  }]
}];
renderDrive();
`);
assert.equal(w.document.getElementById('drive').querySelector('img'), null);
assert.equal(w.document.getElementById('drive').querySelector('script'), null);
assert.equal(w.__x, undefined);

// 5. Check class list and learner rendering with hostile attributes
w.eval(`
CLASS = [{
  id: 'HT-9999',
  name: 'Amina ' + ${JSON.stringify(HOSTILE_IMG)},
  stream: '9A ' + ${JSON.stringify(HOSTILE_SCRIPT)},
  grade: 9,
  alerts: 1,
  told: 0,
  kinds: ['sustained_strength']
}];
renderClass();
`);
assert.equal(w.document.getElementById('people').querySelector('img'), null);
assert.equal(w.document.getElementById('people').querySelector('script'), null);
assert.equal(w.__x, undefined);

// 6. Check learner detail view with hostile records, notes, flags, scores
w.eval(`
L = {
  id: 'HT-9999',
  name: 'Amina ' + ${JSON.stringify(HOSTILE_IMG)},
  stream: '9A ' + ${JSON.stringify(HOSTILE_SCRIPT)},
  grade: 9,
  span: '2024 to 2026',
  reviewed: 50,
  notices: [{
    notice_id: 'NT-01',
    kind: 'sharp_drop',
    text: 'Mathematics dropped ' + ${JSON.stringify(HOSTILE_IMG)},
    evidence: ['R-0001'],
    told_parent: null
  }],
  patterns: [{
    pattern_id: 'P-01',
    type: 'sustained_strength',
    family: 'Mathematics',
    statement: 'Held strength in Mathematics ' + ${JSON.stringify(HOSTILE_SCRIPT)},
    trail: [],
    evidence: ['R-0001'],
    caveats: [],
    current: true,
    terms: 4
  }],
  record_notes: [],
  records: [
    ['R-0001', 1, 'Mathematics', 'EE', 9, 2026, 3, 'Mathematics', 'End term ' + ${JSON.stringify(HOSTILE_IMG)}, ${JSON.stringify(HOSTILE_SCRIPT)}, 'Teacher', '2026-10-10', [${JSON.stringify(HOSTILE_IMG)}]]
  ],
  attendance: [
    ['A-0001', 1, 45, 60]
  ],
  notes: [
    ['N-0001', 1, 'Mathematics', 'Teacher note with ' + ${JSON.stringify(HOSTILE_SCRIPT)}]
  ],
  families: ['Mathematics'],
  grades: [{ grade: 9, read_only: false, who: 'Your class this year' }],
  comments: [],
  pathways: {
    stage: 'suggest',
    intro: 'Intro with ' + ${JSON.stringify(HOSTILE_IMG)},
    pathways: [{
      name: 'STEM',
      tracks: 'Pure Sciences',
      summary: 'Summary ' + ${JSON.stringify(HOSTILE_SCRIPT)},
      lines: [{ kind: 'strength', text: 'Strong in Mathematics ' + ${JSON.stringify(HOSTILE_IMG)}, evidence: ['R-0001'] }]
    }]
  }
};
renderLearner();
evidence('R-0001');
`);
assert.equal(w.document.getElementById('learner').querySelector('img'), null);
assert.equal(w.document.getElementById('learner').querySelector('script'), null);
assert.equal(w.document.getElementById('dlg-body').querySelector('img'), null);
assert.equal(w.document.getElementById('dlg-body').querySelector('script'), null);
assert.equal(w.__x, undefined);

console.log('PASS all portal XSS audit checks passed without script execution.');

dom.window.close();
