"""Writes docs/anleitung/<lang>/README.md (step-by-step guide) and docs/anleitung/README.md (language index) in the four repositories."""
import importlib.util, os, re
from pathlib import Path

HERE = Path(__file__).parent
LANGS = [('de', '🇩🇪', 'Deutsch'), ('en', '🇬🇧', 'English'), ('fr', '🇫🇷', 'Français'), ('fr-BE', '🇧🇪', 'Français (Belgique)'),
         ('hu', '🇭🇺', 'Magyar'), ('sv', '🇸🇪', 'Svenska'), ('nl', '🇳🇱', 'Nederlands'), ('it', '🇮🇹', 'Italiano'), ('es', '🇪🇸', 'Español')]
REPOS = {'adn': '/home/claude/adn-frn-server', 'crosslink': '/home/claude/n8crosslink', 'hotspot': '/home/claude/n8-hotspot',
         'hblink': '/home/claude/hblink4-freeradioid'}


def load(lang):
    name = lang.replace('-', '_')
    spec = importlib.util.spec_from_file_location(name, HERE / f'{name}.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def anchor(n, title):
    s = f'{n}-{title}'.lower()
    s = re.sub(r'[^\w\- ]', '', s, flags=re.U).replace(' ', '-')
    return s


def build():
    mods = {l: load(l) for l, _, _ in LANGS}
    for sysid, repo in REPOS.items():
        base = Path(repo) / 'docs' / 'anleitung'
        for lang, flag, lname in LANGS:
            m = mods[lang]
            S = m.SYSTEMS[sysid]
            steps = []
            for sid, title, body in S['steps']:
                if title is None:
                    title, body = m.SHARED[sid]
                steps.append((sid, title, body))
            bar = ' · '.join((f'**{f} {n}**' if l == lang else f'[{f} {n}](../{l}/README.md)') for l, f, n in LANGS)
            out = [f'# 📘 {S["name"]} – {m.UI["title"]}', '', f'<sub>{m.UI["lang"]}: {bar}</sub>', '', S['intro'], '',
                   f'> 💡 {m.UI["shots"]}', '', f'## {m.UI["contents"]}', '']
            for i, (sid, title, _) in enumerate(steps, 1):
                out.append(f'{i}. [{title}](#{anchor(i, title)})')
            out.append('')
            for i, (sid, title, body) in enumerate(steps, 1):
                out += [f'## {i}. {title}', '']
                img = base / 'img' / lang / f'{sid}.webp'
                if img.exists():
                    out += [f'<p align="center"><img src="../img/{lang}/{sid}.webp" alt="{title}" width="{70 if sid in ("login", "setup", "password", "lang") else 100}%"></p>', '']
                out += [body, '']
            out += ['---', '', f'📖 {m.UI["more"]}: [{S["more"]}](../../../{S["more"]})', '']
            d = base / lang
            d.mkdir(parents=True, exist_ok=True)
            (d / 'README.md').write_text('\n'.join(out))
        # language index
        de = mods['de'].SYSTEMS[sysid]
        idx = [f'# 📘 {de["name"]} – Anleitung · Guide', '',
               'Schritt-für-Schritt-Anleitung mit Bildern in neun Sprachen · Step-by-step guide with pictures in nine languages.', '',
               '| | |', '|---|---|']
        for lang, flag, lname in LANGS:
            m = mods[lang]
            idx.append(f'| {flag} | [**{lname}** – {m.SYSTEMS[sysid]["name"]} – {m.UI["title"]}]({lang}/README.md) |')
        idx += ['', '<p align="center"><img src="img/de/lang.webp" width="55%" alt="🌐 DE ▾"></p>', '']
        (base / 'README.md').write_text('\n'.join(idx))
        print(sysid, 'guides written')


if __name__ == '__main__':
    build()
