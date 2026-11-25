/*
 * N8 Kit 1.1.0 – shared by the N8schicht web interfaces
 * (HobbyRadioPortal, N8 Crosslink, HBlink4-FreeRadioID, adn-frn-server, N8-HotSpot).
 * The same file is in every repository; change it in one, copy it to the others.
 *
 *   N8Kit.lang()                 'de' | 'en'   (cookie n8_lang, valid for every port of the host → all four pages)
 *   N8Kit.setLang('en')          switch without reloading
 *   N8Kit.i18n.add({ base: 'en', de: { 'Last heard': 'Zuletzt gehört' }, rules: [[/^(\d+) stations$/, '$1 Stationen']] })
 *   N8Kit.t('text')              translate one string (for alert/confirm, canvas, …)
 *   N8Kit.langSwitch(container)  DE | EN switch (put into the header, next to Links/Login)
 *   N8Kit.update.banner(el, state, handlers)   update banner under the status strip
 *   N8Kit.update.panel(el, state, handlers)    Admin → Updates
 *   N8Kit.update.run(opts)                     install with progress, health check and reload
 *   N8Kit.nav.tree(el, groups, opts)           admin menu as a tree on the left (same structure in every N8 system)
 *   N8Kit.sys.view(el, name, opts)             the same System views everywhere: update, services, perms, keepalive
 *
 * Translation works on the finished page: text nodes and the attributes title, placeholder, aria-label
 * and alt are looked up in the dictionary of the page language (exact text, then without leading
 * emoji/symbols and trailing punctuation, then the rules). New content is translated as it appears.
 * Elements with translate="no", class "notranslate", <code>, <pre>, <script>, <style>, <textarea> stay as they are.
 */
(function () {
    'use strict';
    if (window.N8Kit) return;
    const COOKIE = 'n8_lang';
    const LANGS = ['de', 'en'];
    const SKIP = new Set(['SCRIPT', 'STYLE', 'CODE', 'PRE', 'TEXTAREA', 'NOSCRIPT', 'SVG', 'KBD', 'SAMP']);
    const ATTRS = ['title', 'placeholder', 'aria-label', 'alt', 'data-label'];
    const ORIG = '__n8o', DONE = '__n8t';

    // ------------------------------------------------------------ language
    function readCookie() {
        const m = document.cookie.match(/(?:^|;\s*)n8_lang=(de|en)\b/);
        return m ? m[1] : null;
    }
    let lang = readCookie();
    if (!lang) { try { lang = localStorage.getItem(COOKIE); } catch (e) { } }
    if (LANGS.indexOf(lang) < 0) lang = 'de';
    const q = (location.search.match(/[?&]lang=(de|en)\b/) || [])[1];
    if (q) lang = q;

    // ------------------------------------------------------------ dictionary
    const packs = [];   // {base, map: Map, rules: [[re, repl]]} per target language
    const cache = new Map();
    function add(pack) {
        const base = pack.base || 'en';
        LANGS.forEach(l => {
            if (l === base || !pack[l]) return;
            const map = new Map();
            Object.keys(pack[l]).forEach(k => map.set(norm(k), pack[l][k]));
            packs.push({ base, to: l, map, rules: Array.isArray(pack.rules) ? pack.rules : ((pack.rules && pack.rules[l]) || []) });
        });
        cache.clear();
        if (started) retranslate();
    }
    function norm(s) { return String(s).replace(/\s+/g, ' ').trim(); }
    const SPLIT = /^([^\p{L}0-9"'„(\[]*)([\s\S]*?)([\s:：…·.,!?)\]*▾›]*)$/u;

    function lookup(core) {
        for (let i = packs.length - 1; i >= 0; i--) {
            const p = packs[i];
            if (p.to !== lang) continue;
            if (p.map.has(core)) return p.map.get(core);
        }
        for (let i = packs.length - 1; i >= 0; i--) {
            const p = packs[i];
            if (p.to !== lang) continue;
            for (const [re, rep] of p.rules) {
                if (re.test(core)) { re.lastIndex = 0; return core.replace(re, typeof rep === 'function' ? rep : rep); }
            }
        }
        return null;
    }
    function t(s) {
        if (s == null) return s;
        s = String(s);
        if (!packs.some(p => p.to === lang) || !/\p{L}/u.test(s)) return s;
        const key = lang + '\u0000' + s;
        if (cache.has(key)) return cache.get(key);
        if (s.indexOf('\n') >= 0) {
            // a paragraph written over several source lines counts as one text; otherwise line by line
            const whole = lookup(norm(s));
            const out = whole != null ? s.match(/^\s*/)[0] + whole + s.match(/\s*$/)[0] : s.split('\n').map(t).join('\n');
            cache.set(key, out);
            return out;
        }
        let out = s;
        const lead = s.match(/^\s*/)[0], trail = s.match(/\s*$/)[0];
        const n = norm(s);
        let r = lookup(n);
        if (r == null) {
            const m = n.match(SPLIT);
            if (m && m[2]) {
                let c = lookup(m[2]);
                if (c != null) r = m[1] + c + m[3];
                else if (m[3] && (c = lookup(m[2] + m[3].trim())) != null) r = m[1] + c + (m[3].match(/\s*$/) || [''])[0];
            }
        }
        if (r != null) out = lead + r + trail;
        if (cache.size > 20000) cache.clear();
        cache.set(key, out);
        return out;
    }

    // ------------------------------------------------------------ DOM
    function skipEl(el) {
        for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
            if (SKIP.has(e.tagName.toUpperCase()) || e.getAttribute('translate') === 'no' || e.classList.contains('notranslate') || e.isContentEditable) return true;
        }
        return false;
    }
    function doText(node) {
        const cur = node.data;
        if (node[DONE] !== cur) node[ORIG] = cur;        // changed by the page → new original
        const o = node[ORIG];
        if (o == null || !/\p{L}/u.test(o)) return;
        const v = t(o);
        node[DONE] = v;
        if (v !== cur) node.data = v;
    }
    function doAttrs(el) {
        for (const a of ATTRS) {
            if (!el.hasAttribute(a)) continue;
            const cur = el.getAttribute(a), k = ORIG + a, d = DONE + a;
            if (el[d] !== cur) el[k] = cur;
            const v = t(el[k]);
            el[d] = v;
            if (v !== cur) el.setAttribute(a, v);
        }
        if ((el.tagName === 'INPUT') && (el.type === 'button' || el.type === 'submit') && el.value) {
            if (el[DONE + 'v'] !== el.value) el[ORIG + 'v'] = el.value;
            const v = t(el[ORIG + 'v']); el[DONE + 'v'] = v; if (v !== el.value) el.value = v;
        }
    }
    function walk(root) {
        if (!root) return;
        if (root.nodeType === 3) { if (root.parentElement && !skipEl(root.parentElement)) doText(root); return; }
        if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) return;
        if (root.nodeType === 1 && skipEl(root)) return;
        const tw = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
            acceptNode(n) {
                if (n.nodeType === 1) {
                    const tg = n.tagName.toUpperCase();
                    if (SKIP.has(tg) || n.getAttribute('translate') === 'no' || n.classList.contains('notranslate')) return NodeFilter.FILTER_REJECT;
                    return NodeFilter.FILTER_ACCEPT;
                }
                return NodeFilter.FILTER_ACCEPT;
            }
        });
        if (root.nodeType === 1) doAttrs(root);
        let n;
        while ((n = tw.nextNode())) { if (n.nodeType === 3) doText(n); else doAttrs(n); }
    }
    let started = false, pending = new Set(), raf = 0, titleOrig = null, titleDone = null;
    function flush() {
        raf = 0;
        const list = Array.from(pending); pending.clear();
        list.forEach(n => { if (n.isConnected) walk(n); });
        doTitle();
    }
    function doTitle() {
        if (document.title !== titleDone) titleOrig = document.title;
        titleDone = t(titleOrig);
        if (titleDone !== document.title) document.title = titleDone;
    }
    function retranslate() {
        document.documentElement.lang = lang;
        document.documentElement.dataset.n8Lang = lang;
        walk(document.body); doTitle();
    }
    function start() {
        if (started) return;
        started = true;
        retranslate();
        new MutationObserver(muts => {
            for (const m of muts) {
                if (m.type === 'childList') m.addedNodes.forEach(n => pending.add(n));
                else if (m.type === 'characterData') { if (m.target[DONE] !== m.target.data) pending.add(m.target); }
                else if (m.type === 'attributes') { if (m.target[DONE + m.attributeName] !== m.target.getAttribute(m.attributeName)) pending.add(m.target); }
            }
            if (pending.size && !raf) raf = requestAnimationFrame(flush);
            if (pending.size > 400) { cancelAnimationFrame(raf); flush(); }
        }).observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
    }

    function setLang(l) {
        if (LANGS.indexOf(l) < 0 || l === lang) return;
        lang = l;
        document.cookie = `${COOKIE}=${l}; path=/; max-age=31536000; SameSite=Lax`;
        try { localStorage.setItem(COOKIE, l); } catch (e) { }
        cache.clear();
        retranslate();
        document.querySelectorAll('.n8-lang').forEach(paintSwitch);
        window.dispatchEvent(new CustomEvent('n8:lang', { detail: { lang: l } }));
    }

    // native dialogs follow the language
    ['alert', 'confirm', 'prompt'].forEach(fn => {
        const orig = window[fn];
        if (typeof orig !== 'function') return;
        window[fn] = function (msg, ...rest) { return orig.call(window, t(msg), ...rest); };
    });

    // ------------------------------------------------------------ language switch
    function paintSwitch(el) {
        el.querySelectorAll('button').forEach(b => {
            const on = b.dataset.l === lang;
            b.classList.toggle('on', on);
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
    }
    function langSwitch(container, opts) {
        if (!container) return null;
        let el = container.querySelector('.n8-lang');
        if (!el) {
            el = document.createElement('span');
            el.className = 'n8-lang notranslate';
            el.setAttribute('role', 'group');
            el.setAttribute('translate', 'no');
            el.title = 'Sprache / Language';
            el.innerHTML = '<button type="button" data-l="de">DE</button><button type="button" data-l="en">EN</button>';
            el.addEventListener('click', e => { const b = e.target.closest('button'); if (b) setLang(b.dataset.l); });
            if (opts && opts.before && opts.before.parentNode === container) container.insertBefore(el, opts.before);
            else if (opts && opts.prepend) container.insertBefore(el, container.firstChild);
            else container.appendChild(el);
        }
        paintSwitch(el);
        return el;
    }

    // ------------------------------------------------------------ helpers
    const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    function fmtTime(v) {
        if (!v) return '–';
        const d = typeof v === 'number' ? new Date(v < 1e12 ? v * 1000 : v) : new Date(v);
        if (isNaN(d)) return String(v);
        return d.toLocaleString(lang === 'en' ? 'en-GB' : 'de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    }

    // ------------------------------------------------------------ updates
    /*
     * state (every app maps its own API onto this):
     *   available  bool        newer version on GitHub
     *   current    "1.3.0"     installed version (or short commit)
     *   latest     "1.4.0"     version on GitHub
     *   notes      [..] | html what is new (optional)
     *   checked    time        last check (epoch s/ms or ISO)
     *   schedule   text        e.g. "stündlich zur vollen Stunde"
     *   can_install bool       this user may install and the server can do it
     *   reason     text        why it cannot be installed (shown instead of the button)
     *   result     {ok, from, to, time, message}   outcome of the last update (rollback included)
     *   log        text        update log
     *   extra      [[label, html], …]   further rows for the panel
     */
    const SNOOZE = 'n8_upd_later';
    function notesHtml(n) {
        if (!n) return '';
        if (Array.isArray(n)) return n.length ? '<ul>' + n.slice(0, 12).map(x => `<li>${esc(x)}</li>`).join('') + '</ul>' : '';
        return String(n);
    }
    function banner(el, s, h) {
        if (!el) return;
        h = h || {};
        let snoozed = null;
        try { snoozed = JSON.parse(localStorage.getItem(SNOOZE + (h.app || '')) || 'null'); } catch (e) { }
        const hide = !s || !s.available || (snoozed && snoozed.v === s.latest && Date.now() - snoozed.t < 864e5);
        el.hidden = !!hide;
        el.classList.add('n8-upd');
        if (hide) { el.innerHTML = ''; return; }
        const notes = notesHtml(s.notes);
        el.innerHTML = `<div class="n8-upd-main"><span class="n8-upd-ico" aria-hidden="true">⬆️</span>
            <span class="n8-upd-txt">Update verfügbar: <b>${esc(s.current || '?')}</b> → <b>${esc(s.latest || '?')}</b></span>
            <span class="n8-upd-act">
                ${notes ? '<button type="button" class="n8-btn" data-a="notes">Was ist neu?</button>' : ''}
                ${s.can_install ? '<button type="button" class="n8-btn primary" data-a="install">Jetzt aktualisieren</button>' : ''}
                ${h.onDetails ? '<button type="button" class="n8-btn" data-a="details">Details</button>' : ''}
                <button type="button" class="n8-btn ghost" data-a="later" title="Bis morgen ausblenden">Später</button>
            </span></div>${notes ? `<div class="n8-upd-notes">${notes}</div>` : ''}`;
        el.onclick = e => {
            const b = e.target.closest('button[data-a]'); if (!b) return;
            const a = b.dataset.a;
            if (a === 'notes') el.classList.toggle('open');
            else if (a === 'install' && h.onInstall) h.onInstall(s);
            else if (a === 'details' && h.onDetails) h.onDetails(s);
            else if (a === 'later') {
                try { localStorage.setItem(SNOOZE + (h.app || ''), JSON.stringify({ v: s.latest, t: Date.now() })); } catch (x) { }
                el.hidden = true;
            }
        };
    }
    function panel(el, s, h) {
        if (!el) return;
        h = h || {};
        const r = s.result;
        const rows = [
            ['Installiert', `<b>${esc(s.current || '–')}</b>`],
            ['Auf GitHub', s.latest ? `<b>${esc(s.latest)}</b> ${s.available ? '<span class="n8-badge ok">Update verfügbar</span>' : '<span class="n8-badge">aktuell</span>'}` : (s.error ? `<span class="n8-badge bad">${esc(s.error)}</span>` : '–')],
            ['Zuletzt geprüft', esc(fmtTime(s.checked))],
            ['Automatische Prüfung', esc(s.schedule || 'stündlich zur vollen Stunde')],
        ];
        if (r) rows.push(['Letztes Update', r.ok
            ? `<span class="n8-badge ok">erfolgreich</span> ${esc(r.from || '')} → <b>${esc(r.to || '')}</b> · ${esc(fmtTime(r.time))}`
            : `<span class="n8-badge bad">zurückgenommen</span> ${esc(r.message || '')} · ${esc(fmtTime(r.time))}`]);
        (s.extra || []).forEach(x => rows.push(x));
        const notes = notesHtml(s.notes);
        el.innerHTML = `<div class="n8-upd-panel">
            <div class="n8-kv">${rows.map(([k, v]) => `<div class="k">${esc(k)}</div><div class="v">${v}</div>`).join('')}</div>
            ${s.available && notes ? `<div class="n8-upd-notes-panel"><div class="n8-sub">Was ist neu</div>${notes}</div>` : ''}
            <div class="n8-actions">
                <button type="button" class="n8-btn" data-a="check">↻ Jetzt prüfen</button>
                <button type="button" class="n8-btn primary" data-a="install" ${s.available && s.can_install ? '' : 'disabled'}>⬆️ Update jetzt installieren</button>
            </div>
            ${s.reason ? `<div class="n8-help">${s.reason}</div>` : ''}
            <div class="n8-help">Geprüft wird jede volle Stunde. Installiert wird nur auf Knopfdruck. Nach dem Update startet der Dienst neu; antwortet die Weboberfläche danach nicht, wird automatisch auf die vorherige Version zurückgesetzt.</div>
            ${s.log ? `<div class="n8-sub">Update-Protokoll</div><pre class="n8-log notranslate">${esc(s.log)}</pre>` : ''}
        </div>`;
        el.onclick = e => {
            const b = e.target.closest('button[data-a]'); if (!b || b.disabled) return;
            if (b.dataset.a === 'check' && h.onCheck) { b.disabled = true; b.textContent = t('↻ Prüfe …'); Promise.resolve(h.onCheck()).finally(() => { b.disabled = false; }); }
            if (b.dataset.a === 'install' && h.onInstall) h.onInstall(s);
        };
    }

    /*
     * run({ from, to, text, password, confirm, install: async (password) => any, version: async () => string, reload })
     *   text     html shown before starting (what is new); password: ask for the password; confirm:false starts at once
     *   install  starts the update on the server (throws with a message on errors)
     *   version  asks the running service for its version; throws while it restarts
     */
    function run(o) {
        return new Promise(resolve => {
            const ov = document.createElement('div');
            ov.className = 'n8-upd-ov';
            const steps = ['Update wird geladen und eingespielt', 'Dienst startet neu', 'Weboberfläche wird geprüft'];
            const ask = o.confirm !== false;
            ov.innerHTML = `<form class="n8-upd-box" role="dialog" aria-modal="true">
                <h3>⬆️ Update ${esc(o.from || '')} → ${esc(o.to || '')}</h3>
                <div class="n8-upd-ask" ${ask ? '' : 'hidden'}>
                    ${o.text ? `<div class="n8-upd-text">${o.text}</div>` : ''}
                    <div class="n8-help">Der Dienst startet dabei neu (etwa eine Minute). Antwortet die Weboberfläche danach nicht, wird automatisch die vorherige Version wiederhergestellt.</div>
                    ${o.password ? '<input class="n8-pw" type="password" name="password" placeholder="Dein Passwort (Bestätigung)" autocomplete="current-password" required>' : ''}
                </div>
                <ol class="n8-steps" ${ask ? 'hidden' : ''}>${steps.map((x, i) => `<li data-i="${i}">${esc(x)}</li>`).join('')}</ol>
                <div class="n8-upd-msg"></div>
                <div class="n8-actions">
                    <button type="button" class="n8-btn" data-a="close" ${ask ? '' : 'hidden'}>${ask ? 'Abbrechen' : 'Schließen'}</button>
                    ${ask ? '<button type="submit" class="n8-btn primary" data-a="go">⬆️ Jetzt aktualisieren</button>' : ''}
                </div></form>`;
            document.body.appendChild(ov);
            const box = ov.querySelector('form'), msg = ov.querySelector('.n8-upd-msg'), close = ov.querySelector('[data-a=close]');
            const pw = ov.querySelector('.n8-pw');
            close.onclick = () => { ov.remove(); resolve(false); };
            const step = (i, cls) => ov.querySelectorAll('.n8-steps li').forEach((li, j) => {
                li.classList.toggle('done', j < i || (j === i && cls === 'done'));
                li.classList.toggle('run', j === i && cls === 'run');
                li.classList.toggle('bad', j === i && cls === 'bad');
            });
            const finish = (ok, text) => {
                msg.innerHTML = text; msg.className = 'n8-upd-msg ' + (ok ? 'ok' : 'bad');
                close.hidden = false; close.textContent = t('Schließen'); close.onclick = () => { ov.remove(); resolve(ok); };
            };
            const go = () => {
                const password = pw ? pw.value : '';
                const g = ov.querySelector('[data-a=go]'); if (g) g.remove();
                ov.querySelector('.n8-upd-ask').hidden = true;
                ov.querySelector('.n8-steps').hidden = false;
                close.hidden = true; msg.textContent = ''; msg.className = 'n8-upd-msg';
                begin(password);
            };
            box.onsubmit = e => { e.preventDefault(); go(); };
            if (pw) setTimeout(() => pw.focus(), 50);
            if (!ask) go();
            function begin(password) {
            step(0, 'run');
            Promise.resolve().then(() => o.install(password)).then(async res => {
                if (res && res.restart === false) { step(2, 'done'); finish(true, esc(t(res.message || 'Update installiert.'))); return; }
                step(1, 'run');
                const t0 = Date.now();
                let wentDown = false, seen = null;
                await new Promise(r => setTimeout(r, 2500));
                while (Date.now() - t0 < (o.timeout || 240000)) {
                    try {
                        seen = await o.version();
                        if (wentDown || Date.now() - t0 > 20000 || (seen && o.to && String(seen).indexOf(o.to) >= 0)) break;
                    } catch (e) { wentDown = true; }
                    await new Promise(r => setTimeout(r, 2000));
                }
                step(2, 'run');
                await new Promise(r => setTimeout(r, 1500));
                try { seen = await o.version(); } catch (e) { seen = null; }
                if (seen == null) { step(2, 'bad'); finish(false, esc(t('Der Dienst antwortet noch nicht. Bitte in ein paar Minuten neu laden oder das Update-Protokoll ansehen.'))); return; }
                if (o.to && String(seen).indexOf(o.to) < 0 && o.from && String(seen).indexOf(o.from) >= 0) {
                    step(2, 'bad'); finish(false, esc(t('Das Update wurde zurückgenommen – es läuft wieder die vorherige Version.')) + ' <b>' + esc(seen) + '</b>'); return;
                }
                step(2, 'done');
                finish(true, esc(t('Update installiert. Die Seite wird neu geladen …')));
                if (o.reload !== false) setTimeout(() => location.reload(), 1800);
            }).catch(e => {
                if (o.password && e && /passw/i.test(e.message || '')) {   // wrong password: ask again
                    ov.querySelector('.n8-steps').hidden = true; ov.querySelector('.n8-upd-ask').hidden = false;
                    msg.textContent = t(e.message); msg.className = 'n8-upd-msg bad';
                    const act = ov.querySelector('.n8-actions');
                    act.insertAdjacentHTML('beforeend', '<button type="submit" class="n8-btn primary" data-a="go">' + esc(t('⬆️ Jetzt aktualisieren')) + '</button>');
                    close.hidden = false; close.textContent = t('Abbrechen'); close.onclick = () => { ov.remove(); resolve(false); };
                    pw.value = ''; pw.focus(); return;
                }
                step(0, 'bad'); finish(false, esc(t(e && e.message ? e.message : String(e))));
            });
            }
        });
    }


    // ============================================================ admin menu as a tree (1.1.0)
    // groups: [{ id, label, items: [{ id, label, hidden }] }] – labels with a leading emoji. opts: { active, onSelect(id), key }
    // The same groups in every N8 system: Betrieb · Benutzer & Zugang · Darstellung · Netz & Domains · System.
    // items may have children: [{ id, label }] – shown indented under the item (the former in-page menus of a page).
    // onSelect gets the id of the item or of the child ('settings' or 'settings:dmr').
    function tree(el, groups, opts) {
        opts = opts || {};
        const key = 'n8nav:' + (opts.key || location.pathname);
        let closed = {};
        try { closed = JSON.parse(localStorage.getItem(key) || '{}'); } catch (e) { closed = {}; }
        const act = opts.active;
        const items = groups.map(g => ({ ...g, items: (g.items || []).filter(i => !i.hidden) })).filter(g => g.items.length);
        const all = items.flatMap(g => g.items.flatMap(i => [i, ...(i.children || [])]));
        const cur = all.find(i => i.id === act);
        const inItem = i => i.id === act || (i.children || []).some(c => c.id === act);
        const btn = (i, cls) => `<button type="button" class="n8-tree-i ${cls || ''} ${i.id === act ? 'on' : ''}" data-i="${esc(i.id)}">${esc(i.label)}${i.badge ? `<span class="n8-badge ${esc(i.badgeClass || '')}">${esc(i.badge)}</span>` : ''}</button>`;
        el.classList.add('n8-tree');
        el.innerHTML = `<button type="button" class="n8-tree-toggle">☰ <span>${esc(cur ? cur.label : 'Menü')}</span></button>
            <div class="n8-tree-body">${items.map(g => {
                const open = !closed[g.id] || g.items.some(inItem);
                return `<div class="n8-tree-g ${open ? 'open' : ''}" data-g="${esc(g.id)}">
                    <button type="button" class="n8-tree-gh"><span class="n8-tree-car">▸</span>${esc(g.label)}</button>
                    <div class="n8-tree-items">${g.items.map(i => btn(i, (i.children || []).length ? 'has-kids' + (inItem(i) ? ' kids-open' : '') : '')
                        + ((i.children || []).length && inItem(i) ? `<div class="n8-tree-kids">${i.children.map(c => btn(c, 'kid')).join('')}</div>` : '')).join('')}</div></div>`;
            }).join('')}</div>`;
        el.querySelector('.n8-tree-toggle').onclick = () => el.classList.toggle('open');
        el.querySelectorAll('.n8-tree-gh').forEach(b => b.onclick = () => {
            const g = b.parentElement; g.classList.toggle('open'); closed[g.dataset.g] = !g.classList.contains('open');
            try { localStorage.setItem(key, JSON.stringify(closed)); } catch (e) { /* private mode */ }
        });
        el.querySelectorAll('.n8-tree-i').forEach(b => b.onclick = () => {
            const id = b.dataset.i;
            tree(el, groups, { ...opts, active: id });          // children open and close with their item
            el.classList.remove('open');
            if (opts.onSelect) opts.onSelect(id);
        });
        retranslateEl(el);
    }
    function retranslateEl(el) { try { walk(el); } catch (e) { /* not started yet */ } }

    // ============================================================ System views (1.1.0) – identical in every N8 system
    // opts.req(method, url, body) → JSON (the page's own fetch with its CSRF header); endpoints are the same everywhere:
    //   /api/admin/services · /api/admin/services/<unit>/<action> · /api/admin/perms · /api/admin/perms/fix
    //   /api/admin/keepalive · /api/admin/update-log
    // opts.update = { load(force) → state for update.panel, install() → result, version() → string } for the view 'update'
    //   (or onInstall(state) to open the project's own N8Kit.update.run dialog). Updates never ask for a password.
    // opts.console = 'sudo /opt/…/scripts/n8-admin.sh' (shown in hints); opts.extra(el) appends project-specific content
    const SVC = { active: 'läuft', inactive: 'gestoppt', failed: 'Fehler', activating: 'startet', deactivating: 'stoppt', reloading: 'lädt neu' };
    const AREA = { user: '👤 Dienstbenutzer', prog: '📦 Programm', data: '💾 Daten', systemd: '⚙️ systemd', sudo: '🛡️ sudo', hw: '🔌 Hardware',
                   source: '🧬 Quellordner', usb: '🔌 USB-Vocoder', https: '🔒 Domains & HTTPS' };
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleString(lang === 'en' ? 'en-GB' : 'de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '–';
    function card(title, body, badge) {
        return `<section class="n8-card"><h3>${esc(title)}${badge ? ' ' + badge : ''}</h3>${body}</section>`;
    }
    async function view(el, name, o) {
        o = o || {};
        const req = o.req, cons = o.console || 'sudo scripts/n8-admin.sh';
        const msg = (e) => `<div class="n8-help">⚠️ ${esc(e && e.message ? e.message : String(e))}</div>`;
        el.classList.add('n8-sys');
        el.innerHTML = '<div class="n8-help">…</div>';
        const paint = (html) => { el.innerHTML = html; retranslateEl(el); };
        if (name === 'update') {
            paint(`<div class="n8-sys-grid">${card('⬆️ Update', '<div class="n8-upd-panel"></div>')}${card('📜 Update-Protokoll', '<div class="n8-sys-log">…</div>')}</div><div class="n8-sys-extra"></div>`);
            const box = el.querySelector('.n8-upd-panel');
            const load = async (force) => {
                let st; try { st = await o.update.load(force); } catch (e) { box.innerHTML = msg(e); return; }
                if (!st) { box.innerHTML = msg(t('Keine Antwort')); return; }
                panel(box, st, { onCheck: () => load(true), onInstall: () => o.update.onInstall ? o.update.onInstall(st) : run({
                    from: st.current, to: st.latest, text: st.notes || '', password: false, timeout: 600000,
                    install: () => o.update.install(), version: () => o.update.version() }) });
            };
            await load(false);
            const logEl = el.querySelector('.n8-sys-log');
            const loadLog = async () => {
                let d; try { d = await req('GET', '/api/admin/update-log'); } catch (e) { logEl.innerHTML = msg(e); return; }
                const r = d.result;
                logEl.innerHTML = `${r ? `<div class="n8-kv"><span>${esc(t('Letztes Update'))}</span><span><span class="n8-badge ${r.ok ? 'ok' : 'bad'}">${esc(t(r.ok ? 'erfolgreich' : 'zurückgenommen'))}</span> ${esc(r.from || '')} → ${esc(r.to || '')} · ${fmt(r.time)}</span>${r.message ? `<span>${esc(t('Meldung'))}</span><span>${esc(r.message)}</span>` : ''}</div>` : ''}
                    <pre class="n8-log">${esc(d.log || t('Noch kein Update über die Weboberfläche.'))}</pre>
                    <div class="n8-actions"><button type="button" class="n8-btn" data-a="reload">↻ ${esc(t('Neu laden'))}</button></div>`;
                logEl.querySelector('[data-a=reload]').onclick = loadLog;
                if (d.running || d.pending) setTimeout(() => { if (document.body.contains(logEl)) loadLog(); }, 3000);
            };
            loadLog();
            if (o.extra) o.extra(el.querySelector('.n8-sys-extra'));
            return;
        }
        if (name === 'services') {
            const load = async () => {
                let d; try { d = await req('GET', '/api/admin/services'); } catch (e) { paint(card('🧩 Dienste', msg(e))); return; }
                const units = (d.units || []).filter(u => !u.hidden);
                const can = (u, a) => (u.actions || []).includes(a);
                const rows = units.map(u => {
                    const st = u.active === 'active' ? 'ok' : u.active === 'failed' ? 'bad' : 'warn';
                    const btn = (a, ic, ti) => can(u, a) ? `<button type="button" class="n8-btn sm ${a === 'stop' ? 'danger' : ''}" title="${esc(t(ti))}" data-u="${esc(u.unit)}" data-a="${a}">${ic}</button>` : '';
                    return `<div class="n8-svc"><div class="n8-svc-n"><b>${esc(u.label || u.unit)}</b><code>${esc(u.unit)}</code></div>
                        <span class="n8-badge ${st}">${esc(t(SVC[u.active] || u.active))}</span>
                        <span class="n8-svc-a">${can(u, 'enable') || can(u, 'disable') ? `<label class="n8-sw"><input type="checkbox" data-auto="${esc(u.unit)}" ${u.enabled === 'enabled' ? 'checked' : ''}><i></i> ${esc(t('Autostart'))}</label>` : `<span class="n8-dim">${esc(t(u.enabled === 'enabled' ? 'Autostart an' : u.enabled || ''))}</span>`}</span>
                        <span class="n8-svc-b">${u.active === 'active' ? btn('restart', '↻', 'Neu starten') + btn('stop', '■', 'Stoppen') : btn('start', '▶', 'Starten')}</span></div>`;
                }).join('');
                paint(card('🧩 Dienste', `<p class="n8-help">${esc(t('Zustand, Autostart beim Booten und Starten · Stoppen · Neu starten – nur, was dieses System freigibt. Ein hier gestoppter Dienst wird vom Keep-Alive nicht wieder gestartet.'))}</p>
                    ${units.length ? `<div class="n8-svc-list">${rows}</div>` : `<div class="n8-help">${esc(t('Noch nicht eingerichtet – einmal auf der Konsole:'))} <code>${esc(cons)} fix-perms</code></div>`}`));
                el.querySelectorAll('[data-a]').forEach(b => b.onclick = async () => {
                    const u = b.dataset.u, a = b.dataset.a;
                    if (a === 'stop' && !confirm(t('Dienst stoppen?') + '\n' + u)) return;
                    b.disabled = true;
                    try { await req('POST', `/api/admin/services/${encodeURIComponent(u)}/${a}`, {}); } catch (e) { alert(e.message); }
                    setTimeout(load, a === 'stop' ? 500 : 1500);
                });
                el.querySelectorAll('[data-auto]').forEach(c => c.onchange = async () => {
                    const a = c.checked ? 'enable' : 'disable';
                    if (a === 'disable' && !confirm(t('Autostart ausschalten? Nach einem Neustart des Servers startet der Dienst dann nicht mehr von selbst.'))) { c.checked = true; return; }
                    try { await req('POST', `/api/admin/services/${encodeURIComponent(c.dataset.auto)}/${a}`, {}); } catch (e) { alert(e.message); }
                    load();
                });
            };
            return load();
        }
        if (name === 'perms') {
            const show = (d, out) => {
                const rows = d.checks || [];
                const badge = !rows.length ? `<span class="n8-badge warn">${esc(t('nicht geprüft'))}</span>` : d.bad ? `<span class="n8-badge bad">${d.bad} ${esc(t('Fehler'))}</span>` : `<span class="n8-badge ok">${esc(t('alles in Ordnung'))}</span>`;
                const areas = [...new Set(rows.map(c => c.area))];
                const bad = rows.filter(c => c.status !== 'ok');
                paint(card('🔐 Berechtigungen & sudo', `<p class="n8-help">${esc(t('Prüft Dienstbenutzer, Programm (root, für den Dienst schreibgeschützt), Daten und Passwörter, systemd-Dienste, „Update jetzt“, Keep-Alive und die sudo-Freigaben. Korrigieren repariert, was falsch ist, und prüft erneut.'))}
                        <br>${esc(t('Konsole:'))} <code>${esc(cons)} check-perms</code> · <code>fix-perms</code></p>
                    ${!rows.length ? `<div class="n8-help">${esc(d.message || '–')}</div>` : `
                    ${bad.length ? `<div class="n8-perm">${bad.map(c => `<div class="n8-perm-r">${c.status === 'warn' ? '⚠️' : '❌'}<b>${esc(t(AREA[c.area] || c.area))}</b><span>${esc(c.text)}</span></div>`).join('')}</div>` : ''}
                    <details class="n8-perm-ok"><summary>${rows.length - bad.length} ${esc(t('Prüfungen in Ordnung'))}</summary><div class="n8-perm">${areas.map(a => rows.filter(c => c.area === a && c.status === 'ok').map(c => `<div class="n8-perm-r">✅<b>${esc(t(AREA[a] || a))}</b><span>${esc(c.text)}</span></div>`).join('')).join('')}</div></details>`}
                    ${out ? `<pre class="n8-log">${esc(out)}</pre>` : ''}
                    <div class="n8-actions"><button type="button" class="n8-btn" data-a="check">🔍 ${esc(t('Erneut prüfen'))}</button><button type="button" class="n8-btn primary" data-a="fix">🛠️ ${esc(t('Korrigieren'))}</button></div>`, badge));
                el.querySelector('[data-a=check]').onclick = load;
                el.querySelector('[data-a=fix]').onclick = async (e) => {
                    e.target.disabled = true; e.target.textContent = t('Korrigiere …');
                    try { const r = await req('POST', '/api/admin/perms/fix', {}); show(r.check || {}, (r.message || '').replace(/\x1b\[[0-9;]*m/g, '')); }
                    catch (x) { alert(x.message); load(); }
                };
            };
            const load = async () => {
                paint(card('🔐 Berechtigungen & sudo', `<div class="n8-help">${esc(t('Prüfe …'))}</div>`));
                try { show(await req('GET', '/api/admin/perms')); } catch (e) { paint(card('🔐 Berechtigungen & sudo', msg(e))); }
            };
            return load();
        }
        if (name === 'keepalive') {
            const load = async () => {
                let d; try { d = await req('GET', '/api/admin/keepalive'); } catch (e) { paint(card('💓 Keep-Alive', msg(e))); return; }
                const c = d.conf || {}, paused = c.paused_until && c.paused_until * 1000 > Date.now();
                const badge = !d.ready ? `<span class="n8-badge warn">${esc(t('nicht eingerichtet'))}</span>` : !c.enabled ? `<span class="n8-badge">${esc(t('aus'))}</span>`
                    : paused ? `<span class="n8-badge warn">${esc(t('pausiert'))}</span>` : d.stale ? `<span class="n8-badge bad">${esc(t('läuft nicht'))}</span>` : `<span class="n8-badge ok">${esc(t('aktiv'))}</span>`;
                const ic = st => ({ ok: '✅', hold: '⏸️', restarted: '🔄', giveup: '❌', unknown: '❔' }[st] || '⚠️');
                paint(card('💓 Keep-Alive', `<p class="n8-help">${esc(t('Jede Minute als root: prüft jeden Dienst wirklich (Weboberfläche und Verbindungen der Protokolle), startet kranke Dienste nach ein paar Minuten neu (höchstens 4× je Stunde), erkennt Internet-Ausfälle und startet danach die Netzdienste neu, und meldet sich bei einer Heartbeat-Adresse (Uptime Kuma „Push“, Healthchecks.io …). Ein von Hand gestoppter Dienst bleibt gestoppt.'))}</p>
                    ${d.ready ? `<div class="n8-kv"><span>🌐 ${esc(t('Internet'))}</span><span>${d.net ? `<span class="n8-badge ok">${esc(t('erreichbar'))}</span>` : `<span class="n8-badge bad">${esc(t('weg seit'))} ${fmt(d.net_down_since)}</span>`}</span>
                        <span>${esc(t('Letzte Prüfung'))}</span><span>${d.age != null && d.age < 120 ? esc(t('gerade eben')) : fmt(d.time)}</span>
                        ${c.heartbeat_url ? `<span>${esc(t('Heartbeat'))}</span><span>${esc(d.heartbeat || '–')}</span>` : ''}</div>
                      <div class="n8-perm" style="margin-top:10px">${(d.checks || []).map(x => `<div class="n8-perm-r">${ic(x.state)}<b>${esc(x.label)}</b><span><span>${esc(t(x.state === 'ok' ? 'gesund' : x.state === 'hold' ? 'von Hand gestoppt – Keep-Alive wartet' : x.state === 'unknown' ? 'kein Neustart' : ''))}${x.state === 'unknown' ? ' · ' : ''}</span>${x.state !== 'ok' && x.state !== 'hold' ? esc(x.why || '') : ''}${x.restarts ? ` · <span>${x.restarts}× ${esc(t('neu gestartet'))}</span>, ${fmt(x.last_restart)}` : ''}</span></div>`).join('')}</div>`
                      : `<div class="n8-help">${esc(t('Einmal auf der Konsole einrichten:'))} <code>${esc(cons)} fix-perms</code></div>`}
                    <form class="n8-form">
                      <label class="n8-sw"><input type="checkbox" name="enabled" ${c.enabled ? 'checked' : ''}><i></i> ${esc(t('Keep-Alive an'))}</label>
                      <label class="n8-sw"><input type="checkbox" name="net_restart" ${c.net_restart ? 'checked' : ''}><i></i> ${esc(t('Netzdienste nach einem Internet-Ausfall neu starten'))}</label>
                      <label>${esc(t('Heartbeat-Adresse'))}<input name="heartbeat_url" value="${esc(c.heartbeat_url || '')}" placeholder="https://hc-ping.com/… · https://kuma…/api/push/…"></label>
                      <label>${esc(t('Heartbeat bei Fehlern (optional)'))}<input name="heartbeat_fail_url" value="${esc(c.heartbeat_fail_url || '')}" placeholder="https://hc-ping.com/…/fail"></label>
                      <div class="n8-actions"><button type="button" class="n8-btn" data-a="pause">${esc(t(paused ? '▶ Fortsetzen' : '⏸ 1 h pausieren (Wartung)'))}</button><button class="n8-btn primary">💾 ${esc(t('Speichern'))}</button></div></form>
                    ${d.log ? `<details class="n8-perm-ok"><summary>${esc(t('Keep-Alive-Protokoll'))}</summary><pre class="n8-log">${esc(d.log)}</pre></details>` : ''}`, badge));
                const f = el.querySelector('form');
                f.onsubmit = async (e) => { e.preventDefault();
                    try { await req('POST', '/api/admin/keepalive', { enabled: f.enabled.checked, net_restart: f.net_restart.checked, heartbeat_url: f.heartbeat_url.value.trim(), heartbeat_fail_url: f.heartbeat_fail_url.value.trim() }); load(); }
                    catch (x) { alert(x.message); } };
                f.querySelector('[data-a=pause]').onclick = async () => { try { await req('POST', '/api/admin/keepalive', { pause_minutes: paused ? 0 : 60 }); load(); } catch (x) { alert(x.message); } };
            };
            return load();
        }
    }

    // the menu structure every N8 system uses (projects fill in their items)
    const GROUPS = { betrieb: '📡 Betrieb', zugang: '👥 Benutzer & Zugang', darstellung: '🎨 Darstellung', netz: '🌐 Netz & Domains', system: '🖥️ System' };
    const SYS_ITEMS = [['sys-update', '⬆️ Update'], ['sys-services', '🧩 Dienste'], ['sys-perms', '🔐 Berechtigungen & sudo'], ['sys-keepalive', '💓 Keep-Alive']];

    // ------------------------------------------------------------ the kit's own words
    add({
        base: 'de', en: {
            'Update verfügbar': 'Update available', 'Was ist neu?': "What's new?", 'Was ist neu': "What's new",
            'Jetzt aktualisieren': 'Update now', 'Details': 'Details', 'Später': 'Later', 'Bis morgen ausblenden': 'Hide until tomorrow',
            'Installiert': 'Installed', 'Auf GitHub': 'On GitHub', 'Zuletzt geprüft': 'Last checked', 'Automatische Prüfung': 'Automatic check',
            'stündlich zur vollen Stunde': 'every full hour', 'aktuell': 'up to date', 'Letztes Update': 'Last update',
            'erfolgreich': 'successful', 'zurückgenommen': 'rolled back', 'Jetzt prüfen': 'Check now', 'Prüfe': 'Checking',
            'Update jetzt installieren': 'Install update now', 'Update-Protokoll': 'Update log',
            'Geprüft wird jede volle Stunde. Installiert wird nur auf Knopfdruck. Nach dem Update startet der Dienst neu; antwortet die Weboberfläche danach nicht, wird automatisch auf die vorherige Version zurückgesetzt.':
                'Checked every full hour. Updates are only installed when you press the button. The service restarts afterwards; if the web interface does not answer, the previous version is restored automatically.',
            'Update wird geladen und eingespielt': 'Downloading and applying the update', 'Abbrechen': 'Cancel',
            'Der Dienst startet dabei neu (etwa eine Minute). Antwortet die Weboberfläche danach nicht, wird automatisch die vorherige Version wiederhergestellt.':
                'The service restarts (about a minute). If the web interface does not answer afterwards, the previous version is restored automatically.',
            'Dein Passwort (Bestätigung)': 'Your password (confirmation)', 'Dienst startet neu': 'Service restarts',
            'Weboberfläche wird geprüft': 'Checking the web interface', 'Schließen': 'Close',
            'Update installiert. Die Seite wird neu geladen …': 'Update installed. Reloading the page …',
            'Update installiert.': 'Update installed.',
            'Das Update wurde zurückgenommen – es läuft wieder die vorherige Version.': 'The update was rolled back – the previous version is running again.',
            'Der Dienst antwortet noch nicht. Bitte in ein paar Minuten neu laden oder das Update-Protokoll ansehen.': 'The service does not answer yet. Reload in a few minutes or look at the update log.',
            'Sprache / Language': 'Language / Sprache',
            'immer': 'always', 'aus': 'off', 'nie': 'never',
            // 1.1.0: menu tree and System views
            'Menü': 'Menu', '📡 Betrieb': '📡 Operation', '👥 Benutzer & Zugang': '👥 Users & access', '🎨 Darstellung': '🎨 Appearance',
            '🌐 Netz & Domains': '🌐 Network & domains', '🖥️ System': '🖥️ System', '⬆️ Update': '⬆️ Update', '🧩 Dienste': '🧩 Services',
            '🔐 Berechtigungen & sudo': '🔐 Permissions & sudo', '💓 Keep-Alive': '💓 Keep-alive', 'Betrieb': 'Operation', 'Benutzer & Zugang': 'Users & access',
            'Darstellung': 'Appearance', 'Netz & Domains': 'Network & domains', 'Dienste': 'Services', 'Berechtigungen & sudo': 'Permissions & sudo',
            'läuft': 'running', 'gestoppt': 'stopped', 'Fehler': 'errors', 'startet': 'starting', 'stoppt': 'stopping', 'lädt neu': 'reloading',
            'Autostart': 'Autostart', 'Autostart an': 'autostart on', 'Neu starten': 'Restart', 'Stoppen': 'Stop', 'Starten': 'Start', 'Dienst stoppen?': 'Stop the service?',
            'Zustand, Autostart beim Booten und Starten · Stoppen · Neu starten – nur, was dieses System freigibt. Ein hier gestoppter Dienst wird vom Keep-Alive nicht wieder gestartet.':
                'State, autostart at boot and start · stop · restart – only what this system allows. A service stopped here is not started again by the keep-alive.',
            'Noch nicht eingerichtet – einmal auf der Konsole:': 'Not set up yet – run once on the console:',
            'Autostart ausschalten? Nach einem Neustart des Servers startet der Dienst dann nicht mehr von selbst.': 'Switch off autostart? After a reboot the service does not start by itself.',
            'nicht geprüft': 'not checked', 'alles in Ordnung': 'all fine', 'Konsole:': 'Console:', 'Prüfungen in Ordnung': 'checks fine', 'Erneut prüfen': 'Check again',
            'Korrigieren': 'Fix', 'Korrigiere …': 'Fixing …', 'Prüfe …': 'Checking …',
            'Prüft Dienstbenutzer, Programm (root, für den Dienst schreibgeschützt), Daten und Passwörter, systemd-Dienste, „Update jetzt“, Keep-Alive und die sudo-Freigaben. Korrigieren repariert, was falsch ist, und prüft erneut.':
                'Checks the service user, program (root, read-only for the service), data and passwords, systemd services, “Update now”, keep-alive and the sudo rules. Fix repairs what is wrong and checks again.',
            '👤 Dienstbenutzer': '👤 Service user', '📦 Programm': '📦 Program', '💾 Daten': '💾 Data', '🔌 Hardware': '🔌 Hardware', '🧬 Quellordner': '🧬 Source folder',
            '🔌 USB-Vocoder': '🔌 USB vocoder', '🔒 Domains & HTTPS': '🔒 Domains & HTTPS',
            'nicht eingerichtet': 'not set up', 'pausiert': 'paused', 'läuft nicht': 'not running', 'aktiv': 'active', 'Internet': 'Internet', 'erreichbar': 'reachable',
            'weg seit': 'down since', 'Letzte Prüfung': 'Last check', 'gerade eben': 'just now', 'Heartbeat': 'Heartbeat', 'gesund': 'healthy', 'kein Neustart': 'no restart',
            'von Hand gestoppt – Keep-Alive wartet': 'stopped by hand – keep-alive waits', 'neu gestartet': 'restarted', 'Einmal auf der Konsole einrichten:': 'Set up once on the console:',
            'Keep-Alive an': 'Keep-alive on', 'Netzdienste nach einem Internet-Ausfall neu starten': 'Restart network services after an internet outage',
            'Heartbeat-Adresse': 'Heartbeat address', 'Heartbeat bei Fehlern (optional)': 'Heartbeat on errors (optional)', '▶ Fortsetzen': '▶ Resume',
            '⏸ 1 h pausieren (Wartung)': '⏸ Pause 1 h (maintenance)', 'Speichern': 'Save', 'Keep-Alive-Protokoll': 'Keep-alive log',
            'Jede Minute als root: prüft jeden Dienst wirklich (Weboberfläche und Verbindungen der Protokolle), startet kranke Dienste nach ein paar Minuten neu (höchstens 4× je Stunde), erkennt Internet-Ausfälle und startet danach die Netzdienste neu, und meldet sich bei einer Heartbeat-Adresse (Uptime Kuma „Push“, Healthchecks.io …). Ein von Hand gestoppter Dienst bleibt gestoppt.':
                'Every minute as root: checks every service for real (web interface and the connections of the protocols), restarts sick services after a few minutes (at most 4× per hour), notices internet outages and restarts the network services afterwards, and reports to a heartbeat address (Uptime Kuma “push”, Healthchecks.io …). A service stopped by hand stays stopped.',
            'Meldung': 'Message', 'Noch kein Update über die Weboberfläche.': 'No update through the web interface yet.', 'Neu laden': 'Reload',
            '📜 Update-Protokoll': '📜 Update log',
        }
    });
    add({
        base: 'en', de: {
            'Update available': 'Update verfügbar', "What's new?": 'Was ist neu?', 'Update now': 'Jetzt aktualisieren', 'Later': 'Später',
            'Check now': 'Jetzt prüfen', 'Installed': 'Installiert', 'On GitHub': 'Auf GitHub', 'Last checked': 'Zuletzt geprüft',
            'up to date': 'aktuell', 'Close': 'Schließen', 'Cancel': 'Abbrechen', 'Save': 'Speichern', 'Delete': 'Löschen', 'Edit': 'Bearbeiten',
            'Login': 'Anmelden', 'Log in': 'Anmelden', 'Log out': 'Abmelden', 'Logout': 'Abmelden', 'Username': 'Benutzername', 'Password': 'Passwort',
            'Links': 'Links', 'Admin': 'Admin', 'Settings': 'Einstellungen', 'Users': 'Benutzer', 'Appearance': 'Aussehen', 'System': 'System',
            'Updates': 'Updates', 'Logs': 'Protokolle', 'Log': 'Protokoll', 'Audit log': 'Änderungsprotokoll', 'Live': 'Live', 'Live data': 'Live-Daten',
            'Statistics': 'Statistik', 'Stats': 'Statistik', 'Last heard': 'Zuletzt gehört', 'Last Heard': 'Zuletzt gehört', 'On air': 'Auf Sendung',
            'Today': 'Heute', '24 h': '24 h', '7 days': '7 Tage', '30 days': '30 Tage', '90 days': '90 Tage', '1 year': '1 Jahr',
            'Time': 'Zeit', 'Duration': 'Dauer', 'Airtime': 'Sprechzeit', 'Calls': 'Gespräche', 'Talks': 'Durchgänge', 'Station': 'Station', 'Stations': 'Stationen',
            'Callsign': 'Rufzeichen', 'Name': 'Name', 'Status': 'Status', 'Online': 'Online', 'Offline': 'Offline', 'Quiet': 'Ruhe', 'Notifications': 'Benachrichtigungen',
            'Loading …': 'Lädt …', 'Loading': 'Lädt', 'Loading links …': 'Links werden geladen …', 'Nothing heard yet.': 'Noch nichts gehört.', 'never': 'nie', 'none': 'keine',
            'yes': 'ja', 'no': 'nein', 'on': 'an', 'off': 'aus', 'Yes': 'Ja', 'No': 'Nein', 'OK': 'OK', 'Back': 'Zurück', 'Refresh': 'Aktualisieren', 'Reload': 'Neu laden',
            'Restart': 'Neu starten', 'Restart now': 'Jetzt neu starten', 'Start': 'Starten', 'Stop': 'Stoppen', 'Upload': 'Hochladen', 'Download': 'Herunterladen',
            'Search': 'Suchen', 'Search …': 'Suchen …', 'Filter': 'Filter', 'All': 'Alle', 'Total': 'Gesamt', 'Version': 'Version', 'Uptime': 'Laufzeit',
            'Change password': 'Passwort ändern', 'Current password': 'Aktuelles Passwort', 'New password': 'Neues Passwort', 'Repeat new password': 'Neues Passwort wiederholen',
            'Role': 'Rolle', 'Created': 'Angelegt', 'Last login': 'Letzte Anmeldung', 'Add user': 'Benutzer anlegen', 'Remove': 'Entfernen', 'Add': 'Hinzufügen',
            'Saved': 'Gespeichert', 'Settings saved': 'Einstellungen gespeichert', 'Error': 'Fehler', 'Warning': 'Warnung', 'Info': 'Info',
            'Talkgroup': 'Talkgroup', 'Talkgroups': 'Talkgroups', 'Slot': 'Slot', 'Source': 'Quelle', 'Target': 'Ziel', 'Direction': 'Richtung',
            'seconds': 'Sekunden', 'minutes': 'Minuten', 'hours': 'Stunden', 'days': 'Tage', 'ago': 'her', 'just now': 'gerade eben',
            'Light': 'Hell', 'Dark': 'Dunkel', 'Auto': 'Automatisch', 'Colours': 'Farben', 'Colors': 'Farben', 'Logo': 'Logo', 'Title': 'Titel', 'Preview': 'Vorschau',
            'Reset': 'Zurücksetzen', 'Apply': 'Übernehmen', 'Copy': 'Kopieren', 'Copied': 'Kopiert', 'Show': 'Anzeigen', 'Hide': 'Ausblenden', 'More': 'Mehr', 'Less': 'Weniger',
            'Show all': 'Alle anzeigen', 'Show less': 'Weniger anzeigen', 'Details': 'Details', 'Description': 'Beschreibung', 'Enabled': 'Aktiv', 'Disabled': 'Aus',
        },
        rules: [
            [/^(\d+) minutes? ago$/, 'vor $1 Min.'], [/^(\d+) seconds? ago$/, 'vor $1 s'], [/^(\d+) hours? ago$/, 'vor $1 Std.'], [/^(\d+) days? ago$/, 'vor $1 Tagen'],
            [/^rolled back to (.+)$/, 'zurückgesetzt auf $1'], [/^rollback failed \(git reset\)$/, 'Zurücksetzen fehlgeschlagen (git reset)'],
            [/^(\d+) min ago$/, 'vor $1 Min.'], [/^(\d+) s ago$/, 'vor $1 s'], [/^(\d+) h ago$/, 'vor $1 Std.'], [/^(\d+) d ago$/, 'vor $1 T.'],
        ]
    });

    window.N8Kit = {
        version: '1.1.0',
        lang: () => lang, setLang, t, langSwitch, esc, fmtTime,
        i18n: { add, retranslate: () => { cache.clear(); retranslate(); }, t },
        update: { banner, panel, run },
        nav: { tree, GROUPS, SYS_ITEMS },
        sys: { view },
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})();
