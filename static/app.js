/* frn_adn web interface. No build step, no external libraries. */
'use strict';

const $ = id => document.getElementById(id);
const S = { info: null, me: null, live: null, ws: null, wsOk: false, services: {}, lhRoom: 'all', tab: 'live',
            stats: { range: 'today', metric: 'duration', data: null, slots: {} },
            admin: { tab: 'server', frn: null, room: null, logs: [] }, chat: { room: 'all', entries: [] } };

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
function avatar(call, cls) { return `<span class="avatar ${cls || ''}" style="background:${avatarColor(call)}">${initials(call)}</span>`; }
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
function toggleLinks(ev) {
    ev.stopPropagation();
    const menu = $('linksMenu'); menu.classList.toggle('open');
    if (menu.dataset.bound !== '1') { menu.dataset.bound = '1'; document.addEventListener('click', e => { if (!menu.contains(e.target)) menu.classList.remove('open'); }); }
}
function applyAccent(value) {
    if (!/^#[0-9a-f]{6}$/i.test(value || '')) return;
    document.documentElement.style.setProperty('--user-accent', value);
    try { localStorage.setItem('frnadn-accent', value); } catch(e) {}
}
try { applyAccent(localStorage.getItem('frnadn-accent') || '#5ac8fa'); } catch(e) {}
function isAdmin() { return S.me && (S.me.role === 'admin' || S.me.role === 'superadmin'); }
function bindSeg(id, fn) {
    $(id).addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; document.querySelectorAll(`#${id} button`).forEach(x => x.classList.toggle('active', x === b)); fn(b.dataset.v); });
}

// ---------------------------------------------------------------- boot
async function boot() {
    try {
        const info = await api('GET', '/api/info');
        S.info = info; S.me = info.user || null;
        if (info.login_required && !S.me) { renderHeader(); if (!info.setup_needed) openLogin(true); return; }
        renderHeader(); renderUser();
        $('ver').textContent = 'v' + info.version;
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
    if (!S.me) { el.innerHTML = '<button class="btn primary" onclick="openLogin()">🔐 Login</button>'; return; }
    el.innerHTML = `<button class="btn" onclick="userMenu(event)">👤 ${esc(S.me.display_name || S.me.username)} ▾</button>`;
}
function userMenu(ev) {
    ev.stopPropagation(); closeModal();
    const r = ev.target.getBoundingClientRect();
    const m = document.createElement('div');
    m.className = 'glass';
    m.style.cssText = `position:fixed;top:${r.bottom + 8}px;right:${Math.max(8, innerWidth - r.right)}px;z-index:300;border-radius:16px;padding:6px;min-width:200px;background:rgba(22,28,48,.95)`;
    m.innerHTML = `<div style="padding:8px 12px" class="dim">${esc(S.me.username)} · ${esc(S.me.role)}</div>
        ${isAdmin() ? '<button class="btn" style="width:100%;border-radius:10px;margin:2px 0" onclick="showTab(\'admin\')">⚙️ Admin</button>' : ''}
        <button class="btn" style="width:100%;border-radius:10px;margin:2px 0" onclick="openAccount()">🔑 My account</button>
        <button class="btn" style="width:100%;border-radius:10px;margin:2px 0" onclick="logout()">🚪 Log out</button>`;
    document.body.appendChild(m);
    setTimeout(() => document.addEventListener('click', () => m.remove(), { once: true }), 0);
}

// ---------------------------------------------------------------- modals
function modal(html, locked, wide) {
    $('modalRoot').innerHTML = `<div class="overlay" id="ov"><div class="modal ${wide ? 'wide' : ''}">${html}</div></div>`;
    if (!locked) $('ov').addEventListener('click', e => { if (e.target.id === 'ov') closeModal(); });
    if (locked) $('ov').dataset.locked = '1';
}
function closeModal() { $('modalRoot').innerHTML = ''; }
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('ov')?.dataset.locked) closeModal(); });
function openLogin(locked) {
    modal(`<img class="logo" src="/static/adn-icon.svg" alt="">
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
        case 'log': S.admin.logs.push(ev.entry); if (S.admin.logs.length > 600) S.admin.logs.shift(); appendLog(ev.entry); break;
    }
}

// ---------------------------------------------------------------- live
function rooms() { return (S.live && S.live.rooms) || []; }
function renderLive() { renderChips(); renderOnAir(); renderRooms(); renderLHFilter(); renderLH(); renderFeed(); }
function renderChips() {
    const set = (id, cls, text) => { const e = $(id); e.className = 'chip ' + cls; e.textContent = text; };
    set('chipLive', S.wsOk ? 'ok' : 'bad', S.wsOk ? '✓ Live data' : '✕ Live data');
    const st = S.live && S.live.server;
    if (!st) set('chipServer', '', '🛰️ FRN server');
    else set('chipServer', st.running ? 'ok' : 'bad', st.running ? '✓ FRN server' : st.error ? '✕ FRN server: error' : st.service === 'active' ? '… FRN server starting' : '✕ FRN server stopped');
    const online = rooms().reduce((a, r) => a + r.clients.filter(c => !c.parrot).length, 0);
    set('chipOnline', online ? 'info' : '', `👥 ${online} online`);
    const talkers = rooms().map(r => r.talking).filter(Boolean);
    set('chipAir', talkers.length ? 'ok' : '', talkers.length ? `🎙️ ${talkers.map(t => t.callsign || '?').join(', ')}` : '💤 Quiet');
    $('sOnline').textContent = online;
}
const CL_ICON = { 0: ['🔗', 'Crosslink'], 1: ['📻', 'Gateway (radio)'], 2: ['💻', 'PC only'] };
function clIcon(c) { if (c.parrot) return '<span title="Parrot – echo test">🦜</span>'; const x = CL_ICON[Number(c.client)] || CL_ICON[2]; return `<span title="${x[1]}">${x[0]}</span>`; }
function renderOnAir() {
    const cards = rooms().filter(r => r.talking).map(r => ({ r, t: r.talking }));
    if (!cards.length) {
        const last = S.live && S.live.last_heard[0];
        $('onair').innerHTML = `<div class="slot idle"><div class="lbl"><span>On air</span><span class="pill">Quiet</span></div>
            <div class="idle-text">${last ? `Last: <b style="color:var(--text)">${esc(last.callsign || '?')}</b> in ${esc(last.room)} · ${fmtDur(last.duration)} · ${ago(last.ts + last.duration)}` : 'Nobody is talking right now'}</div></div>`;
        return;
    }
    $('onair').innerHTML = cards.map(({ r, t }) => `<div class="slot active frn"><div class="lbl"><span>🏠 ${esc(r.name)}</span><span class="pill air">ON AIR</span></div>
        <div class="who ${t.parrot ? '' : 'station-link'}" ${t.parrot ? '' : `onclick="openStation('${esc(t.callsign)}')"`}>${avatar(t.callsign || '?')}
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
    $('rooms').innerHTML = rs.map(r => {
        const n = r.clients.filter(c => !c.parrot).length;
        const rows = r.clients.map(c => `<div class="st-row ${c.talking ? 'talk' : ''} ${c.parrot ? '' : 'station-link'}" ${c.parrot ? '' : `onclick="openStation('${esc(c.callsign)}')"`}>
            ${c.parrot ? '<span class="avatar sm" style="background:linear-gradient(135deg,#30d158,#0a84ff)">🦜</span>' : avatar(c.callsign, 'sm')}<div class="c"><b>${esc(c.callsign)}</b>${c.talking ? '<span class="mic"></span>' : ''}${c.muted ? ' <span title="muted">🔇</span>' : ''}${c.access === 'OWNER' || c.access === 'NETOWNER' ? ' <span title="Owner">👑</span>' : c.access === 'ADMIN' ? ' <span title="Admin">🛡️</span>' : ''}
            <small>${esc(c.name)}${c.name && (c.city || c.country) ? ' · ' : ''}${flag(c.country)} ${esc(place(c))}</small></div>
            <div class="r"><span class="band" title="${esc(c.band)}">${clIcon(c)} <span class="band-txt">${esc((c.band || '').length > 22 ? c.band.slice(0, 21) + '…' : c.band || '')}</span></span>${c.since ? `<div data-since="${c.since}">${since(c.since)}</div>` : ''}</div>
</div>`).join('');
        return `<div class="room ${r.talking ? 'live' : ''}"><div class="room-head"><span class="dot ${S.live.server && S.live.server.running ? 'on' : 'off'}"></span><h3>${r.hidden ? '🔒 ' : ''}${esc(r.name)}</h3>
            ${r.parrot ? '<span class="pill" title="Parrot echo test is on">🦜</span>' : ''}
            <span class="room-count ${n ? '' : 'zero'}">${n}</span></div>
            ${rows || '<div class="none">Nobody in this room</div>'}</div>`;
    }).join('');
}
function renderLHFilter() {
    const names = rooms().map(r => r.name);
    if (S.lhRoom !== 'all' && !names.includes(S.lhRoom)) S.lhRoom = 'all';
    $('lhFilter').innerHTML = [['all', 'All'], ...names.slice(0, 5).map(n => [n, n])].map(([v, l]) => `<button data-v="${esc(v)}" class="${S.lhRoom === v ? 'active' : ''}">${esc(l)}</button>`).join('');
}
$('lhFilter').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; S.lhRoom = b.dataset.v; renderLHFilter(); renderLH(); });
function renderLH(newId) {
    if (!S.live) return;
    let rows = S.live.last_heard || [];
    if (S.lhRoom !== 'all') rows = rows.filter(e => e.room === S.lhRoom);
    rows = rows.slice(0, 20);
    if (!rows.length) { $('lhBody').innerHTML = '<tr><td colspan="5" class="empty">Nothing heard yet.</td></tr>'; return; }
    $('lhBody').innerHTML = rows.map(e => `<tr class="${e.id === newId ? 'new' : ''}"><td>${fmtTime(e.ts)}</td>
        <td>${e.callsign ? `<span class="who station-link" onclick="openStation('${esc(e.callsign)}')">${avatar(e.callsign, 'sm')}<span><b>${esc(e.callsign)}</b> ${flag(e.country)}<small>${esc(e.name || place(e))}</small></span></span>` : '<span class="dim">unknown station</span>'}</td>
        <td><span class="pill tg">${esc(e.room)}</span></td><td class="num">${fmtDur(e.duration)}</td><td class="hide-sm">${bandHtml(e)}</td></tr>`).join('');
}
function renderFeed(flash) {
    const v = (S.live && S.live.visits) || [];
    $('feed').innerHTML = v.length ? v.slice(0, 14).map((e, i) => `<div class="ev ${flash && i === 0 ? 'new' : ''}"><span class="t">${fmtTime(e.ts).slice(0, 5)}</span>
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
        <div class="st-head">${avatar(s.callsign, 'xl')}<div style="min-width:0">
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
    $('dirBody').innerHTML = rows.slice(0, DIR.limit).map(r => `<tr><td><span class="who station-link" onclick="openStation('${esc(r.callsign)}')">${avatar(r.callsign, 'sm')}<span><b>${esc(r.callsign)}</b><small>${esc(r.name)}</small></span></span></td>
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
const ADMIN_TABS = ['settings', 'rooms', 'lists', 'accounts', 'users', 'system', 'logs', 'audit'];
function showAdmin(a) {
    if (!ADMIN_TABS.includes(a)) a = 'settings';
    S.admin.tab = a;
    document.querySelectorAll('#adminTabs button').forEach(b => b.classList.toggle('active', b.dataset.a === a));
    ADMIN_TABS.forEach(x => $('admin-' + x).classList.toggle('hidden', x !== a));
    ({ settings: loadSettings, rooms: loadRoomsAdmin, lists: loadLists, accounts: loadAccounts, users: loadUsers,
       system: loadSystem, logs: loadLogs, audit: loadAudit })[a]().catch(e => $('admin-' + a).innerHTML = `<div class="tile"><div class="notice-box">⚠️ ${esc(e.message)}</div></div>`);
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
        ${st.error ? `<div class="notice-box" style="margin-top:10px">⚠️ ${esc(st.error)}</div>` : ''}`;
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
            <button class="btn small" onclick="showProps()">🧾 Show server.properties</button><span class="dim" id="updInfo" style="font-size:12.5px"></span></div></div>
        <div class="tiles">${d.sections.map(sec => `
        <form class="tile" data-sec="${sec.id}" onsubmit="event.preventDefault(); saveSettings(this)"><h3>${esc(sec.title)}</h3><div class="subt">${esc(sec.subtitle)}</div>
            ${sec.id === 'sysman' ? '<div class="notice-box">🌐 Registered at the SystemManager the server is listed in the FRN system and checks the logins there. The SystemManager tests that address and port are reachable from the internet – set up port forwarding first.</div>' : ''}
            ${sec.fields.map(fieldHtml).join('')}<div class="actions"><button class="btn primary">Save</button></div></form>`).join('')}</div>`;
}
async function saveSettings(form) {
    try {
        const r = await api('POST', '/api/admin/settings', { changes: formValues(form) });
        toast(r.changed.length ? `Saved (${r.changed.length})` : 'No changes'); setRestart(r.restart_needed);
        const i = await api('GET', '/api/info'); S.info = { ...S.info, ...i }; renderHeader();
    } catch (e) { toast(e.message, true); }
}
async function checkUpdate(btn) {
    btn.disabled = true; $('updInfo').textContent = 'checking freeradionetwork.de …';
    try {
        const r = await api('GET', '/api/admin/server/update');
        if (!r.ok) $('updInfo').textContent = `not reachable: ${r.error}`;
        else if (r.update) $('updInfo').innerHTML = `Version <b>${esc(r.latest.version)}</b> (${esc(r.latest.build)}) is available – installed ${esc(r.installed ? r.installed.version : '?')}. <button class="btn small primary" onclick="installUpdate(this)">Install</button>`;
        else $('updInfo').textContent = `✓ up to date (${r.installed ? r.installed.version + ', ' + r.installed.build : '?'})`;
    } catch (e) { $('updInfo').textContent = e.message; }
    btn.disabled = false;
}
async function installUpdate(btn) {
    if (!await confirmBox({ title: 'Install the update?', body: 'FRN_Server.zip is loaded from freeradionetwork.de, FRN_Server.jar replaced and the FRN server restarted.' }, 'Install')) return;
    btn.disabled = true; $('updInfo').textContent = 'downloading …';
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

// admin / mute / block / access lists – kept by the FRN server itself
async function loadLists() {
    const d = await api('GET', '/api/admin/acl');
    const lbl = { AdminList: '🛡️ Admins', MuteList: '🔇 Muted', BlockList: '⛔ Blocked', AccessList: '🔐 Access list' };
    $('admin-lists').innerHTML = `<div class="tile"><h3>🛡️ Admins, muted, blocked and access lists</h3>
        <div class="subt">These lists belong to the FRN server: owners and admins change them in the FRN client (right click on a station). Shown here read-only, as the server stored them.</div>
        ${d.files.length ? d.files.map(f => `<div style="margin-top:14px"><div class="dim" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px">
            ${lbl[f.kind] || esc(f.file)} · ${esc(f.room)} <span class="count">${f.entries.length}</span> <span style="font-weight:400;text-transform:none;letter-spacing:0">· ${esc(f.file)} · ${fmtDate(f.mtime)}</span></div>
            ${f.entries.length ? `<div class="tbl-wrap"><table class="tbl"><tbody>${f.entries.map(e => `<tr>${Object.entries(e).slice(0, 5).map(([k, v]) => `<td><span class="dim" style="font-size:11px">${esc(k)}</span><br>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`
              : `<details><summary class="dim" style="cursor:pointer">show file</summary><pre class="term" style="max-height:240px;overflow:auto">${esc(f.text)}</pre></details>`}</div>`).join('')
          : '<div class="empty">The server has not stored any list yet.</div>'}</div>`;
}

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
            <div class="actions"><button class="btn primary">Create</button></div></form></div>`;
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
        <div class="tile"><h3>⬆️ Software updates</h3><div class="subt">Automatic check every full hour. Updates are only installed after an administrator action.</div>
            <div class="actions" style="justify-content:flex-start"><button class="btn" onclick="checkAllUpdates(this)">↻ Check now</button><button class="btn primary" id="upgradeJava" disabled onclick="upgradeNow('java', this)">Upgrade Java now</button><button class="btn primary" id="upgradeGit" disabled onclick="upgradeNow('github', this)">Upgrade Dashboard now</button></div>
            <div class="dim" id="updInfo" style="font-size:12.5px;margin-top:8px">Not checked yet.</div></div>
        <div class="tile"><h3>📥 Import server.properties</h3><div class="subt">Import supported server settings from an existing FRN installation. A backup is made before replacing the generated configuration. Existing ACL files are left untouched.</div>
            <div class="actions"><input type="file" id="propertiesFile" accept=".properties,text/plain"><button class="btn" onclick="importProperties()">Import configuration</button></div><div id="importInfo" class="dim" style="margin-top:8px"></div></div>
        <div class="tile"><h3>🎨 Appearance</h3><div class="subt">Choose the dashboard accent and upload your own PNG logo (max. 2 MB).</div>
            <div class="actions"><label>Accent <input type="color" id="brandAccent" value="#5ac8fa" onchange="applyAccent(this.value)"></label><input type="file" id="brandLogo" accept="image/png"><button class="btn" onclick="saveBranding()">Save appearance</button></div></div></div>`;
}

async function checkAllUpdates(btn) {
    if (btn) btn.disabled = true;
    try {
        const r = await api('POST', '/api/admin/updates/check', {});
        const gh = r.github || {}, java = r.java || {};
        $('updInfo').innerHTML = `GitHub: ${gh.ok ? (gh.update ? '<b>update available</b>' : 'up to date') : 'check failed: ' + esc(gh.error || 'unknown')} · Java FRN: ${java.ok ? (java.update ? '<b>update available</b>' : 'up to date') : 'check failed: ' + esc(java.error || 'unknown')}<br>Last check: ${r.checked ? new Date(r.checked * 1000).toLocaleString('de-DE') : '–'}`;
        $('upgradeJava').disabled = !java.update;
        $('upgradeGit').disabled = !gh.update;
    } catch(e) { $('updInfo').textContent = e.message; }
    finally { if (btn) btn.disabled = false; }
}
async function upgradeNow(target, btn) {
    const title = target === 'java' ? 'Upgrade Java FRN server?' : 'Upgrade dashboard from GitHub?';
    const body = target === 'java' ? 'The current FRN_Server.jar will be replaced and the Java server restarted.' : 'The dashboard checkout will be fast-forwarded. Local changes prevent the upgrade; restart the dashboard afterwards.';
    if (!await confirmBox({title, body}, 'Upgrade')) return;
    btn.disabled = true;
    try {
        await api('POST', '/api/admin/updates/upgrade', {target});
        toast('Upgrade completed.');
        if (target === 'github') toast('Please restart the dashboard service.');
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
        $('importInfo').textContent = 'Imported: ' + r.imported.join(', ') + (r.backup ? ' · Backup: ' + r.backup : '');
        toast('Configuration imported. Restart the FRN server to apply it.');
    } catch(e) { $('importInfo').textContent = e.message; toast(e.message, true); }
}


async function saveBranding() {
    const file = $('brandLogo')?.files?.[0];
    const accent = $('brandAccent')?.value || '#5ac8fa';
    const payload = {theme: accent};
    if (file) {
        if (file.size > 2 * 1024 * 1024) { toast('Logo is larger than 2 MB.', true); return; }
        payload.logo = await new Promise((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(r.result); r.onerror = reject; r.readAsDataURL(file); });
    }
    try { await api('POST', '/api/admin/branding', payload); applyAccent(accent); $('brandLogo').value = ''; document.querySelectorAll('.brand img, .logo').forEach(x => x.src = '/branding/logo?v=' + Date.now()); toast('Appearance saved.'); }
    catch(e) { toast(e.message, true); }
}
\nasync function restartApp() {
    if (!await confirmBox({ title: 'Restart the dashboard?', body: 'Only frn_adn starts again (a few seconds); the FRN server keeps running.' }, 'Restart')) return;
    try { await api('POST', '/api/admin/restart', {}); toast('Restarting …'); setTimeout(() => location.reload(), 6000); } catch (e) { toast(e.message, true); }
}
async function power(a) {
    if (!await confirmBox({ title: a === 'reboot' ? 'Reboot the machine?' : 'Shut down the machine?', body: a === 'reboot' ? 'The FRN server is back after about a minute.' : 'The FRN server stays off until the machine is started again.' }, a === 'reboot' ? 'Reboot' : 'Shut down', 'danger')) return;
    try { await api('POST', '/api/admin/power', { action: a }); toast(a === 'reboot' ? 'Rebooting …' : 'Shutting down …'); } catch (e) { toast(e.message, true); }
}

// logs
async function loadLogs() {
    const [d, v] = await Promise.all([api('GET', '/api/admin/logs'), api('GET', '/api/admin/visits?limit=100')]);
    S.admin.logs = d.entries;
    $('admin-logs').innerHTML = `<div class="tile"><h3>📜 Events (live)</h3><div class="term logview" id="logView"></div>
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
}
function logLine(e) {
    const cls = { denied: 'e', login: 'g', logout: 't', config: 'w', error: 'e' }[e.kind] || '';
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
        frn_update: '⬆️ FRN update', rooms: '🏠 Rooms', frn_account: '🔑 FRN account', app_restart: '♻️ Dashboard' };
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
