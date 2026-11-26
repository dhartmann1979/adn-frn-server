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
        <td class="news-tt"><b translate="no">${x.icon ? esc(x.icon) + ' ' : ''}${esc(x.title)}</b>${x.teaser ? `<div class="dim" translate="no">${esc(x.teaser.slice(0, 140))}${x.teaser.length > 140 ? ' …' : ''}</div>` : ''}</td>
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
    $('nf_body').addEventListener('input', prev); prev();
    const save = async publish => {
        const b = { id: x.id, title: $('nf_title').value, teaser: $('nf_teaser').value, body: $('nf_body').value, icon: $('nf_icon').value,
            category: $('nf_cat').value, pinned: $('nf_pin').checked, published: publish === undefined ? $('nf_pub').checked : publish };
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
