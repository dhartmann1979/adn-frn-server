/* frn_adn web interface. No build step, no external libraries. */
'use strict';

const $ = id => document.getElementById(id);
const S = { info: null, me: null, live: null, ws: null, wsOk: false, services: {}, lhRoom: 'all', liveRoom: '', tab: 'live',
            stats: { range: 'today', metric: 'duration', data: null, slots: {} },
            admin: { tab: 'server', frn: null, room: null, logs: [], aclClients: [], linkItems: [], linkSettings: null, palettes: {} }, chat: { room: 'all', entries: [] } };

// ---------------------------------------------------------------- helpers
function esc(v) { return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
async function api(method, url, body) {
    const opt = { method, credentials: 'same-origin', headers: { 'X-N8': '1' } };
    if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    const r = await fetch(url, opt);
    let j = {};
    try { j = await r.json(); } catch (e) {}
    if (!r.ok) { const err = new Error(j.error || r.statusText); err.status = r.status; throw err; }
    return j;
}
function fmtDur(s, short) {
    s = Math.round(s || 0);
    if (s < 60) return `${s} s`;
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    if (h) return short ? `${h} h${m ? ' ' + m + ' m' : ''}` : `${h} h ${m} m`;
    return short || !sec ? `${m} m` : `${m} m ${sec} s`;
}
function fmtClock(sec) { sec = Math.max(0, Math.floor(sec)); return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`; }
function fmtTime(ts) { return new Date(ts * 1000).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
function fmtDate(ts) { return ts ? new Date(ts * 1000).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '–'; }
function ago(ts) {
    const d = Date.now() / 1000 - ts;
    if (d < 60) return 'just now'; if (d < 3600) return `${Math.floor(d / 60)} min ago`;
    if (d < 86400) return `${Math.floor(d / 3600)} h ago`; return fmtDate(ts);
}
function since(ts) { if (!ts) return ''; const d = Date.now() / 1000 - ts; return d < 60 ? 'now' : d < 3600 ? `${Math.floor(d / 60)} min` : d < 86400 ? `${Math.floor(d / 3600)} h ${Math.floor((d % 3600) / 60)} m` : `${Math.floor(d / 86400)} d`; }
function fmtBytes(b) { if (b == null) return '–'; const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; while (b >= 1024 && i < 4) { b /= 1024; i++; } return `${b.toFixed(b < 10 && i ? 1 : 0)} ${u[i]}`; }
function num(n) { return Number(n || 0).toLocaleString('de-DE'); }
function initials(c) { return esc((c || '?').replace(/[^A-Za-z0-9]/g, '').replace(/^([A-Z]{1,2}\d)/, '').slice(0, 2).toUpperCase() || (c || '?').slice(0, 2)); }
function hashStr(s) { let h = 0; for (const ch of String(s || '')) h = (h * 31 + ch.charCodeAt(0)) | 0; return Math.abs(h); }
function avatarColor(call) { const h = (hashStr(call) * 47) % 360; return `linear-gradient(135deg, hsl(${h} 70% 50%), hsl(${(h + 40) % 360} 75% 42%))`; }
// ---------------------------------------------------------------- client software avatars
// Own drawings (not the brand logos): a badge with the type name or a symbol. Admins can upload
// their own image per kind (Admin → Theme → Client logos); those come from /client-logos/<key>.
const SW_STYLE = {
    dmr:       { t: 'DMR', c: ['#2f6bff', '#1b2f8f'] },
    zello:     { g: 'walkie', t: 'Z', c: ['#ffb020', '#c2570c'] },
    svxlink:   { t: 'SVX', c: ['#22b35e', '#0f5a31'] },
    echolink:  { t: 'EL', c: ['#18a0d8', '#174a8c'] },
    allstar:   { t: 'ASL', c: ['#9a4dff', '#4a1d96'] },
    c4fm:      { t: 'YSF', c: ['#10b3a3', '#0f4f4a'] },
    dstar:     { t: 'D★', c: ['#6366f1', '#2e2a85'] },
    m17:       { t: 'M17', c: ['#f0503a', '#8a1c12'] },
    teamspeak: { g: 'headset', c: ['#7b8aa3', '#2b3446'] },
    crosslink: { g: 'link', c: ['#16c2d8', '#145d74'] },
    gateway:   { g: 'antenna', c: ['#3ccf6e', '#16622f'] },
    pc:        { g: 'monitor', c: ['#7c83ff', '#3b3a9e'] },
    parrot:    { g: 'echo', c: ['#30d158', '#0a84ff'] },
};
const SW_GLYPH = {
    walkie: '<rect x="20" y="22" width="22" height="32" rx="5" fill="none" stroke="#fff" stroke-width="4"/><path d="M26 22V9" stroke="#fff" stroke-width="4" stroke-linecap="round"/><path d="M26 31h10M26 37h10" stroke="#fff" stroke-width="3" stroke-linecap="round"/>',
    headset: '<path d="M15 38v-6a17 17 0 0 1 34 0v6" fill="none" stroke="#fff" stroke-width="4"/><rect x="12" y="36" width="9" height="14" rx="3" fill="#fff"/><rect x="43" y="36" width="9" height="14" rx="3" fill="#fff"/>',
    link: '<rect x="9" y="25" width="26" height="14" rx="7" fill="none" stroke="#fff" stroke-width="4"/><rect x="29" y="25" width="26" height="14" rx="7" fill="none" stroke="#fff" stroke-width="4"/>',
    antenna: '<path d="M32 26v28M24 54h16" stroke="#fff" stroke-width="4" stroke-linecap="round"/><circle cx="32" cy="22" r="4" fill="#fff"/><path d="M21 13a16 16 0 0 0 0 18M43 13a16 16 0 0 1 0 18" fill="none" stroke="#fff" stroke-width="3.5" stroke-linecap="round"/>',
    monitor: '<rect x="11" y="15" width="42" height="27" rx="4" fill="none" stroke="#fff" stroke-width="4"/><path d="M32 42v8M22 51h20" stroke="#fff" stroke-width="4" stroke-linecap="round"/>',
    echo: '<path d="M18 22h18a10 10 0 0 1 0 20H26l-8 7v-7" fill="none" stroke="#fff" stroke-width="4" stroke-linejoin="round"/><path d="M42 27a8 8 0 0 1 0 10M47 23a14 14 0 0 1 0 18" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>',
};
const SW_LABEL = { dmr: 'DMR', zello: 'Zello', svxlink: 'SvxLink', echolink: 'EchoLink', allstar: 'AllStar', c4fm: 'C4FM / YSF', dstar: 'D-STAR', m17: 'M17',
                   teamspeak: 'TeamSpeak / Mumble', crosslink: 'Crosslink', gateway: 'Gateway (radio)', pc: 'PC / app', parrot: 'Parrot / echo test' };
const SW_SVG = {};
function swSvg(key) {
    if (SW_SVG[key]) return SW_SVG[key];
    const st = SW_STYLE[key] || SW_STYLE.pc;
    const id = 'g' + key;
    const text = st.t && !st.g ? `<text x="32" y="${st.t.length > 2 ? 40 : 42}" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-weight="800" font-size="${st.t.length > 2 ? 20 : 25}" fill="#fff">${st.t}</text>` : '';
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${st.c[0]}"/><stop offset="1" stop-color="${st.c[1]}"/></linearGradient></defs>`
        + `<rect width="64" height="64" fill="url(#${id})"/>${st.g ? SW_GLYPH[st.g] : ''}${text}</svg>`;
    return (SW_SVG[key] = 'data:image/svg+xml,' + encodeURIComponent(svg));
}
function avatar(call, cls, sw) {
    if (sw && SW_STYLE[sw]) {
        const own = S.clientLogos && S.clientLogos[sw];
        const src = own ? `/client-logos/${sw}?v=${own}` : swSvg(sw);
        return `<span class="avatar sw ${cls || ''}" title="${esc(SW_LABEL[sw] || sw)}"><img src="${src}" alt="${esc(SW_LABEL[sw] || sw)}" onerror="this.src='${swSvg(sw)}'"></span>`;
    }
    return `<span class="avatar ${cls || ''}" style="background:${avatarColor(call)}">${initials(call)}</span>`;
}
async function loadClientLogos() {
    try { const d = await api('GET', '/api/client-logos'); S.clientLogos = Object.fromEntries(d.kinds.filter(k => k.own).map(k => [k.key, k.own])); }
    catch (e) { S.clientLogos = {}; }
}
function roleBadge(c) {
    return c.access === 'OWNER' || c.access === 'NETOWNER' ? '<span class="role-badge owner" title="Owner">👑</span>'
         : c.access === 'ADMIN' ? '<span class="role-badge admin" title="Admin">🛡️</span>' : '';
}
async function renderClientLogoAdmin() {
    const el = $('clientLogoAdmin'); if (!el) return;
    let d; try { d = await api('GET', '/api/client-logos'); } catch (e) { el.innerHTML = `<div class="notice-box">⚠️ ${esc(e.message)}</div>`; return; }
    el.innerHTML = `<h3>📡 Client logos</h3>
        <p class="subt">Stations show the software or network they come from as their avatar – detected from band, description and client type (crosslink, gateway, PC).
        The built-in pictures are simple badges. You can replace each one with your own image (PNG, JPEG, WebP, GIF, ICO or plain SVG, max. 512 KB) –
        for example an official logo, if you are allowed to use it.</p>
        <div class="cl-grid">${d.kinds.map(k => `<div class="cl-item">
            <span class="avatar sw"><img src="${k.own ? `/client-logos/${k.key}?v=${k.own}` : swSvg(k.key)}" alt=""></span>
            <div class="cl-txt"><b>${esc(k.label)}</b><small>${k.own ? 'own image' : 'built-in'}</small></div>
            <label class="btn small">⬆️<input type="file" hidden accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml,.ico" onchange="uploadClientLogo('${k.key}', this)"></label>
            ${k.own ? `<button class="btn small" title="Back to the built-in picture" onclick="deleteClientLogo('${k.key}')">↺</button>` : ''}</div>`).join('')}</div>`;
}
async function uploadClientLogo(key, input) {
    const f = input.files && input.files[0]; if (!f) return;
    if (f.size > 512 * 1024) { toast('The image must be smaller than 512 KB.', true); return; }
    try { await api('POST', `/api/admin/client-logos/${key}`, { data: await readFileData(f) }); toast('Logo saved.'); await loadClientLogos(); renderClientLogoAdmin(); renderAllLive(); }
    catch (e) { toast(e.message, true); }
}
async function deleteClientLogo(key) {
    try { await api('DELETE', `/api/admin/client-logos/${key}`); toast('Built-in picture again.'); await loadClientLogos(); renderClientLogoAdmin(); renderAllLive(); }
    catch (e) { toast(e.message, true); }
}
function renderAllLive() { try { renderRooms(); renderOnAir(); renderLH(); } catch (e) { /* not on the live tab yet */ } }
const FLAGS = { germany: 'DE', deutschland: 'DE', austria: 'AT', 'österreich': 'AT', switzerland: 'CH', schweiz: 'CH', netherlands: 'NL', niederlande: 'NL',
    holland: 'NL', belgium: 'BE', belgien: 'BE', luxembourg: 'LU', luxemburg: 'LU', france: 'FR', frankreich: 'FR', italy: 'IT', italien: 'IT',
    spain: 'ES', spanien: 'ES', portugal: 'PT', poland: 'PL', polen: 'PL', 'czech republic': 'CZ', czechia: 'CZ', tschechien: 'CZ', denmark: 'DK',
    'dänemark': 'DK', sweden: 'SE', schweden: 'SE', norway: 'NO', norwegen: 'NO', finland: 'FI', finnland: 'FI', 'united kingdom': 'GB', uk: 'GB',
    england: 'GB', scotland: 'GB', ireland: 'IE', irland: 'IE', hungary: 'HU', ungarn: 'HU', slovakia: 'SK', slowakei: 'SK', slovenia: 'SI',
    croatia: 'HR', kroatien: 'HR', romania: 'RO', rumänien: 'RO', bulgaria: 'BG', greece: 'GR', griechenland: 'GR', turkey: 'TR', 'türkei': 'TR',
    russia: 'RU', russland: 'RU', ukraine: 'UA', usa: 'US', 'united states': 'US', canada: 'CA', kanada: 'CA', australia: 'AU', brazil: 'BR',
    serbia: 'RS', lithuania: 'LT', latvia: 'LV', estonia: 'EE', iceland: 'IS', malta: 'MT', cyprus: 'CY', liechtenstein: 'LI' };
function flag(country) {
    const c = (country || '').trim(); if (!c) return '';
    const iso = /^[A-Z]{2}$/.test(c) ? c : FLAGS[c.toLowerCase()];
    if (!iso) return '';
    return `<span class="flag" title="${esc(c)}">${String.fromCodePoint(...[...iso].map(ch => 0x1F1E6 + ch.charCodeAt(0) - 65))}</span>`;
}
function isRadio(c) { return Number(c.client) === 1 || /MHz|kHz|\bFM\b|PMR|CB|Relais|Repeater/i.test(c.band || ''); }
function bandHtml(c) { if (!c.band) return ''; return `<span class="band" title="${esc(c.band)}">${isRadio(c) ? '📻' : '💻'} <span class="band-txt">${esc(c.band.length > 22 ? c.band.slice(0, 21) + '…' : c.band)}</span></span>`; }
function place(c) { return [c.city, c.country && !flag(c.country) ? c.country : ''].filter(Boolean).join(', '); }
function toast(msg, bad) {
    const t = document.createElement('div');
    t.className = 'chip ' + (bad ? 'bad' : 'ok');
    t.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:4000;box-shadow:0 10px 30px rgba(0,0,0,.4);max-width:90vw;white-space:normal';
    t.textContent = msg; document.body.appendChild(t); setTimeout(() => t.remove(), bad ? 6000 : 3200);
}
async function loadPublicLinks() {
    try {
        const d = await api('GET', '/api/links');
        const pop = $('linksPop');
        if (!pop) return;
        $('linksMenu').classList.toggle('hidden', !d.enabled || d.style === 'bar');
        $('linksBar').hidden = !d.enabled || d.style !== 'bar';
        $('linksMenu').querySelector('.links-label').textContent = d.label || '🔗 Links';
        const markup = (d.links || []).map(x => `<a ${x.new_tab && !x.url.startsWith('#') ? 'target="_blank" rel="noopener noreferrer"' : ''} href="${esc(x.url)}">${linkSiteIcon(x)}<span>${esc(x.label)}</span></a>`).join('');
        pop.innerHTML = markup ? markup.replaceAll('<a ', '<a role="menuitem" ') : '<div class="links-loading">No links configured.</div>';
        $('linksBar').innerHTML = markup;
        document.querySelectorAll('#linksPop img, #linksBar img').forEach(bindSiteIcon);
    } catch (e) { const pop = $('linksPop'); if (pop) pop.innerHTML = '<div class="links-loading">Links unavailable.</div>'; }
}
function bindSiteIcon(img) {
    img.addEventListener('error', () => {
        const tries = Number(img.dataset.retry || 0);
        if (tries >= 2) { img.remove(); return; }
        img.dataset.retry = String(tries + 1);
        setTimeout(() => { if (img.isConnected) img.src = img.src.split('?')[0] + '?retry=' + img.dataset.retry; }, 3500);
    });
}
function linkSiteIcon(item) {
    const fallback = `<span class="site-icon-fallback">${esc(item.icon || '🔗')}</span>`;
    return `<span class="site-icon-wrap">${fallback}${item.site_icon && item.site_icon_url ? `<img src="${esc(item.site_icon_url)}" alt="">` : ''}</span>`;
}
function toggleLinks(ev) {
    ev.stopPropagation();
    const menu = $('linksMenu'); menu.classList.toggle('open');
    menu.querySelector('.links-trigger')?.setAttribute('aria-expanded', menu.classList.contains('open') ? 'true' : 'false');
    if (menu.dataset.bound !== '1') { menu.dataset.bound = '1'; document.addEventListener('click', e => { if (!menu.contains(e.target)) menu.classList.remove('open'); }); }
}
function rgba(hex, alpha) {
    const n = parseInt(String(hex || '').slice(1), 16);
    if (!/^#[0-9a-f]{6}$/i.test(hex || '') || !Number.isFinite(n)) return `rgba(90,200,250,${alpha})`;
    return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${alpha})`;
}
function darken(hex, factor) {
    const n = parseInt(String(hex || '').slice(1), 16);
    if (!/^#[0-9a-f]{6}$/i.test(hex || '') || !Number.isFinite(n)) return '#070b17';
    return '#' + [n >> 16, (n >> 8) & 255, n & 255].map(x => Math.round(x * factor).toString(16).padStart(2, '0')).join('');
}
// Colours come from the shared N8 Theme 2 engine (static/n8-theme.js); the --theme-*/--user-* variables
// of this stylesheet are derived from the same colours.
function applyTheme(theme) {
    const r = N8Theme.apply(theme || {});
    const c = r.colors, light = r.light, root = document.documentElement;
    const panelSolid = light ? '#ffffff' : '#141a2e';
    const set = (k, v) => root.style.setProperty(k, v);
    set('--user-accent', c.accent); set('--user-text', c.text); set('--user-muted', rgba(c.text, light ? .68 : .64));
    set('--theme-accent-soft', rgba(c.accent, .18));
    set('--theme-accent-border', rgba(c.accent, .38));
    set('--theme-accent-focus', rgba(c.accent, .62));
    set('--theme-accent-shadow', rgba(c.accent, .16));
    set('--theme-accent-glow', rgba(c.accent, .35));
    set('--theme-input-bg', light ? 'rgba(255,255,255,.85)' : 'rgba(0,0,0,.28)');
    set('--theme-input-border', rgba(c.text, light ? .18 : .14));
    set('--theme-option-bg', panelSolid);
    set('--theme-popover', light ? 'rgba(255,255,255,.985)' : 'rgba(16,22,40,.985)');
    set('--theme-header', light ? 'rgba(255,255,255,.72)' : 'rgba(20,26,45,.55)');
    return r;
}
function renderFooter(info) {
    const b = (info && info.build) || {};
    const d = b.date ? new Date(b.date) : new Date();
    $('footerYear').textContent = d.getFullYear();
    $('ver').textContent = `ADN FRN Server v${(info && info.version) || '?'}${b.commit ? ' (' + b.commit + ')' : ''}`;
    $('footerDate').textContent = b.date ? d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '';
}
function isAdmin() { return S.me && (S.me.role === 'admin' || S.me.role === 'superadmin'); }
function bindSeg(id, fn) {
    $(id).addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; document.querySelectorAll(`#${id} button`).forEach(x => x.classList.toggle('active', x === b)); fn(b.dataset.v); });
}

// ---------------------------------------------------------------- boot
async function boot() {
    try {
        const [info, branding] = await Promise.all([api('GET', '/api/info'), api('GET', '/api/branding')]);
        applyTheme(branding.theme);
        loadClientLogos().then(() => renderAllLive());
        S.info = info; S.me = info.user || null;
        if (info.login_required && !S.me) { renderHeader(); if (!info.setup_needed) openLogin(true); return; }
        renderHeader(); renderUser(); loadPublicLinks();
        renderFooter(info);
        const live = await api('GET', '/api/live');
        S.live = live; renderLive();
        connectWS();
        loadToday();
        const h = location.hash.replace('#', '');
        if (h) { const [t, a] = h.split('/'); if (['stats', 'stations', 'chat'].includes(t)) showTab(t); else if (t === 'admin' && isAdmin()) showTab('admin', a); }
    } catch (e) { console.error(e); setTimeout(boot, 3000); }
}
function renderHeader() {
    const i = S.info || {};
    $('title').textContent = i.title || 'Auf der NachtSchicht';
    document.title = i.title || 'Auf der NachtSchicht';
    const parts = [i.subtitle, i.address ? `<span class="addr">${esc(i.address)}</span>` : '', i.demo ? 'Demo' : ''].filter(Boolean);
    $('subtitle').innerHTML = parts.map(p => p.startsWith('<') ? p : esc(p)).join(' · ');
    $('tabAdminBtn').classList.toggle('hidden', !isAdmin());
    $('tabChatBtn').classList.toggle('hidden', !i.chat);
    $('setupBanner').classList.toggle('hidden', !i.setup_needed);
}
function renderUser() {
    const el = $('userArea');
    if (!S.me) { el.innerHTML = '<button class="btn primary" onclick="openLogin()" title="Login">🔐<span class="u-name">&nbsp;Login</span></button>'; return; }
    // logged in: name (click = my account) and log out – no drop-down; ⚙️ Admin is a menu item
    const name = esc(S.me.display_name || S.me.username);
    el.innerHTML = `<span class="n8-user"><button class="btn" onclick="openAccount()" title="${name} · ${esc(S.me.role)} – my account">👤<span class="u-name">&nbsp;${name}</span></button>
        <button class="btn n8-logout" onclick="logout()" title="Log out" aria-label="Log out">⏻</button></span>`;
    window.dispatchEvent(new Event('n8:login'));   // update notice for admins (N8 Kit)
}
function userMenu(ev) {
    ev.stopPropagation(); closeModal();
    const r = ev.target.getBoundingClientRect();
    const m = document.createElement('div');
    m.className = 'glass';
    m.style.cssText = `position:fixed;top:${r.bottom + 8}px;right:${Math.max(8, innerWidth - r.right)}px;z-index:300;border-radius:16px;padding:6px;min-width:200px;background:var(--theme-popover)`;
    m.innerHTML = `<div style="padding:8px 12px" class="dim">${esc(S.me.username)} · ${esc(S.me.role)}</div>
        ${isAdmin() ? '<button class="btn" style="width:100%;border-radius:10px;margin:2px 0" onclick="showTab(\'admin\')">⚙️ Admin</button>' : ''}
        <button class="btn" style="width:100%;border-radius:10px;margin:2px 0" onclick="openAccount()">🔑 My account</button>
        <button class="btn" style="width:100%;border-radius:10px;margin:2px 0" onclick="logout()">🚪 Log out</button>`;
    document.body.appendChild(m);
    setTimeout(() => document.addEventListener('click', () => m.remove(), { once: true }), 0);
}

// ---------------------------------------------------------------- modals
// Request an FRN password from the SystemManager (like "Get Password" in the FRN client)
async function openFrnPassword() {
    let d = {}; try { d = await api('GET', '/api/admin/frn-password'); } catch (e) { toast(e.message, true); return; }
    modal(`<h2>📧 Request FRN password</h2>
        <p class="dim" style="margin:0 0 4px">The SystemManager e-mails a password for a new FRN account.</p>
        <p class="dim" style="margin:0 0 4px">Afterwards enter e-mail and password above under SystemManager and save. For a second server use a different name (e.g. “Server Test”) – callsign and name together must be new.</p>
        <p class="dim mono" style="margin:0 0 10px;font-size:12px">${esc(d.host)}:10025</p>
        <form onsubmit="event.preventDefault(); sendFrnPassword(this)">
            <div class="row"><label>Callsign</label><input name="callsign" value="${esc(d.callsign)}" required></div>
            <div class="row"><label>Name</label><input name="name" value="${esc(d.name)}" required></div>
            <div class="row"><label>E-mail (the password is sent there)</label><input type="email" name="email" value="${esc(d.email)}" required></div>
            <div class="row"><label>Band / channel</label><input name="band" value="${esc(d.band)}" placeholder="PC Only, Crosslink or 438.950FM CTC71.9"></div>
            <div class="row"><label>Description</label><input name="description" value="${esc(d.description)}"></div>
            <div class="row"><label>Country</label><input name="country" value="${esc(d.country)}" required></div>
            <div class="row"><label>City - part</label><input name="city" value="${esc(d.city)}" placeholder="Minden - JO42" required></div>
            <div class="err" id="frnPwErr"></div><div class="notice-box" id="frnPwOk" style="display:none"></div>
            <div class="actions"><button type="button" class="btn" onclick="closeModal()">Close</button><button class="btn primary">📧 Request password</button></div>
        </form>`, false, true);
}
async function sendFrnPassword(f) {
    const b = f.querySelector('button.primary'); b.disabled = true; $('frnPwErr').textContent = '';
    try {
        const r = await api('POST', '/api/admin/frn-password', Object.fromEntries(new FormData(f)));
        const ok = $('frnPwOk'); ok.style.display = ''; ok.textContent = (r.ok ? '✅ ' : '⚠️ ') + r.message;
        if (r.ok) toast('FRN password requested');
    } catch (e) { $('frnPwErr').textContent = e.message; } finally { b.disabled = false; }
}
function modal(html, locked, wide) {
    $('modalRoot').innerHTML = `<div class="overlay" id="ov"><div class="modal ${wide ? 'wide' : ''}">${html}</div></div>`;
    if (!locked) $('ov').addEventListener('click', e => { if (e.target.id === 'ov') closeModal(); });
    if (locked) $('ov').dataset.locked = '1';
}
function closeModal() { $('modalRoot').innerHTML = ''; }
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('ov')?.dataset.locked) closeModal(); });
function openLogin(locked) {
    modal(`<img class="logo" src="/branding/logo" alt="">
        <h2 style="text-align:center">${esc((S.info && S.info.title) || 'Auf der NachtSchicht')}</h2>
        <p class="dim" style="text-align:center;margin:0 0 12px">${locked ? 'This dashboard is private. Please log in.' : 'Log in to manage the FRN server.'}</p>
        <form onsubmit="event.preventDefault(); doLogin(this)">
            <div class="row"><label>Username</label><input type="text" name="username" autocomplete="username" required autofocus></div>
            <div class="row"><label>Password</label><input type="password" name="password" autocomplete="current-password" required></div>
            <label style="display:flex;gap:8px;align-items:center;margin-top:6px" class="dim"><input type="checkbox" name="remember"> Stay logged in (30 days)</label>
            <div class="err" id="loginErr"></div>
            <div class="actions">${locked ? '' : '<button type="button" class="btn" onclick="closeModal()">Cancel</button>'}<button class="btn primary">Log in</button></div>
        </form>`, locked);
    setTimeout(() => document.querySelector('#ov input[name=username]')?.focus(), 50);
}
async function doLogin(f) {
    try {
        const r = await api('POST', '/api/auth/login', { username: f.username.value, password: f.password.value, remember: f.remember.checked });
        S.me = r.user; closeModal();
        if (S.ws) { const w = S.ws; S.ws = null; try { w.close(); } catch (e) {} }
        await boot();
    } catch (e) { $('loginErr').textContent = e.message; }
}
async function logout() { await api('POST', '/api/auth/logout', {}); location.hash = ''; location.reload(); }
function openAccount() {
    modal(`<h2>🔑 My account</h2>
        <form onsubmit="event.preventDefault(); saveAccount(this)">
            <div class="row"><label>Username</label><input type="text" name="username" value="${esc(S.me.username)}" autocomplete="username"></div>
            <div class="row"><label>Current password</label><input type="password" name="old" required autocomplete="current-password"></div>
            <div class="row"><label>New password (min. 10)</label><input type="password" name="new" required minlength="10" autocomplete="new-password"></div>
            <div class="row"><label>Repeat</label><input type="password" name="rep" required minlength="10" autocomplete="new-password"></div>
            <div class="err" id="accErr"></div>
            <div class="actions"><button type="button" class="btn" onclick="closeModal()">Cancel</button><button class="btn primary">Save</button></div>
        </form>`);
}
async function saveAccount(f) {
    if (f.new.value !== f.rep.value) { $('accErr').textContent = 'The new passwords differ.'; return; }
    try { await api('POST', '/api/auth/password', { old: f.old.value, new: f.new.value, username: f.username.value.trim() }); closeModal(); toast('Saved. Please log in again.'); setTimeout(() => location.reload(), 1200); }
    catch (e) { $('accErr').textContent = e.message; }
}
function confirmBox(text, okLabel, cls) {
    return new Promise(res => {
        modal(`<h2>${esc(text.title)}</h2><p class="dim">${text.body}</p>
            <div class="actions"><button class="btn" id="cNo">Cancel</button><button class="btn ${cls || 'primary'}" id="cYes">${esc(okLabel)}</button></div>`);
        $('cNo').onclick = () => { closeModal(); res(false); };
        $('cYes').onclick = () => { closeModal(); res(true); };
    });
}

// ---------------------------------------------------------------- tabs
function showTab(tab, sub) {
    S.tab = tab;
    document.querySelectorAll('#mainTabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    ['live', 'stats', 'stations', 'chat', 'admin'].forEach(t => $('tab-' + t).classList.toggle('hidden', t !== tab));
    if (tab === 'stats') loadStats();
    if (tab === 'stations') loadDirectory();
    if (tab === 'chat') loadChat();
    if (tab === 'admin') showAdmin(sub || S.admin.tab);
    history.replaceState(null, '', tab === 'live' ? location.pathname : '#' + tab + (tab === 'admin' ? '/' + (sub || S.admin.tab) : ''));
    hideTip();
}
$('mainTabs').addEventListener('click', e => { const b = e.target.closest('button[data-tab]'); if (b) showTab(b.dataset.tab); });

// ---------------------------------------------------------------- websocket
function connectWS() {
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
    S.ws = ws;
    ws.onopen = () => { S.wsOk = true; renderChips(); };
    ws.onclose = () => { S.wsOk = false; renderChips(); setTimeout(() => { if (S.ws === ws) connectWS(); }, 3000); };
    ws.onmessage = m => { try { onEvent(JSON.parse(m.data)); } catch (e) { console.error(e); } };
}
let todayT = null, heardT = null;
function onEvent(ev) {
    switch (ev.type) {
        case 'hello': S.live = ev.live; renderLive(); break;
        case 'room': {
            if (!S.live) return;
            const i = S.live.rooms.findIndex(r => r.name === ev.room.name);
            if (i >= 0) S.live.rooms[i] = ev.room; else S.live.rooms.push(ev.room);
            renderRooms(); renderOnAir(); renderChips(); break;
        }
        case 'rooms': if (S.live) { S.live.rooms = ev.rooms; renderLive(); } break;
        case 'heard':
            if (S.live) { S.live.last_heard.unshift(ev.entry); S.live.last_heard.length = Math.min(S.live.last_heard.length, 40); renderLH(ev.entry.id); renderOnAir(); }
            clearTimeout(todayT); todayT = setTimeout(() => { loadToday(); if (S.tab === 'stats') loadStats(); }, 1500);
            break;
        case 'heard_update': clearTimeout(heardT); heardT = setTimeout(async () => { S.live = await api('GET', '/api/live'); renderLive(); }, 800); break;
        case 'visit': if (S.live) { S.live.visits.unshift(ev.entry); S.live.visits.length = Math.min(S.live.visits.length, 25); renderFeed(true); } break;
        case 'chat': S.chat.entries.unshift(ev.entry); if (S.tab === 'chat') renderChat(); break;
        case 'server': if (S.live) { S.live.server = ev.server; renderChips(); } break;
        case 'info': api('GET', '/api/info').then(i => { S.info = { ...S.info, ...i }; renderHeader(); }); break;
        case 'client_logos': loadClientLogos().then(() => renderAllLive()); break;
        case 'log': S.admin.logs.push(ev.entry); if (S.admin.logs.length > 600) S.admin.logs.shift(); appendLog(ev.entry); break;
    }
}

// ---------------------------------------------------------------- live
function rooms() { return (S.live && S.live.rooms) || []; }
function renderLive() { renderChips(); renderOnAir(); renderRooms(); renderLHFilter(); renderLH(); renderFeed(); }
function renderChips() {
    // status strip under the menu: a coloured dot says it, the text stays short
    const set = (id, cls, text) => { const e = $(id); e.className = 'n8-ss ' + cls; e.textContent = text; e.title = text; };
    set('chipLive', S.wsOk ? 'ok' : 'bad', S.wsOk ? 'Live data' : 'Live data offline');
    const st = S.live && S.live.server;
    if (!st) set('chipServer', '', 'FRN server');
    else set('chipServer', st.running ? (st.warning ? 'warn' : 'ok') : st.service === 'active' && !st.error ? 'warn' : 'bad',
             st.running ? (st.warning ? 'FRN server · SystemManager warning' : 'FRN server') : st.error ? 'FRN server: error' : st.service === 'active' ? 'FRN server starting' : 'FRN server stopped');
    const online = rooms().reduce((a, r) => a + r.clients.filter(c => !c.parrot).length, 0);
    set('chipOnline', online ? 'info' : 'idle', '');
    $('chipOnline').innerHTML = `<b>${online}</b>&nbsp;online`;
    const talkers = rooms().map(r => r.talking).filter(Boolean);
    set('chipAir', talkers.length ? 'ok' : 'plain', talkers.length ? `🎙️ On air: ${talkers.map(t => t.callsign || '?').join(', ')}` : '💤 Quiet');
    $('sOnline').textContent = online;
}
const CL_ICON = { 0: ['🔗', 'Crosslink'], 1: ['📻', 'Gateway (radio)'], 2: ['💻', 'PC only'] };
function clIcon(c) { if (c.parrot) return '<span title="Parrot – echo test">🦜</span>'; const x = CL_ICON[Number(c.client)] || CL_ICON[2]; return `<span title="${x[1]}">${x[0]}</span>`; }
function clientOrder(c) {
    if (c.parrot) return -1;
    const type = Number(c.client);
    if (type === 2) return 5;
    if (type === 0) return 0;
    if (['OWNER', 'NETOWNER', 'ADMIN'].includes(c.access)) return 1;
    if (Number(c.status) === 0) return 2;
    if (Number(c.status) === 1) return 3;
    return 4;
}
function renderOnAir() {
    const cards = rooms().filter(r => r.talking).map(r => ({ r, t: r.talking }));
    if (!cards.length) {
        const last = S.live && S.live.last_heard[0];
        $('onair').innerHTML = `<div class="slot idle"><div class="lbl"><span>On air</span><span class="pill">Quiet</span></div>
            <div class="idle-text">${last ? `Last: <b style="color:var(--text)">${esc(last.callsign || '?')}</b> in ${esc(last.room)} · ${fmtDur(last.duration)} · ${ago(last.ts + last.duration)}` : 'Nobody is talking right now'}</div></div>`;
        return;
    }
    $('onair').innerHTML = cards.map(({ r, t }) => `<div class="slot active frn"><div class="lbl"><span>🏠 ${esc(r.name)}</span><span class="pill air">ON AIR</span></div>
        <div class="who ${t.parrot ? '' : 'station-link'}" ${t.parrot ? '' : `onclick="openStation('${esc(t.callsign)}')"`}>${avatar(t.callsign || '?', '', t.parrot ? 'parrot' : t.sw)}
          <div style="min-width:0"><div class="call">${clIcon(t)} ${esc(t.callsign || '?')}</div>
          <div class="name">${esc(t.name || '')} ${flag(t.country)} ${esc(place(t))}</div></div>
          <div class="timer" data-start="${t.start}">${fmtClock(Date.now() / 1000 - t.start)}</div></div>
        <div class="meta">${t.band ? `<span class="pill">${esc(t.band)}</span>` : ''}${t.descr ? `<span class="pill">${esc(t.descr)}</span>` : ''}${r.tot ? `<span class="pill">max. ${r.tot} s</span>` : ''}</div></div>`).join('');
}
setInterval(() => document.querySelectorAll('.timer[data-start]').forEach(t => t.textContent = fmtClock(Date.now() / 1000 - Number(t.dataset.start))), 1000);
setInterval(() => { if (S.tab === 'live') document.querySelectorAll('[data-since]').forEach(e => e.textContent = since(Number(e.dataset.since))); }, 30000);

function renderRooms() {
    const rs = rooms();
    $('roomCount').textContent = rs.length;
    if (!rs.length) { $('rooms').innerHTML = '<div class="card empty">No open rooms.</div>'; return; }
    // first look: the room where someone talks, otherwise the fullest one
    if (!rs.some(r => r.name === S.liveRoom)) {
        const busy = rs.find(r => r.talking) || [...rs].sort((a, b) => b.clients.filter(c => !c.parrot).length - a.clients.filter(c => !c.parrot).length)[0];
        S.liveRoom = busy.name;
    }
    const selected = rs.find(r => r.name === S.liveRoom) || rs[0];
    const tabs = rs.map(r => {
        const n = r.clients.filter(c => !c.parrot).length;
        return `<button type="button" class="room-tab ${r.name === selected.name ? 'active' : ''} ${r.talking ? 'is-live' : ''}" data-room="${esc(r.name)}" aria-selected="${r.name === selected.name ? 'true' : 'false'}">
            <span class="room-tab-dot"></span><span class="room-tab-name">${r.hidden ? '🔒 ' : ''}${esc(r.name)}</span><span class="room-count ${n ? '' : 'zero'}">${n}</span>${r.talking ? '<span class="pill air">ON AIR</span>' : ''}
        </button>`;
    }).join('');
    const n = selected.clients.filter(c => !c.parrot).length;
    const rows = selected.clients.map((c, i) => ({ c, i })).sort((a, b) => clientOrder(a.c) - clientOrder(b.c) || a.i - b.i).map(({ c }) => `<div class="st-row ${c.talking ? 'talk' : ''} ${c.parrot ? '' : 'station-link'}" ${c.parrot ? '' : `onclick="openStation('${esc(c.callsign)}')"`}>
        ${avatar(c.callsign, 'sm', c.parrot ? 'parrot' : c.sw)}<div class="c"><b class="st-call">${roleBadge(c)}${esc(c.callsign)}</b>${c.talking ? '<span class="mic"></span>' : ''}${c.muted ? ' <span title="muted">🔇</span>' : ''}
        <small>${esc(c.name)}${c.name && (c.city || c.country) ? ' · ' : ''}${flag(c.country)} ${esc(place(c))}</small></div>
        <div class="r"><span class="band" title="${esc(c.band)}">${clIcon(c)} <span class="band-txt">${esc((c.band || '').length > 22 ? c.band.slice(0, 21) + '…' : c.band || '')}</span></span>${c.since ? `<div data-since="${c.since}">${since(c.since)}</div>` : ''}</div>
    </div>`).join('');
    $('rooms').innerHTML = `<div class="room-tabs" role="tablist" aria-label="FRN rooms">${tabs}</div>
        <div class="room ${selected.talking ? 'live' : ''}" role="tabpanel"><div class="room-head"><span class="dot ${S.live.server && S.live.server.running ? 'on' : 'off'}"></span><h3>${selected.hidden ? '🔒 ' : ''}${esc(selected.name)}</h3>
        ${selected.parrot ? '<span class="pill" title="Parrot echo test is on">🦜</span>' : ''}<span class="room-count ${n ? '' : 'zero'}">${n}</span></div>
        ${rows || '<div class="none">Nobody in this room</div>'}</div>`;
}
$('rooms').addEventListener('click', e => {
    const tab = e.target.closest('.room-tab');
    if (!tab || !tab.dataset.room || tab.dataset.room === S.liveRoom) return;
    S.liveRoom = tab.dataset.room;
    renderRooms();
});
function renderLHFilter() {
    const names = rooms().map(r => r.name);
    if (S.lhRoom !== 'all' && !names.includes(S.lhRoom)) S.lhRoom = 'all';
    $('lhFilter').innerHTML = [['all', 'All'], ...names.slice(0, 5).map(n => [n, n])].map(([v, l]) => `<button data-v="${esc(v)}" class="${S.lhRoom === v ? 'active' : ''}">${esc(l)}</button>`).join('');
}
$('lhFilter').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; S.lhRoom = b.dataset.v; renderLHFilter(); renderLH(); });
// Last heard: compact rows like the DMR dashboard – desktop one line, phone two short lines.
// The first 8 (phone 5) entries are shown, "Show all" shows the rest.
function renderLH(newId) {
    if (!S.live) return;
    let rows = S.live.last_heard || [];
    if (S.lhRoom !== 'all') rows = rows.filter(e => e.room === S.lhRoom);
    rows = rows.slice(0, 20);
    const more = $('lhMore');
    if (!rows.length) { $('lhBody').innerHTML = '<div class="lh-empty">Nothing heard yet.</div>'; if (more) more.hidden = true; return; }
    // desktop: last heard scrolls inside its box next to the rooms, so all rows are shown; phone/tablet: 5 / 8 + "Show all"
    const limit = matchMedia('(max-width: 760px)').matches ? 5 : matchMedia('(min-width: 1101px)').matches ? 1000 : 8;
    if (more) { more.hidden = rows.length <= limit; more.textContent = S.lhAll ? 'Show less ▴' : `Show all ${rows.length} ▾`; }
    if (!S.lhAll) rows = rows.slice(0, limit);
    $('lhBody').innerHTML = rows.map(e => `<div class="lh-row ${e.id === newId ? 'new' : ''}" role="listitem">
        <span class="lh-c lh-time">${fmtTime(e.ts)}</span>
        <span class="lh-c lh-st">${e.callsign ? `<span class="who station-link" onclick="openStation('${esc(e.callsign)}')">${avatar(e.callsign, 'sm', e.sw)}<span class="lh-who"><span class="lh-l1"><b>${esc(e.callsign)}</b>${flag(e.country)}</span><small>${esc(e.name || place(e))}</small></span></span>` : '<span class="dim">unknown station</span>'}</span>
        <span class="lh-c lh-room"><span class="pill tg">${esc(e.room)}</span></span>
        <span class="lh-c lh-dur">${fmtDur(e.duration)}</span>
        <span class="lh-c lh-band">${bandHtml(e)}</span></div>`).join('');
}
function renderFeed(flash) {
    const v = (S.live && S.live.visits) || [];
    $('feed').innerHTML = v.length ? v.slice(0, 40).map((e, i) => `<div class="ev ${flash && i === 0 ? 'new' : ''}"><span class="t">${fmtTime(e.ts).slice(0, 5)}</span>
        <span>${e.action === 'login' ? '🟢' : '⚪'}</span><span style="min-width:0;flex:1"><b class="station-link" onclick="openStation('${esc(e.callsign)}')">${esc(e.callsign)}</b>
        <span class="dim">${e.action === 'login' ? 'joined' : 'left'}</span> ${esc(e.room)}</span></div>`).join('') : '<div class="empty">No logins yet.</div>';
}
async function loadToday() {
    try {
        const d = await api('GET', '/api/stats?range=today'), T = d.totals;
        $('sTalks').textContent = num(T.talks); $('sAir').textContent = fmtDur(T.duration, true);
        $('sSt').textContent = T.stations; $('sPeak').innerHTML = `${T.peak_online}${T.peak_ts ? `<small>${new Date(T.peak_ts * 1000).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}</small>` : ''}`;
    } catch (e) {}
}
setInterval(loadToday, 5 * 60 * 1000);

// ---------------------------------------------------------------- station view
async function openStation(call) {
    if (!call) return;
    modal('<div class="empty">Loading …</div>', false, true);
    let d;
    try { d = await api('GET', `/api/station/${encodeURIComponent(call)}`); } catch (e) { $('ov').querySelector('.modal').innerHTML = `<div class="empty">${esc(call)}: ${esc(e.message)}</div>`; return; }
    const s = d.station;
    const maxH = Math.max(...d.hours, 1);
    const bars = d.hours.map((h, i) => `<rect x="${i * 15 + 1}" y="${60 - Math.max(h ? 3 : 1, h / maxH * 56)}" width="13" height="${Math.max(h ? 3 : 1, h / maxH * 56)}" rx="3" fill="${h ? '#3987e5' : 'rgba(255,255,255,.08)'}"><title>${String(i).padStart(2, '0')}:00 · ${fmtDur(h)}</title></rect>`).join('');
    $('ov').querySelector('.modal').innerHTML = `
        <div class="st-head">${avatar(s.callsign, 'xl', s.sw)}<div style="min-width:0">
            <div class="st-call">${esc(s.callsign)} ${flag(s.country)}</div>
            <div class="dim">${esc(s.name)}${s.name && place(s) ? ' · ' : ''}${esc(place(s))}${s.country && flag(s.country) ? ' · ' + esc(s.country) : ''}</div>
            <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">${s.band ? `<span class="pill">${isRadio(s) ? '📻' : '💻'} ${esc(s.band)}</span>` : ''}${s.descr ? `<span class="pill">${esc(s.descr)}</span>` : ''}
            ${d.online.length ? d.online.map(o => `<span class="pill ok">🟢 online in ${esc(o.room)}</span>`).join('') : `<span class="pill">last seen ${ago(s.last_ts)}${s.last_net ? ' · ' + esc(s.last_net) : ''}</span>`}</div></div>
            <button class="btn small" style="margin-left:auto;align-self:flex-start" onclick="closeModal()">✕</button></div>
        <div class="kpis" style="margin:14px 0 10px">
            <div class="kpi"><div class="k">🎙️ Talks (30 d)</div><div class="v">${d.talks_30d}</div></div>
            <div class="kpi"><div class="k">⏱️ Airtime (30 d)</div><div class="v">${fmtDur(d.duration_30d, true)}</div></div>
            <div class="kpi"><div class="k">🚪 Logins (30 d)</div><div class="v">${d.visits_30d}</div></div>
            <div class="kpi"><div class="k">🕑 Online (30 d)</div><div class="v">${fmtDur(d.online_30d, true)}</div></div></div>
        ${d.rooms.length ? `<div class="dim" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin:6px 0">Rooms</div>
            <div style="display:flex;flex-wrap:wrap;gap:6px">${d.rooms.map(r => `<span class="pill tg">${esc(r.net)} · ${fmtDur(r.duration, true)}</span>`).join('')}</div>` : ''}
        <div class="dim" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin:12px 0 4px">Talks by hour of day (30 days)</div>
        <svg viewBox="0 0 360 74" style="width:100%;height:auto;display:block">${bars}${[0, 6, 12, 18, 23].map(h => `<text x="${h * 15 + 7.5}" y="72" text-anchor="middle" font-size="9" fill="rgba(235,240,250,.5)">${h}</text>`).join('')}</svg>
        ${d.recent.length ? `<div class="tbl-wrap" style="margin-top:10px"><table class="tbl"><thead><tr><th>Time</th><th>Room</th><th class="num">Duration</th></tr></thead><tbody>
            ${d.recent.map(r => `<tr><td>${fmtDate(r.ts)}</td><td>${esc(r.net)}</td><td class="num">${fmtDur(r.duration)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No talks recorded yet.</div>'}
        <div class="dim" style="font-size:12px;margin-top:8px">First seen ${fmtDate(s.first_ts)} · ${num(d.talks_total)} talks, ${fmtDur(d.duration_total, true)} in total</div>`;
}

// ---------------------------------------------------------------- statistics (same charts as the N8schicht dashboard)
const COLORS = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181'];   // validated for the dark surface
const OTHER = '#6b7385';
const SEQ = ['rgba(57,135,229,.18)', 'rgba(57,135,229,.36)', 'rgba(57,135,229,.56)', 'rgba(57,135,229,.78)', '#3987e5'];
function roomColor(n) { const st = S.stats.slots; return n != null && st[n] != null ? COLORS[st[n]] : OTHER; }
function assignColors(series) {
    const keep = {}, used = new Set(), old = S.stats.slots;
    series.forEach(s => { if (s.room != null && old[s.room] != null && !used.has(old[s.room])) { keep[s.room] = old[s.room]; used.add(keep[s.room]); } });
    series.forEach(s => { if (s.room == null || keep[s.room] != null) return; const f = COLORS.findIndex((_, i) => !used.has(i)); if (f >= 0) { keep[s.room] = f; used.add(f); } });
    S.stats.slots = keep;
}
async function loadStats() { try { S.stats.data = await api('GET', `/api/stats?range=${S.stats.range}`); renderStats(); } catch (e) { console.warn(e); } }
bindSeg('stRange', v => { S.stats.range = v; loadStats(); });
bindSeg('stMetric', v => { S.stats.metric = v; renderStats(); });
function sFmt(v) { return S.stats.metric === 'talks' ? Math.round(v).toLocaleString('de-DE') : fmtDur(v, true); }
function renderStats() {
    const d = S.stats.data; if (!d) return;
    assignColors(d.series || []);
    const T = d.totals;
    $('kTalks').textContent = num(T.talks); $('kAir').textContent = fmtDur(T.duration, true);
    $('kSt').textContent = T.stations; $('kPeak').textContent = T.peak_online;
    renderBars(d); renderTime(d); renderOnline(d); renderHeat(d); renderStatTables(d);
}
function empty(el, t) { el.innerHTML = `<div class="empty">${t || 'No talks in this period yet.'}</div>`; }
function renderBars(d) {
    const el = $('stBars'), m = S.stats.metric;
    const rows = [...(d.stations || [])].sort((a, b) => b[m] - a[m] || b.duration - a.duration).slice(0, 10);
    $('stTopNote').textContent = m === 'talks' ? 'by talks' : 'by airtime';
    if (!rows.length) return empty(el);
    const W = Math.max(280, el.clientWidth || 420), rowH = 30, barH = 14, labelW = Math.min(170, Math.max(100, W * 0.36)), valW = 64;
    const max = Math.max(...rows.map(r => r[m])) || 1, plotW = W - labelW - valW;
    let svg = `<svg viewBox="0 0 ${W} ${rows.length * rowH}" role="img" aria-label="Top stations">`;
    rows.forEach((r, i) => {
        const y = i * rowH + (rowH - barH) / 2, w = Math.max(3, (r[m] / max) * plotW), rr = Math.min(4, w / 2);
        const room = Math.floor((labelW - 16 - r.callsign.length * 8.4) / 7.2);
        const name = r.name && room >= 3 ? esc(r.name.length > room ? r.name.slice(0, room - 1) + '…' : r.name) : '';
        svg += `<g class="hit" data-i="${i}" style="cursor:pointer"><rect x="0" y="${i * rowH}" width="${W}" height="${rowH}" fill="transparent"/>
            <text x="0" y="${i * rowH + rowH / 2 + 1}" dominant-baseline="middle" font-size="12.5" font-weight="700" fill="#f5f7fb">${esc(r.callsign)}${name ? `<tspan font-weight="500" fill="rgba(235,240,250,0.62)" dx="6">${name}</tspan>` : ''}</text>
            <path d="M${labelW},${y} h${w - rr} a${rr},${rr} 0 0 1 ${rr},${rr} v${barH - 2 * rr} a${rr},${rr} 0 0 1 -${rr},${rr} h-${w - rr} z" fill="${roomColor(r.room)}"/>
            <text x="${labelW + w + 8}" y="${i * rowH + rowH / 2 + 1}" dominant-baseline="middle" font-size="12" fill="rgba(235,240,250,0.8)">${sFmt(r[m])}</text></g>`;
    });
    el.innerHTML = svg + '</svg>';
    el.querySelectorAll('.hit').forEach(g => {
        const r = rows[+g.dataset.i];
        g.addEventListener('mousemove', ev => tip(ev, `<b>${esc(r.callsign)}${r.name ? ' · ' + esc(r.name) : ''}</b>` + tipRow(null, 'Airtime', fmtDur(r.duration)) +
            tipRow(null, 'Talks', r.talks) + tipRow(roomColor(r.room), 'Mostly in', esc(r.room)) + tipRow(null, 'Last', fmtDate(r.last))));
        g.addEventListener('mouseleave', hideTip);
        g.addEventListener('click', () => { hideTip(); openStation(r.callsign); });
    });
}
function bucketLabel(d, i, long) {
    const t = new Date(d.buckets[i] * 1000);
    if (d.bucket === 'hour') { const h = String(t.getHours()).padStart(2, '0'); return long ? `${t.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })} ${h}:00–${String((t.getHours() + 1) % 24).padStart(2, '0')}:00` : h; }
    if (d.bucket === 'month') return t.toLocaleDateString('de-DE', long ? { month: 'long', year: 'numeric' } : { month: 'short' });
    return long ? t.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit' }) : t.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }).replace(/\.$/, '');
}
function niceMax(v, dur) {
    if (dur) { for (const s of [60, 120, 300, 600, 900, 1200, 1800, 3600, 7200, 10800, 18000, 36000, 72000, 144000, 360000]) if (s * 4 >= v) return s * 4; return Math.ceil(v / 4 / 36000) * 36000 * 4; }
    const p = Math.pow(10, Math.floor(Math.log10(Math.max(1, v / 4))));
    for (const k of [1, 2, 2.5, 5, 10]) if (k * p * 4 >= v) return Math.max(4, k * p * 4);
    return v;
}
function axisEvery(n) { return n <= 8 ? 1 : n <= 24 ? 3 : n <= 31 ? 5 : 10; }
function renderTime(d) {
    const el = $('stTime'), lg = $('stLegend'), m = S.stats.metric, n = d.buckets.length, series = d.series || [];
    const label = s => s.room == null ? s.name : s.room;
    if (!series.length || !d.totals.talks) { lg.innerHTML = ''; return empty(el); }
    lg.innerHTML = series.map(s => `<span><i style="background:${roomColor(s.room)}"></i>${esc(label(s))}</span>`).join('');
    const totals = Array.from({ length: n }, (_, i) => series.reduce((a, s) => a + (s[m][i] || 0), 0));
    const yMax = niceMax(Math.max(...totals) || 1, m === 'duration');
    const W = Math.max(300, el.clientWidth || 600), H = 210, L = 44, R = 6, T = 6, B = 22, pw = W - L - R, ph = H - T - B;
    const cw = pw / n, bw = Math.max(3, Math.min(26, cw * 0.68)), y = v => T + ph - (v / yMax) * ph;
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Activity per room">`;
    for (let k = 0; k <= 4; k++) { const v = yMax * k / 4, yy = y(v);
        svg += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="rgba(255,255,255,${k ? 0.07 : 0.18})"/><text x="${L - 6}" y="${yy}" text-anchor="end" dominant-baseline="middle" font-size="10.5" fill="rgba(235,240,250,0.55)">${k ? sFmt(v) : '0'}</text>`; }
    const every = axisEvery(n);
    for (let i = 0; i < n; i++) {
        const cx = L + cw * i + cw / 2;
        if (i % every === 0) svg += `<text x="${cx}" y="${H - 6}" text-anchor="middle" font-size="10.5" fill="rgba(235,240,250,0.55)">${bucketLabel(d, i)}</text>`;
        let acc = 0;
        const segs = series.map(s => ({ s, v: s[m][i] || 0 })).filter(x => x.v > 0);
        segs.forEach((x, j) => {
            const y1 = y(acc); acc += x.v; const top = j === segs.length - 1;
            let h = y1 - y(acc) - (top ? 0 : 2); if (h < 1) h = 1;
            const xx = cx - bw / 2, r = top ? Math.min(4, bw / 2, h) : 0;
            svg += `<path class="col c${i}" d="M${xx},${y1} v-${h - r} a${r},${r} 0 0 1 ${r},-${r} h${bw - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${h - r} z" fill="${roomColor(x.s.room)}"/>`;
        });
        svg += `<rect class="hc" data-i="${i}" x="${L + cw * i}" y="${T}" width="${cw}" height="${ph}" fill="transparent"/>`;
    }
    el.innerHTML = svg + '</svg>';
    const cols = el.querySelectorAll('.col');
    el.querySelectorAll('.hc').forEach(h => {
        const i = +h.dataset.i;
        h.addEventListener('mousemove', ev => {
            cols.forEach(c => c.style.opacity = c.classList.contains('c' + i) ? '1' : '0.35');
            let html = `<b>${bucketLabel(d, i, true)}</b>`;
            series.forEach(s => { if (s[m][i]) html += tipRow(roomColor(s.room), label(s), sFmt(s[m][i])); });
            html += totals[i] ? tipRow(null, 'Total', sFmt(totals[i])) : '<div class="r"><span>no talks</span></div>';
            tip(ev, html);
        });
        h.addEventListener('mouseleave', () => { cols.forEach(c => c.style.opacity = ''); hideTip(); });
    });
}
function renderOnline(d) {
    const el = $('stOnline'), v = d.online || [], n = v.length;
    if (!v.some(x => x > 0)) return empty(el, 'No samples in this period yet.');
    const W = Math.max(300, el.clientWidth || 600), H = 170, L = 34, R = 8, T = 8, B = 22, pw = W - L - R, ph = H - T - B;
    const yMax = niceMax(Math.max(...v), false), x = i => L + (n === 1 ? pw / 2 : pw * i / (n - 1)), y = val => T + ph - val / yMax * ph;
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Stations online">`;
    for (let k = 0; k <= 4; k++) { const val = yMax * k / 4; svg += `<line x1="${L}" x2="${W - R}" y1="${y(val)}" y2="${y(val)}" stroke="rgba(255,255,255,${k ? .07 : .18})"/><text x="${L - 6}" y="${y(val)}" text-anchor="end" dominant-baseline="middle" font-size="10.5" fill="rgba(235,240,250,.55)">${Math.round(val)}</text>`; }
    const every = axisEvery(n);
    for (let i = 0; i < n; i += every) svg += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle" font-size="10.5" fill="rgba(235,240,250,.55)">${bucketLabel(d, i)}</text>`;
    const pts = v.map((val, i) => `${x(i)},${y(val)}`).join(' ');
    svg += `<polygon points="${x(0)},${y(0)} ${pts} ${x(n - 1)},${y(0)}" fill="rgba(57,135,229,.16)"/><polyline points="${pts}" fill="none" stroke="#3987e5" stroke-width="2" stroke-linejoin="round"/>`;
    svg += `<line id="olX" x1="0" x2="0" y1="${T}" y2="${T + ph}" stroke="rgba(255,255,255,.35)" visibility="hidden"/><circle id="olP" r="4" fill="#3987e5" stroke="#0b1224" stroke-width="2" visibility="hidden"/>`;
    svg += `<rect id="olHit" x="${L}" y="${T}" width="${pw}" height="${ph}" fill="transparent"/>`;
    el.innerHTML = svg + '</svg>';
    const hit = el.querySelector('#olHit'), lx = el.querySelector('#olX'), pt = el.querySelector('#olP'), svgEl = el.querySelector('svg');
    hit.addEventListener('mousemove', ev => {
        const r = svgEl.getBoundingClientRect(), px = (ev.clientX - r.left) / r.width * W;
        const i = Math.max(0, Math.min(n - 1, Math.round((px - L) / (n === 1 ? 1 : pw / (n - 1)))));
        lx.setAttribute('x1', x(i)); lx.setAttribute('x2', x(i)); lx.setAttribute('visibility', 'visible');
        pt.setAttribute('cx', x(i)); pt.setAttribute('cy', y(v[i])); pt.setAttribute('visibility', 'visible');
        tip(ev, `<b>${bucketLabel(d, i, true)}</b>` + tipRow('#3987e5', 'Stations online (max.)', v[i]));
    });
    hit.addEventListener('mouseleave', () => { lx.setAttribute('visibility', 'hidden'); pt.setAttribute('visibility', 'hidden'); hideTip(); });
}
function renderHeat(d) {
    const el = $('stHeat'), h = d.heat || [], days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const max = Math.max(...h.flat(), 0);
    $('heatNote').textContent = `airtime, last ${Math.round(d.heat_days)} days`;
    if (!max) return empty(el);
    const step = v => v <= 0 ? null : SEQ[Math.min(4, Math.floor(v / max * 4.999))];
    let html = '<div class="heat"><span></span>' + Array.from({ length: 24 }, (_, i) => `<span class="hl">${i % 3 === 0 ? i : ''}</span>`).join('');
    h.forEach((row, di) => {
        html += `<span class="lbl">${days[di]}</span>` + row.map((v, hi) => `<span class="cell" data-d="${di}" data-h="${hi}" style="${step(v) ? `background:${step(v)}` : ''}"></span>`).join('');
    });
    html += `</div><div class="heat-legend">less ${SEQ.map(c => `<i style="background:${c}"></i>`).join('')} more</div>`;
    el.innerHTML = html;
    el.querySelectorAll('.cell').forEach(c => {
        c.addEventListener('mousemove', ev => tip(ev, `<b>${days[c.dataset.d]} ${String(c.dataset.h).padStart(2, '0')}:00–${String((+c.dataset.h + 1) % 24).padStart(2, '0')}:00</b>` + tipRow('#3987e5', 'Airtime', fmtDur(h[c.dataset.d][c.dataset.h]))));
        c.addEventListener('mouseleave', hideTip);
    });
}
function renderStatTables(d) {
    const maxS = Math.max(...d.rooms.map(r => r.share), 0) || 1;
    $('stRoomTable').innerHTML = d.rooms.length ? d.rooms.map(r => `<tr><td><b>${esc(r.name)}</b></td><td class="num">${num(r.talks)}</td><td class="num">${fmtDur(r.duration, true)}</td>
        <td class="num hide-sm">${r.stations}</td><td class="hide-sm"><span class="share"><span class="bar"><div style="width:${r.share / maxS * 100}%;background:${roomColor(r.name)}"></div></span>${Math.round(r.share * 100)} %</span></td></tr>`).join('')
        : '<tr><td colspan="5" class="empty">–</td></tr>';
    $('stStTable').innerHTML = d.stations.length ? d.stations.slice(0, 15).map(s => `<tr><td><span class="who station-link" onclick="openStation('${esc(s.callsign)}')">${avatar(s.callsign, 'sm')}<span><b>${esc(s.callsign)}</b> ${flag(s.country)}<small>${esc(s.name || '')}</small></span></span></td>
        <td class="num">${num(s.talks)}</td><td class="num">${fmtDur(s.duration, true)}</td><td class="hide-sm">${esc(s.room)}</td></tr>`).join('')
        : '<tr><td colspan="4" class="empty">–</td></tr>';
}
function tipRow(c, l, v) { return `<div class="r"><span>${c ? `<i style="background:${c}"></i>` : ''}${esc(String(l))}</span><span>${v}</span></div>`; }
function tip(ev, html) {
    const t = $('tip'); t.innerHTML = html; t.style.display = 'block';
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + t.offsetWidth > innerWidth - 8) x = ev.clientX - t.offsetWidth - 14;
    if (y + t.offsetHeight > innerHeight - 8) y = ev.clientY - t.offsetHeight - 14;
    t.style.left = Math.max(8, x) + 'px'; t.style.top = Math.max(8, y) + 'px';
}
function hideTip() { $('tip').style.display = 'none'; }
let rsT = null; addEventListener('resize', () => { clearTimeout(rsT); rsT = setTimeout(() => { if (S.tab === 'stats') renderStats(); }, 150); });

// ---------------------------------------------------------------- stations directory
const DIR = { data: null, filter: 'all', limit: 100 };
async function loadDirectory() { try { DIR.data = (await api('GET', '/api/stations')).stations; renderDirectory(); } catch (e) { toast(e.message, true); } }
function renderDirectory() {
    if (!DIR.data) return;
    const q = $('dirSearch').value.trim().toLowerCase();
    const online = new Map(); rooms().forEach(r => r.clients.forEach(c => online.set(c.callsign, r.name)));
    let rows = DIR.data;
    if (DIR.filter === 'online') rows = rows.filter(r => online.has(r.callsign));
    if (DIR.filter === 'talked') rows = rows.filter(r => r.talks > 0).sort((a, b) => b.duration - a.duration);
    if (q) rows = rows.filter(r => [r.callsign, r.name, r.city, r.country].some(x => (x || '').toLowerCase().includes(q)));
    $('dirCount').textContent = num(rows.length);
    $('dirBody').innerHTML = rows.slice(0, DIR.limit).map(r => `<tr><td><span class="who station-link" onclick="openStation('${esc(r.callsign)}')">${avatar(r.callsign, 'sm', r.sw)}<span><b>${esc(r.callsign)}</b><small>${esc(r.name)}</small></span></span></td>
        <td class="hide-sm">${flag(r.country)} ${esc(place(r))}</td><td class="hide-sm">${bandHtml(r)}</td>
        <td class="num">${r.talks || '<span class="dim">–</span>'}</td><td class="num hide-sm">${r.talks ? fmtDur(r.duration, true) : ''}</td>
        <td>${online.has(r.callsign) ? `<span class="pill ok">🟢 ${esc(online.get(r.callsign))}</span>` : `${ago(r.last_ts)}${r.last_net ? ` <span class="dim">· ${esc(r.last_net)}</span>` : ''}`}</td></tr>`).join('')
        || '<tr><td colspan="6" class="empty">No station found.</td></tr>';
    $('dirMore').classList.toggle('hidden', rows.length <= DIR.limit);
    $('dirMore').textContent = `Show all ${num(rows.length)}`;
}
let dirT = null;
$('dirSearch').addEventListener('input', () => { clearTimeout(dirT); dirT = setTimeout(() => { DIR.limit = 100; renderDirectory(); }, 120); });
$('dirMore').addEventListener('click', () => { DIR.limit = 100000; renderDirectory(); });
bindSeg('dirFilter', v => { DIR.filter = v; DIR.limit = 100; renderDirectory(); });

// ---------------------------------------------------------------- chat
async function loadChat() { try { S.chat.entries = (await api('GET', '/api/chat?limit=200')).entries; renderChat(); } catch (e) { $('chatList').innerHTML = `<div class="empty">${esc(e.message)}</div>`; } }
function renderChat() {
    const names = [...new Set(S.chat.entries.map(e => e.net || e.room))];
    $('chatFilter').innerHTML = [['all', 'All'], ...names.slice(0, 6).map(n => [n, n])].map(([v, l]) => `<button data-v="${esc(v)}" class="${S.chat.room === v ? 'active' : ''}">${esc(l)}</button>`).join('');
    const rows = S.chat.entries.filter(e => S.chat.room === 'all' || (e.net || e.room) === S.chat.room);
    $('chatList').innerHTML = rows.length ? rows.map(e => `<div class="msg">${avatar(e.callsign || '?', 'sm')}<div class="bubble"><div class="h"><b>${esc(e.callsign || 'unknown')}</b> · ${esc(e.net || e.room)} · ${fmtDate(e.ts)}${e.private ? ' · 🔒 private' : ''}</div>
        <div class="txt">${esc(e.text)}</div></div></div>`).join('') : '<div class="empty">No messages yet.</div>';
}
$('chatFilter').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; S.chat.room = b.dataset.v; renderChat(); });

// ---------------------------------------------------------------- admin
const ADMIN_TABS = ['settings', 'rooms', 'lists', 'accounts', 'users', 'system', 'theme', 'links', 'import', 'logs', 'audit'];
function showAdmin(a) {
    if (!ADMIN_TABS.includes(a)) a = 'settings';
    S.admin.tab = a;
    document.querySelectorAll('#adminTabs button').forEach(b => b.classList.toggle('active', b.dataset.a === a));
    ADMIN_TABS.forEach(x => $('admin-' + x).classList.toggle('hidden', x !== a));
    ({ settings: loadSettings, rooms: loadRoomsAdmin, lists: loadLists, accounts: loadAccounts, users: loadUsers,
       system: loadSystem, theme: loadThemeAdmin, links: loadLinksAdmin, import: loadImportAdmin, logs: loadLogs, audit: loadAudit })[a]().catch(e => $('admin-' + a).innerHTML = `<div class="tile"><div class="notice-box">⚠️ ${esc(e.message)}</div></div>`);
    if (S.tab === 'admin') history.replaceState(null, '', '#admin/' + a);
}
$('adminTabs').addEventListener('click', e => { const b = e.target.closest('button[data-a]'); if (b) showAdmin(b.dataset.a); });
function setRestart(on) { $('restartBanner').classList.toggle('hidden', !on); }
async function serverCtl(action, btn) {
    const txt = { restart: ['Restart the FRN server?', 'All stations are disconnected and reconnect by themselves after a few seconds. The new configuration is used.', 'Restart'],
        stop: ['Stop the FRN server?', 'All stations are disconnected and nobody can connect until it is started again.', 'Stop'],
        start: ['Start the FRN server?', 'The FRN server starts with the current configuration.', 'Start'] }[action];
    if (!await confirmBox({ title: txt[0], body: txt[1] }, txt[2], action === 'stop' ? 'danger' : 'primary')) return;
    if (btn) btn.disabled = true;
    try { const r = await api('POST', `/api/admin/server/${action}`, {}); setRestart(false); toast(action === 'stop' ? 'FRN server stopped' : 'FRN server is starting …'); S.live && (S.live.server = r.server); }
    catch (e) { toast(e.message, true); }
    if (btn) btn.disabled = false;
    if (S.tab === 'admin' && ['settings', 'system'].includes(S.admin.tab)) setTimeout(() => showAdmin(S.admin.tab), 2500);
}
function restartServer(btn) { return serverCtl('restart', btn); }
function serverBox(st, jar) {
    const ok = st.running, svc = st.service || 'unknown';
    return `<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <span class="dot ${ok ? 'on' : 'off'}"></span><b>Java FRN server</b>
        <span class="dim">${ok ? `port ${esc(st.listen.join(', '))} · ${st.clients} stations · since ${fmtDate(st.started)}` : svc === 'active' ? 'starting …' : `service ${esc(svc)}`}
            · ${esc(st.version || (jar ? jar.version + ' (' + jar.build + ')' : 'version unknown'))}</span>
        <span style="flex:1"></span>
        ${svc === 'active' ? `<button class="btn small" onclick="serverCtl('stop', this)">⏹ Stop</button>` : `<button class="btn small" onclick="serverCtl('start', this)">▶ Start</button>`}
        <button class="btn small primary" onclick="serverCtl('restart', this)">🔄 Restart</button></div>
        ${st.error ? `<div class="notice-box" style="margin-top:10px">⚠️ ${esc(st.error)}<div style="margin-top:6px">📋 <span>The reason is in the public FRN error log:</span> <a href="#" onclick="event.preventDefault(); showAdmin('logs')">Logs → FRN error log</a> · <a href="http://log.freeradionetwork.de:60080/error_log.php" target="_blank" rel="noopener">open the complete log ↗</a></div></div>` : ''}`;
}
function fieldHtml(f) {
    const lbl = `<label for="f_${f.key}">${esc(f.label)}</label>`;
    const help = f.help ? `<div class="help">${esc(f.help)}</div>` : '';
    let input;
    if (f.kind === 'bool') input = `<label class="switch"><input type="checkbox" id="f_${f.key}" name="${f.key}" ${f.value ? 'checked' : ''}><span></span></label>`;
    else if (f.kind === 'choice') input = `<select id="f_${f.key}" name="${f.key}">${f.choices.map(c => `<option value="${esc(c[0])}" ${String(c[0]) === String(f.value ?? '') ? 'selected' : ''}>${esc(c[1])}</option>`).join('')}</select>`;
    else if (f.kind === 'longtext') return `<div class="row wide">${lbl}<textarea id="f_${f.key}" name="${f.key}" spellcheck="false" style="min-height:70px">${esc(f.value)}</textarea>${help}</div>`;
    else if (f.kind === 'password') input = `<div class="pw-wrap"><input type="password" id="f_${f.key}" name="${f.key}" value="${esc(f.value)}" autocomplete="new-password"><button type="button" class="btn small" onclick="const i=this.previousElementSibling;i.type=i.type==='password'?'text':'password';if(i.value==='••••••••')i.value=''">👁</button></div>`;
    else if (f.kind === 'int') input = `<input type="number" id="f_${f.key}" name="${f.key}" value="${esc(f.value ?? '')}" ${f.min != null ? `min="${f.min}"` : ''} ${f.max != null ? `max="${f.max}"` : ''}>`;
    else input = `<input type="text" id="f_${f.key}" name="${f.key}" value="${esc(f.value ?? '')}">`;
    return `<div class="row">${lbl}${input}${help}</div>`;
}
function formValues(form) { const v = {}; form.querySelectorAll('[name]').forEach(i => { if (i.dataset.skip) return; v[i.name] = i.type === 'checkbox' ? i.checked : i.value; }); return v; }

// settings: everything of server.properties plus the dashboard
async function loadSettings() {
    const d = await api('GET', '/api/admin/settings');
    setRestart(d.restart_needed);
    $('admin-settings').innerHTML = `<div class="tile" style="margin-bottom:14px">${serverBox(d.server, d.jar)}
        <div class="actions" style="justify-content:flex-start;margin-top:10px"><button class="btn small" onclick="checkUpdate(this)">⬆️ Check for update</button>
            <button class="btn small" onclick="showProps()">🧾 Show server.properties</button><span class="dim" id="javaUpdInfo" style="font-size:12.5px"></span></div></div>
        <div class="tiles">${d.sections.map(sec => `
        <form class="tile" data-sec="${sec.id}" onsubmit="event.preventDefault(); saveSettings(this)"><h3>${esc(sec.title)}</h3><div class="subt">${esc(sec.subtitle)}</div>
            ${sec.id === 'sysman' ? '<div class="notice-box">🌐 Registered at the SystemManager the server is listed in the FRN system and checks the logins there. The SystemManager tests that address and port are reachable from the internet – set up port forwarding first.</div><div class="notice-box">🔑 Every FRN server needs its own FRN account – the same e-mail and password on two servers are refused (“the same credentials are already online on another server”). <button type="button" class="btn small" style="margin-left:6px" onclick="openFrnPassword()">📧 Request FRN password</button></div><div class="notice-box">📋 <span>Refused by the SystemManager? The reason is in the public FRN error log of freeradionetwork.de (Help → Error log).</span> <button type="button" class="btn small" style="margin-left:6px" onclick="showAdmin(\'logs\')">📋 FRN error log</button> <a class="btn small" href="http://log.freeradionetwork.de:60080/error_log.php" target="_blank" rel="noopener">open ↗</a></div>' : ''}
            ${sec.fields.map(fieldHtml).join('')}<div class="actions"><button class="btn primary">Save</button></div></form>`).join('')}</div>`;
}
async function saveSettings(form) {
    try {
        const r = await api('POST', '/api/admin/settings', { changes: formValues(form) });
        toast(r.dashboard_restart_needed ? 'HTTPS settings saved. Restart the dashboard service to apply them.' : (r.changed.length ? `Saved (${r.changed.length})` : 'No changes')); setRestart(r.restart_needed);
        const i = await api('GET', '/api/info'); S.info = { ...S.info, ...i }; renderHeader();
    } catch (e) { toast(e.message, true); }
}
async function checkUpdate(btn) {
    btn.disabled = true; $('javaUpdInfo').textContent = 'checking freeradionetwork.de …';
    try {
        const r = await api('GET', '/api/admin/server/update');
        if (!r.ok) $('javaUpdInfo').textContent = `not reachable: ${r.error}`;
        else if (r.update) $('javaUpdInfo').innerHTML = `Version <b>${esc(r.latest.version)}</b> (${esc(r.latest.build)}) is available – installed ${esc(r.installed ? r.installed.version : '?')}. <button class="btn small primary" onclick="installUpdate(this)">Install</button>`;
        else $('javaUpdInfo').textContent = `✓ up to date (${r.installed ? r.installed.version + ', ' + r.installed.build : '?'})`;
    } catch (e) { $('javaUpdInfo').textContent = e.message; }
    btn.disabled = false;
}
async function installUpdate(btn) {
    if (!await confirmBox({ title: 'Install the update?', body: 'FRN_Server.zip is loaded from freeradionetwork.de, FRN_Server.jar replaced and the FRN server restarted.' }, 'Install')) return;
    btn.disabled = true; $('javaUpdInfo').textContent = 'downloading …';
    try { const r = await api('POST', '/api/admin/server/update', {}); toast(`Installed: ${r.installed ? r.installed.version : ''}`); loadSettings(); } catch (e) { toast(e.message, true); btn.disabled = false; }
}
async function showProps() {
    const r = await api('GET', '/api/admin/server/properties');
    modal(`<h2>🧾 server.properties</h2><p class="dim" style="margin:4px 0 8px">${esc(r.path)} – written from the database, do not edit by hand.</p>
        <pre class="term" style="max-height:60vh;overflow:auto">${esc(r.text)}</pre><div class="actions"><button class="btn" onclick="closeModal()">Close</button></div>`, false, true);
}

// rooms (netNN of server.properties)
const ROOM_FIELDS = [
    ['enabled', 'Room is open (_enable)', 'bool', 'Off: the server does not offer this room'],
    ['hidden', 'Hidden on the dashboard', 'bool', 'Only after login on the dashboard (the FRN clients still see it)'],
    ['owners', 'Room owners (_owner)', 'text', 'E-mails, comma separated; NETOWNER rights in this room. Empty = server owner'],
    ['show_info', 'Info message (_show_infomessage)', 'choice', 'Who sees the info message of the access list', [['acl', 'only clients affected by the access list'], ['always', 'always']]],
    ['tot', 'Max. transmission (_tot, s)', 'int', 'Default 180'],
    ['speechpause', 'Speech pause (_speechpause, ms)', 'int', '0 = none'],
    ['speechpause_msg', 'Speech pause message', 'text', 'Sent to PC-only clients; {callsign} is replaced'],
    ['parrot', 'Parrot (_parrot_enable)', 'bool', 'Echo test: plays back every transmission'],
    ['parrot_startstop', 'Parrot start/stop (_parrot_startstop_enable)', 'bool', 'The parrot can be switched on and off by text message'],
    ['unmute_min', 'Unmute after (_unmute, min)', 'int', '0 = muted until unmuted'],
    ['acl_cl', 'Crosslinks allowed (_acl_cl)', 'text', 'Empty = all, none = no crosslinks, or e-mails'],
    ['acl_gw', 'Gateways allowed (_acl_gw)', 'text', 'Empty = all, none = no gateways, or e-mails'],
    ['acl_info', 'Message for refused crosslinks/gateways (_acl_info)', 'text', 'Simple HTML'],
    ['bl_regexp', 'Block pattern (_bl_regexp)', 'text', 'Regular expression on name, e-mail and city'],
    ['bl_info', 'Message for blocked clients (_bl_info)', 'text', 'Simple HTML'],
    ['tg_params', 'Telegram bot (_tgbot_params)', 'text', 'min. transmission ms;min. idle ms;bot token;channel ID – e.g. 6000;30000;123:ABC;-100123'],
];
async function loadRoomsAdmin() {
    const d = await api('GET', '/api/admin/rooms');
    setRestart(d.restart_needed);
    S.admin.rooms = d.rooms;
    if (!d.rooms.find(r => r.id === S.admin.room)) S.admin.room = d.rooms[0] && d.rooms[0].id;
    const r = d.rooms.find(x => x.id === S.admin.room);
    const f = (k, l, kind, help, choices) => fieldHtml({ key: k, label: l, kind, help, choices, value: r[k] });
    const net = x => 'net' + String(x.idx).padStart(2, '0');
    $('admin-rooms').innerHTML = `<div class="grid rooms-admin">
        <div class="tile"><h3>🏠 Rooms</h3><div class="subt">Order on the dashboard; the FRN clients see the rooms sorted by name. ⭐ = default room, 🦜 = net00, the test/parrot room.</div>
            <div class="room-list">${d.rooms.map((x, i) => `<div class="room-item ${x.id === S.admin.room ? 'active' : ''}" onclick="S.admin.room=${x.id};loadRoomsAdmin()">
                <span class="n">${x.name === d.default_room ? '⭐ ' : ''}${x.idx === 0 ? '🦜 ' : ''}${x.hidden ? '🔒 ' : ''}${x.enabled ? '' : '⛔ '}${esc(x.name)} <span class="dim mono" style="font-size:11px">${net(x)}</span></span><span class="room-count ${x.online ? '' : 'zero'}">${x.online}</span>
                <button class="btn small" title="Up" onclick="event.stopPropagation();moveRoom(${i},-1)" ${i ? '' : 'disabled'}>▲</button>
                <button class="btn small" title="Down" onclick="event.stopPropagation();moveRoom(${i},1)" ${i < d.rooms.length - 1 ? '' : 'disabled'}>▼</button></div>`).join('')}</div>
            <form class="actions" style="justify-content:stretch" onsubmit="event.preventDefault();addRoom(this)">
                <input type="text" name="name" placeholder="New room" required style="flex:2"><select name="tpl" style="flex:1" title="Copy settings from"><option value="">empty</option>${d.rooms.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join('')}</select>
                <button class="btn primary">➕ Add</button></form></div>
        ${r ? `<form class="tile" onsubmit="event.preventDefault()" id="roomForm"><h3>${esc(r.name)} <span class="dim mono" style="font-size:12px">${net(r)}</span></h3>
            <div class="subt">${r.online} stations online · the FRN server uses changes after a restart${r.idx === 0 ? ' · net00 is always the test/parrot room of the server' : ''}</div>
            ${f('name', 'Name (' + net(r) + ')', 'text', '')}
            ${ROOM_FIELDS.filter(x => !(r.idx === 0 && x[0] === 'parrot')).map(([k, l, kind, help, ch]) => f(k, l, kind, help, ch)).join('')}
            <div class="actions">${r.name !== d.default_room && r.idx !== 0 ? `<button type="button" class="btn" onclick="makeDefault('${esc(r.name)}')">⭐ Default room</button>` : ''}
                ${r.idx !== 0 ? `<button type="button" class="btn danger" onclick="deleteRoom(${r.id}, '${esc(r.name)}')">🗑️ Delete</button>` : ''}<span style="flex:1"></span>
                <button type="button" class="btn primary" onclick="saveRoom()">Save</button></div></form>` : '<div class="tile empty">No room.</div>'}</div>`;
}
async function saveRoom() {
    try { const r = await api('PATCH', `/api/admin/rooms/${S.admin.room}`, { values: formValues($('roomForm')) }); setRestart(r.restart_needed); toast('Saved – restart the FRN server to use it'); loadRoomsAdmin(); } catch (e) { toast(e.message, true); }
}
async function addRoom(f) {
    try { const r = await api('POST', '/api/admin/rooms', { name: f.name.value.trim(), template: f.tpl.value ? Number(f.tpl.value) : null }); S.admin.room = r.id; toast('Room created'); loadRoomsAdmin(); } catch (e) { toast(e.message, true); }
}
async function moveRoom(i, delta) {
    const ids = S.admin.rooms.map(r => r.id), j = i + delta; [ids[i], ids[j]] = [ids[j], ids[i]];
    try { await api('POST', '/api/admin/rooms/order', { ids }); loadRoomsAdmin(); } catch (e) { toast(e.message, true); }
}
async function deleteRoom(id, name) {
    if (!await confirmBox({ title: `Delete room ${name}?`, body: 'After the next restart of the FRN server the room is gone; its stations land in the default room. Statistics are kept.' }, 'Delete', 'danger')) return;
    try { await api('DELETE', `/api/admin/rooms/${id}`); toast('Deleted'); loadRoomsAdmin(); } catch (e) { toast(e.message, true); }
}
async function makeDefault(name) { try { await api('POST', '/api/admin/settings', { changes: { 'frn.default_room': name } }); loadRoomsAdmin(); } catch (e) { toast(e.message, true); } }

// ACL lists: SQLite-backed forms exported to the FRN server's XML files.
const ACL_LABEL = { admin: '🛡️ Admins', mute: '🔇 Muted', block: '⛔ Blocked', access: '🔐 Access list' };
function aclListForm(room, kind, entries) {
    const kindEntries = entries || [];
    const rows = kindEntries.length ? kindEntries.map(e => `<form class="acl-entry" data-acl-form data-action="edit" data-kind="${kind}" data-room="${room.id}" data-row="${esc(e.row_id)}">
        <input type="hidden" name="id" value="${esc(e.id)}">
        <label>FRN ID<input type="text" name="id_display" value="${esc(e.id)}" readonly title="The entry ID is kept for compatibility"></label>
        <label>E-mail<input type="text" name="email" value="${esc(e.email)}" maxlength="250" required></label>
        <label>Callsign<input type="text" name="callsign" value="${esc(e.callsign)}" maxlength="30"></label>
        <label>Name<input type="text" name="name" value="${esc(e.name)}" maxlength="80"></label>
        <label>Client type<select name="client_type"><option value="0" ${e.client_type === '0' ? 'selected' : ''}>Crosslink</option><option value="1" ${e.client_type === '1' ? 'selected' : ''}>Gateway</option><option value="2" ${e.client_type === '2' ? 'selected' : ''}>PC Only</option></select></label>
        <label>Band / channel<input type="text" name="band_channel" value="${esc(e.band_channel)}" maxlength="100"></label>
        <label>Country<input type="text" name="country" value="${esc(e.country)}" maxlength="80"></label>
        <label>City<input type="text" name="city" value="${esc(e.city)}" maxlength="100"></label>
        ${kind === 'access' ? `<label class="acl-check"><input type="checkbox" name="can_tx" ${e.can_tx ? 'checked' : ''}> Can transmit</label>` : ''}
        <div class="acl-actions"><button class="btn small" type="submit">Save</button><button class="btn small danger" type="button" data-acl-delete>Remove</button></div>
    </form>`).join('') : '<div class="empty acl-empty">No entries in this list.</div>';
    const pick = S.admin.aclClients.length ? `<label class="acl-pick">Copy an online station <select data-acl-client><option value="">Select a connected station…</option>${S.admin.aclClients.map((c, i) => `<option value="${i}">${esc(c.callsign)} · ${esc(c.email || 'no e-mail')} · ${esc(c.id)}</option>`).join('')}</select></label>` : '';
    return `<section class="acl-list"><h4>${ACL_LABEL[kind]} <span class="count">${kindEntries.length}</span></h4>${rows}
        <form class="acl-entry acl-add" data-acl-form data-action="add" data-kind="${kind}" data-room="${room.id}">
            <div class="acl-add-title">Add entry</div>${pick}
            <label>FRN client ID<input type="text" name="id" maxlength="120" required></label>
            <label>E-mail<input type="text" name="email" maxlength="250" required></label>
            <label>Callsign<input type="text" name="callsign" maxlength="30"></label>
            <label>Name<input type="text" name="name" maxlength="80"></label>
            <label>Client type<select name="client_type"><option value="0">Crosslink</option><option value="1">Gateway</option><option value="2" selected>PC Only</option></select></label>
            <label>Band / channel<input type="text" name="band_channel" value="PC Only" maxlength="100"></label>
            <label>Country<input type="text" name="country" maxlength="80"></label>
            <label>City<input type="text" name="city" maxlength="100"></label>
            ${kind === 'access' ? '<label class="acl-check"><input type="checkbox" name="can_tx" checked> Can transmit</label>' : ''}
            <div class="acl-actions"><button class="btn primary small" type="submit">Add to list</button></div>
        </form></section>`;
}
async function loadLists() {
    try {
        const d = await api('GET', '/api/admin/acl');
        S.admin.aclClients = d.clients || [];
        $('admin-lists').innerHTML = `<div class="tile"><h3>🛡️ Server access lists</h3>
            <div class="subt">Lists are stored in SQLite and written in the FRN server's XML format. Existing XML entries are imported automatically. Changes take effect after restarting the FRN server; original XML files are backed up before replacement.</div>
            ${d.errors && d.errors.length ? `<div class="notice-box">Some ACL files could not be imported: ${d.errors.map(esc).join('<br>')}</div>` : ''}
            ${d.rooms.map(room => {
                const file = kind => d.files.find(f => f.room_id === room.id && f.kind === ({admin:'AdminList',mute:'MuteList',block:'BlockList',access:'AccessList'}[kind]));
                return `<section class="acl-room"><h3>🏠 ${esc(room.name)} <span class="dim mono">net${String(room.idx).padStart(2, '0')}</span></h3>
                    <form class="acl-mode" data-acl-form data-action="config" data-kind="access" data-room="${room.id}">
                        <label><input type="checkbox" name="access_on" ${room.access_on ? 'checked' : ''}> Only allow entries on the access list</label>
                        <label><input type="checkbox" name="txright_on" ${room.txright_on ? 'checked' : ''}> Require talk permission</label>
                        <label class="acl-notice">Access message<textarea name="notice" maxlength="1000">${esc(room.notice)}</textarea></label>
                        <div class="acl-actions"><button class="btn small" type="submit">Save access settings</button></div>
                    </form>
                    <div class="acl-grid">${['admin','mute','block','access'].map(kind => aclListForm(room, kind, file(kind)?.entries || [])).join('')}</div>
                </section>`;
            }).join('') || '<div class="empty">No rooms configured.</div>'}
            <div class="notice-box">FRN owners and admins can still change these lists in the FRN client. The dashboard imports changes from the XML files before displaying or editing them.</div>
        </div>`;
    } catch (e) { $('admin-lists').innerHTML = `<div class="tile empty">${esc(e.message)}</div>`; }
}
async function saveAclForm(f, action = f.dataset.action) {
    const kind = f.dataset.kind, room_id = Number(f.dataset.room);
    const b = { action, kind, room_id };
    if (action === 'config') {
        b.access_on = f.elements.access_on.checked; b.txright_on = f.elements.txright_on.checked;
        b.notice = f.elements.notice.value;
    } else {
        const entry = Object.fromEntries(new FormData(f));
        entry.id = f.dataset.action === 'edit' ? f.elements.id.value : entry.id;
        entry.can_tx = f.elements.can_tx ? f.elements.can_tx.checked : true;
        b.entry = entry;
        if (action === 'edit') { b.row_id = f.dataset.row; b.old_email = f.elements.email.defaultValue; }
    }
    try {
        const r = await api('POST', '/api/admin/acl', b);
        setRestart(r.restart_needed);
        toast('ACL saved. Restart the FRN server to apply the change.');
        await loadLists();
    } catch (e) { toast(e.message, true); }
}
$('admin-lists').addEventListener('submit', e => {
    const f = e.target.closest('[data-acl-form]');
    if (!f) return;
    e.preventDefault(); saveAclForm(f);
});
$('admin-lists').addEventListener('click', async e => {
    const button = e.target.closest('[data-acl-delete]');
    if (!button) return;
    const f = button.closest('[data-acl-form]');
    if (!await confirmBox({ title: 'Remove this ACL entry?', body: 'The list file will be backed up before it is rewritten. Restart the FRN server to apply the change.' }, 'Remove', 'danger')) return;
    try {
        const r = await api('POST', '/api/admin/acl', { action: 'delete', kind: f.dataset.kind, room_id: Number(f.dataset.room), row_id: f.dataset.row });
        setRestart(r.restart_needed); toast('ACL entry removed. Restart the FRN server to apply the change.'); await loadLists();
    } catch (err) { toast(err.message, true); }
});
$('admin-lists').addEventListener('change', e => {
    const select = e.target.closest('[data-acl-client]');
    if (!select || select.value === '') return;
    const c = S.admin.aclClients[Number(select.value)], f = select.closest('form');
    if (!c || !f) return;
    for (const [key, value] of Object.entries({ id: c.id, email: c.email, callsign: c.callsign, name: c.name,
        client_type: c.client_type, band_channel: c.band_channel })) if (f.elements[key] && value) f.elements[key].value = value;
});

// own password list (stand-alone: acl/FRNPasswd.xml)
async function loadAccounts() {
    const d = await api('GET', '/api/admin/accounts');
    $('admin-accounts').innerHTML = `<div class="grid users-grid">
        <div class="tile"><h3>🔑 FRN accounts</h3><div class="subt">The password list of the server for <b>stand-alone</b> mode (acl/FRNPasswd.xml).
            ${!d.standalone ? '<br>⚠️ The server is registered at the SystemManager: logins are checked there, this list is not used.' : d.enabled ? ' Only these accounts get in.' : '<br>⚠️ The list is switched off (Settings → SystemManager): every password is accepted.'}</div>
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Station</th><th>E-mail</th><th class="hide-sm">Last login</th><th></th></tr></thead><tbody>
        ${d.accounts.map(a => `<tr><td><b>${esc(a.callsign)}</b> ${a.disabled ? '<span class="pill bad">locked</span>' : ''}<br><span class="dim">${esc(a.name)}</span></td><td class="mono" style="font-size:12.5px">${esc(a.email)}</td>
            <td class="hide-sm">${a.last_login ? fmtDate(a.last_login) : '–'}</td><td class="num"><button class="btn small" onclick='editAccount(${JSON.stringify(a).replace(/'/g, '&#39;')})'>Edit</button></td></tr>`).join('') || '<tr><td colspan="4" class="empty">No accounts yet.</td></tr>'}
        </tbody></table></div></div>
        <form class="tile" onsubmit="event.preventDefault(); saveAccountEntry(this)"><h3>➕ New FRN account</h3>
            <div class="row"><label>E-mail (login of the FRN client)</label><input type="text" name="email" required></div>
            <div class="row"><label>Callsign</label><input type="text" name="callsign" required></div>
            <div class="row"><label>Name</label><input type="text" name="name"></div>
            <div class="row"><label>FRN password</label><input type="password" name="password" required minlength="4" autocomplete="new-password"><div class="help">The server needs the password itself in FRNPasswd.xml (file readable only by the service).</div></div>
            <div class="actions"><button class="btn primary">Create</button></div></form></div>`;
}
async function saveAccountEntry(f, close) {
    try { const r = await api('POST', '/api/admin/accounts', { email: f.email.value, callsign: f.callsign.value, name: f.name.value, password: f.password.value, disabled: f.disabled ? f.disabled.checked : false });
        if (close) closeModal(); setRestart(r.restart_needed); toast('Saved'); loadAccounts(); } catch (e) { toast(e.message, true); }
}
function editAccount(a) {
    modal(`<h2>${esc(a.callsign || a.email)}</h2><form onsubmit="event.preventDefault(); saveAccountEntry(this, true)">
        <input type="hidden" name="email" value="${esc(a.email)}">
        <div class="row"><label>Callsign</label><input type="text" name="callsign" value="${esc(a.callsign)}"></div>
        <div class="row"><label>Name</label><input type="text" name="name" value="${esc(a.name)}"></div>
        <div class="row"><label>New password (empty = keep)</label><input type="password" name="password" minlength="4" autocomplete="new-password"></div>
        <label style="display:flex;gap:8px;align-items:center" class="dim"><input type="checkbox" name="disabled" ${a.disabled ? 'checked' : ''}> Locked</label>
        <div class="actions"><button type="button" class="btn danger" onclick="delAccount('${esc(a.email)}')">Delete</button><span style="flex:1"></span>
        <button type="button" class="btn" onclick="closeModal()">Cancel</button><button class="btn primary">Save</button></div></form>`);
}
async function delAccount(email) { closeModal(); if (!await confirmBox({ title: `Delete ${email}?`, body: 'The station cannot log in with this account any more (after the next restart).' }, 'Delete', 'danger')) return;
    try { const r = await api('DELETE', `/api/admin/accounts/${encodeURIComponent(email)}`); setRestart(r.restart_needed); loadAccounts(); } catch (e) { toast(e.message, true); } }

// users
async function loadUsers() {
    const d = await api('GET', '/api/admin/users');
    const sa = S.me.role === 'superadmin';
    $('admin-users').innerHTML = `<div class="grid users-grid">
        <div class="tile"><h3>👥 Users</h3><div class="subt">Superadmin: everything, also admins. Admins: everything except other admins. Users: see the dashboard also when it is private, and hidden rooms.</div>
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th>User</th><th>Role</th><th class="hide-sm">Last login</th><th></th></tr></thead><tbody>
        ${d.users.map(u => `<tr><td><b>${esc(u.username)}</b> ${u.disabled ? '<span class="pill bad">locked</span>' : ''}<br><span class="dim">${esc(u.display_name)}</span></td>
            <td><span class="pill ${u.role === 'superadmin' ? 'warn' : u.role === 'admin' ? 'ok' : ''}">${u.role}</span></td><td class="hide-sm">${u.last_login ? fmtDate(u.last_login) : '–'}</td>
            <td class="num">${u.role === 'superadmin' || (u.role === 'admin' && !sa) ? '' : `<button class="btn small" onclick='editUser(${JSON.stringify(u).replace(/'/g, '&#39;')})'>Edit</button>`}</td></tr>`).join('')}
        </tbody></table></div></div>
        <form class="tile" onsubmit="event.preventDefault(); createUser(this)"><h3>➕ New user</h3>
            <div class="row"><label>Username</label><input type="text" name="username" required></div>
            <div class="row"><label>Name</label><input type="text" name="display_name"></div>
            <div class="row"><label>Password (min. 10)</label><input type="password" name="password" required minlength="10" autocomplete="new-password"></div>
            <div class="row"><label>Role</label><select name="role"><option value="user">User</option>${sa ? '<option value="admin">Admin</option>' : ''}</select></div>
            <div class="actions"><button class="btn primary">Create</button></div></form></div>
`;
}
async function createUser(f) {
    try { await api('POST', '/api/admin/users', { username: f.username.value, display_name: f.display_name.value, password: f.password.value, role: f.role.value }); toast('User created'); loadUsers(); }
    catch (e) { toast(e.message, true); }
}
function editUser(u) {
    const sa = S.me.role === 'superadmin';
    modal(`<h2>Edit ${esc(u.username)}</h2><form onsubmit="event.preventDefault(); saveUser(${u.id}, this)">
        <div class="row"><label>Username</label><input type="text" name="username" value="${esc(u.username)}"></div>
        <div class="row"><label>Name</label><input type="text" name="display_name" value="${esc(u.display_name)}"></div>
        <div class="row"><label>Role</label><select name="role"><option value="user" ${u.role === 'user' ? 'selected' : ''}>User</option>${sa ? `<option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>` : ''}</select></div>
        <div class="row"><label>New password (empty = keep)</label><input type="password" name="password" minlength="10" autocomplete="new-password"></div>
        <label style="display:flex;gap:8px;align-items:center" class="dim"><input type="checkbox" name="disabled" ${u.disabled ? 'checked' : ''}> Locked</label>
        <div class="err" id="uErr"></div>
        <div class="actions"><button type="button" class="btn danger" onclick="delUser(${u.id}, '${esc(u.username)}')">Delete</button><span style="flex:1"></span>
        <button type="button" class="btn" onclick="closeModal()">Cancel</button><button class="btn primary">Save</button></div></form>`);
}
async function saveUser(id, f) {
    const b = { username: f.username.value, display_name: f.display_name.value, role: f.role.value, disabled: f.disabled.checked };
    if (f.password.value) b.password = f.password.value;
    try { await api('PATCH', `/api/admin/users/${id}`, b); closeModal(); toast('Saved'); loadUsers(); } catch (e) { $('uErr').textContent = e.message; }
}
async function delUser(id, name) {
    closeModal();
    if (!await confirmBox({ title: `Delete ${name}?`, body: 'The user and all sessions are removed.' }, 'Delete', 'danger')) return;
    try { await api('DELETE', `/api/admin/users/${id}`); toast('Deleted'); loadUsers(); } catch (e) { toast(e.message, true); }
}

// system
async function loadSystem() {
    const d = await api('GET', '/api/admin/system'), i = d.info, st = d.server;
    const memUsed = i.mem_total ? (i.mem_total - i.mem_available) : null;
    const sa = S.me.role === 'superadmin';
    $('admin-system').innerHTML = `<div class="grid g2">
        <div class="tile"><h3>🛰️ FRN server</h3><div class="kv" style="margin-top:10px">
            <div class="k">Service</div><div class="v">${st.running ? '<span class="pill ok">running</span>' : `<span class="pill bad">${esc(st.service)}</span>`}${st.restarts ? ` <span class="dim">${st.restarts} restarts</span>` : ''}</div>
            <div class="k">Port</div><div class="v mono" style="font-size:12px">${esc((st.listen || []).join(', ') || '–')}</div>
            <div class="k">Running since</div><div class="v">${fmtDate(st.started)}</div>
            <div class="k">Stations online</div><div class="v">${d.online}</div>
            <div class="k">Program</div><div class="v">Java FRN_Server ${esc(st.version || (d.jar ? d.jar.version + ' (' + d.jar.build + ')' : '?'))}</div>
            <div class="k">FRN_Server.jar</div><div class="v mono" style="font-size:11px">${esc(d.jar_path)}</div>
            <div class="k">Configuration</div><div class="v mono" style="font-size:11px">${esc(d.frn_home)}</div>
            <div class="k">frn_adn</div><div class="v">${esc(d.app_version)}${d.demo ? ' (demo)' : ''} · up ${fmtDur(d.uptime, true)} · ${d.sockets} browsers</div></div>
            ${st.error ? `<div class="notice-box" style="margin-top:10px">⚠️ ${esc(st.error)}</div>` : ''}
            <div class="actions"><button class="btn" onclick="restartApp()">♻️ Restart dashboard</button><button class="btn primary" onclick="serverCtl('restart', this)">🔄 Restart FRN server</button></div></div>
        <div class="tile"><h3>🗄️ Data (SQLite)</h3><div class="kv" style="margin-top:10px">
            <div class="k">Rooms</div><div class="v">${num(d.counts.rooms)}</div><div class="k">FRN accounts</div><div class="v">${num(d.counts.frn_accounts)}</div>
            <div class="k">Talks</div><div class="v">${num(d.counts.talks)}${d.since ? ` <span class="dim">since ${fmtDate(d.since)}</span>` : ''}</div>
            <div class="k">Daily totals</div><div class="v">${num(d.counts.talk_daily)}</div>
            <div class="k">Logins</div><div class="v">${num(d.counts.visits)}</div><div class="k">Stations</div><div class="v">${num(d.counts.stations)}</div>
            <div class="k">Chat messages</div><div class="v">${num(d.counts.chat)}</div>
            <div class="k">Database</div><div class="v">${fmtBytes(d.db_size)} <span class="dim mono" style="font-size:11px">${esc(d.data_dir)}</span></div>
            <div class="k">Statistics cache</div><div class="v">${num(d.cache.hits)} hits · ${num(d.cache.misses)} computed</div></div></div>
        <div class="tile"><h3>🖥️ Machine</h3><div class="kv" style="margin-top:10px">
            <div class="k">Host</div><div class="v">${esc(i.hostname)} · ${esc((i.ips || []).join(', '))}</div><div class="k">System</div><div class="v">${esc(i.os)}</div>
            <div class="k">Load</div><div class="v">${i.load.join(' · ')} (${i.cpus} cores)</div>
            <div class="k">Memory</div><div class="v">${fmtBytes(memUsed)} of ${fmtBytes(i.mem_total)}</div>
            <div class="k">Disk</div><div class="v">${fmtBytes(i.disk_total - i.disk_free)} of ${fmtBytes(i.disk_total)}</div>
            <div class="k">Uptime</div><div class="v">${fmtDur(i.uptime, true)}</div></div>
            ${sa ? '<div class="actions"><button class="btn" onclick="power(\'reboot\')">🔄 Reboot</button><button class="btn danger" onclick="power(\'poweroff\')">⏻ Shut down</button></div>' : ''}</div>
        <div class="tile"><h3>⬆️ Updates</h3>
            <div id="updInfo" style="font-size:12.5px">Not checked yet.</div>
            <div class="n8-sub">☕ Java FRN server</div>
            <div id="javaInfo" style="font-size:12.5px">–</div>
            <div class="actions" style="justify-content:flex-start"><button class="btn primary" id="upgradeJava" disabled onclick="upgradeNow('java', this)">Upgrade Java now</button>
                <button class="btn" onclick="showUpdateLog(this)">📜 Update log</button></div>
            <pre class="term hidden" id="updLog" style="height:260px;margin-top:10px"></pre></div>
        </div>
        <div class="grid g2" style="margin-top:14px">
        <div class="tile"><h3>🧩 Services</h3><div class="subt">Status, autostart at boot and start, stop, restart – only the services released for this dashboard.</div>
            <div id="svcList"><div class="dim">loading …</div></div></div>
        <div class="tile"><h3>🔐 Permissions &amp; sudo <span id="permBadge"></span></h3>
            <div class="subt">Checks the service user, program and data permissions, systemd units and the sudo rules. <b>Fix</b> repairs what is wrong and checks again. Console: <span class="mono">sudo scripts/n8-admin.sh check-perms</span> / <span class="mono">fix-perms</span>.</div>
            <div id="permList"><div class="dim">checking …</div></div>
            <div class="actions" style="justify-content:flex-start"><button class="btn" onclick="loadPerms()">🔍 Check again</button><button class="btn primary" id="permFix" onclick="fixPerms(this)">🛠️ Fix</button></div>
            <pre class="term hidden" id="permOut" style="height:220px;margin-top:10px"></pre></div>
        </div>
        ${sa ? '<div class="grid g2" style="margin-top:14px" id="backupTiles"><div class="tile"><div class="empty">Loading …</div></div></div>' : ''}`;
    checkAllUpdates();
    loadServices(); loadPerms();
    if (sa) loadBackups();
}

// ---------------------------------------------------------------- services, permissions & sudo, update log (scripts/n8-admin.sh)
const SVC_STATE = { active: 'running', inactive: 'stopped', failed: 'failed', activating: 'starting', deactivating: 'stopping' };
function renderServices(d) {
    const el = $('svcList'); if (!el) return;
    if (!d.units.length) { el.innerHTML = '<div class="notice-box">Not set up yet – run once on the console: <span class="mono">sudo scripts/n8-admin.sh fix-perms</span></div>'; return; }
    const cls = a => a === 'active' ? 'ok' : a === 'failed' ? 'bad' : 'warn';
    const b = (u, a, icon, title) => u.actions.includes(a) ? `<button class="btn small" title="${title}" onclick="svcAction('${esc(u.unit)}','${a}',this)">${icon}</button>` : '';
    el.innerHTML = `<div class="tbl-wrap"><table class="tbl"><tbody>${d.units.map(u => `<tr>
        <td><span class="dot ${u.active === 'active' ? 'on' : 'off'}"></span> <b>${esc(u.label)}</b><div class="dim mono" style="font-size:11.5px">${esc(u.unit)}</div></td>
        <td><span class="pill ${cls(u.active)}">${esc(SVC_STATE[u.active] || u.active)}</span></td>
        <td>${u.actions.includes('enable') ? `<label class="switch" style="display:inline-block;vertical-align:middle" title="Autostart at boot"><input type="checkbox" ${u.enabled === 'enabled' ? 'checked' : ''} onchange="svcAction('${esc(u.unit)}', this.checked ? 'enable' : 'disable', this)"><span></span></label> <span class="dim">Autostart</span>` : `<span class="dim">${esc(u.enabled)}</span>`}</td>
        <td class="num" style="white-space:nowrap">${u.active === 'active' ? b(u, 'restart', '🔄', 'Restart') + b(u, 'stop', '⏹', 'Stop') : b(u, 'start', '▶', 'Start')}</td></tr>`).join('')}</tbody></table></div>`;
}
async function loadServices() { try { renderServices(await api('GET', '/api/admin/services')); } catch (e) { const el = $('svcList'); if (el) el.innerHTML = `<div class="notice-box">⚠️ ${esc(e.message)}</div>`; } }
async function svcAction(unit, action, el) {
    if (['stop', 'disable'].includes(action)) {
        const self = unit === 'frnadn.service';
        if (!await confirmBox({ title: `${action === 'stop' ? 'Stop' : 'Disable autostart of'} ${unit}?`, body: self && action === 'stop' ? 'The dashboard is gone afterwards – start it again on the console: sudo systemctl start frnadn' : 'Stations on this server may lose the connection.' }, action === 'stop' ? 'Stop' : 'Disable', 'danger')) { if (el && el.type === 'checkbox') el.checked = true; return; }
    }
    if (el) el.disabled = true;
    try { const r = await api('POST', `/api/admin/services/${encodeURIComponent(unit)}/${action}`, {}); toast('✓ ' + (r.message || action)); renderServices(r); }
    catch (e) { toast(e.message, true); loadServices(); }
}
async function loadPerms() {
    const el = $('permList'); if (!el) return;
    el.innerHTML = '<div class="dim">checking …</div>';
    let d; try { d = await api('GET', '/api/admin/perms'); } catch (e) { el.innerHTML = `<div class="notice-box">⚠️ ${esc(e.message)}</div>`; return; }
    renderPerms(d);
}
const PERM_AREA = { user: '👤 Service user', prog: '📦 Program', data: '💾 Data', systemd: '⚙️ systemd', sudo: '🛡️ sudo' };
function renderPerms(d) {
    const el = $('permList'), rows = d.checks || [];
    $('permBadge').innerHTML = !rows.length ? '<span class="pill warn">not checked</span>' : d.bad ? `<span class="pill bad">${d.bad} errors</span>` : '<span class="pill ok">all fine</span>';
    if (!rows.length) { el.innerHTML = `<div class="notice-box">${esc(d.message || '–')}</div>`; return; }
    const areas = [...new Set(rows.map(c => c.area))];
    el.innerHTML = `<div class="tbl-wrap" style="max-height:340px;overflow:auto"><table class="tbl"><tbody>${areas.map(a => rows.filter(c => c.area === a).map((c, i) =>
        `<tr><td style="width:130px">${i ? '' : `<b>${esc(PERM_AREA[a] || a)}</b>`}</td><td style="width:24px">${c.status === 'ok' ? '✅' : c.status === 'warn' ? '⚠️' : '❌'}</td>
         <td class="${c.status === 'bad' ? '' : 'dim'}" style="white-space:normal">${esc(c.text)}</td></tr>`).join('')).join('')}</tbody></table></div>`;
}
async function fixPerms(btn) {
    btn.disabled = true; const out = $('permOut'); out.classList.remove('hidden'); out.textContent = 'checking and fixing …';
    try { const r = await api('POST', '/api/admin/perms/fix', {}); out.textContent = r.message || ''; if (r.check) renderPerms(r.check); toast(r.ok ? 'Permissions are fine' : 'Not everything could be fixed', !r.ok); loadServices(); }
    catch (e) { out.textContent = e.message; toast(e.message, true); }
    btn.disabled = false;
}
async function showUpdateLog(btn) {
    const el = $('updLog'); el.classList.toggle('hidden'); if (el.classList.contains('hidden')) return;
    try { const d = await api('GET', '/api/admin/update-log'); el.textContent = d.log || 'No update from the dashboard yet.'; el.scrollTop = el.scrollHeight; }
    catch (e) { el.textContent = e.message; }
}

// ---------------------------------------------------------------- backup & restore (superadmin)
// Encrypted .frnbak with its own password (same format as the other N8schicht projects)
async function loadBackups(manifest) {
    const el = $('backupTiles'); if (!el) return;
    let d; try { d = await api('GET', '/api/admin/backups'); } catch (e) { el.innerHTML = `<div class="tile"><div class="notice-box">⚠️ ${esc(e.message)}</div></div>`; return; }
    const lr = d.last_restore;
    el.innerHTML = `<form class="tile" onsubmit="event.preventDefault(); createBackup(this)"><h3>💾 Backup</h3>
        <div class="subt">Everything in one encrypted file (.frnbak): settings, users, rooms, access lists, FRN accounts, statistics, chat,
        client logos, branding and the configuration of the FRN server. Choose a password – without it the backup cannot be opened, keep it in your password safe.
        The latest backups stay on the server.</div>
        <div class="row"><label>Password for the backup (min. 10 characters)</label><input type="password" name="pw" minlength="${d.min_password}" required autocomplete="new-password"></div>
        <div class="row"><label>Repeat</label><input type="password" name="pw2" required autocomplete="new-password"></div>
        <div class="actions"><button class="btn primary">💾 Create backup</button></div>
        ${d.backups.length ? `<div class="tbl-wrap" style="margin-top:10px"><table class="tbl"><thead><tr><th>Backup</th><th class="num">Size</th><th></th></tr></thead><tbody>
            ${d.backups.map(b => `<tr><td>${fmtDate(b.created)}<br><span class="dim mono" style="font-size:11px">${esc(b.name)}</span></td><td class="num">${fmtBytes(b.size)}</td>
            <td class="num"><a class="btn small" style="text-decoration:none" href="/api/admin/backups/${encodeURIComponent(b.name)}" download>⬇️ Download</a> <button type="button" class="btn small danger" onclick="deleteBackup('${esc(b.name)}')">✕</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No backups yet.</div>'}</form>
      <form class="tile" onsubmit="event.preventDefault(); restoreBackup(this)"><h3>♻️ Restore</h3>
        <div class="subt">Replaces database, branding and FRN configuration with the backup. The dashboard restarts, applies the backup and then
        restarts the FRN server – connected stations reconnect by themselves. The current state is kept in before-restore-… in the data directory.
        Afterwards you log in with the accounts from the backup.</div>
        ${lr ? `<div class="notice-box"><span>${lr.ok ? '✅ Last restore' : '⚠️ Last restore failed'}</span>: <span>${fmtDate(lr.applied)}</span> · <span class="mono">${esc(lr.ok ? ((lr.manifest || {}).host || '') + ' ' + ((lr.manifest || {}).version || '') : lr.error || '')}</span></div>` : ''}
        <div class="row"><label>Backup file (.frnbak)</label><input type="file" name="file" accept=".frnbak"></div>
        <div class="row"><label>Password of the backup</label><input type="password" name="pw" autocomplete="off"></div>
        <div id="restoreInfo">${manifest ? restoreInfo(manifest) : ''}</div>
        ${manifest ? '<div class="row"><label>Type RESTORE to confirm</label><input type="text" name="confirm" autocomplete="off"></div>' : ''}
        <div class="actions"><button type="button" class="btn" onclick="checkRestore(this.form)">🔍 Check</button>${manifest ? '<button class="btn danger">♻️ Restore now</button>' : ''}</div></form>`;
}
function restoreInfo(m) {
    const c = m.counts || {};
    return `<div class="kv" style="margin:8px 0"><div class="k">Backup</div><div class="v"><span class="mono">${esc([m.title, m.host, m.created_by].filter(Boolean).join(' · '))}</span> · ${fmtDate(m.created)}</div>
        <div class="k">Version</div><div class="v">adn-frn-server ${esc(m.version || '')}</div>
        <div class="k">Rooms</div><div class="v">${num(c.rooms)}</div><div class="k">Users</div><div class="v">${num(c.users)}</div>
        <div class="k">FRN accounts</div><div class="v">${num(c.accounts)}</div><div class="k">Stations</div><div class="v">${num(c.stations)}</div>
        <div class="k">Talks</div><div class="v">${num(c.talks)}</div></div>`;
}
async function createBackup(f) {
    if (f.pw.value !== f.pw2.value) { toast('The passwords differ.', true); return; }
    const b = f.querySelector('button.primary'); b.disabled = true;
    try { const r = await api('POST', '/api/admin/backups', { password: f.pw.value }); toast('Backup created'); await loadBackups();
          location.href = '/api/admin/backups/' + encodeURIComponent(r.name); }
    catch (e) { toast(e.message, true); } finally { b.disabled = false; }
}
async function deleteBackup(name) {
    if (!await confirmBox({ title: 'Delete this backup?', body: name }, 'Delete', 'danger')) return;
    try { await api('DELETE', '/api/admin/backups/' + encodeURIComponent(name)); loadBackups(); } catch (e) { toast(e.message, true); }
}
async function checkRestore(f) {
    const file = f.file.files[0];
    try {
        if (file) {
            const r = await fetch('/api/admin/restore/upload', { method: 'POST', body: file, credentials: 'same-origin', headers: { 'X-N8': '1', 'Content-Type': 'application/octet-stream' } });
            if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || j.detail || 'Upload failed'); }
        }
        const pw = f.pw.value;
        const d = await api('POST', '/api/admin/restore/check', { password: pw });
        S.admin.restorePw = pw;
        await loadBackups(d.manifest);
        const nf = $('backupTiles').querySelectorAll('form')[1]; nf.pw.value = pw;
    } catch (e) { toast(e.message, true); }
}
async function restoreBackup(f) {
    if (!await confirmBox({ title: 'Restore this backup now?', body: 'The dashboard restarts and replaces all data with the backup; the FRN server restarts too.' }, 'Restore', 'danger')) return;
    try {
        await api('POST', '/api/admin/restore', { password: f.pw.value, confirmation: (f.confirm || {}).value || '' });
        toast('Restoring – the dashboard restarts …');
        setTimeout(() => location.reload(), 6000);
    } catch (e) { toast(e.message, true); }
}

async function loadThemeAdmin() {
    const d = await api('GET', '/api/branding');
    S.admin.branding = d.theme; S.admin.saved = d.theme;
    renderThemeAdmin();
}
function renderThemeAdmin() {
    const t = S.admin.branding || N8Theme.DEFAULTS;
    const stamp = Date.now();
    $('admin-theme').innerHTML = `<div class="tile theme-card">
        <h3>🎨 Colours</h3>
        <p class="subt">Pick a colour profile, then change any colour you like – or build a completely own scheme. The whole page shows it right away; it only stays after <b>Save</b>. Same colour engine as HBlink4-FreeRadioID and N8-HotSpot.</p>
        ${N8Theme.editorHtml(t, 'themeEditor')}
    </div>
    <div class="tile theme-card">
        <h3>🖼️ Logo &amp; site icon</h3>
        <div class="theme-assets">
            <div class="theme-asset"><div class="theme-asset-preview"><img id="logoPreview" src="/branding/logo?v=${stamp}" alt="Current dashboard logo"></div><div>
                <b>Dashboard logo</b><p class="subt">PNG image, up to 2 MB. Shown in the header and sign-in dialog.</p>
                <input type="file" id="themeLogoFile" accept="image/png"><label class="theme-toggle"><input type="checkbox" id="resetLogo"> Use default logo</label>
            </div></div>
            <div class="theme-asset"><div class="theme-asset-preview"><img id="siteIconPreview" src="/branding/site-icon?v=${stamp}" alt="Current site icon"></div><div>
                <b>Site icon / favicon</b><p class="subt">PNG or ICO, up to 2 MB. Used in browser tabs and bookmarks.</p>
                <input type="file" id="themeSiteIconFile" accept="image/png,.ico,image/x-icon"><label class="theme-toggle"><input type="checkbox" id="resetSiteIcon"> Use default site icon</label>
            </div></div>
        </div>
        <div class="actions"><button class="btn" onclick="N8Theme.setEditor($('themeEditor'), N8Theme.DEFAULTS); applyTheme(themeFormValue())">↺ N8 standard</button>
            <button class="btn" onclick="loadThemeAdmin(); applyTheme(S.admin.saved)">Discard changes</button>
            <button class="btn primary" onclick="saveBranding(this)">💾 Save colours, logo &amp; icon</button></div>
        <div class="dim" id="themeInfo" role="status"></div>
    </div>
    <div class="tile theme-card" id="clientLogoAdmin"></div>`;
    N8Theme.bindEditor($('themeEditor'), t2 => applyTheme(t2));
    $('themeLogoFile').addEventListener('change', () => { $('resetLogo').checked = false; previewUpload('themeLogoFile', 'logoPreview'); });
    $('themeSiteIconFile').addEventListener('change', () => { $('resetSiteIcon').checked = false; previewUpload('themeSiteIconFile', 'siteIconPreview'); });
    $('resetLogo').addEventListener('change', () => { if ($('resetLogo').checked) { $('themeLogoFile').value = ''; $('logoPreview').src = '/static/adn-icon.svg'; } });
    $('resetSiteIcon').addEventListener('change', () => { if ($('resetSiteIcon').checked) { $('themeSiteIconFile').value = ''; $('siteIconPreview').src = '/static/adn-icon.svg'; } });
    renderClientLogoAdmin();
}
function previewUpload(fileId, imageId) {
    const file = $(fileId).files?.[0];
    if (file) $(imageId).src = URL.createObjectURL(file);
}
function themeFormValue() { return N8Theme.readEditor($('themeEditor')); }
function readFileData(file) {
    return new Promise((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(r.result); r.onerror = reject; r.readAsDataURL(file); });
}
async function saveBranding(btn) {
    const logo = $('themeLogoFile').files?.[0], icon = $('themeSiteIconFile').files?.[0];
    if ((logo && logo.size > 2 * 1024 * 1024) || (icon && icon.size > 2 * 1024 * 1024)) { toast('Logo and site icon must each be no larger than 2 MB.', true); return; }
    const payload = { theme: themeFormValue(), reset_logo: $('resetLogo').checked, reset_site_icon: $('resetSiteIcon').checked };
    try {
        if (logo) payload.logo = await readFileData(logo);
        if (icon) payload.site_icon = await readFileData(icon);
        if (btn) btn.disabled = true;
        const d = await api('POST', '/api/admin/branding', payload);
        S.admin.branding = d.theme; S.admin.saved = d.theme; applyTheme(d.theme);
        const stamp = Date.now();
        document.querySelectorAll('.brand img, .logo').forEach(x => x.src = '/branding/logo?v=' + stamp);
        document.querySelector('link[rel="icon"]').href = '/branding/site-icon?v=' + stamp;
        $('themeInfo').textContent = 'Theme and branding saved for all visitors.';
        toast('Theme saved.'); await loadThemeAdmin();
    } catch (e) { $('themeInfo').textContent = e.message; toast(e.message, true); }
    finally { if (btn) btn.disabled = false; }
}

async function loadLinksAdmin() {
    const d = await api('GET', '/api/admin/links');
    S.admin.linkItems = (d.links || []).map(x => ({ ...x }));
    S.admin.linkSettings = { enabled: d.enabled, label: d.label, style: d.style };
    renderLinksAdmin();
}
function renderLinksAdmin() {
    const s = S.admin.linkSettings || { enabled: true, label: '🔗 Links', style: 'menu' };
    $('admin-links').innerHTML = `<div class="tile links-editor">
        <h3>🔗 Dashboard link menu</h3>
        <p class="subt">Edit the link menu or button row. Website favicons are fetched securely and cached in the SQLite database.</p>
        <div class="links-editor-options">
            <label class="theme-toggle"><input type="checkbox" id="linksEnabled" ${s.enabled ? 'checked' : ''}> Show links on the dashboard</label>
            <label>Menu button text<input type="text" id="linksLabel" maxlength="30" value="${esc(s.label)}"></label>
            <label>Display<select id="linksStyle"><option value="menu" ${s.style === 'menu' ? 'selected' : ''}>Dropdown menu</option><option value="bar" ${s.style === 'bar' ? 'selected' : ''}>Row of buttons</option></select></label>
        </div>
        <div id="linkRows">${S.admin.linkItems.map((x, i) => linkEditorRow(x, i)).join('') || '<div class="empty">No links added.</div>'}</div>
        <div class="actions"><button class="btn" data-link-add>＋ Add link</button><button class="btn" onclick="loadLinksAdmin()">Reset changes</button><button class="btn" onclick="saveLinksAdmin(this, true)">Save &amp; refresh site icons</button><button class="btn primary" onclick="saveLinksAdmin(this)">Save links</button></div>
        <div class="dim" id="linksInfo" role="status"></div>
    </div>`;
    $('admin-links').querySelectorAll('.link-row-preview img').forEach(bindSiteIcon);
}
function linkEditorRow(x, i) {
    return `<div class="link-editor-row" data-link-row="${i}">
        <label>Name<input type="text" data-field="label" maxlength="50" required value="${esc(x.label || '')}"></label>
        <label>Address<input type="text" data-field="url" maxlength="500" placeholder="https://example.org" required value="${esc(x.url || '')}"></label>
        <label>Fallback icon<input type="text" data-field="icon" maxlength="8" value="${esc(x.icon || '🔗')}" title="Emoji used when the website has no cached icon"></label>
        <div class="link-row-options"><label><input type="checkbox" data-field="site_icon" ${x.site_icon !== false ? 'checked' : ''}> Site icon</label><label><input type="checkbox" data-field="new_tab" ${x.new_tab !== false ? 'checked' : ''}> New tab</label></div>
        <div class="link-row-actions"><span class="link-row-preview">${linkSiteIcon(x)}</span><button class="btn small" data-link-up title="Move up">↑</button><button class="btn small" data-link-down title="Move down">↓</button><button class="btn small danger" data-link-remove title="Remove">×</button></div>
    </div>`;
}
$('admin-links').addEventListener('click', e => {
    if (e.target.closest('[data-link-add], [data-link-remove], [data-link-up], [data-link-down]')) syncLinkEditor();
    if (e.target.closest('[data-link-add]')) {
        if (S.admin.linkItems.length >= 20) { toast('You can add up to 20 links.', true); return; }
        S.admin.linkItems.push({ label: '', url: '', icon: '🔗', site_icon: true, new_tab: true }); renderLinksAdmin(); return;
    }
    const row = e.target.closest('[data-link-row]');
    if (!row) return;
    const i = Number(row.dataset.linkRow);
    if (e.target.closest('[data-link-remove]')) S.admin.linkItems.splice(i, 1);
    else if (e.target.closest('[data-link-up]') && i > 0) [S.admin.linkItems[i - 1], S.admin.linkItems[i]] = [S.admin.linkItems[i], S.admin.linkItems[i - 1]];
    else if (e.target.closest('[data-link-down]') && i < S.admin.linkItems.length - 1) [S.admin.linkItems[i + 1], S.admin.linkItems[i]] = [S.admin.linkItems[i], S.admin.linkItems[i + 1]];
    else return;
    renderLinksAdmin();
});
function syncLinkEditor() {
    const root = $('linkRows');
    if (!root) return;
    S.admin.linkItems = [...root.querySelectorAll('[data-link-row]')].map(row => ({
        label: row.querySelector('[data-field="label"]').value.trim(), url: row.querySelector('[data-field="url"]').value.trim(),
        icon: row.querySelector('[data-field="icon"]').value.trim(), site_icon: row.querySelector('[data-field="site_icon"]').checked,
        new_tab: row.querySelector('[data-field="new_tab"]').checked
    }));
}
async function saveLinksAdmin(btn, refreshIcons = false) {
    syncLinkEditor();
    const items = S.admin.linkItems;
    if (btn) btn.disabled = true;
    try {
        const d = await api('POST', '/api/admin/links', { enabled: $('linksEnabled').checked, label: $('linksLabel').value,
            style: $('linksStyle').value, items, refresh_icons: refreshIcons });
        S.admin.linkItems = (d.links || []).map(x => ({ ...x }));
        S.admin.linkSettings = { enabled: d.enabled, label: d.label, style: d.style };
        renderLinksAdmin(); await loadPublicLinks();
        $('linksInfo').textContent = refreshIcons ? 'Links saved and site icons refreshed into SQLite.' : 'Links saved. Site icons are cached in SQLite.';
        toast(refreshIcons ? 'Links saved and site icons refreshed.' : 'Links saved.');
    } catch (e) { $('linksInfo').textContent = e.message; toast(e.message, true); }
    finally { if (btn) btn.disabled = false; }
}

async function loadImportAdmin() {
    $('admin-import').innerHTML = `<div class="tile import-card">
        <h3>📥 Import legacy server.properties</h3>
        <p class="subt">Optional: import settings from the previous FRN installation into this fresh installation. Only supported properties and room definitions are transferred. The old database, Java JAR, ACL lists and password XML files are not copied.</p>
        <div class="import-drop">
            <label for="propertiesFile">Select the old server.properties file</label>
            <input type="file" id="propertiesFile" accept=".properties,text/plain">
            <button class="btn primary" onclick="importProperties()">Import server.properties</button>
        </div>
        <div id="importInfo" class="dim" role="status" style="margin-top:12px"></div>
    </div>`;
}
// checkAllUpdates / upgradeNow: simple fallbacks – static/extras.js replaces them with the detailed version
async function checkAllUpdates(btn) {
    if (btn) btn.disabled = true;
    try {
        const r = await api('POST', '/api/admin/updates/check', {});
        const gh = r.github || {}, java = r.java || {};
        $('updInfo').innerHTML = `GitHub: ${gh.ok ? (gh.update ? '<b>update available</b>' : 'up to date') : 'check failed: ' + esc(gh.error || 'unknown')} · Java FRN: ${java.ok ? (java.update ? '<b>update available</b>' : 'up to date') : 'check failed: ' + esc(java.error || 'unknown')}`;
        $('upgradeJava').disabled = !java.update;
        $('upgradeGit').disabled = !gh.update;
    } catch(e) { $('updInfo').textContent = e.message; }
    finally { if (btn) btn.disabled = false; }
}
async function upgradeNow(target, btn) {
    const title = target === 'java' ? 'Upgrade Java FRN server?' : 'Upgrade dashboard from GitHub?';
    const body = target === 'java' ? 'The current FRN_Server.jar will be replaced and the Java server restarted.' : 'The dashboard checkout will be fast-forwarded. The FRN server restarts to refresh its live status, then restart the dashboard to load the update.';
    if (!await confirmBox({title, body}, 'Upgrade')) return;
    btn.disabled = true;
    try {
        await api('POST', '/api/admin/updates/upgrade', {target});
        toast('Upgrade completed.');
        await checkAllUpdates();
    } catch(e) { toast(e.message, true); btn.disabled = false; }
}
async function importProperties() {
    const file = $('propertiesFile')?.files?.[0];
    if (!file) { toast('Select a server.properties file first.', true); return; }
    if (!await confirmBox({title:'Import server.properties?', body:'Supported settings will be imported into the dashboard database. The current server.properties is backed up first. Room-specific ACLs and other XML files are not modified.'}, 'Import')) return;
    try {
        const text = await file.text();
        const r = await api('POST', '/api/admin/server/properties/import', {text});
        $('importInfo').textContent = 'Imported settings: ' + r.imported.join(', ') + ' · Rooms: ' + (r.rooms || []).join(', ') + (r.backup ? ' · Backup: ' + r.backup : '');
        toast('Configuration imported. Restart the FRN server to apply it.');
    } catch(e) { $('importInfo').textContent = e.message; toast(e.message, true); }
}


async function restartApp() {
    if (!await confirmBox({ title: 'Restart the dashboard?', body: 'Only frn_adn starts again (a few seconds); the FRN server keeps running.' }, 'Restart')) return;
    try { await api('POST', '/api/admin/restart', {}); toast('Restarting …'); setTimeout(() => location.reload(), 6000); } catch (e) { toast(e.message, true); }
}
async function power(a) {
    if (!await confirmBox({ title: a === 'reboot' ? 'Reboot the machine?' : 'Shut down the machine?', body: a === 'reboot' ? 'The FRN server is back after about a minute.' : 'The FRN server stays off until the machine is started again.' }, a === 'reboot' ? 'Reboot' : 'Shut down', 'danger')) return;
    try { await api('POST', '/api/admin/power', { action: a }); toast(a === 'reboot' ? 'Rebooting …' : 'Shutting down …'); } catch (e) { toast(e.message, true); }
}

// public FRN error log of freeradionetwork.de
async function loadFrnErrorlog(force) {
    const box = $('frnElList'); if (!box) return;
    let d; try { d = await api('GET', '/api/admin/frn-errorlog' + (force ? '?force=1' : '')); } catch (e) { box.innerHTML = `<div class="notice-box">⚠️ ${esc(e.message)}</div>`; return; }
    const n = d.mine.reduce((a, g) => a + g.count, 0);
    $('frnElBadge').innerHTML = d.error ? '<span class="badge warn">not reachable</span>' : n ? `<span class="badge err">${n} ${N8Kit.i18n.t('entries about this server')}</span>` : '<span class="badge ok">nothing about this server</span>';
    const when = (ts) => ts.slice(8, 10) + '.' + ts.slice(5, 7) + '. ' + ts.slice(11, 16);
    const row = (g) => `<tr><td style="white-space:nowrap">${esc(when(g.ts))}${g.count > 1 ? `<div class="dim" style="font-size:12px">${g.count}× ${N8Kit.i18n.t('since')} ${esc(g.first.slice(11, 16))}</div>` : ''}</td>
        <td>${g.kind === 'Client' ? '👤 Client' : '🖥️ Server'}<div class="dim mono" style="font-size:12px">${esc(g.id)}${g.name ? ', ' + esc(g.name) : ''}</div></td>
        <td style="white-space:normal;min-width:320px"><b>${esc(g.message)}</b>${g.hint ? `<div style="margin-top:3px">💡 ${esc(N8Kit.i18n.t(g.hint))}</div>` : g.hint_en ? `<div class="dim">${esc(g.hint_en)}</div>` : ''}</td></tr>`;
    box.innerHTML = (d.error ? `<div class="notice-box">⚠️ ${esc(d.error)}</div>` : '')
        + (d.mine.length ? `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Time</th><th>Who</th><th>Message</th></tr></thead><tbody>${d.mine.map(row).join('')}</tbody></table></div>`
            : d.error ? '' : `<div class="dim">✅ ${N8Kit.i18n.t('No entries about this server in the last entries of the log')} (${d.total}${d.span ? ', ' + esc(d.span[0].slice(11, 16)) + '–' + esc(d.span[1].slice(11, 16)) : ''}).</div>`)
        + `<div class="dim" style="font-size:12px;margin-top:8px">${N8Kit.i18n.t('Server')} ${esc(d.scope.servers.join(', ') || '–')} · ${N8Kit.i18n.t('Callsigns')} ${esc(d.scope.callsigns.join(', ') || '–')}${d.others && d.others.length ? ` · ${N8Kit.i18n.t('other stations in the log')}: ${d.others.slice(0, 6).map(g => esc(g.id)).join(', ')}` : ''}</div>`;
}

// logs
async function loadLogs() {
    const [d, v] = await Promise.all([api('GET', '/api/admin/logs'), api('GET', '/api/admin/visits?limit=100')]);
    S.admin.logs = d.entries;
    $('admin-logs').innerHTML = `<div class="tile" style="margin-bottom:14px"><h3>📋 Public FRN error log <span id="frnElBadge"></span></h3>
        <div class="subt">For problems always look here first: the FRN SystemManager of freeradionetwork.de writes every refused login of servers and clients there (wrong FRN password, multiple connection, port not reachable …) – the reason the FRN server itself does not tell. Shown are entries about this server address, the owner's callsign and stations refused here. New entries also appear in the events below.</div>
        <div id="frnElList"><div class="dim">loading …</div></div>
        <div class="actions" style="justify-content:flex-start"><button class="btn small" onclick="loadFrnErrorlog(true)">🔄 Reload</button>
            <a class="btn small" href="http://log.freeradionetwork.de:60080/error_log.php" target="_blank" rel="noopener">📋 Open the complete error log ↗</a></div></div>
        <div class="tile"><h3>📜 Events (live)</h3><div class="term logview" id="logView"></div>
        <div class="actions" style="justify-content:flex-start"><button class="btn" onclick="loadJournal('frnlog')">🛰️ server.log of the FRN server</button>
            <button class="btn" onclick="loadJournal('frn-server')">Journal frn-server</button><button class="btn" onclick="loadJournal('frnadn')">Journal frnadn</button></div>
        <pre class="term hidden" id="jView" style="height:360px"></pre></div>
        <div class="tile" style="margin-top:14px"><h3>🚪 Logins</h3><div class="subt">With e-mail and address – only visible to admins.</div><div class="tbl-wrap" style="max-height:460px;overflow:auto"><table class="tbl">
        <thead><tr><th>Login</th><th>Station</th><th>Room</th><th class="hide-sm">E-mail</th><th class="hide-sm">Address</th><th class="num">Online</th></tr></thead><tbody>
        ${v.entries.map(x => `<tr><td>${fmtDate(x.login_ts)}</td><td><b>${esc(x.callsign)}</b> <span class="dim">${esc(x.name)}</span></td><td>${esc(x.net)}</td>
            <td class="hide-sm mono" style="font-size:12px">${esc(x.email)}</td><td class="hide-sm mono" style="font-size:12px">${esc(x.peer)}</td>
            <td class="num">${x.logout_ts ? fmtDur(x.logout_ts - x.login_ts, true) : '<span class="pill ok">online</span>'}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">No logins recorded yet.</td></tr>'}
        </tbody></table></div></div>`;
    renderLogs();
    loadFrnErrorlog();
}
function logLine(e) {
    const cls = { denied: 'e', login: 'g', logout: 't', config: 'w', error: 'e', frnlog: 'w' }[e.kind] || '';
    return `<div class="${cls}"><span class="t">${fmtTime(e.ts)}</span> ${esc(e.text)}</div>`;
}
function renderLogs() { const v = $('logView'); if (!v) return; v.innerHTML = S.admin.logs.slice(-400).map(logLine).join('') || '<div class="t">No events yet.</div>'; v.scrollTop = v.scrollHeight; }
function appendLog(e) {
    const v = $('logView'); if (!v) return;
    const atEnd = v.scrollTop + v.clientHeight >= v.scrollHeight - 30;
    v.insertAdjacentHTML('beforeend', logLine(e)); if (atEnd) v.scrollTop = v.scrollHeight;
}
async function loadJournal(what) {
    const j = $('jView'); j.classList.remove('hidden'); j.textContent = 'Loading …';
    try { j.textContent = (await api('GET', what === 'frnlog' ? '/api/admin/frnlog?lines=400' : `/api/admin/journal?lines=300&unit=${what}`)).text; j.scrollTop = j.scrollHeight; } catch (e) { j.textContent = e.message; }
}

// sessions & audit
async function loadAudit() {
    const [s, a] = await Promise.all([api('GET', '/api/admin/sessions'), api('GET', '/api/admin/audit')]);
    const lbl = { login: '🔓 Login', login_failed: '⛔ Login failed', settings_changed: '⚙️ Dashboard settings', frn_config: '🛰️ server.json', service: '🔄 Service',
        user_created: '➕ User', user_changed: '✏️ User', user_deleted: '🗑️ User', password_changed: '🔑 Password', reboot: '🔄 Reboot', poweroff: '⏻ Shutdown',
        session_revoked: '🚫 Session', update: '⬆️ Update', frn_start: '▶ FRN server', frn_stop: '⏹ FRN server', frn_restart: '🔄 FRN server',
        frn_update: '⬆️ FRN update', frn_password_request: '📧 FRN password requested', rooms: '🏠 Rooms', frn_account: '🔑 FRN account', app_restart: '♻️ Dashboard',
        api_token_created: '🔌 API token', api_token_revoked: '🔌 API token revoked', acl: '🚦 Lists', backup_created: '💾 Backup created', backup_downloaded: '💾 Backup downloaded', backup_deleted: '💾 Backup deleted', backup_restore: '♻️ Restore started', backup_restored: '♻️ Backup restored' };
    $('admin-audit').innerHTML = `<div class="grid g2">
        <div class="tile"><h3>🔑 Active sessions</h3><div class="tbl-wrap"><table class="tbl"><thead><tr><th>User</th><th>IP</th><th class="hide-sm">Since</th><th></th></tr></thead><tbody>
        ${s.sessions.map(x => `<tr><td>${esc(x.username)}</td><td class="mono">${esc(x.ip)}</td><td class="hide-sm">${fmtDate(x.created_at)}</td><td class="num"><button class="btn small" onclick="revokeS('${x.id}')">End</button></td></tr>`).join('')}
        </tbody></table></div></div>
        <div class="tile"><h3>📜 Change log</h3><div class="tbl-wrap" style="max-height:520px;overflow:auto"><table class="tbl"><thead><tr><th>Time</th><th>What</th><th>Who</th><th class="hide-sm">Details</th></tr></thead><tbody>
        ${a.entries.map(x => `<tr><td>${fmtDate(x.ts)}</td><td>${lbl[x.action] || esc(x.action)}</td><td>${esc(x.username)}</td><td class="hide-sm dim" style="white-space:normal;max-width:320px">${esc(x.detail)}${x.ip ? ` · ${esc(x.ip)}` : ''}</td></tr>`).join('')}
        </tbody></table></div></div></div>`;
}
async function revokeS(id) { try { await api('DELETE', `/api/admin/sessions/${id}`); loadAudit(); } catch (e) { toast(e.message, true); } }

boot();

// collapsible section headers (state kept per browser, like on the DMR dashboard)
(function () {
    const KEY = 'frnadn.collapsed';
    let st = {}; try { st = JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) {}
    const apply = k => { const on = !!st[k]; document.querySelectorAll(`[data-section="${k}"]`).forEach(h => h.classList.toggle('collapsed', on));
        document.querySelectorAll(`[data-body="${k}"]`).forEach(b => b.classList.toggle('hidden', on)); };
    document.querySelectorAll('.collapsible[data-section]').forEach(h => { apply(h.dataset.section);
        h.addEventListener('click', () => { st[h.dataset.section] = !st[h.dataset.section]; try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} apply(h.dataset.section); }); });
})();

// Desktop live page: last heard and rooms fill the rest of the window (same height, both scroll inside),
// so on air, the lists and everything above fit on one screen. Recomputed when on air or the window changes.
(function () {
    const page = $('tab-live'), box = page && page.querySelector('.lv-lh');
    if (!box || !window.ResizeObserver) return;
    const fit = () => {
        if (!matchMedia('(min-width: 1101px)').matches || page.classList.contains('hidden')) return;
        const top = box.getBoundingClientRect().top + scrollY;
        page.style.setProperty('--lv-h', Math.max(420, Math.min(1000, innerHeight - top - 16)) + 'px');
    };
    new ResizeObserver(fit).observe(page.querySelector('.lv-onair'));
    addEventListener('resize', fit);
    setTimeout(fit, 300);
})();
