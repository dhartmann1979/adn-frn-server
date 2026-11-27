/* adn-frn-server – Admin → 📰 Portal: news (only admins are authors) and the settings of the portal page.
 * Uses the helpers of app.js: api, $, esc, toast, modal, closeModal, confirmBox, fieldHtml, formValues, fmtDate, S. */
'use strict';

const PORTAL = { news: [], cats: [], url: '/portal', domain: '' };

async function loadPortalData() {
    const d = await api('GET', '/api/admin/portal');
    PORTAL.news = d.news || []; PORTAL.cats = d.categories || []; PORTAL.url = d.url || '/portal'; PORTAL.domain = d.domain || '';
    PORTAL.settings = d.settings;
    return d;
}
const catLabel = id => (PORTAL.cats.find(c => c.id === id) || { label: id }).label;

// ---------------------------------------------------------------- 📝 News
async function loadNewsAdmin() {
    await loadPortalData();
    renderNewsAdmin();
}
function renderNewsAdmin() {
    const n = PORTAL.news, pub = n.filter(x => x.published).length;
    const row = x => `<tr class="${x.published ? '' : 'news-draft'}">
        <td class="news-tt">${x.image_url ? `<img class="news-thumb" src="${esc(x.image_url)}" alt="">` : ''}<b translate="no">${x.icon ? esc(x.icon) + ' ' : ''}${esc(x.title)}</b>${x.teaser ? `<div class="dim" translate="no">${esc(x.teaser.slice(0, 140))}${x.teaser.length > 140 ? ' …' : ''}</div>` : ''}</td>
        <td><span class="nc-cat ${esc(x.category)}">${esc(catLabel(x.category))}</span></td>
        <td>${x.published ? '<span class="badge ok">Published</span>' : '<span class="badge warn">Draft</span>'}${x.pinned ? ' <span class="badge">📌 Pinned</span>' : ''}</td>
        <td class="nowrap">${esc(fmtDate(x.published_at || x.created_at))}<div class="dim">✍️ ${esc(x.author_name || x.author)}${x.updated_by && x.updated_by !== x.author ? ` · ✏️ ${esc(x.updated_by)}` : ''}</div></td>
        <td class="nowrap news-act">
            <button class="btn small" data-news-edit="${x.id}">✏️ Edit</button>
            <button class="btn small ${x.published ? '' : 'good'}" data-news-pub="${x.id}">${x.published ? '⏸ Unpublish' : '🚀 Publish'}</button>
            ${x.published ? `<a class="btn small" href="/news/${x.id}" target="_blank" rel="noopener">↗</a>` : ''}
            <button class="btn small danger" data-news-del="${x.id}">🗑</button></td></tr>`;
    $('admin-news').innerHTML = `<div class="tile">
        <div class="news-head"><div><h3>📝 News</h3>
            <div class="subt">Only admins write and publish news – they appear on the portal page. Drafts are visible here only.</div></div>
            <div class="actions" style="margin:0"><a class="btn" href="${esc(PORTAL.url)}" target="_blank" rel="noopener">📰 Open portal page ↗</a>
            <button class="btn primary" data-news-new>＋ New news</button></div></div>
        <div class="news-stats"><span class="badge ok">${pub} published</span> <span class="badge warn">${n.length - pub} drafts</span>
            ${PORTAL.domain ? `<span class="badge">🌐 ${esc(PORTAL.domain)}</span>` : '<span class="dim">Own domain: 🌐 Network, ports &amp; domains → 🔒 Domains &amp; HTTPS</span>'}</div>
        ${n.length ? `<div class="tbl-wrap"><table class="tbl news-tbl"><thead><tr><th>Title</th><th>Category</th><th>Status</th><th>Date</th><th></th></tr></thead>
            <tbody>${n.map(row).join('')}</tbody></table></div>` : '<div class="empty">📭 No news yet – „＋ New news“ writes the first one.</div>'}
    </div>`;
}
function newsEditor(x) {
    x = x || { title: '', teaser: '', body: '', category: 'info', icon: '', pinned: false, published: false };
    modal(`<h3>${x.id ? '✏️ Edit news' : '＋ New news'}</h3>
        <form id="newsForm" class="news-form" onsubmit="event.preventDefault()">
            <div class="news-row3">
                <div class="row"><label for="nf_icon">Icon</label><input type="text" id="nf_icon" maxlength="8" value="${esc(x.icon)}" placeholder="📢"></div>
                <div class="row grow"><label for="nf_title">Title</label><input type="text" id="nf_title" maxlength="140" required value="${esc(x.title)}" translate="no"></div>
                <div class="row"><label for="nf_cat">Category</label><select id="nf_cat">${PORTAL.cats.map(c => `<option value="${esc(c.id)}" ${c.id === x.category ? 'selected' : ''}>${esc(c.label)}</option>`).join('')}</select></div>
            </div>
            <div class="news-img-row">
                <div class="news-img" id="nf_img">${x.image_url ? `<img src="${esc(x.image_url)}" alt="">` : '<span>🖼️<br>Topic image</span>'}</div>
                <div class="news-img-side">
                    <div class="actions" style="justify-content:flex-start;margin:0">
                        <label class="btn">📤 Choose image<input type="file" id="nf_file" accept="image/jpeg,image/png,image/webp" hidden></label>
                        <button type="button" class="btn" id="nf_imgdel" ${x.image_url ? '' : 'hidden'}>🗑 Remove image</button></div>
                    <div class="row"><label for="nf_alt">Image description <span class="dim">(for screen readers)</span></label><input type="text" id="nf_alt" maxlength="200" value="${esc(x.image_alt || '')}" translate="no"></div>
                    <div class="help">JPEG, PNG or WebP – made smaller in the browser (max. 1600 px wide); shown at the top of the card and the article, 16:9.</div>
                </div>
            </div>
            <div class="row"><label for="nf_teaser">Teaser <span class="dim">(short summary on the card, optional)</span></label><input type="text" id="nf_teaser" maxlength="400" value="${esc(x.teaser)}" translate="no"></div>
            <div class="news-split">
                <div class="row"><label for="nf_body">Text</label><textarea id="nf_body" maxlength="20000" spellcheck="true" translate="no">${esc(x.body)}</textarea>
                    <div class="help">**bold** · *italic* · \`code\` · [link](https://…) · # heading · - list · 1. list · &gt; quote · --- line</div></div>
                <div class="row"><label>Preview</label><div class="md news-preview" id="nf_prev" translate="no"></div></div>
            </div>
            <div class="news-flags"><label class="switch-row"><label class="switch"><input type="checkbox" id="nf_pin" ${x.pinned ? 'checked' : ''}><span></span></label> 📌 Pin to the top</label>
                <label class="switch-row"><label class="switch"><input type="checkbox" id="nf_pub" ${x.published ? 'checked' : ''}><span></span></label> 🚀 Published</label></div>
            <div class="actions"><button type="button" class="btn" onclick="closeModal()">Cancel</button>
                <button type="button" class="btn" id="nf_draft">💾 Save as draft</button>
                <button type="button" class="btn primary" id="nf_save">🚀 Save &amp; publish</button></div>
        </form>`, false, true);
    const prev = () => { $('nf_prev').innerHTML = PortalMD.render($('nf_body').value) || '<span class="dim">…</span>'; };
    let image = 'keep';
    $('nf_file').onchange = async e => {
        const f = e.target.files[0]; if (!f) return;
        try {
            image = await newsShrink(f);
            $('nf_img').innerHTML = `<img src="${image}" alt="">`; $('nf_imgdel').hidden = false;
        } catch (x) { toast(x.message, true); }
        e.target.value = '';
    };
    $('nf_imgdel').onclick = () => { image = ''; $('nf_img').innerHTML = '<span>🖼️<br>Topic image</span>'; $('nf_imgdel').hidden = true; };
    $('nf_body').addEventListener('input', prev); prev();
    const save = async publish => {
        const b = { id: x.id, title: $('nf_title').value, teaser: $('nf_teaser').value, body: $('nf_body').value, icon: $('nf_icon').value,
            category: $('nf_cat').value, pinned: $('nf_pin').checked, published: publish === undefined ? $('nf_pub').checked : publish,
            image, image_alt: $('nf_alt').value };
        if (!b.title.trim()) { $('nf_title').focus(); return; }
        try {
            const r = await api('POST', '/api/admin/news', b);
            closeModal(); toast(r.item.published ? '🚀 Published' : '💾 Saved as draft'); loadNewsAdmin();
        } catch (e) { toast(e.message, true); }
    };
    $('nf_draft').onclick = () => save(false);
    $('nf_save').onclick = () => save(true);
    $('nf_title').focus();
}
$('admin-news').addEventListener('click', async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.matches('[data-news-new]')) return newsEditor();
    const id = Number(b.dataset.newsEdit || b.dataset.newsPub || b.dataset.newsDel);
    const x = PORTAL.news.find(n => n.id === id); if (!x) return;
    if (b.dataset.newsEdit) return newsEditor(x);
    if (b.dataset.newsPub) {
        try { await api('POST', `/api/admin/news/${id}/publish`, { published: !x.published }); toast(x.published ? '⏸ Unpublished' : '🚀 Published'); loadNewsAdmin(); }
        catch (err) { toast(err.message, true); }
        return;
    }
    if (b.dataset.newsDel) {
        if (!await confirmBox({ title: 'Delete the news?', body: `„${x.title}“ is removed for good.` }, 'Delete')) return;
        try { await api('DELETE', `/api/admin/news/${id}`); toast('🗑 Deleted'); loadNewsAdmin(); } catch (err) { toast(err.message, true); }
    }
});

// ---------------------------------------------------------------- ⚙️ Portal page
async function loadPortalAdmin() {
    const d = await loadPortalData();
    const fields = (d.settings.fields || []).filter(f => f.key !== 'portal.domain');
    $('admin-portalcfg').innerHTML = `<div class="tiles tiles-even">
        <form class="tile" id="portalForm" onsubmit="event.preventDefault(); savePortalSettings(this)">
            <h3>⚙️ Portal page</h3><div class="subt">Public page with the news of the operators – at /portal and on its own domain.</div>
            ${fields.map(fieldHtml).join('')}
            <div class="actions"><a class="btn" href="${esc(PORTAL.url)}" target="_blank" rel="noopener">📰 Open portal page ↗</a><button class="btn primary">Save</button></div>
        </form>
        <div class="tile">
            <h3>🌐 Portal domain</h3>
            <div class="subt">Every domain or subdomain shows what you choose under 🔒 Domains & HTTPS → “Shows”: the Live dashboard or the portal page – any number of domains, all with Let's Encrypt.</div>
            ${PORTAL.domain ? `<div class="notice-box">✅ <b>${esc(PORTAL.domain)}</b> – <a href="${esc(PORTAL.url)}" target="_blank" rel="noopener">${esc(PORTAL.url)}</a></div>`
                : '<div class="notice-box">No own domain yet – the portal is at /portal of the dashboard.</div>'}
            <div class="actions" style="justify-content:flex-start"><button type="button" class="btn" onclick="showAdmin('domains')">🔒 Domains &amp; HTTPS</button></div>
            <h3 style="margin-top:18px">👥 Authors</h3>
            <div class="subt">Only admins (role Admin or Superadmin) write, edit, publish and delete news. Users and visitors only read. Every change is in the 📜 log.</div>
            <div class="actions" style="justify-content:flex-start"><button type="button" class="btn" onclick="showAdmin('users')">👥 Users</button><button type="button" class="btn" onclick="showAdmin('news')">📝 News</button></div>
            <h3 style="margin-top:18px">📡 RSS</h3>
            <div class="subt">Published news as a feed: <a href="/portal/rss.xml" target="_blank" rel="noopener"><code>/portal/rss.xml</code></a></div>
        </div></div>`;
}
async function savePortalSettings(form) {
    try {
        const r = await api('POST', '/api/admin/portal/settings', { changes: formValues(form) });
        toast(r.changed.length ? `Saved (${r.changed.length})` : 'No changes');
    } catch (e) { toast(e.message, true); }
}

// topic image: made smaller in the browser (max. 1600 × 900 px area, JPEG/WebP ~85 %) before it is uploaded
function newsShrink(file) {
    return new Promise((resolve, reject) => {
        if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return reject(new Error('JPEG, PNG or WebP only.'));
        const img = new Image(), url = URL.createObjectURL(file);
        img.onload = () => {
            const scale = Math.min(1, 1600 / img.width, 1200 / img.height);
            const c = document.createElement('canvas');
            c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
            c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
            URL.revokeObjectURL(url);
            let out = c.toDataURL('image/webp', 0.85);
            if (!out.startsWith('data:image/webp')) out = c.toDataURL('image/jpeg', 0.85);
            if (out.length > 1.9e6) out = c.toDataURL('image/jpeg', 0.7);
            resolve(out);
        };
        img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('The image cannot be read.')); };
        img.src = url;
    });
}

// ---------------------------------------------------------------- 🧩 Widgets at the side of the portal page
const WADM = { list: [], kinds: {}, local: [] };
const W_HELP = {
    hblink4: 'HBlink4-FreeRadioID: Admin → Settings → 🔐 Dashboard access → “Live data for the ADN portal page” on, paste the key.',
    crosslink: 'N8 Crosslink: Admin → 🏠 Allgemein → “📰 Live-Daten für die Portal-Seite” on, paste the key.',
    hotspot: 'N8 Hotspot: Admin → Settings → 🌐 Dashboard → “Live data for the ADN portal page” on, paste the key. Only in the local network.',
    gateway: 'N8 Gateway: switch on the portal feed there and paste the key (as soon as N8 Gateway offers it). Only in the local network.',
};
async function loadWidgetsAdmin() {
    const d = await api('GET', '/api/admin/portal/widgets');
    WADM.list = d.widgets || []; WADM.kinds = d.kinds || {}; WADM.local = d.local_only || [];
    WADM.interval = d.interval; WADM.side = d.side;
    renderWidgetsAdmin();
}
function wState(w) {
    if (w.builtin) return '<span class="dim">own FRN server</span>';
    if (!w.enabled) return '<span class="dim">off</span>';
    if (w.error) return `<span class="cl-bad" title="${esc(w.error)}">✕ <span>${esc(w.error)}</span></span>${w.ok_at ? ` <span class="dim">· <span>last data</span> ${esc(fmtDate(w.ok_at))}</span>` : ''}`;
    if (w.ok_at) return `<span class="cl-ok">✓ <span>live data</span></span> <span class="dim">${esc(fmtDate(w.ok_at))}${w.data && w.data.version ? ' · ' + esc(w.data.version) : ''}</span>`;
    return '<span class="dim">not fetched yet</span>';
}
function renderWidgetsAdmin() {
    const L = WADM.list;
    const row = (w, i) => `<div class="wa-row ${w.enabled ? '' : 'off'}" data-wid="${w.id}">
        <div class="wa-move"><button class="btn small" data-w-up="${w.id}" ${i ? '' : 'disabled'} title="Up">▲</button><button class="btn small" data-w-down="${w.id}" ${i < L.length - 1 ? '' : 'disabled'} title="Down">▼</button></div>
        <div class="wa-main"><b><span>${esc(w.kind_label)}</span></b>${w.title ? ` <span class="dim">· <span translate="no">${esc(w.title)}</span></span>` : ''}
            <div class="wa-sub">${w.url ? `<span class="mono">${esc(w.url)}</span> · ` : ''}${wState(w)}</div></div>
        <label class="switch" title="Show on the portal page"><input type="checkbox" data-w-on="${w.id}" ${w.enabled ? 'checked' : ''}><span></span></label>
        <div class="wa-act"><button class="btn small" data-w-edit="${w.id}">✏️ Edit</button>
            ${w.builtin ? '' : `<button class="btn small" data-w-test="${w.id}">🔄 Fetch now</button><button class="btn small danger" data-w-del="${w.id}">🗑</button>`}</div></div>`;
    $('admin-widgets').innerHTML = `<div class="tiles tiles-even">
        <div class="tile"><h3>🧩 Widgets of the portal page</h3>
            <div class="subt">Shown ${WADM.side === 'left' ? 'left' : 'right'} of the news, from top to bottom in this order. The live data of the other N8 systems are fetched every ${esc(WADM.interval)} s, encrypted with their sync key, and cached in SQLite – visitors get the cached copy. Side and interval: ⚙️ Portal page.</div>
            <div class="wa-list">${L.map(row).join('')}</div>
            <div class="actions" style="justify-content:flex-start;flex-wrap:wrap">${Object.keys(WADM.kinds).filter(k => !k.startsWith('frn_')).map(k => `<button class="btn" data-w-new="${k}">＋ ${esc(WADM.kinds[k])}</button>`).join('')}
                <a class="btn" href="${esc(PORTAL.url || '/portal')}" target="_blank" rel="noopener">📰 Open portal page ↗</a></div></div>
        <div class="tile"><h3>🔐 How a system is connected</h3>
            <div class="subt">Every system gets its own sync key. It never travels: the portal and the system use it to encrypt each request and each answer (like Master &amp; Backup). The systems send only what their public live page shows – no IP addresses, no accounts.</div>
            <ol class="wa-steps"><li>Here: <b>＋ system</b>, its dashboard address, <b>🎲 New key</b> → copy the key.</li>
                <li>On the system: switch the portal feed on and paste the key (see below).</li><li>Here: <b>💾 Save</b> – the portal fetches at once and shows whether it works.</li></ol>
            <div class="wa-help">${Object.entries(W_HELP).map(([k, v]) => `<div><b>${esc(WADM.kinds[k] || k)}</b> – <span>${esc(v)}</span></div>`).join('')}</div>
            <div class="notice-box">📶 <span>N8 Hotspot and N8 Gateway answer only in the local network – they are asked only at a LAN address (e.g. http://192.168.1.20).</span></div></div></div>`;
}
function widgetEditor(w) {
    const nw = !w.id, kind = w.kind, local = WADM.local.includes(kind);
    modal(`<h3>${nw ? '＋' : '✏️'} <span>${esc(WADM.kinds[kind] || kind)}</span></h3>
        <form id="wForm" onsubmit="event.preventDefault()">
            <div class="row"><label for="wf_title">Title on the portal page</label><input type="text" id="wf_title" maxlength="80" value="${esc(w.title || '')}" placeholder="${w.builtin ? '' : 'Empty = the title of the system'}" translate="no"></div>
            ${w.builtin ? '' : `
            <div class="row"><label for="wf_url">Dashboard address of the system</label><input type="text" id="wf_url" value="${esc(w.url || '')}" placeholder="${local ? 'http://192.168.1.20' : 'https://dmr.example.org'}" spellcheck="false">
                <div class="help">${local ? 'Only in the local network (LAN address).' : 'The address of its web interface, with https:// – e.g. https://dmr.die-n8schicht.de'}</div></div>
            <div class="row"><label for="wf_key">Sync key</label><div class="pw-wrap"><input type="text" id="wf_key" value="" placeholder="${w.key_set ? '•••••••• (unchanged)' : 'at least 24 characters'}" autocomplete="off" spellcheck="false">
                <button type="button" class="btn small" id="wf_gen">🎲 New key</button><button type="button" class="btn small" id="wf_copy">📋</button></div>
                <div class="help">${esc(W_HELP[kind] || '')}</div></div>
            <div class="row"><label for="wf_link">Link of the widget <span class="dim">(optional)</span></label><input type="text" id="wf_link" value="${esc(w.link || '')}" placeholder="https://…" spellcheck="false">
                <div class="help">A click on “Open …” leads there – e.g. the public dashboard. Empty = no button (the address above is not shown to visitors).</div></div>
            <div class="news-flags"><label class="switch-row"><label class="switch"><input type="checkbox" id="wf_lh" ${w.show_lh !== 0 ? 'checked' : ''}><span></span></label> <span>Show last heard</span></label>
                <label class="switch-row"><span>Entries</span> <select id="wf_lhn">${[3, 4, 5, 6, 8].map(n => `<option ${n === (w.lh_count || 5) ? 'selected' : ''}>${n}</option>`).join('')}</select></label></div>`}
            <div class="news-flags"><label class="switch-row"><label class="switch"><input type="checkbox" id="wf_on" ${w.enabled !== 0 ? 'checked' : ''}><span></span></label> <span>Show on the portal page</span></label></div>
            <div id="wf_res"></div>
            <div class="actions"><button type="button" class="btn" onclick="closeModal()">Cancel</button><button type="button" class="btn primary" id="wf_save">💾 Save</button></div>
        </form>`, false, true);
    if (!w.builtin) {
        $('wf_gen').onclick = async () => { try { $('wf_key').value = (await api('POST', '/api/admin/portal/widgets/key', {})).key; $('wf_key').select(); } catch (e) { toast(e.message, true); } };
        $('wf_copy').onclick = () => { const v = $('wf_key').value; if (!v) return toast('Enter or create a key first', true); navigator.clipboard && navigator.clipboard.writeText(v); toast('Copied'); };
    }
    $('wf_save').onclick = async () => {
        const b = { id: w.id, kind, title: $('wf_title').value, enabled: $('wf_on').checked };
        if (!w.builtin) Object.assign(b, { url: $('wf_url').value, key: $('wf_key').value, link: $('wf_link').value, show_lh: $('wf_lh').checked, lh_count: +$('wf_lhn').value });
        $('wf_save').disabled = true;
        try {
            const r = await api('POST', '/api/admin/portal/widgets', b);
            const t = r.widget.test;
            if (t && !t.ok) {
                $('wf_res').innerHTML = `<div class="notice-box cl-alarm">⚠️ <span>Saved, but the system does not answer yet:</span> <b>${esc(t.error)}</b></div>`;
                w = r.widget; $('wf_save').disabled = false; loadWidgetsAdmin(); return;
            }
            closeModal(); toast(t ? `✅ ${t.data.title || ''} – live data received` : 'Saved'); loadWidgetsAdmin();
        } catch (e) { $('wf_res').innerHTML = `<div class="notice-box cl-alarm">⚠️ ${esc(e.message)}</div>`; $('wf_save').disabled = false; }
    };
}
document.addEventListener('click', async e => {
    const b = e.target.closest('[data-w-up],[data-w-down],[data-w-edit],[data-w-test],[data-w-del],[data-w-new]');
    if (!b || !$('admin-widgets') || !$('admin-widgets').contains(b)) return;
    const id = +(b.dataset.wUp || b.dataset.wDown || b.dataset.wEdit || b.dataset.wTest || b.dataset.wDel || 0), w = WADM.list.find(x => x.id === id);
    if (b.dataset.wNew) return widgetEditor({ kind: b.dataset.wNew, enabled: 1, show_lh: 1, lh_count: 5 });
    if (b.dataset.wEdit) return widgetEditor(w);
    if (b.dataset.wUp || b.dataset.wDown) {
        const ids = WADM.list.map(x => x.id), i = ids.indexOf(id), j = b.dataset.wUp ? i - 1 : i + 1;
        if (j < 0 || j >= ids.length) return;
        [ids[i], ids[j]] = [ids[j], ids[i]];
        try { await api('POST', '/api/admin/portal/widgets/order', { ids }); loadWidgetsAdmin(); } catch (err) { toast(err.message, true); }
        return;
    }
    if (b.dataset.wTest) {
        b.disabled = true;
        try { const r = await api('POST', `/api/admin/portal/widgets/${id}/test`, {}); r.ok ? toast(`✅ ${r.data.title || ''} – live data received`) : toast(r.error, true); }
        catch (err) { toast(err.message, true); }
        loadWidgetsAdmin(); return;
    }
    if (b.dataset.wDel) {
        if (!await confirmBox({ title: 'Delete the widget?', body: `${w.kind_label}${w.title ? ' – ' + w.title : ''} disappears from the portal page. Switch the portal feed off on the system too.` }, 'Delete', 'danger')) return;
        try { await api('DELETE', `/api/admin/portal/widgets/${id}`); toast('🗑 Deleted'); loadWidgetsAdmin(); } catch (err) { toast(err.message, true); }
    }
});
document.addEventListener('change', async e => {
    const c = e.target.closest('[data-w-on]');
    if (!c) return;
    const w = WADM.list.find(x => x.id === +c.dataset.wOn);
    try { await api('POST', '/api/admin/portal/widgets', { id: w.id, kind: w.kind, title: w.title, url: w.url, key: '', link: w.link, show_lh: !!w.show_lh, lh_count: w.lh_count, enabled: c.checked }); loadWidgetsAdmin(); }
    catch (err) { toast(err.message, true); c.checked = !c.checked; }
});
