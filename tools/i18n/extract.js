// collect all English UI strings (and rules) of the N8 systems → strings.json {repo: [..]}, rules.json
const fs = require('fs');
const files = {
  kit: ['adn-frn-server/static/n8-kit.js', 'adn-frn-server/static/n8-theme.js'],
  adn: ['adn-frn-server/static/i18n-app.js'],
  crosslink: ['n8crosslink/n8crosslink/web/static/i18n-crosslink.js'],
  hotspot: ['n8-hotspot/static/i18n-app.js'],
  hblink: ['hblink4-freeradioid/dashboard/static/i18n-dashboard.js'],
};
const norm = s => String(s).replace(/\s+/g, ' ').trim();
const SPLIT = /^([^\p{L}0-9"'„(\[]*)([\s\S]*?)([\s:：…·.,!?)\]*▾›]*)$/u;
const out = {}, rules = {};
for (const [k, fl] of Object.entries(files)) {
  const set = new Map();
  rules[k] = [];
  for (const f of fl) {
    const src = fs.readFileSync('/home/claude/' + f, 'utf8');
    const packs = [];
    const sandbox = { window: {}, document: { cookie: '', readyState: 'complete', documentElement: { dataset: {} }, querySelectorAll: () => [], addEventListener() {} },
      location: { search: '', protocol: 'http:' }, navigator: { languages: ['de'] }, localStorage: { getItem() { return null; }, setItem() {} },
      MutationObserver: function () { this.observe = () => {}; }, requestAnimationFrame() {}, CustomEvent: function () {}, NodeFilter: {},
    };
    if (k === 'kit') {
      // capture the add() calls of the kit itself
      const code = src.replace(/function add\(pack\) \{/, 'function add(pack) { __cap(pack);');
      const fn = new Function('window', 'document', 'location', 'navigator', 'localStorage', 'MutationObserver', 'requestAnimationFrame', 'CustomEvent', 'NodeFilter', '__cap', 'global', code);
      try { fn(sandbox.window, sandbox.document, sandbox.location, sandbox.navigator, sandbox.localStorage, sandbox.MutationObserver, sandbox.requestAnimationFrame, sandbox.CustomEvent, sandbox.NodeFilter, p => packs.push(p), { N8Kit: { i18n: { add: p => packs.push(p) } } }); }
      catch (e) { console.error(f, e.message); }
    } else {
      const fn = new Function('N8Kit', src);
      fn({ i18n: { add: p => packs.push(p) } });
    }
    for (const p of packs) {
      if (p.base === 'de' && p.en) for (const v of Object.values(p.en)) set.set(norm(v), 1);
      if ((p.base || 'en') === 'en' && p.de) for (const kk of Object.keys(p.de)) set.set(norm(kk), 1);
      const rl = Array.isArray(p.rules) ? p.rules.map(r => [p.base === 'de' ? 'en' : 'de', r]) : Object.entries(p.rules || {}).flatMap(([l, rs]) => rs.map(r => [l, r]));
      for (const [l, [re, rep]] of rl) rules[k].push({ to: l, re: re.source, flags: re.flags, rep: typeof rep === 'string' ? rep : String(rep) });
    }
  }
  // strip leading emoji/symbols and trailing punctuation like the kit does, keep the core
  const cores = new Map();
  for (const s of set.keys()) { if (!/\p{L}/u.test(s)) continue; const m = s.match(SPLIT); const c = m && m[2] ? m[2] + (/[.!?…]$/.test(m[3].trim()) && m[2].length > 30 ? '' : '') : s; cores.set(c, 1); }
  out[k] = [...cores.keys()];
}
fs.writeFileSync('/home/claude/i18n/strings.json', JSON.stringify(out, null, 1));
fs.writeFileSync('/home/claude/i18n/rules.json', JSON.stringify(rules, null, 1));
const all = new Set(Object.values(out).flat());
console.log(Object.fromEntries(Object.entries(out).map(([k, v]) => [k, v.length])), 'unique', all.size, 'chars', [...all].join('').length, 'rules', Object.values(rules).map(r => r.length));
