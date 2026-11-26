"""Build n8-i18n-intl.js per repository from the translation chunks (fr, fr-BE, hu, sv, nl, it, es; keyed by English)."""
import json, os, re
B = '/home/claude/i18n'
chunks = json.load(open(f'{B}/chunks.json'))
strings = json.load(open(f'{B}/strings.json'))
LANGS = ['fr', 'hu', 'sv', 'nl', 'it', 'es']
tr = {l: {} for l in LANGS}
for i, c in enumerate(chunks):
    for l in LANGS:
        p = f'{B}/tr/c{i}.{l}.txt'
        if not os.path.exists(p): continue
        lines = open(p).read().rstrip('\n').split('\n')
        if len(lines) != len(c): raise SystemExit(f'{p}: {len(lines)} lines, expected {len(c)}')
        for en, x in zip(c, lines):
            if x.strip() and x != en: tr[l][en] = x
frbe = json.load(open(f'{B}/fr-BE.json')) if os.path.exists(f'{B}/fr-BE.json') else {}
rules = json.load(open(f'{B}/rules_tr.json')) if os.path.exists(f'{B}/rules_tr.json') else {}
TARGETS = {
    'adn': 'adn-frn-server/static',
    'crosslink': 'n8crosslink/n8crosslink/web/static',
    'hotspot': 'n8-hotspot/static',
    'hblink': 'hblink4-freeradioid/dashboard/static',
}
NAMES = {'fr': 'Français + Français (Belgique)', 'hu': 'Magyar', 'sv': 'Svenska', 'nl': 'Nederlands', 'it': 'Italiano', 'es': 'Español'}
def js(o): return json.dumps(o, ensure_ascii=False, separators=(',', ':'))
def rjs(lst): return '[' + ', '.join(f'[new RegExp({json.dumps(r["re"])}, {json.dumps(r["flags"])}), {json.dumps(r["rep"], ensure_ascii=False)}]' for r in lst) + ']'
for k, d in TARGETS.items():
    # every text of every system: the systems share many texts, and a text found in one is often shown in another as well
    used = list(dict.fromkeys(x for c in chunks for x in c))
    old_all = os.path.join('/home/claude', d, 'n8-i18n-intl.js')
    if os.path.exists(old_all): os.remove(old_all)
    stats = {}
    for l in LANGS:
        langs = [l] + (['fr-BE'] if l == 'fr' else [])
        parts, rparts = [], []
        for x in langs:
            src = tr[x] if x in tr else frbe
            parts.append(f'    {json.dumps(x)}: {js({s: src[s] for s in used if s in src})}')
            rl = [r for r in rules.get(x, []) if r['repo'] in ('kit', k)]
            if rl: rparts.append(f'        {json.dumps(x)}: {rjs(rl)}')
        body = ',\n'.join(parts)
        rbody = ',\n'.join(rparts)
        out = f"""/* N8 Kit 1.6 – user interface in {NAMES[l]}. Loaded by n8-kit.js only when this language is chosen.
 * Generated from the translation tables (keyed by the English text; German texts are looked up in English first, see n8-kit.js).
 * Do not edit by hand – a text without translation is shown in English. */
N8Kit.i18n.add({{
    base: 'en',
{body},
    rules: {{
{rbody}
    }}
}});
"""
        open(os.path.join('/home/claude', d, f'n8-i18n-{l}.js'), 'w').write(out)
        stats[l] = len(tr[l])
    print(k, 'files written', [f'n8-i18n-{l}.js' for l in LANGS])
