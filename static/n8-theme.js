/*
 * N8 Theme 2 – shared colour engine of the N8schicht dashboards
 * (HBlink4-FreeRadioID, ADN FRN Server, N8-HotSpot). The same file is in all three repositories;
 * change it in one, copy it to the others.
 *
 * A theme is a small object; every colour may be empty (= taken from the profile):
 *   { preset, accent, accent2, background, glow1, glow2, glow3, text, panel,
 *     glow (0–150 %), glass (0–100), blur (bool), radius (0–28 px) }
 *
 *   N8Theme.apply(theme)            sets the CSS variables and the page background
 *   N8Theme.resolve(theme)          the effective colours (profile + own colours)
 *   N8Theme.editorHtml(theme, id)   complete colour editor (profiles, colours, sliders, preview)
 *   N8Theme.readEditor(root)        theme object from an editor
 *   N8Theme.bindEditor(root, cb)    live preview while editing; cb(theme) after every change
 */
(function (global) {
    'use strict';

    const PRESETS = {
        n8:       { name: 'N8 Night',  accent: '#5ac8fa', accent2: '#9bd8ff', background: '#070b17', glow1: '#0a84ff', glow2: '#bf5af2', glow3: '#30d158', text: '#f5f7fb', panel: '#ffffff' },
        ocean:    { name: 'Ocean',     accent: '#22d3ee', accent2: '#99f6e4', background: '#04121c', glow1: '#0ea5e9', glow2: '#14b8a6', glow3: '#3b82f6', text: '#effbfa', panel: '#e6fffb' },
        aurora:   { name: 'Aurora',    accent: '#34d399', accent2: '#bef264', background: '#04130e', glow1: '#10b981', glow2: '#22d3ee', glow3: '#a3e635', text: '#f0fdf4', panel: '#ecfdf5' },
        ember:    { name: 'Ember',     accent: '#fb923c', accent2: '#fde68a', background: '#140906', glow1: '#f97316', glow2: '#ef4444', glow3: '#facc15', text: '#fff7ed', panel: '#fff1e6' },
        violet:   { name: 'Violet',    accent: '#c084fc', accent2: '#f0abfc', background: '#0d0918', glow1: '#8b5cf6', glow2: '#ec4899', glow3: '#6366f1', text: '#faf5ff', panel: '#f5ecff' },
        graphite: { name: 'Graphite',  accent: '#a3b1c6', accent2: '#e2e8f0', background: '#0b0c0f', glow1: '#64748b', glow2: '#475569', glow3: '#94a3b8', text: '#f1f5f9', panel: '#ffffff' },
        daylight: { name: 'Daylight',  accent: '#0a6fd6', accent2: '#5e5ce6', background: '#eef3f9', glow1: '#7cc4ff', glow2: '#d6b4ff', glow3: '#9de8b6', text: '#152235', panel: '#ffffff' },
    };
    const COLOR_KEYS = ['accent', 'accent2', 'background', 'glow1', 'glow2', 'glow3', 'text', 'panel'];
    const LABELS = {
        accent: ['Accent', 'Buttons, numbers, active tabs'],
        accent2: ['Accent 2', 'Second colour of buttons and the title'],
        background: ['Background', 'Page colour behind everything'],
        glow1: ['Glow top left', ''], glow2: ['Glow top right', ''], glow3: ['Glow bottom', ''],
        text: ['Text', 'Empty = suits the background automatically'],
        panel: ['Card tint', 'Colour mixed into the glass cards'],
    };
    const DEFAULTS = { preset: 'n8', glow: 100, glass: 50, blur: true, radius: 22 };
    const HEX = /^#[0-9a-f]{6}$/i;

    const rgb = h => { const n = parseInt(String(h || '#000000').slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
    const hex = a => '#' + a.map(x => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, '0')).join('');
    const mix = (a, b, t) => hex(rgb(a).map((x, i) => x + (rgb(b)[i] - x) * t));
    const rgba = (c, a) => `rgba(${rgb(c).join(', ')}, ${Math.max(0, Math.min(1, a)).toFixed(3)})`;
    const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    const clamp = (v, lo, hi, d) => { const n = Number(v); return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : d; };

    function normalize(t) {
        t = t || {};
        const out = { preset: PRESETS[t.preset] ? t.preset : DEFAULTS.preset };
        COLOR_KEYS.forEach(k => { out[k] = HEX.test(t[k] || '') ? String(t[k]).toLowerCase() : ''; });
        out.glow = clamp(t.glow, 0, 150, DEFAULTS.glow);
        out.glass = clamp(t.glass, 0, 100, DEFAULTS.glass);
        out.blur = t.blur !== false && t.blur !== 'false' && t.blur !== 0;
        out.radius = clamp(t.radius, 0, 28, DEFAULTS.radius);
        return out;
    }

    function resolve(t) {
        t = normalize(t);
        const p = PRESETS[t.preset];
        const c = {};
        COLOR_KEYS.forEach(k => { c[k] = t[k] || p[k]; });
        const light = lum(c.background) > 0.45;
        if (!t.text) c.text = light ? '#152235' : '#f5f7fb';
        return { ...t, colors: c, light };
    }

    function apply(theme, opts) {
        opts = opts || {};
        const r = resolve(theme), c = r.colors, light = r.light;
        const doc = document.documentElement, s = doc.style;
        const glow = r.glow / 100, glass = r.glass / 100;
        s.setProperty('--accent', c.accent);
        s.setProperty('--accent-rgb', rgb(c.accent).join(', '));
        s.setProperty('--accent2', c.accent2);
        s.setProperty('--title-to', light ? mix(c.accent2, '#000000', 0.15) : mix(c.accent2, '#ffffff', 0.25));
        s.setProperty('--bg', c.background);
        s.setProperty('--text', c.text);
        s.setProperty('--text-dim', rgba(c.text, light ? 0.68 : 0.62));
        s.setProperty('--text-faint', rgba(c.text, light ? 0.5 : 0.42));
        // glass cards: the panel tint at an opacity that follows "card brightness"
        s.setProperty('--glass-bg', light ? rgba(c.panel, 0.45 + glass * 0.45) : rgba(c.panel, 0.02 + glass * 0.07));
        s.setProperty('--glass-bg-strong', light ? rgba(c.panel, 0.7 + glass * 0.3) : rgba(c.panel, 0.05 + glass * 0.09));
        s.setProperty('--surface', light ? rgba(c.panel, 0.55 + glass * 0.4) : rgba(mix(c.background, c.panel, 0.08), 0.55));
        s.setProperty('--surface-2', light ? rgba(c.panel, 0.8) : rgba(mix(c.background, c.panel, 0.12), 0.7));
        s.setProperty('--glass-border', light ? rgba(c.text, 0.12) : rgba(c.panel, 0.12));
        s.setProperty('--glass-highlight', light ? 'rgba(255, 255, 255, 0.9)' : rgba(c.panel, 0.18));
        s.setProperty('--glass-shadow', light ? '0 8px 30px rgba(20, 40, 80, 0.10)' : '0 10px 40px rgba(0, 0, 0, 0.35)');
        s.setProperty('--glass-blur', r.blur ? 'blur(22px) saturate(170%)' : 'none');
        s.setProperty('--radius-lg', `${r.radius}px`);
        s.setProperty('--radius-md', `${Math.round(r.radius * 0.73)}px`);
        s.setProperty('--radius-sm', `${Math.round(r.radius * 0.55)}px`);
        // signal colours: darker on light backgrounds so they stay readable
        s.setProperty('--green', light ? '#15803d' : '#30d158');
        s.setProperty('--amber', light ? '#a16207' : '#ffd60a');
        s.setProperty('--red', light ? '#c0362c' : '#ff453a');
        doc.dataset.themeMode = light ? 'light' : 'dark';
        doc.style.colorScheme = light ? 'light' : 'dark';
        const meta = document.querySelector('meta[name="theme-color"]'); if (meta) meta.content = c.background;
        let el = document.getElementById('n8ThemeStyle');
        if (!el) { el = document.createElement('style'); el.id = 'n8ThemeStyle'; document.head.appendChild(el); }
        const g = (col, a) => rgba(col, a * glow * (light ? 0.8 : 1));
        el.textContent = `
            body { background:
                radial-gradient(1100px 700px at 8% -10%, ${g(c.glow1, 0.35)}, transparent 60%),
                radial-gradient(900px 650px at 100% 0%, ${g(c.glow2, 0.28)}, transparent 60%),
                radial-gradient(900px 700px at 50% 110%, ${g(c.glow3, 0.18)}, transparent 60%),
                linear-gradient(180deg, ${c.background} 0%, ${mix(c.background, light ? '#ffffff' : '#1a2440', light ? 0.5 : 0.18)} 100%) !important;
                background-attachment: fixed !important; color: var(--text); }
            .btn-primary, .btn-s.btn-primary, .btn.primary { background: linear-gradient(135deg, ${c.accent}, ${c.accent2}) !important;
                color: ${lum(c.accent) > 0.5 ? '#0b1224' : '#ffffff'} !important; }
            ${opts.extraCss || ''}`;
        return r;
    }

    // ------------------------------------------------------------------ editor
    const esc = v => String(v ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

    function swatch(key) {
        const p = PRESETS[key];
        return `radial-gradient(60px 40px at 15% 0%, ${p.glow1}99, transparent), radial-gradient(60px 40px at 100% 0%, ${p.glow2}88, transparent), ${p.background}`;
    }

    function editorHtml(theme, id) {
        const t = normalize(theme), r = resolve(t);
        const presets = Object.keys(PRESETS).map(k => `
            <button type="button" class="n8t-preset ${k === t.preset ? 'active' : ''}" data-preset="${k}" style="background:${swatch(k)};color:${PRESETS[k].text}">
                <i style="background:linear-gradient(135deg,${PRESETS[k].accent},${PRESETS[k].accent2})"></i><span>${esc(PRESETS[k].name)}</span></button>`).join('');
        const colors = COLOR_KEYS.map(k => `
            <label class="n8t-color" title="${esc(LABELS[k][1])}">
                <input type="color" data-color="${k}" value="${esc(t[k] || r.colors[k])}">
                <span class="n8t-cl"><b>${esc(LABELS[k][0])}</b><small class="${t[k] ? 'own' : ''}">${t[k] ? 'own colour' : 'from profile'}</small></span>
                <button type="button" class="n8t-reset" data-reset="${k}" title="Back to the profile colour" ${t[k] ? '' : 'hidden'}>↺</button>
            </label>`).join('');
        const slider = (k, label, min, max, unit, help) => `
            <label class="n8t-slider"><span><b>${esc(label)}</b><output>${t[k]}${unit}</output></span>
                <input type="range" data-num="${k}" min="${min}" max="${max}" value="${t[k]}" data-unit="${unit}">
                ${help ? `<small>${esc(help)}</small>` : ''}</label>`;
        return `
        <div class="n8t-editor" id="${esc(id || 'n8tEditor')}" data-preset="${esc(t.preset)}">
            <div class="n8t-sec"><div class="n8t-h">Colour profile</div><div class="n8t-presets">${presets}</div></div>
            <div class="n8t-sec"><div class="n8t-h">Own colours <small>Click a colour to change it; ↺ takes it from the profile again.</small></div>
                <div class="n8t-colors">${colors}</div></div>
            <div class="n8t-sec n8t-sliders">
                ${slider('glow', 'Background glow', 0, 150, ' %', '0 = flat background')}
                ${slider('glass', 'Card brightness', 0, 100, '', 'How strongly the glass cards stand out')}
                ${slider('radius', 'Roundness', 0, 28, ' px', 'Corners of cards and buttons')}
                <label class="n8t-switch"><input type="checkbox" data-bool="blur" ${t.blur ? 'checked' : ''}><span></span>
                    <b>Glass blur</b><small>Off = faster on old phones</small></label>
            </div>
            <div class="n8t-preview"><div class="n8t-pv-head"><span class="n8t-pv-logo"></span><div><div class="n8t-pv-title">Title</div><div class="n8t-pv-sub">Subtitle</div></div>
                <span class="n8t-pv-chip">✓ Live</span></div>
                <div class="n8t-pv-row"><span class="n8t-pv-tab">🎙️ Live</span><span class="n8t-pv-num">1.287</span><span class="n8t-pv-btn">Save</span></div>
                <div class="n8t-pv-contrast"></div></div>
        </div>`;
    }

    function readEditor(root) {
        const t = { preset: root.dataset.preset || 'n8' };
        root.querySelectorAll('[data-color]').forEach(i => { t[i.dataset.color] = i.dataset.own === '1' ? i.value : ''; });
        root.querySelectorAll('[data-num]').forEach(i => { t[i.dataset.num] = Number(i.value); });
        root.querySelectorAll('[data-bool]').forEach(i => { t[i.dataset.bool] = i.checked; });
        return normalize(t);
    }

    function contrast(a, b) { const x = lum(a) + 0.05, y = lum(b) + 0.05; return x > y ? x / y : y / x; }

    function refresh(root) {
        const t = readEditor(root), r = resolve(t);
        root.querySelectorAll('.n8t-preset').forEach(b => b.classList.toggle('active', b.dataset.preset === t.preset));
        root.querySelectorAll('[data-color]').forEach(i => {
            const own = i.dataset.own === '1';
            if (!own) i.value = r.colors[i.dataset.color];
            const lab = i.closest('.n8t-color');
            lab.querySelector('small').textContent = own ? 'own colour' : 'from profile';
            lab.querySelector('small').classList.toggle('own', own);
            lab.querySelector('.n8t-reset').hidden = !own;
        });
        root.querySelectorAll('[data-num]').forEach(i => { i.closest('label').querySelector('output').textContent = i.value + (i.dataset.unit || ''); });
        const cr = contrast(r.colors.text, r.colors.background);
        const warn = root.querySelector('.n8t-pv-contrast');
        warn.textContent = cr < 4.5 ? `⚠️ Text is hard to read on this background (contrast ${cr.toFixed(1)} : 1, at least 4.5 recommended)` : `✓ Readable (contrast ${cr.toFixed(1)} : 1)`;
        warn.classList.toggle('bad', cr < 4.5);
        return t;
    }

    function bindEditor(root, onChange) {
        if (!root) return;
        // a colour is "own" when the editor was rendered with one (its reset button is visible)
        root.querySelectorAll('[data-color]').forEach(i => { i.dataset.own = root.querySelector(`[data-reset="${i.dataset.color}"]`).hidden ? '0' : '1'; });
        const changed = () => { const t = refresh(root); apply(t); if (onChange) onChange(t); };
        root.addEventListener('click', e => {
            const p = e.target.closest('.n8t-preset');
            if (p) { root.dataset.preset = p.dataset.preset; changed(); return; }
            const rs = e.target.closest('.n8t-reset');
            if (rs) { e.preventDefault(); root.querySelector(`[data-color="${rs.dataset.reset}"]`).dataset.own = '0'; changed(); }
        });
        root.addEventListener('input', e => { if (e.target.dataset.color) e.target.dataset.own = '1'; changed(); });
        root.addEventListener('change', e => { if (e.target.dataset.color) e.target.dataset.own = '1'; changed(); });
        refresh(root);
    }

    function setEditor(root, theme) {
        const t = normalize(theme);
        root.dataset.preset = t.preset;
        root.querySelectorAll('[data-color]').forEach(i => { i.dataset.own = t[i.dataset.color] ? '1' : '0'; if (t[i.dataset.color]) i.value = t[i.dataset.color]; });
        root.querySelectorAll('[data-num]').forEach(i => { i.value = t[i.dataset.num]; });
        root.querySelectorAll('[data-bool]').forEach(i => { i.checked = !!t[i.dataset.bool]; });
        refresh(root); apply(t);
    }

    global.N8Theme = { PRESETS, COLOR_KEYS, DEFAULTS, normalize, resolve, apply, editorHtml, readEditor, bindEditor, setEditor, contrast };
})(window);
