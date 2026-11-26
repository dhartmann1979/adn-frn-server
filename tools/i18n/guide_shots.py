"""Screenshots for the step-by-step guides: every step in every language, with a spotlight and numbered markers.

python3 guide_shots.py <system> [lang ...]
"""
import io, json, sys, time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
from playwright.sync_api import sync_playwright

LANGS = ['de', 'en', 'fr', 'fr-BE', 'hu', 'sv', 'nl', 'it', 'es']
SYS = {
    'adn': dict(url='http://127.0.0.1:8095/', user='dennis', pw='Demo-Passwort-1', api='/api/auth/login', admin="showTab('admin')",
                out='/home/claude/adn-frn-server/docs/anleitung/img'),
    'crosslink': dict(url='http://127.0.0.1:8098/', user='n8schicht', pw='Demo-Passwort-1', api='/api/login', admin="showTab('admin')",
                      out='/home/claude/n8crosslink/docs/anleitung/img'),
    'hotspot': dict(url='http://127.0.0.1:8720/', user='n8schicht', pw='n8schicht', api='/api/auth/login', admin="showTab('admin')",
                    out='/home/claude/n8-hotspot/docs/anleitung/img'),
    'hblink': dict(url='http://127.0.0.1:8073/', user='chef', pw='Demo-Passwort-1', api='/api/auth/login', admin="openAdmin()",
                   out='/home/claude/hblink4-freeradioid/docs/anleitung/img'),
}
# per system: (step id, action, [selectors to mark 1, 2, …])
STEPS = {
    'adn': [('login', 'login', ['.n8-login']), ('lang', 'lang', ['.n8-lang-btn', '.n8-lang-pop']),
            ('frn', 'tree:settings:server', ['tree', 'main']), ('rooms', 'tree:rooms', ['tree', 'main']),
            ('domains', 'tree:domains', ['tree', 'main']), ('users', 'tree:users', ['tree', 'main']),
            ('update', 'tree:sys-update', ['tree', 'main']), ('backup', 'tree:backup', ['tree', 'main'])],
    'crosslink': [('setup', 'setup', ['.n8-login']), ('lang', 'lang', ['.n8-lang-btn', '.n8-lang-pop']),
                  ('frn', 'tree:frn', ['tree', 'main']), ('dmr', 'tree:dmr', ['tree', 'main']), ('routes', 'tree:routes', ['tree', 'main']),
                  ('domains', 'tree:domains', ['tree', 'main']), ('update', 'tree:sys-update', ['tree', 'main']), ('backup', 'tree:backup', ['tree', 'main'])],
    'hotspot': [('login', 'login', ['.n8-login']), ('password', 'factory', ['.modal']), ('lang', 'lang', ['.n8-lang-btn', '.n8-lang-pop']),
                ('station', 'tree:settings:station', ['tree', 'main']), ('modem', 'tree:settings:modem', ['tree', 'main']),
                ('network', 'tree:settings:network', ['tree', 'main']), ('cal', 'tree:cal', ['tree', 'main']), ('update', 'tree:sys-update', ['tree', 'main'])],
    'hblink': [('login', 'login', ['.n8-login']), ('lang', 'lang', ['.n8-lang-btn', '.n8-lang-pop']),
               ('dmr', 'tree:dmrset', ['tree', 'main']), ('access', 'tree:settings', ['tree', 'main']), ('aprs', 'tree:aprs', ['tree', 'main']),
               ('domains', 'tree:domains', ['tree', 'main']), ('users', 'tree:users', ['tree', 'main']), ('update', 'tree:sys-update', ['tree', 'main'])],
}
MARK_JS = """(sels) => {
  document.querySelectorAll('.n8g-mark').forEach(e => e.remove());
  const pick = s => s === 'tree' ? document.querySelector('.n8-tree-i.on') : s === 'main' ? (document.querySelector('.n8-admin-main') || document.querySelector('.hb-admin .admin-body')) : document.querySelector(s);
  const rects = [];
  sels.forEach((s, i) => {
    const el = pick(s); if (!el) return;
    let r = el.getBoundingClientRect();
    const top = Math.max(r.top, 4), bottom = Math.min(r.bottom, innerHeight - 4), left = Math.max(r.left, 4), right = Math.min(r.right, innerWidth - 4);
    r = { left, top, width: right - left, height: bottom - top };
    rects.push(r);
    const box = document.createElement('div'); box.className = 'n8g-mark';
    box.style.cssText = `position:fixed;z-index:2147483646;pointer-events:none;left:${r.left - 5}px;top:${r.top - 5}px;width:${r.width + 10}px;height:${r.height + 10}px;border-radius:14px;border:3px solid #ffd60a;box-shadow:0 0 0 2px rgba(0,0,0,.35),0 0 24px rgba(255,214,10,.55);`;
    const b = document.createElement('div'); b.className = 'n8g-mark'; b.textContent = String(i + 1);
    const bx = Math.max(6, r.left - 18), by = Math.max(6, r.top - 18);
    b.style.cssText = `position:fixed;z-index:2147483647;pointer-events:none;left:${bx}px;top:${by}px;width:34px;height:34px;border-radius:50%;background:#ffd60a;color:#111;font:800 18px/34px system-ui,sans-serif;text-align:center;box-shadow:0 3px 10px rgba(0,0,0,.5);`;
    document.body.append(box, b);
  });
  return rects;
}"""


def frame(png: bytes, out: Path) -> None:
    """Rounded corners and a soft shadow on a transparent background, saved as WebP."""
    im = Image.open(io.BytesIO(png)).convert('RGBA')
    w, h = im.size
    r = 18
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], r, fill=255)
    im.putalpha(mask)
    pad = 24
    canvas = Image.new('RGBA', (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new('L', (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(sh).rounded_rectangle([pad, pad + 6, pad + w, pad + h + 6], r, fill=110)
    sh = sh.filter(ImageFilter.GaussianBlur(12))
    canvas.paste((0, 0, 0, 255), (0, 0), sh)
    canvas.alpha_composite(im, (pad, pad))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, 'WEBP', quality=82, method=6)


def run(sysname: str, langs: list) -> None:
    c = SYS[sysname]
    with sync_playwright() as p:
        b = p.chromium.launch()
        for lang in langs:
            ctx = b.new_context(viewport={'width': 1440, 'height': 860}, device_scale_factor=1, locale='de-DE')
            pg = ctx.new_page()
            q = f'?lang={lang}'
            for sid, act, sels in STEPS[sysname]:
                pg.goto(c['url'] + q); time.sleep(1.8)
                logged = pg.evaluate("!!document.querySelector('.n8-user-btn')")
                need_login = act.startswith('tree') or act == 'factory'
                if need_login and not logged:
                    pg.evaluate("""async ([u, pw, api]) => fetch(api, {method:'POST', headers:{'Content-Type':'application/json','X-N8':'1','X-Dashboard':'1'}, body: JSON.stringify({username:u, password:pw})})""",
                                [c['user'], c['pw'], c['api']])
                    pg.goto(c['url'] + q); time.sleep(2)
                if not need_login and logged:
                    ctx.clear_cookies(); pg.goto(c['url'] + q); time.sleep(1.8)
                pg.evaluate("document.querySelectorAll('.n8-upd-ov,.overlay').forEach(e=>e.remove())")
                clip = None
                if act == 'login':
                    pg.click('.n8-login-btn'); time.sleep(.6)
                    pg.fill('.n8-login input[name=username]', c['user'])
                elif act == 'setup':
                    pg.evaluate("openLogin('setup')"); time.sleep(.6)
                    pg.fill('.n8-login input[name=username]', 'n8schicht')
                elif act == 'lang':
                    pg.click('.n8-lang-btn'); time.sleep(.5)
                    clip = {'x': 760, 'y': 0, 'width': 680, 'height': 500}
                elif act == 'factory':
                    pg.evaluate("openAccount(true)"); time.sleep(.6)
                elif act.startswith('tree:'):
                    item = act[5:]
                    pg.evaluate(c['admin']); time.sleep(1.2)
                    pg.evaluate("document.querySelectorAll('.n8-upd-ov').forEach(e=>e.remove())")
                    pg.evaluate("""(id) => { const g = document.querySelector('.n8-tree-i[data-i="' + id + '"]'); const grp = g && g.closest('.n8-tree-g');
                        if (grp && !grp.classList.contains('open')) grp.querySelector('.n8-tree-gh').click(); }""", item); time.sleep(.4)
                    pg.evaluate("""(id) => { const g = document.querySelector('.n8-tree-i[data-i="' + id + '"]'); if (g) g.click(); }""", item); time.sleep(1.4)
                    pg.evaluate("document.querySelectorAll('.n8-upd-ov').forEach(e=>e.remove())")
                time.sleep(.3)
                if act in ('login', 'setup', 'factory'):
                    box = pg.evaluate("(() => { const e = document.querySelector('.n8-login') || document.querySelector('.modal'); const r = e.getBoundingClientRect(); return {x: r.left, y: r.top, w: r.width, h: r.height}; })()")
                    x0, y0 = max(0, box['x'] - 70), max(0, box['y'] - 60)
                    clip = {'x': x0, 'y': y0, 'width': min(1440 - x0, box['w'] + 140), 'height': min(860 - y0, box['h'] + 120)}
                pg.evaluate(MARK_JS, sels); time.sleep(.2)
                png = pg.screenshot(clip=clip) if clip else pg.screenshot()
                frame(png, Path(c['out']) / lang / f'{sid}.webp')
            ctx.close()
            print(sysname, lang, 'ok')
        b.close()


if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2:] or LANGS)
