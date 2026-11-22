/* frn_adn 2.1 – link list, software updates and header menu, in the style of HBlink4-FreeRadioID.
   Loaded after app.js: the functions below replace the simpler versions defined there
   (loadPublicLinks, loadLinksAdmin, saveLinksAdmin, checkAllUpdates, upgradeNow, applyAccent). */
(function () {
    'use strict';
    const byId = id => document.getElementById(id);
    const html = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const reduceMotion = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // ------------------------------------------------------------ accent colour (RGB for tinted backgrounds)
    const baseAccent = window.applyAccent;
    window.applyAccent = function (value) {
        if (typeof baseAccent === 'function') baseAccent(value);
        if (/^#[0-9a-f]{6}$/i.test(value || '')) {
            document.documentElement.style.setProperty('--accent-rgb', [1, 3, 5].map(i => parseInt(value.slice(i, i + 2), 16)).join(','));
        }
    };
    try { window.applyAccent(localStorage.getItem('frnadn-accent') || '#5ac8fa'); } catch (e) { /* storage blocked */ }

    // ------------------------------------------------------------ public link menu / link bar
    let LINKS = { enabled: true, label: '🔗 Links', style: 'menu', items: [] };

    function linkHtml(i) {
        const url = String(i.url || '');
        const anchor = /^#./.test(url);
        const external = i.new_tab !== false && !anchor && !/^(\/(?!\/)|mailto:)/.test(url);
        return `<a role="menuitem" href="${html(url)}"${external ? ' target="_blank" rel="noopener noreferrer"' : ''}${anchor ? ` data-anchor="${html(url.slice(1))}"` : ''}>`
            + `<span class="li-ic" aria-hidden="true"><span class="site-icon-fallback">${html(i.icon || '🔗')}</span>${i.site_icon && i.site_icon_url ? `<img class="site-icon-img" src="${html(i.site_icon_url)}" alt="">` : ''}</span><span class="li-tx">${html(i.label)}</span></a>`;
    }

    function bindSiteIcons(root) {
        root.querySelectorAll('.site-icon-img').forEach(img => img.addEventListener('error', () => {
            const retries = Number(img.dataset.retry || 0);
            if (retries >= 4) { img.remove(); return; }
            img.dataset.retry = String(retries + 1);
            setTimeout(() => { if (img.isConnected) img.src = img.src.split('?')[0] + '?retry=' + img.dataset.retry; }, 3500);
        }));
    }

    function renderLinks() {
        const menu = byId('linksMenu'), bar = byId('linksBar');
        if (!menu) return;
        const items = LINKS.enabled ? LINKS.items.filter(i => i && i.label && i.url) : [];
        if (!items.length) { menu.hidden = true; if (bar) bar.hidden = true; return; }
        if (LINKS.style === 'bar' && bar) {
            menu.hidden = true; menu.classList.remove('open');
            bar.hidden = false; bar.innerHTML = items.map(linkHtml).join(''); bindSiteIcons(bar);
        } else {
            if (bar) bar.hidden = true;
            menu.hidden = false;
            const label = menu.querySelector('.links-label');
            if (label) label.textContent = LINKS.label || '🔗 Links';
            byId('linksPop').innerHTML = items.map(linkHtml).join(''); bindSiteIcons(byId('linksPop'));
        }
    }

    window.loadPublicLinks = async function () {
        try {
            const d = await api('GET', '/api/links');
            LINKS = { enabled: d.enabled !== false, label: d.label || '🔗 Links', style: d.style === 'bar' ? 'bar' : 'menu', items: d.links || d.items || [] };
        } catch (e) { LINKS.items = []; }
        renderLinks();
    };

    // "#stats" style links switch to that tab instead of leaving the page; Escape closes the menu
    document.addEventListener('click', ev => {
        const a = ev.target.closest && ev.target.closest('a[data-anchor]');
        if (!a) return;
        const btn = document.querySelector(`#mainTabs [data-tab="${a.dataset.anchor}"]`);
        if (btn && typeof showTab === 'function') { ev.preventDefault(); showTab(a.dataset.anchor); }
        const m = byId('linksMenu'); if (m) m.classList.remove('open');
    });
    document.addEventListener('keydown', ev => {
        if (ev.key !== 'Escape') return;
        const m = byId('linksMenu');
        if (m && m.classList.contains('open')) { m.classList.remove('open'); m.querySelector('.links-trigger')?.setAttribute('aria-expanded', 'false'); m.querySelector('.links-trigger')?.focus(); }
    });

    // ------------------------------------------------------------ admin: link editor
    let lnCfg = { enabled: true, label: '🔗 Links', style: 'menu' };
    let lnItems = [];

    function lnRows() {
        const el = byId('lnList'); if (!el) return;
        el.innerHTML = lnItems.length ? lnItems.map((it, i) => `
            <div class="ln-row" data-i="${i}">
                <input class="ln-icon" value="${html(it.icon)}" placeholder="🔗" maxlength="8" aria-label="Icon" title="Emoji in front of the name" oninput="lnSet(${i}, 'icon', this.value)">
                <input class="ln-label" value="${html(it.label)}" placeholder="Name, e.g. Website" maxlength="50" aria-label="Name" oninput="lnSet(${i}, 'label', this.value)">
                <input class="ln-url" value="${html(it.url)}" placeholder="https://…" maxlength="500" aria-label="Address" oninput="lnSet(${i}, 'url', this.value)">
                <label class="ln-site-icon" title="Show this website's cached favicon"><input type="checkbox" ${it.site_icon !== false ? 'checked' : ''} onchange="lnSet(${i}, 'site_icon', this.checked)"> site icon <span class="ln-site-preview"><span class="site-icon-fallback">${html(it.icon || '🔗')}</span>${it.site_icon && it.site_icon_url ? `<img class="site-icon-img" src="${html(it.site_icon_url)}" alt="">` : ''}</span></label>
                <label class="ln-newtab" title="Open in a new browser tab"><span class="switch"><input type="checkbox" ${it.new_tab ? 'checked' : ''} onchange="lnSet(${i}, 'new_tab', this.checked)"><span></span></span> new tab</label>
                <span class="ln-move">
                    <button type="button" class="btn small" title="Up" aria-label="Move up" onclick="lnMove(${i}, -1)" ${i ? '' : 'disabled'}>↑</button>
                    <button type="button" class="btn small" title="Down" aria-label="Move down" onclick="lnMove(${i}, 1)" ${i < lnItems.length - 1 ? '' : 'disabled'}>↓</button>
                    <button type="button" class="btn small danger" title="Remove" aria-label="Remove" onclick="lnDel(${i})">🗑</button>
                </span>
            </div>`).join('') : '<div class="ln-empty">No links yet. Add the first one below.</div>';
        bindSiteIcons(el);
    }
    const lnDirty = () => { const f = byId('lnForm'); if (f) f.classList.add('is-dirty'); const s = byId('linksInfo'); if (s) s.textContent = ''; };
    window.lnSet = (i, k, v) => { lnItems[i][k] = v; lnDirty(); };
    window.lnMove = (i, d) => { const j = i + d; if (j < 0 || j >= lnItems.length) return; [lnItems[i], lnItems[j]] = [lnItems[j], lnItems[i]]; lnRows(); lnDirty(); };
    window.lnDel = i => { lnItems.splice(i, 1); lnRows(); lnDirty(); };
    window.lnAdd = tpl => {
        if (lnItems.length >= 20) { toast('Up to 20 links are possible.', true); return; }
        lnItems.push(tpl || { icon: '🔗', label: '', url: '', site_icon: true, new_tab: true }); lnRows(); lnDirty();
        const rows = document.querySelectorAll('#lnList .ln-label'); if (rows.length) rows[rows.length - 1].focus();
    };
    window.lnCfg = (k, v) => { lnCfg[k] = v; lnDirty(); };

    window.loadLinksAdmin = async function () {
        const d = await api('GET', '/api/admin/links');
        lnCfg = { enabled: d.enabled !== false, label: d.label || '🔗 Links', style: d.style === 'bar' ? 'bar' : 'menu' };
        lnItems = (d.links || d.items || []).map(i => ({ ...i, icon: i.icon || '', label: i.label, url: i.url,
            site_icon: i.site_icon !== false, new_tab: i.new_tab !== false }));
        byId('admin-links').innerHTML = `<form class="tile links-editor" id="lnForm" onsubmit="event.preventDefault(); saveLinksAdmin(this.querySelector('button.primary'))">
            <div class="ed-head"><div><h3>🔗 Link menu</h3>
                <p class="subt">Your own links in the header: website, chat group, wiki, donation page … Everyone sees them, also without login.</p></div>
                <span class="dirty-tag">unsaved</span></div>
            <div class="ed-row"><label for="lnEnabled">Show the link menu</label>
                <label class="switch"><input type="checkbox" id="lnEnabled" ${lnCfg.enabled ? 'checked' : ''} onchange="lnCfg('enabled', this.checked)"><span></span></label></div>
            <div class="ed-row"><label for="lnLabel">Menu button text</label>
                <input type="text" id="lnLabel" value="${html(lnCfg.label)}" maxlength="30" oninput="lnCfg('label', this.value)"></div>
            <div class="ed-row"><label for="lnStyle">Display</label>
                <select id="lnStyle" onchange="lnCfg('style', this.value)">
                    <option value="menu" ${lnCfg.style === 'menu' ? 'selected' : ''}>Button with drop-down menu</option>
                    <option value="bar" ${lnCfg.style === 'bar' ? 'selected' : ''}>Row of buttons below the header</option></select></div>
            <div class="ed-row wide"><label>Links <small class="dim">(order = order in the menu)</small></label>
                <div id="lnList" class="ln-list"></div>
                <div class="ln-add">
                    <button type="button" class="btn small primary" onclick="lnAdd()">➕ Add link</button>
                    <span class="dim">Quick start:</span>
                    <button type="button" class="btn small" onclick="lnAdd({icon:'🌐', label:'Website', url:'https://', new_tab:true})">🌐 Website</button>
                    <button type="button" class="btn small" onclick="lnAdd({icon:'💬', label:'Chat group', url:'https://', new_tab:true})">💬 Chat</button>
                    <button type="button" class="btn small" onclick="lnAdd({icon:'✉️', label:'Contact', url:'mailto:', new_tab:false})">✉️ E-mail</button>
                    <button type="button" class="btn small" onclick="lnAdd({icon:'📇', label:'Stations', url:'#stations', new_tab:false})">📇 Stations tab</button>
                </div>
                <p class="dim ed-note">Allowed: <code>https://…</code>, <code>http://…</code>, <code>mailto:…</code>, <code>#stats</code> (switches to that tab) and <code>/path</code> on this server.</p>
            </div>
            <div class="actions"><span class="dim" id="linksInfo" role="status"></span><button type="button" class="btn" onclick="saveLinksAdmin(this, true)">↻ Save &amp; refresh site icons</button><button type="submit" class="btn primary">💾 Save links</button></div>
        </form>`;
        lnRows();
    };

    window.saveLinksAdmin = async function (btn, refreshIcons) {
        const info = byId('linksInfo');
        for (const it of lnItems) {
            if (!String(it.label).trim() || !String(it.url).trim()) { info.textContent = 'Every link needs a name and an address.'; return; }
        }
        if (btn) btn.disabled = true;
        try {
            const r = await api('POST', '/api/admin/links', { enabled: lnCfg.enabled, label: lnCfg.label, style: lnCfg.style, refresh_icons: !!refreshIcons,
                items: lnItems.map(i => ({ icon: String(i.icon || '').trim(), label: String(i.label).trim(), url: String(i.url).trim(), site_icon: i.site_icon !== false, new_tab: !!i.new_tab })) });
            lnItems = (r.links || r.items || []).map(i => ({ ...i, icon: i.icon || '', label: i.label, url: i.url,
                site_icon: i.site_icon !== false, new_tab: i.new_tab !== false }));
            lnRows(); byId('lnForm').classList.remove('is-dirty');
            info.textContent = refreshIcons ? 'Links saved and site icons refreshed into SQLite.' : 'Saved. Site icons are cached in SQLite.';
            toast(refreshIcons ? 'Links saved and icons refreshed.' : 'Link menu saved.');
            await window.loadPublicLinks();
        } catch (e) { info.textContent = e.message; toast(e.message, true); }
        finally { if (btn) btn.disabled = false; }
    };

    // ------------------------------------------------------------ admin: software updates
    let lastUpd = null;
    const when = ts => ts ? new Date(ts * 1000).toLocaleString() : '–';
    const short = s => html(String(s || '').slice(0, 7));

    function dashboardRow(gh) {
        if (!gh || gh.ok === undefined) return '';
        const loc = gh.local || {}, lat = gh.latest || {};
        const cur = `${loc.version ? 'v' + html(loc.version) : '?'}${loc.short ? ` <span class="mono">${short(loc.commit)}</span>` : ''}`;
        let badge, detail = '';
        if (!gh.ok) { badge = '<span class="upd-badge bad">check failed</span>'; detail = `<div class="upd-hint">${html(gh.error)}</div>`; }
        else if (gh.error) { badge = '<span class="upd-badge warn">unknown state</span>'; detail = `<div class="upd-hint">${html(gh.error)}${gh.hint ? '<br>' + html(gh.hint) : ''}</div>`; }
        else if (gh.update) {
            badge = '<span class="upd-badge new">update available</span>';
            const nv = gh.remote_version ? `v${html(gh.remote_version)} ` : '';
            detail = `<div class="upd-new">→ <b>${nv}<span class="mono">${short(lat.commit)}</span></b> · ${gh.behind} new commit${gh.behind === 1 ? '' : 's'} · <a href="${html(gh.url)}" target="_blank" rel="noopener noreferrer">compare on GitHub</a></div>`
                + `<ul class="upd-commits">${(gh.commits || []).map(c => `<li><span class="mono">${short(c.short)}</span> ${html(c.message)}</li>`).join('')}</ul>`
                + (gh.hint ? `<div class="upd-hint">${html(gh.hint)}</div>` : '');
        } else { badge = '<span class="upd-badge ok">up to date</span>'; detail = lat.message ? `<div class="upd-hint">Latest: ${html(lat.message)}</div>` : ''; }
        return `<div class="upd-row"><div class="upd-top"><b>🖥️ Dashboard</b> <span class="dim">GitHub ${html(gh.repo)} · ${html(gh.branch)}</span>${badge}</div>
            <div class="upd-ver">Installed: ${cur}</div>${detail}</div>`;
    }

    function javaRow(j) {
        if (!j) return '';
        const inst = j.installed ? `${html(j.installed.version)} (build ${html(j.installed.build)})` : 'unknown';
        let badge, detail = '';
        if (!j.ok) { badge = '<span class="upd-badge bad">check failed</span>'; detail = `<div class="upd-hint">${html(j.error)}</div>`; }
        else if (j.update && j.latest) { badge = '<span class="upd-badge new">update available</span>'; detail = `<div class="upd-new">→ <b>${html(j.latest.version)}</b> (build ${html(j.latest.build)}) from freeradionetwork.de</div>`; }
        else badge = '<span class="upd-badge ok">up to date</span>';
        return `<div class="upd-row"><div class="upd-top"><b>☕ Java FRN server</b> <span class="dim">freeradionetwork.de</span>${badge}</div>
            <div class="upd-ver">Installed: ${inst}</div>${detail}</div>`;
    }

    window.checkAllUpdates = async function (btn) {
        const box = byId('updInfo');
        if (btn) btn.disabled = true;
        if (box && !lastUpd) box.textContent = 'Checking …';
        try {
            const r = await api('POST', '/api/admin/updates/check', {});
            lastUpd = r;
            const gh = r.github || {}, java = r.java || {};
            if (box) box.innerHTML = dashboardRow(gh) + javaRow(java) + `<div class="upd-when">Last check: ${when(r.checked)} · automatic check every full hour</div>`;
            const jb = byId('upgradeJava'), gb = byId('upgradeGit');
            if (jb) jb.disabled = !(java.ok && java.update);
            if (gb) gb.disabled = !gh.can_upgrade;
        } catch (e) { if (box) box.textContent = e.message; }
        finally { if (btn) btn.disabled = false; }
    };

    function restartOverlay(text) {
        let o = byId('restartOverlay');
        if (!o) { o = document.createElement('div'); o.id = 'restartOverlay'; o.className = 'restart-overlay'; o.setAttribute('role', 'alertdialog'); document.body.appendChild(o); }
        o.innerHTML = `<div class="restart-box"><div class="restart-spin" aria-hidden="true"></div><div>${html(text)}</div></div>`;
        return o;
    }

    // after the dashboard exits for its restart: wait until it answers again, then reload the page
    async function waitForDashboard() {
        restartOverlay('Dashboard updated – restarting …');
        const started = Date.now();
        let down = false;
        await new Promise(r => setTimeout(r, 2500));
        while (Date.now() - started < 90000) {
            try {
                const r = await fetch('/api/info', { cache: 'no-store' });
                if (r.ok && (down || Date.now() - started > 8000)) { location.reload(); return; }
            } catch (e) { down = true; }
            await new Promise(r => setTimeout(r, 1500));
        }
        restartOverlay('The dashboard did not come back within 90 seconds. Check: sudo systemctl status frnadn');
        byId('restartOverlay').addEventListener('click', () => byId('restartOverlay').remove());
    }

    window.upgradeNow = async function (target, btn) {
        const gh = (lastUpd && lastUpd.github) || {}, java = (lastUpd && lastUpd.java) || {};
        const isJava = target === 'java';
        const title = isJava ? 'Upgrade Java FRN server?' : 'Upgrade dashboard from GitHub?';
        const body = isJava
            ? `FRN_Server.zip is loaded from freeradionetwork.de${java.latest ? ' (' + html(java.latest.version) + ')' : ''}, FRN_Server.jar is replaced and the Java server restarts. Stations reconnect by themselves.`
            : `${html(gh.behind || 'New')} commit${gh.behind === 1 ? '' : 's'} will be applied${gh.remote_version ? ' (v' + html(gh.remote_version) + ')' : ''}. Changed Python packages are installed, then the FRN server and dashboard restart. Connected stations reconnect automatically, and this page reloads.`;
        if (!await confirmBox({ title, body }, 'Upgrade')) return;
        if (btn) btn.disabled = true;
        try {
            const r = await api('POST', '/api/admin/updates/upgrade', isJava ? { target } : { target, expected: (gh.latest || {}).commit });
            if (isJava) toast('Java FRN server upgraded' + (r.installed ? ' to ' + r.installed.version : '') + '.');
            else if (!r.changed) toast('Already up to date.');
            else if (r.restarting) {
                if (r.frn_restart && !r.frn_restart.ok) alert('Dashboard updated, but the FRN server could not be restarted automatically. Please restart it from Admin → System.\n\n' + (r.frn_restart.out || 'Unknown error'));
                await waitForDashboard(); return;
            }
            else toast('FRN server restarted. Restart the dashboard to load the update: sudo systemctl restart frnadn', true);
            await window.checkAllUpdates();
        } catch (e) { toast(e.message, true); if (btn) btn.disabled = false; }
    };

    // the first render may have used the simple link list while this file was still loading
    if (byId('linksMenu')) window.loadPublicLinks();
}());
