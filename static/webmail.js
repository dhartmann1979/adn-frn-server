/* adn-frn-server – ✉️ Webmail (N8 Mail): the mailbox of the logged-in user.
 * Folders | list | message. HTML mails open in a sandboxed frame without scripts; remote images only on request.
 * Uses the helpers of app.js: api, $, esc, toast, confirmBox, S. */
'use strict';

const WM = { me: null, folder: 'INBOX', page: 0, q: '', list: null, sel: null, msg: null, checked: new Set(), timer: null };
const wmT = s => (window.N8Kit && N8Kit.i18n ? N8Kit.i18n.t(s) : s);
const FOLDER_ICON = { inbox: '📥', drafts: '📝', sent: '📤', junk: '🚫', trash: '🗑️', '': '📁' };
const FOLDER_NAME = { inbox: 'Inbox', drafts: 'Drafts', sent: 'Sent', junk: 'Junk', trash: 'Trash' };

function wmDate(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000), now = new Date();
    const de = N8Kit.locale();
    if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString(de, { hour: '2-digit', minute: '2-digit' });
    if (now - d < 6 * 864e5) return d.toLocaleDateString(de, { weekday: 'short', hour: '2-digit', minute: '2-digit' });
    return d.toLocaleDateString(de, { day: '2-digit', month: '2-digit', year: '2-digit' });
}
function wmSize(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : n > 1024 ? Math.round(n / 1024) + ' KB' : n + ' B'; }
function wmFolderLabel(f) { return f.role && FOLDER_NAME[f.role] ? wmT(FOLDER_NAME[f.role]) : f.name; }

async function loadWebmail() {
    const el = $('wm');
    if (!WM.me) el.innerHTML = '<div class="tile dim">loading …</div>';
    try { WM.me = await api('GET', '/api/mail/me'); }
    catch (e) { el.innerHTML = `<div class="tile notice-box">⚠️ ${esc(e.message)}</div>`; return; }
    renderWmShell();
    await wmLoadList();
    clearInterval(WM.timer);
    WM.timer = setInterval(() => { if (S.tab === 'mail' && !document.hidden) wmRefresh(); }, 30000);
}
async function wmRefresh() {
    try { WM.me = await api('GET', '/api/mail/me'); renderWmFolders(); await wmLoadList(true); } catch (e) { }
}
function renderWmShell() {
    $('wm').innerHTML = `
    <aside class="wm-side tile">
        <button class="btn primary wm-new" id="wmNew">✏️ ${esc(wmT('Write'))}</button>
        <div class="wm-me"><b translate="no">${esc(WM.me.address)}</b>${WM.me.aliases.length ? `<div class="dim" translate="no">${WM.me.aliases.map(esc).join('<br>')}</div>` : ''}</div>
        <nav id="wmFolders"></nav>
        <div class="wm-quota" id="wmQuota"></div>
        <details class="wm-help"><summary>📱 ${esc(wmT('Mail program'))}</summary>
            <div class="dim">IMAP <code>${esc(WM.me.server.host)}</code> 993 SSL/TLS<br>SMTP <code>${esc(WM.me.server.host)}</code> 465 SSL/TLS · 587 STARTTLS<br>${esc(wmT('User: your address · password: your dashboard password'))}</div></details>
    </aside>
    <section class="wm-list tile">
        <div class="wm-tools"><input type="search" id="wmSearch" placeholder="🔎 ${esc(wmT('Search'))}" value="${esc(WM.q)}">
            <button class="btn small" id="wmReload" title="Reload">🔄</button></div>
        <div class="wm-bulk" id="wmBulk" hidden></div>
        <div id="wmItems"></div>
        <div class="wm-pager" id="wmPager"></div>
    </section>
    <section class="wm-read tile" id="wmRead"><div class="wm-empty">✉️ ${esc(wmT('Choose a message'))}</div></section>`;
    renderWmFolders();
    $('wmNew').onclick = () => wmCompose();
    $('wmReload').onclick = () => wmRefresh();
    let t; $('wmSearch').oninput = e => { clearTimeout(t); t = setTimeout(() => { WM.q = e.target.value.trim(); WM.page = 0; wmLoadList(); }, 400); };
}
function renderWmFolders() {
    $('wmFolders').innerHTML = WM.me.folders.map(f => `<button class="wm-folder ${f.name === WM.folder ? 'active' : ''}" data-f="${esc(f.name)}">
        <span>${FOLDER_ICON[f.role] || '📁'} ${esc(wmFolderLabel(f))}</span>${f.unseen ? `<span class="badge">${f.unseen}</span>` : ''}</button>`).join('');
    $('wmFolders').querySelectorAll('[data-f]').forEach(b => b.onclick = () => { WM.folder = b.dataset.f; WM.page = 0; WM.sel = null; WM.checked.clear(); renderWmFolders(); wmLoadList(); wmShowEmpty(); });
    const q = WM.me.quota;
    $('wmQuota').innerHTML = q ? `<div class="wm-qbar"><i style="width:${Math.min(100, q.used_kb / q.limit_kb * 100).toFixed(1)}%"></i></div>
        <div class="dim">${(q.used_kb / 1024).toFixed(1)} / ${(q.limit_kb / 1024).toFixed(0)} MB</div>` : '';
}
function wmShowEmpty() { $('wmRead').innerHTML = `<div class="wm-empty">✉️ ${esc(wmT('Choose a message'))}</div>`; $('wm').classList.remove('reading'); }
async function wmLoadList(quiet) {
    try { WM.list = await api('GET', `/api/mail/list?folder=${encodeURIComponent(WM.folder)}&page=${WM.page}&q=${encodeURIComponent(WM.q)}`); }
    catch (e) { if (!quiet) $('wmItems').innerHTML = `<div class="notice-box">⚠️ ${esc(e.message)}</div>`; return; }
    renderWmList();
}
function renderWmList() {
    const L = WM.list, sent = (WM.me.folders.find(f => f.name === WM.folder) || {}).role === 'sent';
    $('wmItems').innerHTML = L.items.length ? L.items.map(m => `<div class="wm-item ${m.seen ? '' : 'unseen'} ${WM.sel === m.uid ? 'active' : ''}" data-uid="${m.uid}">
        <input type="checkbox" class="wm-ck" data-uid="${m.uid}" ${WM.checked.has(m.uid) ? 'checked' : ''}>
        <div class="wm-who" translate="no">${esc(sent ? (m.to[0] || '') : (m.from.name || m.from.address))}</div>
        <div class="wm-when">${m.flagged ? '⭐ ' : ''}${m.attachment ? '📎 ' : ''}${esc(wmDate(m.date))}</div>
        <div class="wm-subj" translate="no">${m.answered ? '↩ ' : ''}${esc(m.subject)}</div></div>`).join('')
        : `<div class="wm-empty">📭 ${esc(wmT(WM.q ? 'Nothing found' : 'No messages'))}</div>`;
    const pages = Math.ceil(L.total / L.per);
    $('wmPager').innerHTML = pages > 1 ? `<button class="btn small" ${WM.page ? '' : 'disabled'} data-p="-1">‹</button><span class="dim">${WM.page + 1} / ${pages} · ${L.total}</span><button class="btn small" ${WM.page + 1 < pages ? '' : 'disabled'} data-p="1">›</button>`
        : `<span class="dim">${L.total} ${esc(wmT('messages'))}</span>`;
    $('wmPager').querySelectorAll('[data-p]').forEach(b => b.onclick = () => { WM.page += +b.dataset.p; wmLoadList(); });
    $('wmItems').querySelectorAll('.wm-item').forEach(it => it.onclick = e => { if (e.target.classList.contains('wm-ck')) return; wmOpen(+it.dataset.uid); });
    $('wmItems').querySelectorAll('.wm-ck').forEach(c => c.onchange = () => { c.checked ? WM.checked.add(+c.dataset.uid) : WM.checked.delete(+c.dataset.uid); renderWmBulk(); });
    renderWmBulk();
}
function renderWmBulk() {
    const n = WM.checked.size, b = $('wmBulk');
    b.hidden = !n;
    if (!n) return;
    b.innerHTML = `<span>${n} ${esc(wmT('selected'))}</span><button class="btn small" data-a="seen">✓ ${esc(wmT('read'))}</button><button class="btn small" data-a="unseen">● ${esc(wmT('unread'))}</button>
        <button class="btn small" data-a="spam">🚫 ${esc(wmT('Spam'))}</button><button class="btn small danger" data-a="delete">🗑️</button>`;
    b.querySelectorAll('[data-a]').forEach(x => x.onclick = () => wmAct(x.dataset.a, [...WM.checked]));
}
async function wmAct(action, uids) {
    try {
        await api('POST', '/api/mail/act', { folder: WM.folder, uids, action });
        WM.checked.clear();
        if (['delete', 'spam', 'inbox'].includes(action) && uids.includes(WM.sel)) { WM.sel = null; wmShowEmpty(); }
        await wmRefresh();
    } catch (e) { toast(e.message, true); }
}
async function wmOpen(uid) {
    WM.sel = uid; renderWmList();
    $('wm').classList.add('reading');
    $('wmRead').innerHTML = '<div class="wm-empty">…</div>';
    let m; try { m = await api('GET', `/api/mail/msg?folder=${encodeURIComponent(WM.folder)}&uid=${uid}`); } catch (e) { $('wmRead').innerHTML = `<div class="notice-box">⚠️ ${esc(e.message)}</div>`; return; }
    WM.msg = m;
    const chk = Object.entries(m.checks || {}).filter(([, v]) => v).map(([k, v]) => `<span class="badge ${v === 'pass' ? 'ok' : v === 'none' ? '' : 'err'}">${k.toUpperCase()} ${esc(v)}</span>`).join(' ');
    $('wmRead').innerHTML = `<div class="wm-rtools">
            <button class="btn small wm-back" id="wmBack">← ${esc(wmT('Back'))}</button>
            <button class="btn small" id="wmReply">↩ ${esc(wmT('Reply'))}</button><button class="btn small" id="wmReplyAll">↩↩ ${esc(wmT('Reply all'))}</button>
            <button class="btn small" id="wmFwd">↪ ${esc(wmT('Forward'))}</button><button class="btn small" id="wmFlag">⭐</button>
            <button class="btn small" id="wmSpam">${(WM.me.folders.find(f => f.name === WM.folder) || {}).role === 'junk' ? '📥 ' + esc(wmT('Not spam')) : '🚫 ' + esc(wmT('Spam'))}</button>
            <button class="btn small danger" id="wmDel">🗑️</button></div>
        <h2 class="wm-h" translate="no">${esc(m.subject || '(no subject)')}</h2>
        <div class="wm-meta" translate="no"><div><b>${esc(m.from)}</b></div><div class="dim">${esc(wmT('to'))} ${esc(m.to)}${m.cc ? ' · cc ' + esc(m.cc) : ''}</div>
            <div class="dim">${m.date ? esc(new Date(m.date * 1000).toLocaleString(N8Kit.locale())) : ''} ${chk}${m.spam ? ' <span class="badge warn">Spam</span>' : ''}</div></div>
        ${m.attachments.length ? `<div class="wm-atts">${m.attachments.map(a => `<a class="btn small" href="/api/mail/att?folder=${encodeURIComponent(WM.folder)}&uid=${m.uid}&part=${a.part}" translate="no">📎 ${esc(a.name)} <span class="dim">${wmSize(a.size)}</span></a>`).join('')}</div>` : ''}
        ${m.html ? `<div class="wm-htmlbar"><button class="btn small" id="wmText">📝 Text</button><button class="btn small" id="wmHtml">🌐 HTML</button><button class="btn small" id="wmImg" hidden>🖼️ ${esc(wmT('Load images'))}</button></div>` : ''}
        <div class="wm-body" id="wmBody"></div>`;
    const showText = () => { $('wmBody').innerHTML = `<pre class="wm-text" translate="no">${esc(m.text || '')}</pre>`; if ($('wmImg')) $('wmImg').hidden = true; };
    const showHtml = images => {
        $('wmBody').innerHTML = `<iframe class="wm-frame" sandbox="allow-popups allow-popups-to-escape-sandbox" referrerpolicy="no-referrer"
            src="/api/mail/html?folder=${encodeURIComponent(WM.folder)}&uid=${m.uid}&images=${images ? 1 : 0}"></iframe>`;
        if ($('wmImg')) $('wmImg').hidden = images;
    };
    if (m.html) { $('wmText').onclick = showText; $('wmHtml').onclick = () => showHtml(false); $('wmImg').onclick = () => showHtml(true); showHtml(false); } else showText();
    $('wmBack').onclick = () => { WM.sel = null; wmShowEmpty(); renderWmList(); };
    $('wmReply').onclick = () => wmCompose('reply'); $('wmReplyAll').onclick = () => wmCompose('all'); $('wmFwd').onclick = () => wmCompose('fwd');
    $('wmFlag').onclick = () => wmAct('flag', [uid]);
    $('wmSpam').onclick = () => wmAct((WM.me.folders.find(f => f.name === WM.folder) || {}).role === 'junk' ? 'inbox' : 'spam', [uid]);
    $('wmDel').onclick = () => wmAct('delete', [uid]);
    if (!WM.list.items.find(x => x.uid === uid)?.seen) setTimeout(wmRefresh, 400);
}
function wmQuote(m) {
    return '\n\n' + wmT('On') + ' ' + (m.date ? new Date(m.date * 1000).toLocaleString(N8Kit.locale()) : '') + ', ' + m.from + ':\n' + (m.text || '').split('\n').map(l => '> ' + l).join('\n');
}
function wmCompose(kind) {
    const m = WM.msg;
    let to = '', cc = '', subject = '', text = '', irt = '', refs = '';
    if (kind && m) {
        const re = s => /^(re|aw|antw):/i.test(s) ? s : 'Re: ' + s;
        if (kind === 'fwd') { subject = /^(fwd?|wg):/i.test(m.subject) ? m.subject : 'Fwd: ' + m.subject; text = `\n\n-------- ${wmT('Forwarded message')} --------\nFrom: ${m.from}\nTo: ${m.to}\nSubject: ${m.subject}\n\n${m.text || ''}`; }
        else {
            to = m.reply_to || m.from; subject = re(m.subject || ''); text = wmQuote(m); irt = m.message_id; refs = m.references;
            if (kind === 'all') cc = [m.to, m.cc].filter(Boolean).join(', ').split(',').map(x => x.trim()).filter(x => x && !x.toLowerCase().includes(WM.me.address)).join(', ');
        }
    }
    const atts = [];
    modal(`<h3>✏️ ${esc(wmT(kind === 'fwd' ? 'Forward' : kind ? 'Reply' : 'New message'))}</h3>
        <form id="wmForm" class="wm-compose" onsubmit="event.preventDefault()">
            <div class="row"><label>${esc(wmT('From'))}</label><div translate="no"><b>${esc(WM.me.name)}</b> &lt;${esc(WM.me.address)}&gt;</div></div>
            <div class="row"><label for="wcTo">${esc(wmT('To'))}</label><input type="text" id="wcTo" value="${esc(to)}" placeholder="name@example.org, …" translate="no"></div>
            <div class="row"><label for="wcCc">Cc</label><input type="text" id="wcCc" value="${esc(cc)}" translate="no"></div>
            <div class="row"><label for="wcBcc">Bcc</label><input type="text" id="wcBcc" translate="no"></div>
            <div class="row"><label for="wcSubj">${esc(wmT('Subject'))}</label><input type="text" id="wcSubj" value="${esc(subject)}" translate="no"></div>
            <textarea id="wcText" translate="no">${esc(text)}</textarea>
            <div class="wm-catts" id="wcAtts"></div>
            <div class="actions"><label class="btn">📎 ${esc(wmT('Attach'))}<input type="file" id="wcFile" multiple hidden></label><span class="grow"></span>
                <button type="button" class="btn" onclick="closeModal()">${esc(wmT('Cancel'))}</button><button type="button" class="btn primary" id="wcSend">📤 ${esc(wmT('Send'))}</button></div>
        </form>`, false, true);
    const paintAtts = () => { $('wcAtts').innerHTML = atts.map((a, i) => `<span class="badge">📎 ${esc(a.name)} · ${wmSize(a.size)} <a href="#" data-i="${i}">✕</a></span>`).join(' ');
        $('wcAtts').querySelectorAll('[data-i]').forEach(x => x.onclick = e => { e.preventDefault(); atts.splice(+x.dataset.i, 1); paintAtts(); }); };
    $('wcFile').onchange = async e => {
        for (const f of e.target.files) {
            if (atts.reduce((s, a) => s + a.size, 0) + f.size > 20 * 1048576) { toast(wmT('Attachments larger than 20 MB.'), true); break; }
            const data = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(String(fr.result).split(',')[1]); fr.readAsDataURL(f); });
            atts.push({ name: f.name, type: f.type || 'application/octet-stream', size: f.size, data });
        }
        e.target.value = ''; paintAtts();
    };
    $('wcSend').onclick = async e => {
        e.target.disabled = true;
        try {
            const r = await api('POST', '/api/mail/send', { to: $('wcTo').value, cc: $('wcCc').value, bcc: $('wcBcc').value, subject: $('wcSubj').value,
                text: $('wcText').value, in_reply_to: irt, references: refs, attachments: atts,
                reply_folder: kind && kind !== 'fwd' ? WM.folder : '', reply_uid: kind && kind !== 'fwd' && m ? m.uid : 0 });
            closeModal(); toast('📤 ' + (r.message || 'Sent')); wmRefresh();
        } catch (x) { toast(x.message, true); e.target.disabled = false; }
    };
    (to ? $('wcText') : $('wcTo')).focus();
    if (to) { $('wcText').setSelectionRange(0, 0); }
}
window.loadWebmail = loadWebmail;
