/* adn-frn-server – Admin → ✉️ E-Mail (N8 Mail) and 🌐 Netz → ✉️ Mail domains.
 * Uses the helpers of app.js: api, $, esc, toast, confirmBox, fieldHtml, formValues, fmtDate, S, showAdmin. */
'use strict';

const MAIL = { view: null, out: '' };
const MAIL_SRV_KEYS = ['mail.enabled', 'mail.relay_host', 'mail.relay_port', 'mail.relay_tls', 'mail.relay_user', 'mail.relay_password', 'mail.relay_spf',
    'mail.inbound_tls', 'mail.quota_mb', 'mail.max_size_mb', 'mail.postmaster', 'mail.spam_junk', 'mail.spam_reject'];
const MAIL_DMARC_KEYS = ['mail.dkim_selector', 'mail.dmarc_policy', 'mail.dmarc_alignment', 'mail.dmarc_rua', 'mail.bimi', 'mail.bimi_vmc', 'mail.mta_sts'];

async function mailView(force) {
    if (!MAIL.view || force) MAIL.view = await api('GET', '/api/admin/mail');
    return MAIL.view;
}
const isSuper = () => S.me && S.me.role === 'superadmin';
function mailFields(keys) { return keys.map(k => (MAIL.view.fields || []).find(f => f.key === k)).filter(Boolean); }
function svcBadge(name, st) {
    const ok = st === 'active';
    return `<span class="badge ${ok ? 'ok' : st === 'inactive' || st === 'unknown' ? 'warn' : 'err'}">${ok ? '●' : '○'} ${esc(name)} · ${esc(st || '–')}</span>`;
}
function mailWarnings(v) {
    return (v.warnings || []).map(w => `<div class="notice-box">⚠️ ${esc(w)}</div>`).join('');
}
async function saveMailForm(form, after) {
    try {
        const r = await api('POST', '/api/admin/mail/settings', { changes: formValues(form) });
        toast(r.message || 'Saved');
        await mailView(true);
        if (after) after();
    } catch (e) { toast(e.message, true); }
}
async function mailAction(act, btn) {
    if (act === 'disable' && !await confirmBox({ title: 'Switch the mail server off?', body: 'Dovecot and Rspamd stop, Postfix gets its configuration from before N8 Mail. Mailboxes and DKIM keys stay on the disk.' }, 'Switch off')) return;
    if (act === 'install' && !await confirmBox({ title: 'Install the mail server?', body: 'postfix, dovecot-imapd, dovecot-lmtpd, dovecot-sieve and rspamd are installed with apt and set up – this takes a few minutes.' }, 'Install')) return;
    const old = btn.textContent; btn.disabled = true; btn.textContent = '⏳ …';
    const out = $('mailOut'); if (out) { out.hidden = false; out.textContent = 'Running – this can take a few minutes …'; }
    try {
        const r = await api('POST', '/api/admin/mail/action', { action: act });
        MAIL.view = r.view; MAIL.out = (r.message || '') + (r.log ? '\n\n' + r.log : '');
        toast((r.ok === false ? '⚠️ ' : '✅ ') + (r.message || act), r.ok === false);
        renderMailSrv();
    } catch (e) { toast(e.message, true); btn.disabled = false; btn.textContent = old; if (out) out.textContent = e.message; }
}

// ---------------------------------------------------------------- 📮 Mail server
async function loadMailSrv() { await mailView(true); renderMailSrv(); }
function renderMailSrv() {
    const v = MAIL.view, st = v.state || {}, sv = st.services || {}, la = st.last_apply, c = st.cert || {};
    const inst = !!st.installed, conf = !!st.configured, main = (v.domains || [])[0];
    const kv = (k, val) => `<div class="row"><label>${esc(k)}</label><div>${val}</div></div>`;
    $('admin-mailsrv').innerHTML = `<div class="tiles tiles-even">
      <div class="tile">
        <h3>📮 Mail server</h3>
        <div class="subt">Postfix (SMTP) · Dovecot (IMAP) · Rspamd (spam, DKIM, SPF/DMARC check) on this machine. Every dashboard user has a mailbox with the same password.</div>
        ${mailWarnings(v)}
        <div class="mail-svcs">${['postfix', 'dovecot', 'rspamd'].map(u => svcBadge(u, sv[u] || (inst ? 'unknown' : 'not installed'))).join(' ')}</div>
        ${kv('Installed', inst ? `✅ ${esc(Object.entries(st.versions || {}).map(([k, x]) => k + ' ' + x).join(' · '))}` : '<span class="dim">no</span>')}
        ${kv('Configured', conf ? '✅ yes' : '<span class="dim">not yet</span>')}
        ${kv('Mail domains', (v.domains || []).length ? v.domains.map(d => `<code>${esc(d)}</code>`).join(' ') : '<span class="dim">none</span> <button class="btn small" onclick="showAdmin(\'maildomains\')">✉️ Mail domains</button>')}
        ${kv('Certificate', c.names ? `${c.days != null ? `<span class="badge ${c.days < 14 ? 'err' : 'ok'}">${c.days} days</span> ` : ''}<span class="dim">${esc((c.names || []).filter(n => n.startsWith('mail.') || n.startsWith('mta-sts.')).join(', ') || '–')}</span>` : '<span class="dim">–</span>')}
        ${kv('Queue', st.queue != null ? `${st.queue} waiting` : '–')}
        ${kv('Mailboxes', `${(v.boxes || []).filter(b => b.ready && !b.disabled).length} active${st.storage_kb != null ? ` · ${(st.storage_kb / 1024).toFixed(1)} MB` : ''}`)}
        ${kv('Last apply', la ? `${la.ok ? '✅' : '⚠️'} ${esc(fmtDate(la.time))} · ${la.mailboxes} mailboxes` : '<span class="dim">never</span>')}
        ${kv('Status checked', st.time ? esc(fmtDate(st.time)) : '<span class="dim">never</span>')}
        <div class="actions" style="justify-content:flex-start">
          <button class="btn small" id="mailStatusBtn">🔄 Check status</button>
          ${inst ? `<button class="btn small primary" id="mailApplyBtn">✅ Apply</button>` : ''}
          ${isSuper() && !inst ? '<button class="btn small primary" id="mailInstallBtn">⚙️ Install mail server</button>' : ''}
          ${isSuper() && inst ? '<button class="btn small" id="mailInstallBtn">⚙️ Install again / repair</button>' : ''}
          ${isSuper() && conf ? '<button class="btn small danger" id="mailOffBtn">⏻ Switch off</button>' : ''}
        </div>
        <pre class="log mail-out" id="mailOut" ${MAIL.out ? '' : 'hidden'}>${esc(MAIL.out)}</pre>
      </div>
      <form class="tile" id="mailSrvForm" onsubmit="event.preventDefault(); saveMailForm(this, renderMailSrv)">
        <h3>🔁 Upstream, TLS & limits</h3>
        <div class="subt">Outgoing mail goes through the server of your provider (smarthost) – always encrypted. Mail programs only connect with TLS.</div>
        ${mailFields(MAIL_SRV_KEYS).map(fieldHtml).join('')}
        <div class="actions"><button class="btn primary">Save</button></div>
      </form>
      <div class="tile">
        <h3>📱 Mail programs</h3>
        <div class="subt">Thunderbird, Outlook, Apple Mail, K-9/FairEmail … – user name is the e-mail address (or the dashboard user name), the password the dashboard password.</div>
        ${main ? `<table class="tbl mail-client"><tbody>
          <tr><td>Incoming (IMAP)</td><td><code>mail.${esc(main)}</code></td><td>993</td><td><span class="badge ok">SSL/TLS</span></td></tr>
          <tr><td>Outgoing (SMTP)</td><td><code>mail.${esc(main)}</code></td><td>465</td><td><span class="badge ok">SSL/TLS</span></td></tr>
          <tr><td>or</td><td><code>mail.${esc(main)}</code></td><td>587</td><td><span class="badge ok">STARTTLS</span></td></tr>
          <tr><td>Authentication</td><td colspan="3">normal password</td></tr></tbody></table>
          <div class="dim" style="margin-top:8px">Mail programs find the settings by themselves through the SRV records (🧾 DNS templates). Unencrypted IMAP (143) is off.</div>`
        : '<div class="dim">Enter a mail domain first.</div>'}
        <h3 style="margin-top:16px">🔐 Security</h3>
        <ul class="mail-list">
          <li>Only TLS 1.2+: IMAPS 993, SMTPS 465, submission 587 (STARTTLS required), login only after TLS.</li>
          <li>Port 25: STARTTLS offered${v.fields && (v.fields.find(f => f.key === 'mail.inbound_tls') || {}).value ? ' and <b>required</b>' : ''}; SPF, DKIM and DMARC of incoming mail are checked, spam goes to “Junk”.</li>
          <li>Outgoing: DKIM signature for every domain, upstream only encrypted with a checked certificate.</li>
          <li>Users send only with their own address (or their aliases).</li>
          <li>Passwords: Dovecot only gets a SHA512-CRYPT hash; the webmail uses its own master access, never the user's password.</li>
        </ul>
      </div></div>`;
    $('mailStatusBtn').onclick = e => mailAction('status', e.target);
    if ($('mailApplyBtn')) $('mailApplyBtn').onclick = e => mailAction('apply', e.target);
    if ($('mailInstallBtn')) $('mailInstallBtn').onclick = e => mailAction('install', e.target);
    if ($('mailOffBtn')) $('mailOffBtn').onclick = e => mailAction('disable', e.target);
}

// ---------------------------------------------------------------- 📬 Mailboxes
async function loadMailboxes() {
    const v = await mailView(true);
    const row = b => `<tr class="${b.disabled ? 'news-draft' : ''}"><td><b>${esc(b.address || b.local)}</b>${b.aliases.length ? `<div class="dim">${b.aliases.map(esc).join(', ')}</div>` : ''}</td>
        <td>${esc(b.username)}${b.display_name ? `<div class="dim">${esc(b.display_name)}</div>` : ''}</td>
        <td><span class="badge">${esc(b.role)}</span></td>
        <td>${b.disabled ? '<span class="badge warn">locked</span>' : b.ready ? '<span class="badge ok">active</span>' : '<span class="badge warn">waits for login</span>'}
            ${b.address === v.postmaster ? ' <span class="badge">📮 postmaster</span>' : ''}</td></tr>`;
    $('admin-mailboxes').innerHTML = `<div class="tile">
        <h3>📬 Mailboxes</h3>
        <div class="subt">Every dashboard user automatically has a mailbox – the user name is the address, the password the dashboard password. New users, new passwords, locked or deleted users reach the mail server by themselves.</div>
        ${(v.boxes || []).some(b => !b.ready) ? '<div class="notice-box">⏳ “waits for login”: users from before the mail server have no mail password yet – it is made at their next login to the dashboard (or when an admin sets a new password).</div>' : ''}
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Address</th><th>User</th><th>Role</th><th>Status</th></tr></thead>
        <tbody>${(v.boxes || []).map(row).join('') || '<tr><td colspan="4" class="dim">No mail domain yet.</td></tr>'}</tbody></table></div>
        ${(v.skipped || []).length ? `<h3 style="margin-top:14px">Without a mailbox</h3><div class="tbl-wrap"><table class="tbl"><tbody>${v.skipped.map(x => `<tr><td>${esc(x.username)}</td><td class="dim">${esc(x.reason)}</td></tr>`).join('')}</tbody></table></div>` : ''}
        <div class="dim" style="margin-top:10px">Role addresses postmaster@, abuse@, hostmaster@, dmarc@ and tls-reports@ of every domain go to ${v.postmaster ? `<b>${esc(v.postmaster)}</b>` : 'the superadmin'}.</div>
        <div class="actions" style="justify-content:flex-start"><button class="btn" onclick="showAdmin('users')">👥 Users</button><button class="btn" onclick="showAdmin('mailsrv')">📮 Mail server</button></div>
    </div>`;
}

// ---------------------------------------------------------------- 🛡️ DMARC & BIMI
async function loadMailDmarc() {
    const v = await mailView(true);
    let b = {}; try { b = await api('GET', '/api/admin/mail/bimi'); } catch (e) { b = { svg: '', problems: [e.message], urls: {} }; }
    const dk = (v.state || {}).dkim || {};
    $('admin-maildmarc').innerHTML = `<div class="tiles tiles-even">
      <form class="tile" id="mailDmarcForm" onsubmit="event.preventDefault(); saveMailForm(this, loadMailDmarc)">
        <h3>🛡️ DKIM, DMARC & MTA-STS</h3>
        <div class="subt">The server signs every outgoing mail (DKIM), checks SPF, DKIM and DMARC of incoming mail and tells others how to treat forged mail. The DNS records are made for you under 🧾 DNS templates.</div>
        ${mailFields(MAIL_DMARC_KEYS).map(fieldHtml).join('')}
        <div class="actions"><button type="button" class="btn" onclick="showAdmin('maildns')">🧾 DNS templates</button><button class="btn primary">Save</button></div>
        <h3 style="margin-top:14px">🔑 DKIM keys</h3>
        ${(v.domains || []).map(d => `<div class="row"><label><code>${esc(d)}</code></label><div>${dk[d] ? '<span class="badge ok">key ready (RSA 2048)</span>' : '<span class="badge warn">made at the next „Apply“</span>'}</div></div>`).join('') || '<div class="dim">No mail domain yet.</div>'}
      </form>
      <div class="tile">
        <h3>🏷️ BIMI logo</h3>
        <div class="subt">Your logo next to your mails in Gmail, Yahoo, Apple Mail … Needs DMARC quarantine or reject; Gmail and Apple also want a VMC/CMC certificate. The logo must be SVG Tiny PS – the server checks it and serves it under /.well-known/bimi/.</div>
        <div class="bimi-wrap"><div class="bimi-prev">${b.svg ? `<img alt="BIMI" src="data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(b.svg)))}">` : ''}</div>
          <div class="bimi-info">${(b.problems || []).length ? `<div class="notice-box">⚠️ ${b.problems.map(esc).join('<br>')}</div>` : '<span class="badge ok">✓ SVG Tiny PS</span>'}
            <div class="dim" style="margin-top:6px">${b.own ? 'own logo' : 'made automatically from the title'}</div>
            ${Object.entries(b.urls || {}).map(([d, u]) => `<div class="dim" style="font-size:12px"><a href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a></div>`).join('')}</div></div>
        <div class="row"><label for="bimiText">Letters</label><input type="text" id="bimiText" maxlength="3" placeholder="N8"></div>
        <div class="row"><label for="bimiAccent">Colour</label><input type="color" id="bimiAccent" value="#5ac8fa"></div>
        <div class="actions" style="justify-content:flex-start">
          <button class="btn" id="bimiGen">✨ Make logo</button>
          <label class="btn">📤 Upload SVG<input type="file" id="bimiFile" accept=".svg,image/svg+xml" hidden></label>
          ${b.own ? '<button class="btn" id="bimiReset">↺ Standard</button>' : ''}</div>
      </div></div>`;
    $('bimiGen').onclick = async () => {
        try { await api('POST', '/api/admin/mail/bimi', { generate: true, text: $('bimiText').value, accent: $('bimiAccent').value }); toast('✅ BIMI logo made'); loadMailDmarc(); }
        catch (e) { toast(e.message, true); }
    };
    $('bimiFile').onchange = async e => {
        const f = e.target.files[0]; if (!f) return;
        try { await api('POST', '/api/admin/mail/bimi', { svg: await f.text() }); toast('✅ BIMI logo saved'); loadMailDmarc(); } catch (x) { toast(x.message, true); }
    };
    if ($('bimiReset')) $('bimiReset').onclick = async () => { await api('POST', '/api/admin/mail/bimi', { reset: true }); loadMailDmarc(); };
}

// ---------------------------------------------------------------- 🧾 DNS templates
async function loadMailDns(check) {
    const el = $('admin-maildns');
    if (!check) el.innerHTML = '<div class="tile"><div class="dim">loading …</div></div>';
    let d; try { d = await api('GET', '/api/admin/mail/dns' + (check ? '?check=1' : '')); } catch (e) { el.innerHTML = `<div class="tile notice-box">⚠️ ${esc(e.message)}</div>`; return; }
    MAIL.dns = d;
    const ck = r => !r.check ? '' : r.check.status === 'ok' ? '<span class="badge ok">✓ set</span>'
        : r.check.status === 'skip' ? '<span class="badge">–</span>'
        : r.check.status === 'diff' ? `<span class="badge err" title="${esc((r.check.found || []).join(' | '))}">≠ differs</span>` : '<span class="badge warn">missing</span>';
    const card = t => `<div class="tile mail-dns">
        <div class="news-head"><div><h3>🧾 ${esc(t.domain)}</h3><div class="subt">Mail server <code>${esc(t.host)}</code> · enter these records at your DNS provider. Required ones first; the PTR (reverse DNS) is set at your hosting provider.</div></div>
          <div class="actions" style="margin:0"><button class="btn small" data-copyzone="${esc(t.domain)}">📋 Copy all</button><button class="btn small" data-zone="${esc(t.domain)}">⬇ Zone file</button></div></div>
        <div class="tbl-wrap"><table class="tbl dns-tbl"><thead><tr><th>Type</th><th>Name</th><th>Value</th><th>Purpose</th>${d.checked ? '<th>DNS</th>' : ''}</tr></thead><tbody>
        ${t.records.map((r, i) => `<tr class="${r.required ? '' : 'dns-opt'}"><td><span class="badge">${esc(r.type)}</span>${r.priority != null ? ` <span class="dim">${r.priority}</span>` : ''}</td>
            <td class="dns-name"><code>${esc(r.name)}</code></td>
            <td class="dns-val"><code>${esc(r.value)}</code> <button class="btn small" data-copy="${esc(t.domain)}|${i}" title="Copy">📋</button></td>
            <td class="dim">${esc(r.why)}${r.required ? '' : ' <span class="badge">optional</span>'}</td>${d.checked ? `<td>${ck(r)}</td>` : ''}</tr>`).join('')}
        </tbody></table></div></div>`;
    el.innerHTML = `<div class="tile"><h3>🧾 DNS templates</h3>
        <div class="subt">Made from your settings: MX, A/AAAA, SPF${'' /* */}, DKIM (the public key appears after „Apply“), DMARC, BIMI, MTA-STS, TLS-RPT and SRV records for mail programs. „Check DNS“ asks the DNS what is set right now.</div>
        <div class="actions" style="justify-content:flex-start"><button class="btn primary" id="dnsCheck">🔎 Check DNS now</button><button class="btn" onclick="showAdmin('maildomains')">✉️ Mail domains</button></div></div>
        ${d.templates.length ? d.templates.map(card).join('') : '<div class="tile dim">No mail domain yet.</div>'}`;
    $('dnsCheck').onclick = e => { e.target.disabled = true; e.target.textContent = '🔎 …'; loadMailDns(true); };
    el.querySelectorAll('[data-copy]').forEach(b => b.onclick = () => {
        const [dom, i] = b.dataset.copy.split('|'); const r = d.templates.find(t => t.domain === dom).records[+i];
        navigator.clipboard.writeText(r.value).then(() => toast('📋 Copied'));
    });
    el.querySelectorAll('[data-copyzone]').forEach(b => b.onclick = () => navigator.clipboard.writeText(d.zones[b.dataset.copyzone]).then(() => toast('📋 Copied')));
    el.querySelectorAll('[data-zone]').forEach(b => b.onclick = () => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([d.zones[b.dataset.zone]], { type: 'text/plain' }));
        a.download = `${b.dataset.zone}.n8mail.zone.txt`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    });
}

// ---------------------------------------------------------------- 🌐 Netz → ✉️ Mail domains
async function loadMailDomains() {
    const v = await mailView(true);
    const doms = v.domains || [];
    const have = new Set(((v.state || {}).cert || {}).names || []);
    const wait = new Set(v.dns_waiting || []);
    const autoF = (v.fields || []).find(f => f.key === 'mail.auto_domains');
    $('admin-maildomains').innerHTML = `<div class="tiles tiles-even">
      <div class="tile">
        <h3>✉️ Mail domains</h3>
        <div class="subt">The first domain is the main domain (user@main-domain); every further domain is an alias for the same mailboxes. Each domain gets mail.&lt;domain&gt; on the Let's Encrypt certificate of the dashboard – the mail server uses only TLS.</div>
        ${mailWarnings(v)}
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Domain</th><th>Mail server</th><th>Certificate</th><th></th></tr></thead><tbody>
        ${doms.map((d, i) => `<tr><td><b>${esc(d)}</b> ${i === 0 ? '<span class="badge">main domain</span>' : ''}</td><td><code>mail.${esc(d)}</code></td>
            <td>${have.has('mail.' + d) ? '<span class="badge ok">✓ in the certificate</span>' : wait.has('mail.' + d) ? '<span class="badge warn">⏳ waits for DNS</span>' : '<span class="badge warn">not yet</span>'}</td>
            <td class="news-act">${i > 0 ? `<button class="btn small" data-up="${i}" title="Make main domain">⬆</button>` : ''}<button class="btn small danger" data-rm="${i}">Remove</button></td></tr>`).join('')
            || '<tr><td colspan="4" class="dim">No mail domain yet.</td></tr>'}</tbody></table></div>
        <div class="mail-add"><input type="text" id="mailDomNew" placeholder="example.org" autocomplete="off"><button class="btn primary" id="mailDomAdd">➕ Add mail domain</button></div>
        <form id="mailAutoForm" class="mail-auto" onsubmit="event.preventDefault(); saveMailForm(this, loadMailDomains)">${autoF ? fieldHtml(autoF) : ''}
          <div class="actions" style="justify-content:flex-start"><button class="btn small">Save</button><button type="button" class="btn small primary" id="mailAutoNow">🔄 Check now</button></div></form>
        <div class="dim" style="margin-top:8px">Fully automatic: new domains under 🔒 Domains &amp; HTTPS become mail domains, mail.&lt;domain&gt; gets on the Let's Encrypt certificate as soon as its DNS points to this server (checked every 30 minutes, without a restart), and the mail server takes it over by itself.</div>
        ${(v.auto_skip || []).length ? `<div class="dim" style="margin-top:6px">Removed by hand, not added again: ${v.auto_skip.map(esc).join(', ')}</div>` : ''}
      </div>
      <div class="tile">
        <h3>🧭 Order</h3>
        <ol class="mail-list">
          <li>DNS: mail.&lt;domain&gt; (A/AAAA) → this server; MX → mail.&lt;domain&gt;.</li>
          <li>🔒 Domains & HTTPS: the dashboard has its domain and HTTPS is on.</li>
          <li>Add the mail domain here (or let it be added automatically) – the certificate is extended by itself as soon as the DNS is right.</li>
          <li>📮 Mail server: ⚙️ Install, upstream, ✅ Apply.</li>
          <li>🧾 DNS templates: SPF, DKIM, DMARC, BIMI … at the DNS provider, PTR at the hosting provider.</li>
          <li>🔌 Ports: 25, 465, 587, 993 open in firewall and router.</li>
        </ol>
        <div class="actions" style="justify-content:flex-start"><button class="btn" onclick="showAdmin('domains')">🔒 Domains & HTTPS</button><button class="btn" onclick="showAdmin('maildns')">🧾 DNS templates</button><button class="btn" onclick="showAdmin('mailsrv')">📮 Mail server</button></div>
      </div></div>`;
    const save = async list => {
        try { const r = await api('POST', '/api/admin/mail/settings', { changes: { 'mail.domains': list.join(', ') } }); toast(r.message || 'Saved'); loadMailDomains(); }
        catch (e) { toast(e.message, true); }
    };
    $('mailAutoNow').onclick = async e => {
        e.target.disabled = true; e.target.textContent = '⏳ …';
        try { const r = await api('POST', '/api/admin/mail/auto', {}); MAIL.view = r.view; toast('✅ ' + r.message); loadMailDomains(); }
        catch (x) { toast(x.message, true); e.target.disabled = false; }
    };
    $('mailDomAdd').onclick = () => {
        const d = $('mailDomNew').value.trim().toLowerCase().replace(/^mail\./, '').replace(/\.$/, '');
        if (!/^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$/.test(d)) { toast('Not a valid domain', true); return; }
        if (doms.includes(d)) { toast('Already there', true); return; }
        save([...doms, d]);
    };
    $('admin-maildomains').querySelectorAll('[data-rm]').forEach(b => b.onclick = async () => {
        const d = doms[+b.dataset.rm];
        if (!await confirmBox({ title: `Remove ${d}?`, body: 'Addresses of this domain stop receiving mail after the next „Apply“. Mailboxes and mails stay.' }, 'Remove')) return;
        save(doms.filter((x, i) => i !== +b.dataset.rm));
    });
    $('admin-maildomains').querySelectorAll('[data-up]').forEach(b => b.onclick = () => { const i = +b.dataset.up; save([doms[i], ...doms.filter((x, j) => j !== i)]); });
}
