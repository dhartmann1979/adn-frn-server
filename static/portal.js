/* adn-frn-server – 📰 portal page: news of the operators (only admins write them, in Admin → 📰 Portal). */
'use strict';
const $ = id => document.getElementById(id);
const esc = PortalMD.esc;
const t = s => (window.N8Kit && N8Kit.i18n ? N8Kit.i18n.t(s) : s);
const P = { offset: 0, category: '', info: null, items: [], total: 0 };

async function api(url) {
    const r = await fetch(url, { credentials: 'same-origin' });
    let j = {};
    try { j = await r.json(); } catch (e) { }
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
}
function rgba(hex, a) {
    const n = parseInt(String(hex || '').slice(1), 16);
    if (!/^#[0-9a-f]{6}$/i.test(hex || '')) return `rgba(90,200,250,${a})`;
    return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
}
function applyTheme(theme) {               // the same colours as the dashboard (N8 Theme 2)
    const r = N8Theme.apply(theme || {}), c = r.colors, light = r.light, set = (k, v) => document.documentElement.style.setProperty(k, v);
    set('--user-accent', c.accent); set('--user-text', c.text); set('--user-muted', rgba(c.text, light ? .68 : .64));
    set('--theme-accent-soft', rgba(c.accent, .18)); set('--theme-accent-border', rgba(c.accent, .38));
    set('--theme-popover', light ? 'rgba(255,255,255,.985)' : 'rgba(16,22,40,.985)');
    set('--theme-header', light ? 'rgba(255,255,255,.72)' : 'rgba(20,26,45,.55)');
}
const fmtDate = ts => ts ? new Date(ts * 1000).toLocaleDateString(N8Kit.locale(),
    { day: '2-digit', month: 'long', year: 'numeric' }) : '';
function fmtDur(s) {
    s = Math.round(s || 0);
    if (s < 60) return `${s} s`;
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return h ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min`;
}
const catOf = id => (P.info.categories || []).find(c => c.id === id) || { id, label: id };

function renderHeader(i) {
    document.title = `News – ${i.title}`;
    $('title').textContent = i.title + (i.role === 'master' ? ' [Master]' : i.role === 'backup' ? ' [Backup]' : i.role === 'off' ? ' [Standalone]' : '');
    $('subtitle').textContent = i.subtitle || '';
    const dash = i.dashboard_url || '/';
    ['tabLive', 'tabStats', 'tabAdmin'].forEach(id => { const a = $(id); a.href = dash.replace(/\/$/, '/') + (a.dataset.hash || ''); });
    $('tabAdmin').classList.toggle('hidden', !(i.user && i.user.admin));
    $('liveBtn').href = dash;
    $('userArea').innerHTML = i.user
        ? `<a class="btn" href="${esc(dash)}${i.user.admin ? '#admin' : ''}">👤 ${esc(i.user.username)}</a>`
        : `<a class="btn" href="${esc(dash)}">🔑 ${esc(t('Login'))}</a>`;
    $('ver').textContent = `ADN FRN Server v${i.version}`;
    $('footerYear').textContent = new Date().getFullYear();
}
function renderHero(i) {
    $('heroTitle').textContent = i.title;
    $('heroKicker').textContent = '📰 ' + (i.subtitle || t('News'));
    $('heroIntro').innerHTML = PortalMD.render(i.intro || '');
    const f = [];
    if (i.live) f.push([t('Online now'), i.live.online]);
    if (i.today) f.push([t('Talks today'), i.today.talks ?? '–']);
    $('heroFacts').innerHTML = f.map(([k, v]) => `<div class="ph-fact"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join('');
    $('heroFacts').hidden = !f.length;
}
function renderSide(i) {
    $('todayBox').hidden = !i.today;
    if (i.today) {
        const d = i.today;
        $('todayStats').innerHTML = [[t('Talks'), d.talks ?? 0], [t('Airtime'), fmtDur(d.duration)], [t('Stations'), d.stations ?? 0], [t('Peak online'), d.peak_online ?? 0]]
            .map(([k, v]) => `<div class="ps-stat"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join('');
    }
    $('liveBox').hidden = !i.live;
    if (i.live) {
        $('liveOnline').textContent = `${i.live.online} ${t('online')}`;
        const rooms = i.live.rooms.filter(r => !r.parrot || r.stations);
        $('liveRooms').innerHTML = rooms.length ? rooms.map(r => `<div class="ps-room ${r.talking ? 'talking' : ''}">
            <div class="nm">${esc(r.name)}${r.talking ? `<span class="air">🎙️ ${esc(r.talking.callsign || '')} ${esc(r.talking.name || '')}</span>` : ''}</div>
            <div class="n">${r.stations}</div></div>`).join('') : `<div class="dim">${esc(t('No rooms'))}</div>`;
    }
    const kv = [];
    if (i.address) kv.push([t('FRN server'), `<code>${esc(i.address)}</code>`]);
    if (i.owner) kv.push([t('Operator'), esc(i.owner)]);
    if (i.website) kv.push([t('Website'), `<a href="${esc(i.website)}" target="_blank" rel="noopener">${esc(i.website.replace(/^https?:\/\//, ''))}</a>`]);
    $('connectInfo').innerHTML = kv.length ? `<div class="ps-kv">${kv.map(([k, v]) => `<span class="k">${esc(k)}</span><span>${v}</span>`).join('')}</div>` : '';
    $('connectBox').hidden = !kv.length;
    // the slim status line like on the dashboard
    if (i.live) {
        const air = i.live.rooms.find(r => r.talking);
        $('chipServer').className = 'n8-ss ' + (i.live.running ? 'ok' : 'bad'); $('chipServer').textContent = t('FRN server');
        $('chipOnline').className = 'n8-ss ok'; $('chipOnline').textContent = `${i.live.online} ${t('online')}`;
        $('chipAir').className = 'n8-ss ' + (air ? 'rx' : ''); $('chipAir').textContent = air ? `🎙️ ${air.talking.callsign} · ${air.name}` : t('Quiet');
    } else $('statusStrip').hidden = true;
}
function renderCats(i) {
    const cats = [{ id: '', label: '🗂️ ' + t('All') }, ...(i.categories || [])];
    $('catFilter').innerHTML = cats.map(c => `<button data-c="${esc(c.id)}" class="${c.id === P.category ? 'active' : ''}">${esc(t(c.label))}</button>`).join('');
}
function card(n) {
    const c = catOf(n.category);
    return `<article class="card news-card ${n.pinned ? 'pinned' : ''} ${n.image_url ? 'has-img' : ''} cat-${esc(n.category)}" data-id="${n.id}" tabindex="0">
        ${n.image_url ? `<div class="nc-img"><img src="${esc(n.image_url)}" alt="${esc(n.image_alt || '')}" loading="lazy" translate="no"></div>` : ''}
        <div class="nc-txt"><div class="nc-meta">${n.pinned ? `<span class="nc-pin">📌 ${esc(t('Pinned'))}</span>` : ''}<span class="nc-cat ${esc(n.category)}">${esc(t(c.label))}</span>
            <span>${esc(fmtDate(n.published_at))}</span>${n.author_name ? `<span>· ✍️ ${esc(n.author_name)}</span>` : ''}</div>
        <h3>${n.icon ? `<span class="ic">${esc(n.icon)}</span>` : ''}<span translate="no">${esc(n.title)}</span></h3>
        ${n.teaser ? `<div class="teaser" translate="no">${esc(n.teaser)}</div>` : n.body ? `<div class="teaser" translate="no">${esc(n.body.replace(/[#*>`_\[\]]/g, '').slice(0, 260))}${n.body.length > 260 ? ' …' : ''}</div>` : ''}
        ${n.body ? `<div class="nc-more">${esc(t('Read more'))} →</div>` : ''}</div>
    </article>`;
}
function renderList() {
    $('newsHead').textContent = t('Latest news');
    $('newsList').innerHTML = P.items.length ? `<div class="news-list">${P.items.map(card).join('')}</div>`
        : `<div class="card empty">📭 ${esc(t('No news yet.'))}</div>`;
    $('moreBtn').hidden = P.items.length >= P.total;
}
function renderArticle(n) {
    const c = catOf(n.category);
    document.title = `${n.title} – ${P.info.title}`;
    $('newsHead').textContent = t('News');
    $('catFilter').hidden = true; $('moreBtn').hidden = true;
    $('newsList').innerHTML = `<article class="card news-full">
        ${n.image_url ? `<div class="nf-img"><img src="${esc(n.image_url)}" alt="${esc(n.image_alt || '')}" translate="no"></div>` : ''}
        <a class="btn small back" href="/portal">← ${esc(t('All news'))}</a>
        <div class="nc-meta" style="margin-top:10px">${n.pinned ? `<span class="nc-pin">📌 ${esc(t('Pinned'))}</span>` : ''}<span class="nc-cat ${esc(n.category)}">${esc(t(c.label))}</span>
            <span>${esc(fmtDate(n.published_at))}</span>${n.author_name ? `<span>· ✍️ ${esc(n.author_name)}</span>` : ''}
            ${n.updated_at && n.published_at && n.updated_at - n.published_at > 600 ? `<span>· ${esc(t('updated'))} ${esc(fmtDate(n.updated_at))}</span>` : ''}</div>
        <h2>${n.icon ? `<span>${esc(n.icon)}</span>` : ''}<span translate="no">${esc(n.title)}</span></h2>
        ${n.teaser ? `<div class="teaser" translate="no">${esc(n.teaser)}</div>` : ''}
        <div class="md" translate="no">${PortalMD.render(n.body)}</div>
    </article>`;
}
async function load(append) {
    const m = location.pathname.match(/^\/news\/(\d+)/);
    try {
        const [branding, d] = await Promise.all([P.info ? null : api('/api/branding').catch(() => null),
            m ? api(`/api/portal/news/${m[1]}`) : api(`/api/portal?offset=${P.offset}&category=${encodeURIComponent(P.category)}`)]);
        if (branding) applyTheme(branding.theme);
        P.info = d;
        renderHeader(d);
        if (m) {
            const s = await api('/api/portal?offset=0').catch(() => null);
            if (s) { renderHero({ ...d, ...s }); renderSide(s); }
            renderArticle(d.item);
        } else {
            renderHero(d); renderSide(d); renderCats(d);
            P.items = append ? P.items.concat(d.news) : d.news; P.total = d.total;
            renderList();
        }
    } catch (e) {
        $('newsList').innerHTML = `<div class="card empty">⚠️ ${esc(e.message)}</div>`;
    }
}
async function loadLinks() {
    try {
        const d = await api('/api/links');
        $('linksMenu').classList.toggle('hidden', !d.enabled);
        $('linksMenu').querySelector('.links-label').textContent = d.label || '🔗 Links';
        $('linksPop').innerHTML = (d.links || []).map(x => `<a role="menuitem" ${x.new_tab ? 'target="_blank" rel="noopener noreferrer"' : ''} href="${esc(x.url)}">
            <span class="site-icon-wrap"><span class="site-icon-fallback">${esc(x.icon || '🔗')}</span>${x.site_icon && x.site_icon_url ? `<img src="${esc(x.site_icon_url)}" alt="" onerror="this.remove()">` : ''}</span><span>${esc(x.label)}</span></a>`).join('')
            || `<div class="links-loading">${esc(t('No links configured.'))}</div>`;
    } catch (e) { $('linksMenu').classList.add('hidden'); }
}
$('linksMenu').querySelector('.links-trigger').addEventListener('click', e => { e.stopPropagation(); $('linksMenu').classList.toggle('open'); });
document.addEventListener('click', e => { if (!$('linksMenu').contains(e.target)) $('linksMenu').classList.remove('open'); });
$('catFilter').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; P.category = b.dataset.c; P.offset = 0; load(false); });
$('moreBtn').addEventListener('click', () => { P.offset = P.items.length; load(true); });
$('newsList').addEventListener('click', e => { const c = e.target.closest('.news-card'); if (c) location.href = '/news/' + c.dataset.id; });
$('newsList').addEventListener('keydown', e => { const c = e.target.closest('.news-card'); if (c && e.key === 'Enter') location.href = '/news/' + c.dataset.id; });
window.addEventListener('n8:lang', () => load(false));
load(false); loadLinks();
setInterval(() => { if (!location.pathname.startsWith('/news/') && !document.hidden && P.offset === 0) load(false); }, 30000);
