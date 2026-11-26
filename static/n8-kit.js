/*
 * N8 Kit 1.6.0 – shared by the N8schicht web interfaces
 * (N8 Crosslink, HBlink4-FreeRadioID, adn-frn-server, N8-HotSpot).
 * The same file is in every repository; change it in one, copy it to the others.
 *
 *   N8Kit.lang()                 'de' | 'en' | 'fr' | 'fr-BE' | 'hu' | 'sv' | 'nl' | 'it' | 'es'
 *                                (cookie n8_lang, valid for every port of the host → all four pages)
 *   N8Kit.locale()               'de-DE', 'en-GB', 'fr-FR', … – for toLocaleString()
 *   N8Kit.setLang('fr')          switch without reloading
 *   N8Kit.i18n.add({ base: 'en', de: { 'Last heard': 'Zuletzt gehört' }, rules: [[/^(\d+) stations$/, '$1 Stationen']] })
 *                                more languages: { base: 'en', fr: {…}, hu: {…}, rules: { fr: [[re, repl]], … } } – always keyed by
 *                                the English text: a German text is first looked up in English, then in the target language;
 *                                a text without translation stays English (fr-BE falls back to fr).
 *   N8Kit.t('text')              translate one string (for alert/confirm, canvas, …)
 *   N8Kit.langSwitch(container)  language menu (🌐 DE ▾ with all nine languages; put into the header, next to Links/Login)
 *   N8Kit.login.open(opts)       the same login window everywhere (logo, title, eye for the password, Caps Lock hint, stay logged in,
 *                                language menu, lockout message); opts.submit({username, password, password2, remember}) → Promise
 *   N8Kit.userMenu(el, me, opts) header: 🔐 Login button, or avatar + name ▾ with my account, admin, … and log out
 *   N8Kit.update.banner(el, state, handlers)   update banner under the status strip
 *   N8Kit.update.panel(el, state, handlers)    Admin → Updates
 *   N8Kit.update.run(opts)                     install with progress, health check and reload
 *   N8Kit.nav.tree(el, groups, opts)           admin menu as a tree on the left (same structure in every N8 system)
 *   N8Kit.sys.view(el, name, opts)             the same System views everywhere: update, services, perms, keepalive, crashes
 *   N8Kit.access.view(el, name, opts)          Benutzer & Zugang: users, sessions, audit (look of HBlink4-FreeRadioID)
 *   N8Kit.net.view(el, name, opts)             Netz, Ports & Domains: ports, domains (look of N8 Crosslink)
 *   N8Kit.sys.crashPopup(opts)                 after the admin login: window with new crashes/hangs (until marked as read)
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
    const LANGS = ['de', 'en', 'fr', 'fr-BE', 'hu', 'sv', 'nl', 'it', 'es'];
    // native name, short code in the header, locale for dates and numbers
    const LANG_INFO = {
        'de': ['Deutsch', 'DE', 'de-DE'], 'en': ['English', 'EN', 'en-GB'], 'fr': ['Français', 'FR', 'fr-FR'],
        'fr-BE': ['Français (Belgique)', 'BE', 'fr-BE'], 'hu': ['Magyar', 'HU', 'hu-HU'], 'sv': ['Svenska', 'SV', 'sv-SE'],
        'nl': ['Nederlands', 'NL', 'nl-NL'], 'it': ['Italiano', 'IT', 'it-IT'], 'es': ['Español', 'ES', 'es-ES'],
    };
    const FALLBACK = { 'fr-BE': ['fr-BE', 'fr'] };
    const SKIP = new Set(['SCRIPT', 'STYLE', 'CODE', 'PRE', 'TEXTAREA', 'NOSCRIPT', 'SVG', 'KBD', 'SAMP']);
    const ATTRS = ['title', 'placeholder', 'aria-label', 'alt', 'data-label'];
    const ORIG = '__n8o', DONE = '__n8t';

    // ------------------------------------------------------------ language
    function readCookie() {
        const m = document.cookie.match(/(?:^|;\s*)n8_lang=([A-Za-z-]{2,5})/);
        return m ? m[1] : null;
    }
    let lang = readCookie();
    if (!lang) { try { lang = localStorage.getItem(COOKIE); } catch (e) { } }
    if (LANGS.indexOf(lang) < 0) {
        // first visit: the browser language, if we have it
        const nav = (navigator.languages || [navigator.language || '']).map(x => String(x));
        lang = 'de';
        for (const x of nav) {
            const full = LANGS.find(l => l.toLowerCase() === x.toLowerCase()), short = LANGS.find(l => l === x.slice(0, 2).toLowerCase());
            if (full || short) { lang = full || short; break; }
        }
    }
    const q = (location.search.match(/[?&]lang=([A-Za-z-]{2,5})/) || [])[1];
    if (q && LANGS.indexOf(q) >= 0) lang = q;
    const locale = () => (LANG_INFO[lang] || LANG_INFO.de)[2];

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

    function lookup(core, L) {
        for (let i = packs.length - 1; i >= 0; i--) {
            const p = packs[i];
            if (p.to !== L) continue;
            if (p.map.has(core)) return p.map.get(core);
        }
        for (let i = packs.length - 1; i >= 0; i--) {
            const p = packs[i];
            if (p.to !== L) continue;
            for (const [re, rep] of p.rules) {
                if (re.test(core)) { re.lastIndex = 0; return core.replace(re, typeof rep === 'function' ? rep : rep); }
            }
        }
        return null;
    }
    // one language: exact text, then without leading symbols and trailing punctuation
    function tr1(n, L) {
        let r = lookup(n, L);
        if (r == null) {
            const m = n.match(SPLIT);
            if (m && m[2]) {
                let c = lookup(m[2], L);
                if (c != null) r = m[1] + c + m[3];
                else if (m[3] && (c = lookup(m[2] + m[3].trim(), L)) != null) r = m[1] + c + (m[3].match(/\s*$/) || [''])[0];
            }
        }
        return r;
    }
    // target language with fallbacks: fr-BE → fr; German source → English → target; nothing → English
    function trn(n) {
        const chain = FALLBACK[lang] || [lang];
        for (const L of chain) { const r = tr1(n, L); if (r != null) return r; }
        if (lang === 'de' || lang === 'en') return null;
        const e = tr1(n, 'en');
        if (e == null) return null;
        for (const L of chain) { const r = tr1(norm(e), L); if (r != null) return r; }
        return e;
    }
    function t(s) {
        if (s == null) return s;
        s = String(s);
        if (!packs.some(p => p.to === lang || p.to === 'en') || !/\p{L}/u.test(s)) return s;
        const key = lang + '\u0000' + s;
        if (cache.has(key)) return cache.get(key);
        if (s.indexOf('\n') >= 0) {
            // a paragraph written over several source lines counts as one text; otherwise line by line
            const whole = trn(norm(s));
            const out = whole != null ? s.match(/^\s*/)[0] + whole + s.match(/\s*$/)[0] : s.split('\n').map(t).join('\n');
            cache.set(key, out);
            return out;
        }
        let out = s;
        const lead = s.match(/^\s*/)[0], trail = s.match(/\s*$/)[0];
        const r = trn(norm(s));
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
        document.cookie = `${COOKIE}=${l}; path=/; max-age=31536000; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`;
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

    // ------------------------------------------------------------ language menu (1.6: dropdown with all languages)
    let menuSeq = 0;
    function paintSwitch(el) {
        const info = LANG_INFO[lang] || LANG_INFO.de;
        const cur = el.querySelector('.n8-lang-cur');
        if (cur) cur.textContent = info[1];
        el.querySelectorAll('[data-l]').forEach(b => {
            const on = b.dataset.l === lang;
            b.classList.toggle('on', on);
            b.setAttribute('aria-checked', on ? 'true' : 'false');
        });
    }
    // small dropdown helper: trigger + panel, closes on outside click / Escape, arrow keys move between the entries
    function dropdown(root, trigger, panel) {
        const items = () => Array.from(panel.querySelectorAll('[role^=menuitem]:not([hidden]):not(:disabled)'));
        const close = (focus) => { if (!root.classList.contains('open')) return; root.classList.remove('open'); trigger.setAttribute('aria-expanded', 'false'); if (focus) trigger.focus(); };
        const open = () => {
            document.querySelectorAll('.n8-dd.open').forEach(o => { if (o !== root) o.classList.remove('open'); });
            root.classList.add('open'); trigger.setAttribute('aria-expanded', 'true');
            const r = trigger.getBoundingClientRect();
            panel.classList.toggle('left', r.left + r.width / 2 < window.innerWidth / 2);
            const on = panel.querySelector('.on') || items()[0]; if (on) setTimeout(() => on.focus({ preventScroll: true }), 0);
        };
        trigger.setAttribute('aria-haspopup', 'menu'); trigger.setAttribute('aria-expanded', 'false');
        if (!panel.id) panel.id = 'n8dd' + (++menuSeq);
        trigger.setAttribute('aria-controls', panel.id);
        trigger.addEventListener('click', e => { e.stopPropagation(); root.classList.contains('open') ? close() : open(); });
        trigger.addEventListener('keydown', e => { if (e.key === 'ArrowDown') { e.preventDefault(); open(); } });
        panel.addEventListener('keydown', e => {
            const list = items(), i = list.indexOf(document.activeElement);
            if (e.key === 'Escape') { e.preventDefault(); close(true); }
            else if (e.key === 'ArrowDown') { e.preventDefault(); (list[i + 1] || list[0]).focus(); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); (list[i - 1] || list[list.length - 1]).focus(); }
            else if (e.key === 'Tab') close();
        });
        panel.addEventListener('click', e => { if (e.target.closest('[role^=menuitem]')) close(); });
        document.addEventListener('click', e => { if (!root.contains(e.target)) close(); });
        return { open, close };
    }
    function langSwitch(container, opts) {
        if (!container) return null;
        let el = container.querySelector('.n8-lang');
        if (el && !el.classList.contains('n8-dd')) { el.remove(); el = null; }      // old DE | EN switch
        if (!el) {
            el = document.createElement('div');
            el.className = 'n8-lang n8-dd notranslate';
            el.setAttribute('translate', 'no');
            el.innerHTML = '<button type="button" class="n8-lang-btn" title="Sprache · Language · Langue · Nyelv · Språk · Taal · Lingua · Idioma">'
                + '<span class="n8-lang-ic" aria-hidden="true">🌐</span><span class="n8-lang-cur"></span><span class="n8-dd-car" aria-hidden="true">▾</span></button>'
                + '<div class="n8-dd-pop n8-lang-pop" role="menu" aria-label="Language">'
                + LANGS.map(l => `<button type="button" role="menuitemradio" data-l="${l}" lang="${LANG_INFO[l][2]}"><span class="n8-lang-code">${LANG_INFO[l][1]}</span>${LANG_INFO[l][0]}</button>`).join('')
                + '</div>';
            dropdown(el, el.firstChild, el.querySelector('.n8-lang-pop'));
            el.querySelector('.n8-lang-pop').addEventListener('click', e => { const b = e.target.closest('[data-l]'); if (b) setLang(b.dataset.l); });
            if (opts && opts.before && opts.before.parentNode === container) container.insertBefore(el, opts.before);
            else if (opts && opts.prepend) container.insertBefore(el, container.firstChild);
            else container.appendChild(el);
        }
        paintSwitch(el);
        return el;
    }

    // ------------------------------------------------------------ user menu in the header (1.6)
    // me = null → 🔐 Login button; otherwise avatar + name ▾ with a small card (name, role) and the entries in opts.items
    function userInitials(n) { return String(n || '?').trim().split(/[\s._@-]+/).filter(Boolean).slice(0, 2).map(x => x[0]).join('').toUpperCase() || '?'; }
    function userMenu(el, me, opts) {
        if (!el) return;
        opts = opts || {};
        if (!me) {
            el.innerHTML = `<button type="button" class="n8-login-btn ${opts.btnClass || 'btn primary hdr-btn login'}"><span aria-hidden="true">🔐</span><span class="u-name">${esc(opts.loginLabel || 'Anmelden')}</span></button>`;
            el.firstChild.addEventListener('click', () => opts.onLogin && opts.onLogin());
            return;
        }
        const name = me.name || me.username || '';
        const av = opts.avatar || `<span class="n8-av">${esc(userInitials(name))}</span>`;
        const items = (opts.items || []).filter(x => x && !x.hidden);
        el.innerHTML = `<div class="n8-user n8-dd">
            <button type="button" class="n8-user-btn ${opts.btnClass || 'btn hdr-btn'}" title="${esc(name)}${me.role ? ' · ' + esc(me.role) : ''}">${av}<span class="u-name">${esc(name)}</span><span class="n8-dd-car" aria-hidden="true">▾</span></button>
            <div class="n8-dd-pop n8-user-pop" role="menu">
                <div class="n8-user-card">${av.replace('class="n8-av', 'class="n8-av big')}<div><b>${esc(name)}</b>${me.role ? `<span class="n8-role n8-role-${esc(String(me.role).toLowerCase())}">${esc(opts.roleLabel || me.role)}</span>` : ''}${me.sub ? `<small>${esc(me.sub)}</small>` : ''}</div></div>
                ${items.map((x, i) => `${x.sep ? '<hr>' : ''}<button type="button" role="menuitem" data-i="${i}"${x.disabled ? ' disabled' : ''}><span class="n8-mi-ic" aria-hidden="true">${x.icon || ''}</span>${esc(x.label)}</button>`).join('')}
                <hr><button type="button" role="menuitem" class="n8-mi-out" data-i="out"><span class="n8-mi-ic" aria-hidden="true">⏻</span>${esc(opts.logoutLabel || 'Abmelden')}</button>
            </div></div>`;
        const root = el.firstChild;
        dropdown(root, root.querySelector('.n8-user-btn'), root.querySelector('.n8-user-pop'));
        root.querySelector('.n8-user-pop').addEventListener('click', e => {
            const b = e.target.closest('[data-i]'); if (!b) return;
            if (b.dataset.i === 'out') { if (opts.onLogout) opts.onLogout(); }
            else { const x = items[+b.dataset.i]; if (x && x.onClick) x.onClick(); }
        });
    }

    // ------------------------------------------------------------ login window (1.6) – the same in every N8 system
    // opts: title, subtitle, logo, remember (text or false), closable (default true), setup (true → repeat password, minLength),
    //       submit({username, password, password2, remember}) → Promise (throw Error(message) on failure), user (prefill)
    function loginOpen(opts) {
        opts = opts || {};
        loginClose();
        const closable = opts.closable !== false;
        const ov = document.createElement('div');
        ov.className = 'n8-login-ov';
        ov.innerHTML = `<form class="n8-login" autocomplete="on" novalidate role="dialog" aria-modal="true" aria-labelledby="n8LoginT">
            ${closable ? '<button type="button" class="n8-login-x" aria-label="Schließen" title="Schließen">✕</button>' : ''}
            ${opts.logo ? `<img class="n8-login-logo" src="${esc(opts.logo)}" alt="">` : ''}
            <h2 id="n8LoginT">${esc(opts.title || 'Anmelden')}</h2>
            ${opts.subtitle ? `<p class="n8-login-sub">${esc(opts.subtitle)}</p>` : ''}
            <label class="n8-field"><span>${esc(opts.userLabel || 'Benutzername')}</span>
                <span class="n8-inp"><span class="n8-inp-ic" aria-hidden="true">👤</span><input name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required value="${esc(opts.user || '')}"></span></label>
            <label class="n8-field"><span>${esc('Passwort')}</span>
                <span class="n8-inp"><span class="n8-inp-ic" aria-hidden="true">🔑</span><input name="password" type="password" autocomplete="${opts.setup ? 'new-password' : 'current-password'}" required${opts.minLength ? ` minlength="${+opts.minLength}"` : ''}>
                <button type="button" class="n8-eye" aria-label="Passwort anzeigen" title="Passwort anzeigen">👁</button></span></label>
            ${opts.setup ? `<label class="n8-field"><span>${esc('Passwort wiederholen')}</span>
                <span class="n8-inp"><span class="n8-inp-ic" aria-hidden="true">🔑</span><input name="password2" type="password" autocomplete="new-password" required></span></label>` : ''}
            <div class="n8-caps" hidden>⇪ ${esc('Feststelltaste ist an')}</div>
            ${opts.remember ? `<label class="n8-login-rem"><input type="checkbox" name="remember"><span class="n8-sw-ui" aria-hidden="true"></span><span>${esc(opts.remember === true ? 'Angemeldet bleiben' : opts.remember)}</span></label>` : ''}
            <div class="n8-login-err" role="alert" hidden></div>
            <button type="submit" class="n8-login-go"><span class="n8-spin" aria-hidden="true"></span><span>${esc(opts.button || (opts.setup ? 'Anlegen' : 'Anmelden'))}</span></button>
            <div class="n8-login-foot"><span class="n8-login-lock">🔒 ${esc(location.protocol === 'https:' ? 'Verschlüsselte Verbindung' : 'Unverschlüsselte Verbindung (HTTP)')}</span></div>
        </form>`;
        document.body.appendChild(ov);
        const f = ov.querySelector('form'), err = f.querySelector('.n8-login-err'), go = f.querySelector('.n8-login-go');
        langSwitch(f.querySelector('.n8-login-foot'));
        const pw = f.password;
        f.querySelector('.n8-eye').addEventListener('click', e => {
            const show = pw.type === 'password'; pw.type = show ? 'text' : 'password';
            if (f.password2) f.password2.type = pw.type;
            e.currentTarget.classList.toggle('on', show); pw.focus();
        });
        const caps = e => { if (e.getModifierState) f.querySelector('.n8-caps').hidden = !e.getModifierState('CapsLock'); };
        f.addEventListener('keydown', caps); f.addEventListener('keyup', caps);
        if (closable) {
            f.querySelector('.n8-login-x').addEventListener('click', loginClose);
            ov.addEventListener('mousedown', e => { if (e.target === ov) loginClose(); });
            ov.addEventListener('keydown', e => { if (e.key === 'Escape') loginClose(); });
        }
        const fail = m => {
            err.textContent = m; err.hidden = false;
            f.classList.remove('shake'); void f.offsetWidth; f.classList.add('shake');
        };
        f.addEventListener('submit', async e => {
            e.preventDefault();
            err.hidden = true;
            const v = { username: f.username.value.trim(), password: pw.value, password2: f.password2 ? f.password2.value : undefined, remember: !!(f.remember && f.remember.checked) };
            if (!v.username || !v.password) { fail(t('Bitte Benutzername und Passwort eingeben.')); (v.username ? pw : f.username).focus(); return; }
            if (opts.setup && opts.minLength && v.password.length < opts.minLength) { fail(t('Das Passwort ist zu kurz.') + ` (min. ${opts.minLength})`); pw.focus(); return; }
            if (opts.setup && v.password !== v.password2) { fail(t('Die Passwörter stimmen nicht überein.')); f.password2.focus(); return; }
            go.disabled = true; f.classList.add('busy');
            try {
                await opts.submit(v);
                loginClose();
            } catch (x) {
                fail(t((x && x.message) || 'Anmeldung fehlgeschlagen.'));
                pw.select();
            } finally { go.disabled = false; f.classList.remove('busy'); }
        });
        setTimeout(() => (opts.user ? pw : f.username).focus(), 30);
        return ov;
    }
    function loginClose() { document.querySelectorAll('.n8-login-ov').forEach(o => o.remove()); }

    // ------------------------------------------------------------ helpers
    const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    function fmtTime(v) {
        if (!v) return '–';
        const d = typeof v === 'number' ? new Date(v < 1e12 ? v * 1000 : v) : new Date(v);
        if (isNaN(d)) return String(v);
        return d.toLocaleString(locale(), { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
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
                    // the version did not change: was it rolled back, or did the update not even start? (data/update.result)
                    let r = null;
                    try { const d = await (await fetch(o.resultUrl || '/api/admin/update-log', { credentials: 'same-origin', cache: 'no-store' })).json(); r = d && d.result; } catch (e) { r = null; }
                    const fresh = r && !r.ok && r.time && r.time * 1000 >= t0 - 15000;
                    if (fresh && !/zurück/i.test(r.message || '')) {          // stopped before anything was changed
                        step(0, 'bad');
                        finish(false, esc(t('Nicht aktualisiert – es läuft unverändert die bisherige Version.')) + ' <b>' + esc(seen) + '</b><br>' + esc(t(r.message || ''))
                            + '<br><span class="n8-help">' + esc(t('Einzelheiten im Update-Protokoll (System → Update).')) + '</span>');
                        return;
                    }
                    step(2, 'bad'); finish(false, esc(t('Das Update wurde zurückgenommen – es läuft wieder die vorherige Version.')) + ' <b>' + esc(seen) + '</b>'
                        + (fresh && r.message ? '<br>' + esc(t(r.message)) : '')); return;
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
    // groups: [{ id, label, items: [{ id, label, hidden, badge, badgeClass, children }] }] – labels with a leading emoji. opts: { active, onSelect(id), key }
    // The same groups in every N8 system: Betrieb · Benutzer & Zugang · Darstellung · Netz & Domains · System.
    // items may have children: [{ id, label }] – shown indented under the item (the former in-page menus of a page).
    // onSelect gets the id of the item or of the child ('settings' or 'settings:dmr').
    function tree(el, groups, opts) {
        opts = opts || {};
        // groups start closed (the same in every N8 system); only the group of the open page and the groups you opened are open
        const key = 'n8nav2:' + (opts.key || location.pathname);
        let opened = {};
        try { opened = JSON.parse(sessionStorage.getItem(key) || '{}'); } catch (e) { opened = {}; }
        const act = opts.active;
        const items = groups.map(g => ({ ...g, items: (g.items || []).filter(i => !i.hidden) })).filter(g => g.items.length);
        const all = items.flatMap(g => g.items.flatMap(i => [i, ...(i.children || [])]));
        const cur = all.find(i => i.id === act);
        const inItem = i => i.id === act || (i.children || []).some(c => c.id === act);
        const btn = (i, cls) => `<button type="button" class="n8-tree-i ${cls || ''} ${i.id === act ? 'on' : ''}" data-i="${esc(i.id)}">${esc(i.label)}${i.badge ? `<span class="n8-badge ${esc(i.badgeClass || '')}">${esc(i.badge)}</span>` : ''}</button>`;
        el.classList.add('n8-tree');
        el.innerHTML = `<button type="button" class="n8-tree-toggle">☰ <span>${esc(cur ? cur.label : 'Menü')}</span></button>
            <div class="n8-tree-body">${items.map(g => {
                const open = !!opened[g.id] || g.items.some(inItem);
                return `<div class="n8-tree-g ${open ? 'open' : ''}" data-g="${esc(g.id)}">
                    <button type="button" class="n8-tree-gh"><span class="n8-tree-car">▸</span>${esc(g.label)}</button>
                    <div class="n8-tree-items">${g.items.map(i => btn(i, (i.children || []).length ? 'has-kids' + (inItem(i) ? ' kids-open' : '') : '')
                        + ((i.children || []).length && inItem(i) ? `<div class="n8-tree-kids">${i.children.map(c => btn(c, 'kid')).join('')}</div>` : '')).join('')}</div></div>`;
            }).join('')}</div>`;
        el.querySelector('.n8-tree-toggle').onclick = () => el.classList.toggle('open');
        el.querySelectorAll('.n8-tree-gh').forEach(b => b.onclick = () => {
            const g = b.parentElement; g.classList.toggle('open'); if (g.classList.contains('open')) opened[g.dataset.g] = 1; else delete opened[g.dataset.g];
            try { sessionStorage.setItem(key, JSON.stringify(opened)); } catch (e) { /* private mode */ }
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
    const fmt = ts => ts ? new Date(ts * 1000).toLocaleString(locale(), { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '–';
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
                    let r = null;
                    try { r = await req('POST', `/api/admin/services/${encodeURIComponent(u)}/${a}`, {}); } catch (e) { alert(e.message); }
                    if (r && r.self) {          // der eigene Dienst startet neu: warten, bis die Weboberfläche wieder antwortet
                        paint(card('🧩 Dienste', `<div class="n8-help">⏳ ${esc(t(a === 'stop' ? 'Die Weboberfläche wird gestoppt …' : 'Die Weboberfläche startet neu – einen Moment …'))}</div>`));
                        if (a === 'stop') return;
                        const t0 = Date.now();
                        await new Promise(res => setTimeout(res, 3000));
                        while (Date.now() - t0 < 120000) {
                            try { await req('GET', '/api/admin/services'); break; } catch (e) { await new Promise(res => setTimeout(res, 2000)); }
                        }
                        return load();
                    }
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
        if (name === 'crashes') return crashView(el, o, paint, msg);
    }

    // ============================================================ crashes (1.3.0) – identical in every N8 system
    // /api/admin/crashes → { items: [{id, time, unit, service, kind, reason, restarted, new}], unacked, week: {service: n}, watch: {units} }
    // /api/admin/crashes/<id> → { log }   ·   POST /api/admin/crashes/ack { all: true } | { ids: [...] }
    const KIND = { crash: ['💥', 'Absturz', 'bad'], watchdog: ['⏱️', 'Watchdog', 'bad'], oom: ['🧠', 'Speicher voll', 'bad'], exit: ['⏹️', 'Beendet', 'warn'],
                   timeout: ['⌛', 'Zeitüberschreitung', 'bad'], stall: ['⏳', 'Hänger', 'warn'], task: ['🧩', 'Teil abgestürzt', 'warn'],
                   thread: ['🧵', 'Thread abgestürzt', 'warn'], helper: ['⚙️', 'Hilfsprozess abgestürzt', 'warn'], keepalive: ['💓', 'Keep-Alive-Neustart', 'warn'],
                   restart: ['↻', 'Neustart', 'warn'], intern: ['⚠️', 'Fehler', 'warn'] };
    const kindOf = k => KIND[k] || ['⚠️', k || '?', 'warn'];
    const fmtFull = ts => ts ? new Date(ts * 1000).toLocaleString(locale(), { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '–';
    function crashRow(e) {
        const k = kindOf(e.kind);
        return `<details class="n8-crash ${e.new ? 'new' : ''}" data-id="${esc(e.id)}"><summary>
            <span class="n8-crash-ic">${k[0]}</span><span class="n8-crash-t">${esc(fmtFull(e.time))}</span>
            <span class="n8-badge ${k[2]}">${esc(t(k[1]))}</span><b class="n8-crash-s">${esc(e.service || e.unit || '?')}</b>
            <span class="n8-crash-r">${esc(e.reason || '')}</span>
            <span class="n8-crash-m">${e.restarted ? `<span class="n8-badge ok">↻ ${esc(t('neu gestartet'))}</span>` : ''}${e.new ? `<span class="n8-badge bad">${esc(t('neu'))}</span>` : ''}<code>${esc(e.unit || '')}</code></span>
            </summary><pre class="n8-log">…</pre>
            <div class="n8-actions"><button type="button" class="n8-btn" data-del="${esc(e.id)}">🗑 ${esc(t('Diesen Befund löschen'))}</button></div></details>`;
    }
    function bindRows(el, req) {
        el.querySelectorAll('details.n8-crash').forEach(d => d.addEventListener('toggle', async () => {
            if (!d.open || d.dataset.loaded) return;
            d.dataset.loaded = '1';
            const pre = d.querySelector('pre');
            try { const r = await req('GET', '/api/admin/crashes/' + encodeURIComponent(d.dataset.id)); pre.textContent = r.log || t('Kein Protokoll vorhanden.'); }
            catch (x) { pre.textContent = x.message; }
        }));
    }
    async function crashView(el, o, paint, msg) {
        const req = o.req, cons = o.console || 'sudo scripts/n8-admin.sh';
        let filter = '';
        const load = async () => {
            let d; try { d = await req('GET', '/api/admin/crashes'); } catch (e) { paint(card('💥 Abstürze', msg(e))); return; }
            const items = (d.items || []).filter(e => !filter || (e.service || e.unit) === filter);
            const week = Object.entries(d.week || {}).sort((a, b) => b[1] - a[1]);
            const units = (d.watch && d.watch.units) || [];
            const badge = d.unacked ? `<span class="n8-badge bad">${d.unacked} ${esc(t('neu'))}</span>` : `<span class="n8-badge ok">${esc(t('alles gelesen'))}</span>`;
            paint(`<div class="n8-crash-sys">${card('💥 Abstürze', `<p class="n8-help">${esc(t('Jeder Absturz, Hänger und Notfall-Neustart aller Dienste wird hier festgehalten – mit dem Teil der Anwendung, in dem er passiert ist, und dem vollständigen Protokoll (Journal, Python-Stack). Der Dienst wird dabei automatisch neu gestartet. Neue Befunde erscheinen nach der Anmeldung als Hinweis, bis sie als gelesen markiert sind.'))}</p>
                ${week.length ? `<div class="n8-crash-week"><span class="n8-dim">${esc(t('Letzte 7 Tage'))}:</span> ${week.map(([s, n]) => `<button type="button" class="n8-chip ${filter === s ? 'on' : ''}" data-f="${esc(s)}">${esc(s)} <b>${n}</b></button>`).join('')}${filter ? `<button type="button" class="n8-chip" data-f="">✕ ${esc(t('alle'))}</button>` : ''}</div>` : ''}
                <div class="n8-crash-list">${items.length ? items.map(crashRow).join('') : `<div class="n8-help">✅ ${esc(t('Keine Abstürze festgehalten.'))}</div>`}</div>
                <div class="n8-actions">${d.unacked ? `<button type="button" class="n8-btn primary" data-a="ack">✔ ${esc(t('Alle als gelesen markieren'))}</button>` : ''}${items.length ? `<button type="button" class="n8-btn danger" data-a="del">🗑 ${esc(filter ? t('Angezeigte löschen') + ` (${items.length})` : t('Alle löschen'))}</button>` : ''}<button type="button" class="n8-btn" data-a="reload">↻ ${esc(t('Neu laden'))}</button></div>`, badge)}
                ${card('🛡️ Absturz-Wächter', units.length ? `<p class="n8-help">${esc(t('Diese Dienste werden überwacht. Nach jedem unerwarteten Ende hält systemd den Befund fest und startet den Dienst neu; bleibt er ausgefallen, startet ihn der Keep-Alive neu.'))}</p>
                    <div class="n8-perm">${units.map(u => `<div class="n8-perm-r">✅<b>${esc(u.label || u.unit)}</b><span><code>${esc(u.unit)}</code> · ${esc(t('Neustart'))}: ${esc(u.restart || '–')}</span></div>`).join('')}</div>`
                    : `<p class="n8-help">⚠️ ${esc(t('Der Absturz-Wächter ist noch nicht eingerichtet. Er wird beim nächsten Update eingerichtet – oder einmal auf der Konsole:'))}</p><pre class="n8-log">${esc(cons)} setup-crashwatch</pre>`)}</div>`);
            bindRows(el, req);
            el.querySelectorAll('[data-f]').forEach(b => b.onclick = () => { filter = b.dataset.f; load(); });
            const ack = el.querySelector('[data-a=ack]');
            if (ack) ack.onclick = async () => { try { await req('POST', '/api/admin/crashes/ack', { all: true }); load(); if (o.onAck) o.onAck(); } catch (x) { alert(x.message); } };
            el.querySelector('[data-a=reload]').onclick = load;
            // bereinigen: alle (oder die gefilterten) Befunde samt Protokoll löschen
            const del = async (body, question) => {
                if (!confirm(question)) return;
                try { await req('POST', '/api/admin/crashes/delete', body); if (o.onAck) o.onAck(); load(); } catch (x) { alert(x.message); }
            };
            const delAll = el.querySelector('[data-a=del]');
            if (delAll) delAll.onclick = () => filter
                ? del({ ids: items.map(e => e.id) }, t('Die angezeigten Befunde samt Protokoll löschen?') + ` (${items.length})`)
                : del({ all: true }, t('Alle Befunde samt Protokoll löschen? Das lässt sich nicht rückgängig machen.'));
            el.querySelectorAll('[data-del]').forEach(b => b.onclick = ev => { ev.preventDefault(); del({ ids: [b.dataset.del] }, t('Diesen Befund samt Protokoll löschen?')); });
        };
        return load();
    }
    // after the admin login (and on every admin page load): show new crashes once per browser tab until they are marked as read
    // opts = { req, open: () => go to System → Abstürze, force }
    async function crashPopup(o) {
        o = o || {};
        let d; try { d = await o.req('GET', '/api/admin/crashes'); } catch (e) { return null; }
        if (!d || !d.unacked) return d;
        const fresh = (d.items || []).filter(e => e.new);
        const key = 'n8_crash_seen';
        let seen = ''; try { seen = sessionStorage.getItem(key) || ''; } catch (e) { }
        if (!o.force && seen === fresh[0].id) return d;
        try { sessionStorage.setItem(key, fresh[0].id); } catch (e) { }
        if (document.querySelector('.n8-crash-ov')) return d;
        const ov = document.createElement('div');
        ov.className = 'n8-upd-ov n8-crash-ov';
        ov.innerHTML = `<div class="n8-upd-box n8-crash-box" role="dialog" aria-modal="true">
            <h3>💥 ${esc(fresh.length === 1 ? t('1 neuer Absturz') : t('{n} neue Abstürze').replace('{n}', fresh.length))}</h3>
            <p class="n8-help">${esc(t('Seit dem letzten Lesen ist ein Dienst abgestürzt oder hing. Er wurde automatisch neu gestartet. Der Befund nennt den Teil der Anwendung und enthält das vollständige Protokoll.'))}</p>
            <div class="n8-crash-list">${fresh.slice(0, 6).map(crashRow).join('')}</div>
            ${fresh.length > 6 ? `<div class="n8-help">+ ${fresh.length - 6} ${esc(t('weitere'))}</div>` : ''}
            <div class="n8-actions">${o.open ? `<button type="button" class="n8-btn" data-a="open">🔎 ${esc(t('Alle Abstürze ansehen'))}</button>` : ''}
              <button type="button" class="n8-btn" data-a="later">${esc(t('Später'))}</button>
              <button type="button" class="n8-btn primary" data-a="ack">✔ ${esc(t('Gelesen'))}</button></div></div>`;
        document.body.appendChild(ov);
        retranslateEl(ov);
        bindRows(ov, o.req);
        const close = () => ov.remove();
        ov.addEventListener('click', e => { if (e.target === ov) close(); });
        ov.querySelector('[data-a=later]').onclick = close;
        const op = ov.querySelector('[data-a=open]'); if (op) op.onclick = () => { close(); o.open(); };
        ov.querySelector('[data-a=ack]').onclick = async () => { try { await o.req('POST', '/api/admin/crashes/ack', { ids: fresh.map(e => e.id) }); } catch (x) { } close(); if (o.onAck) o.onAck(); };
        return d;
    }


    // ============================================================ Benutzer & Zugang (1.4.0) – Vorbild HBlink4-FreeRadioID, gleich in allen N8-Systemen
    // N8Kit.access.view(el, 'users' | 'sessions' | 'audit', opts)
    //   opts.req(method, url, body)       die Anfrage-Funktion des Projekts
    //   opts.me = { username, role }      wer angemeldet ist
    //   opts.roles = [{ id, label, assign: 'all' | 'superadmin' | 'none' }]   wählbare Rollen (Reihenfolge = Anzeige)
    //   opts.fields = ['display_name', 'dmr_id', 'callsign']                  zusätzliche Felder je Benutzer
    //   opts.api = { list, create, update, remove, sessions, revoke, audit }    eigene Adressen (sonst /api/admin/users, /sessions, /audit)
    //   opts.locked(u, me) → Text | ''    warum ein Benutzer hier nicht änderbar ist; opts.avatar(u) → HTML; opts.note → Hinweis unter der Tabelle
    //   opts.columns = [{ label, html(u) }]   zusätzliche Spalten · opts.actions(u) → [{ label, run(u) }] zusätzliche Knöpfe · opts.minPw (8)
    const FIELD = { display_name: ['Anzeigename', 'text'], dmr_id: ['DMR-ID', 'numeric'], callsign: ['Rufzeichen', 'text'] };
    const ago = ts => ts ? fmtShort(ts) : '–';
    function fmtShort(ts) { return new Date(ts * 1000).toLocaleString(locale(), { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }); }
    function shortUA(ua) {
        if (!ua) return '–';
        const b = /Edg\//.test(ua) ? 'Edge' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
        const os = /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS' : /Windows/.test(ua) ? 'Windows' : /Mac OS/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : '';
        return `${b}${os ? ' · ' + os : ''}`;
    }
    function initials(u) {
        const n = String(u.display_name || u.username || '?').trim();
        return esc((n.match(/\b\w/g) || [n[0] || '?']).slice(0, 2).join('').toUpperCase());
    }
    async function accessView(el, name, o) {
        const req = o.req, me = o.me || {};
        const A = Object.assign({
            list: async () => { const r = await req('GET', '/api/admin/users'); return r.users || r.items || []; },
            create: d => req('POST', '/api/admin/users', d),
            update: (u, d) => req('PATCH', '/api/admin/users/' + encodeURIComponent(u.id), d),
            remove: u => req('DELETE', '/api/admin/users/' + encodeURIComponent(u.id)),
            sessions: async () => { const r = await req('GET', '/api/admin/sessions'); return r.sessions || r.items || []; },
            revoke: s => req('DELETE', '/api/admin/sessions/' + encodeURIComponent(s.id)),
            audit: async () => { const r = await req('GET', '/api/admin/audit'); return r.audit || r.entries || r.items || []; },
        }, o.api || {});
        const roles = o.roles || [{ id: 'superadmin', label: 'Superadmin', assign: 'none' }, { id: 'admin', label: 'Admin', assign: 'superadmin' }, { id: 'user', label: 'Benutzer', assign: 'all' }];
        const RL = Object.fromEntries(roles.map(r => [r.id, r.label]));
        const fields = o.fields || ['display_name'];
        const msg = e => `<div class="n8-help">⚠️ ${esc(e && e.message ? e.message : String(e))}</div>`;
        const paint = html => { el.innerHTML = html; retranslateEl(el); };
        const role = r => `<span class="n8-role n8-role-${esc(r)}">${esc(t(RL[r] || r))}</span>`;
        const toast = (m, bad) => { if (o.toast) o.toast(m, bad); else if (bad) alert(m); };
        el.classList.add('n8-access');
        if (name === 'users') {
            const canAssign = r => r.assign === 'all' || (r.assign === 'superadmin' && me.role === 'superadmin') || (r.assign === 'admin' && ['admin', 'superadmin'].includes(me.role));
            const opts = sel => roles.filter(r => canAssign(r) || r.id === sel).map(r => `<option value="${esc(r.id)}" ${r.id === sel ? 'selected' : ''} ${canAssign(r) ? '' : 'disabled'}>${esc(t(r.label))}</option>`).join('');
            const locked = u => o.locked ? o.locked(u, me) : (u.role === 'superadmin' && me.role !== 'superadmin' ? t('nur Superadmin') : '');
            const cols = o.columns || [], minPw = o.minPw || 8;
            const load = async () => {
                let users; try { users = await A.list(); } catch (e) { paint(card('👥 Benutzer', msg(e))); return; }
                const inp = (f, u) => `<input name="${f}" placeholder="${esc(t(FIELD[f][0]))}" ${FIELD[f][1] === 'numeric' ? 'inputmode="numeric"' : ''} value="${esc(u ? (u[f] ?? '') : '')}">`;
                const rows = users.map((u, i) => {
                    const lk = locked(u);
                    return `<tr class="${u.disabled ? 'off' : ''}"><td><span class="n8-user-c">${o.avatar ? o.avatar(u) : `<span class="n8-av">${initials(u)}</span>`}
                            <span><b>${esc(u.username)}</b>${u.display_name ? `<br><small>${esc(u.display_name)}</small>` : ''}</span></span></td>
                        <td>${role(u.role)}${u.disabled ? ` <span class="n8-role n8-role-off">${esc(t('gesperrt'))}</span>` : ''}</td>
                        ${fields.filter(f => f !== 'display_name').map(f => `<td>${esc(u[f] || '–')}</td>`).join('')}
                        ${cols.map(c => `<td>${c.html(u)}</td>`).join('')}
                        <td>${esc(ago(u.last_login))}</td>
                        <td class="n8-act">${(o.actions ? o.actions(u) : []).map((a, k) => `<button type="button" class="n8-btn sm" data-x="${i}:${k}">${esc(t(a.label))}</button>`).join('')}${lk ? `<small class="n8-dim">${esc(lk)}</small>` : `<button type="button" class="n8-btn sm" data-edit="${i}">${esc(t('Bearbeiten'))}</button>`}</td></tr>
                        ${lk ? '' : `<tr class="n8-edit" data-row="${i}" hidden><td colspan="${4 + cols.length + fields.filter(f => f !== 'display_name').length}"><form class="n8-iform" data-i="${i}">
                            ${fields.map(f => inp(f, u)).join('')}
                            <input name="password" type="password" placeholder="${esc(t('Neues Passwort (optional)'))}" autocomplete="new-password">
                            <select name="role">${opts(u.role)}</select>
                            <label class="n8-chk"><input type="checkbox" name="disabled" ${u.disabled ? 'checked' : ''}> ${esc(t('gesperrt'))}</label>
                            <button class="n8-btn primary sm" type="submit">${esc(t('Speichern'))}</button>
                            <button class="n8-btn sm danger" type="button" data-del="${i}">${esc(t('Löschen'))}</button></form></td></tr>`}`;
                }).join('');
                const first = roles.find(r => r.id === o.defaultRole) || roles.filter(canAssign).slice(-1)[0];
                paint(card('👥 Benutzer', `<p class="n8-help">${esc(t(o.intro || 'Wer sich anmelden darf. Admins sehen IP-Adressen und Ports und ändern Einstellungen; Benutzer sehen nur das Dashboard.'))}</p>
                    <form class="n8-iform create">
                        <input name="username" placeholder="${esc(t('Benutzername'))}" required autocomplete="off">
                        ${fields.map(f => inp(f)).join('')}
                        <input name="password" type="password" placeholder="${esc(t('Passwort (min. {n})').replace('{n}', minPw))}" minlength="${minPw}" required autocomplete="new-password">
                        <select name="role">${opts(first ? first.id : '')}</select>
                        <button class="n8-btn primary sm" type="submit">＋ ${esc(t('Benutzer anlegen'))}</button></form>
                    <table class="n8-tbl"><thead><tr><th>${esc(t('Benutzer'))}</th><th>${esc(t('Rolle'))}</th>${fields.filter(f => f !== 'display_name').map(f => `<th>${esc(t(FIELD[f][0]))}</th>`).join('')}${cols.map(c => `<th>${esc(t(c.label))}</th>`).join('')}<th>${esc(t('Letzte Anmeldung'))}</th><th></th></tr></thead>
                    <tbody>${rows}</tbody></table>${o.note ? `<p class="n8-help">${esc(t(o.note))}</p>` : ''}`));
                const fd = f => { const d = {}; for (const x of f.elements) if (x.name) d[x.name] = x.type === 'checkbox' ? x.checked : x.value.trim(); if ('dmr_id' in d) d.dmr_id = d.dmr_id ? Number(d.dmr_id) : null; return d; };
                el.querySelector('form.create').onsubmit = async e => {
                    e.preventDefault(); const d = fd(e.target);
                    try { await A.create(d); toast(t('Benutzer angelegt') + ': ' + d.username); load(); } catch (x) { toast(x.message, true); }
                };
                el.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => { const r = el.querySelector(`tr[data-row="${b.dataset.edit}"]`); r.hidden = !r.hidden; });
                el.querySelectorAll('[data-x]').forEach(b => b.onclick = () => { const [i, k] = b.dataset.x.split(':').map(Number); o.actions(users[i])[k].run(users[i], load); });
                el.querySelectorAll('form[data-i]').forEach(f => f.onsubmit = async e => {
                    e.preventDefault(); const d = fd(f); if (!d.password) delete d.password;
                    try { await A.update(users[f.dataset.i], d); toast(t('Gespeichert')); load(); } catch (x) { toast(x.message, true); }
                });
                el.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => {
                    if (!b.dataset.armed) { b.dataset.armed = '1'; b.textContent = t('Wirklich löschen?'); return; }
                    try { await A.remove(users[b.dataset.del]); toast(t('Benutzer gelöscht')); load(); } catch (x) { toast(x.message, true); }
                });
            };
            return load();
        }
        if (name === 'sessions') {
            const load = async () => {
                let list; try { list = await A.sessions(); } catch (e) { paint(card('🔑 Sitzungen', msg(e))); return; }
                paint(card('🔑 Sitzungen', `<p class="n8-help">${esc(t('Alle aktuellen Anmeldungen. Mit „Abmelden“ ist das Gerät sofort abgemeldet.'))}</p>
                    ${!list.length ? `<div class="n8-help">${esc(t('Keine aktiven Sitzungen.'))}</div>` : `<table class="n8-tbl"><thead><tr><th>${esc(t('Benutzer'))}</th><th>IP</th><th>Browser</th><th>${esc(t('Zuletzt aktiv'))}</th><th>${esc(t('Läuft ab'))}</th><th></th></tr></thead>
                    <tbody>${list.map((x, i) => `<tr><td><b>${esc(x.username)}</b> ${x.role ? role(x.role) : ''}${x.current ? ` <span class="n8-badge ok">${esc(t('diese Sitzung'))}</span>` : ''}</td>
                        <td><code>${esc(x.ip || '–')}</code></td><td>${esc(shortUA(x.user_agent))}</td><td>${esc(ago(x.last_seen || x.created_at))}</td><td>${esc(ago(x.expires_at))}</td>
                        <td class="n8-act">${x.id ? `<button type="button" class="n8-btn sm danger" data-rev="${i}">${esc(t('Abmelden'))}</button>` : ''}</td></tr>`).join('')}</tbody></table>`}`));
                el.querySelectorAll('[data-rev]').forEach(b => b.onclick = async () => {
                    try { await A.revoke(list[b.dataset.rev]); toast(t('Sitzung beendet')); load(); } catch (x) { toast(x.message, true); }
                });
            };
            return load();
        }
        if (name === 'audit') {
            let list; try { list = await A.audit(); } catch (e) { paint(card('📜 Protokoll', msg(e))); return; }
            paint(card('📜 Protokoll', `<p class="n8-help">${esc(t('Anmeldungen, Fehlversuche und jede Änderung im Adminbereich – mit Zeit, Person und IP-Adresse.'))}</p>
                ${!list.length ? `<div class="n8-help">–</div>` : `<table class="n8-tbl"><thead><tr><th>${esc(t('Zeit'))}</th><th>${esc(t('Ereignis'))}</th><th>${esc(t('Benutzer'))}</th><th>${esc(t('Einzelheiten'))}</th><th>IP</th></tr></thead>
                <tbody>${list.map(a => `<tr><td>${esc(ago(a.ts || a.time))}</td><td>${esc((o.actions || {})[a.action] || a.action || '')}</td><td>${esc(a.username || a.user || '')}</td><td>${esc(a.detail || '')}</td><td><code>${esc(a.ip || '')}</code></td></tr>`).join('')}</tbody></table>`}`));
        }
    }

    // ============================================================ Netz, Ports & Domains (1.4.0) – Vorbild N8 Crosslink, gleich in allen N8-Systemen
    // N8Kit.net.view(el, 'ports' | 'domains', { req, onRestart })
    //   GET  /api/admin/ports   → { intro, note, restart: { text, button }, groups: [{ title, rows: [{ key, label, dir: 'in'|'out', proto, help, value,
    //                               kind: 'port'|'text', min, readonly }] }] }
    //   POST /api/admin/ports   { values: { key: value } } → { ok, message }
    //   GET  /api/admin/domains → { intro, hint, ok, sites: [{ domain, https, cert: { days, issuer, expires, staging } | null, dns: [], info,
    //                               renew, remove }], add: { allowed, email, staging, reason, button }, options: [{ key, label, value, help }], renew_auto }
    //   POST /api/admin/domains { domain, email, staging } · POST /api/admin/domains/<d>/renew · DELETE /api/admin/domains/<d>
    //   POST /api/admin/domains/options { key: value }
    //   1.5: optional per domain a target (what the domain shows, e.g. Live dashboard or portal):
    //        sites[i].targets = [{ id, label }], sites[i].target = id → select; POST /api/admin/domains/<d>/target { target }
    //        add.targets = [{ id, label }], add.target = default → select in the add form, sent as { …, target }
    async function netView(el, name, o) {
        const req = o.req;
        const msg = e => `<div class="n8-help">⚠️ ${esc(e && e.message ? e.message : String(e))}</div>`;
        const paint = html => { el.innerHTML = html; retranslateEl(el); };
        const out = (r, ok) => { const p = el.querySelector('.n8-net-out'); if (p) p.textContent = (r && (r.message || '')) + (r && r.log ? '\n\n' + r.log : ''); if (o.toast && r) o.toast((r.ok === false ? '⚠️ ' : '✅ ') + (r.message || ''), r.ok === false); };
        el.classList.add('n8-net');
        if (name === 'ports') {
            const load = async () => {
                let d; try { d = await req('GET', '/api/admin/ports'); } catch (e) { paint(card('🔌 Ports', msg(e))); return; }
                const row = r => `<tr><td><b>${esc(t(r.label))}</b>${r.help ? `<div class="n8-dim">${esc(t(r.help))}</div>` : ''}</td>
                    <td class="n8-nowrap"><span class="n8-badge ${r.dir === 'in' ? 'warn' : ''}">${r.dir === 'in' ? '⬇ ' + esc(t('eingehend')) : '⬆ ' + esc(t('ausgehend'))}</span>${r.proto ? ` <span class="n8-badge">${esc(r.proto)}</span>` : ''}</td>
                    <td class="n8-num">${r.readonly ? `<code>${esc(r.value ?? '–')}</code>` : `<input class="n8-in" data-k="${esc(r.key)}" data-kind="${r.kind || 'port'}" ${(r.kind || 'port') === 'port' ? `type="number" min="${r.min ?? 1}" max="65535"` : 'type="text"'} value="${esc(r.value ?? '')}">`}</td></tr>`;
                paint(`${card('🔌 Ports', `<p class="n8-help">${esc(t(d.intro || 'Alle Ports an einer Stelle. Eingehend: in Firewall und Router freigeben, wenn das von außen erreichbar sein soll. Ausgehend: die Gegenstelle muss erreichbar sein.'))}</p>
                    ${d.note ? `<div class="n8-help">♻️ ${esc(t(d.note))}</div>` : ''}`)}
                    <div class="n8-net-grid" style="margin-top:16px">${(d.groups || []).map(g => card(g.title, `${g.help ? `<p class="n8-help">${esc(t(g.help))}</p>` : ''}<table class="n8-tbl"><tbody>${g.rows.map(row).join('')}</tbody></table>`)).join('')}</div>
                    <div class="n8-actions">${(d.groups || []).some(g => g.rows.some(r => !r.readonly)) ? `<button type="button" class="n8-btn primary" data-a="save">💾 ${esc(t('Ports speichern'))}</button>` : ''}${d.restart ? `<button type="button" class="n8-btn" data-a="restart">♻️ ${esc(t(d.restart.button || 'Dienst neu starten'))}</button>` : ''}</div>
                    <pre class="n8-log n8-net-out" hidden></pre>`);
                const sb = el.querySelector('[data-a=save]');
                if (sb) sb.onclick = async e => {
                    const values = {};
                    el.querySelectorAll('.n8-in[data-k]').forEach(i => { values[i.dataset.k] = i.dataset.kind === 'port' ? Number(i.value) : i.value.trim(); });
                    e.target.disabled = true;
                    try { const r = await req('POST', '/api/admin/ports', { values }); await load(); out(r); const q = el.querySelector('.n8-net-out'); if (q) q.hidden = !r.message; }
                    catch (x) { e.target.disabled = false; alert(x.message); }
                };
                const rb = el.querySelector('[data-a=restart]');
                if (rb) rb.onclick = async () => { if (o.onRestart) o.onRestart(); else { try { await req('POST', d.restart.url || '/api/admin/ports/restart', {}); } catch (x) { } alert(t('Der Dienst startet neu – die Seite danach neu laden.')); } };
            };
            return load();
        }
        if (name === 'domains') {
            const load = async () => {
                let d; try { d = await req('GET', '/api/admin/domains'); } catch (e) { paint(card('🔒 Domains & HTTPS', msg(e))); return; }
                const days = c => c && c.days != null ? (c.days < 0 ? t('abgelaufen') : t('noch {n} Tage').replace('{n}', c.days)) : '';
                const certBadge = s => !s.cert ? `<span class="n8-badge warn">${esc(t('kein Zertifikat'))}</span>`
                    : s.cert.staging ? `<span class="n8-badge warn">${esc(t('Test-Zertifikat'))}</span>`
                    : s.cert.days != null && s.cert.days < 14 ? `<span class="n8-badge bad">${esc(days(s.cert))}</span>` : `<span class="n8-badge ok">${esc(t('gültig'))}${s.cert.days != null ? ' · ' + esc(days(s.cert)) : ''}</span>`;
                const sites = d.sites || [];
                const add = d.add || {};
                const opts = d.options || [];
                const hasTargets = sites.some(x => x.targets || x.target_label);
                paint(`${card('🔒 Domains & HTTPS', `<p class="n8-help">${esc(t(d.intro || 'Eigene Domains mit kostenlosem Zertifikat von Let’s Encrypt.'))}</p>
                    ${d.hint ? `<div class="n8-help">⚠️ ${esc(t(d.hint))}</div>` : ''}
                    ${opts.length ? `<div class="n8-net-opts">${opts.map(x => `<label class="n8-sw"><input type="checkbox" data-opt="${esc(x.key)}" ${x.value ? 'checked' : ''}><i></i> ${esc(t(x.label))}</label>${x.help ? `<div class="n8-dim">${esc(t(x.help))}</div>` : ''}`).join('')}</div>` : ''}
                    ${sites.length ? `<table class="n8-tbl"><thead><tr><th>${esc(t('Domain'))}</th>${hasTargets ? `<th>${esc(t('Zeigt'))}</th>` : ''}<th>${esc(t('Zertifikat'))}</th><th></th></tr></thead><tbody>${sites.map((s, i) => `<tr>
                        <td><b>${esc(s.domain)}</b>${s.label ? ` <span class="n8-badge">${esc(t(s.label))}</span>` : ''}<div class="n8-dim">${s.dns && s.dns.length ? 'DNS: ' + s.dns.map(esc).join(', ') : s.dns ? '⚠️ ' + esc(t('DNS: kein Eintrag gefunden')) : ''}${s.info ? (s.dns ? ' · ' : '') + esc(t(s.info)) : ''}</div></td>
                        ${hasTargets ? `<td>${s.targets ? `<select class="n8-in n8-target" data-target="${i}" aria-label="${esc(t('Zeigt'))}">${s.targets.map(x => `<option value="${esc(x.id)}" ${x.id === s.target ? 'selected' : ''}>${esc(t(x.label))}</option>`).join('')}</select>` : `<span class="n8-dim">${esc(t(s.target_label || '–'))}</span>`}</td>` : ''}
                        <td>${s.https ? '<span class="n8-badge ok">HTTPS</span>' : `<span class="n8-badge warn">${esc(t('nur HTTP'))}</span>`} ${certBadge(s)}${s.cert && (s.cert.issuer || s.cert.expires) ? `<div class="n8-dim">${esc(s.cert.issuer || '')}${s.cert.expires ? ' · ' + esc(t('bis')) + ' ' + esc(s.cert.expires) : ''}</div>` : ''}</td>
                        <td class="n8-act"><a class="n8-btn sm" href="https://${esc(s.domain)}/" target="_blank" rel="noopener">↗</a>
                          ${s.renew !== false ? `<button type="button" class="n8-btn sm" data-renew="${i}">${s.cert ? '🔄 ' + esc(t('Erneuern')) : '🔒 ' + esc(t('Zertifikat holen'))}</button>` : ''}
                          ${s.remove !== false ? `<button type="button" class="n8-btn sm danger" data-rm="${i}">${esc(t('Entfernen'))}</button>` : ''}</td></tr>`).join('')}</tbody></table>`
                    : `<div class="n8-help">${esc(t('Noch keine Domain.'))}</div>`}
                    ${d.renew_auto != null ? `<div class="n8-help">${d.renew_auto ? '✅ ' + esc(t('Zertifikate werden automatisch erneuert.')) : '⚠️ ' + esc(t('Automatische Erneuerung ist nicht eingerichtet.'))}</div>` : ''}`)}
                    ${add.allowed === false && !add.reason ? '' : card('➕ Domain hinzufügen', `${add.reason ? `<p class="n8-help">${esc(t(add.reason))}</p>` : ''}
                    <div class="n8-net-form"><label>${esc(t('Domain'))}<input class="n8-in" type="text" data-f="domain" placeholder="${esc(add.placeholder || 'dienst.example.org')}" autocomplete="off" value="${esc(add.domain || '')}"></label>
                    ${add.targets ? `<label>${esc(t('Zeigt'))}<select class="n8-in" data-f="target">${add.targets.map(x => `<option value="${esc(x.id)}" ${x.id === add.target ? 'selected' : ''}>${esc(t(x.label))}</option>`).join('')}</select></label>` : ''}
                    <label>${esc(t('E-Mail für Let’s Encrypt'))}<input class="n8-in" type="email" data-f="email" value="${esc(add.email || '')}" placeholder="sysop@example.org"></label>
                    <label class="n8-sw"><input type="checkbox" data-f="staging" ${add.staging ? 'checked' : ''}><i></i> ${esc(t('Test-Zertifikat (Let’s-Encrypt-Staging)'))}</label></div>
                    <div class="n8-actions"><button type="button" class="n8-btn primary" data-a="add" ${add.allowed === false ? 'disabled' : ''}>🔒 ${esc(t(add.button || 'Domain anlegen & Zertifikat holen'))}</button></div>`)}
                    <pre class="n8-log n8-net-out" hidden></pre>`);
                const outEl = () => el.querySelector('.n8-net-out');
                const busy = (b, txt) => { b.disabled = true; b.textContent = txt; const p = outEl(); p.hidden = false; p.textContent = t('Läuft – das kann bis zu einer Minute dauern …'); };
                const done = async r => { const keep = r; await load(); const p = outEl(); if (p) { p.hidden = false; p.textContent = (keep.message || '') + (keep.log ? '\n\n' + keep.log : ''); } if (o.toast) o.toast((keep.ok === false ? '⚠️ ' : '✅ ') + (keep.message || ''), keep.ok === false); };
                const ab = el.querySelector('[data-a=add]');
                if (ab) ab.onclick = async () => {
                    const f = k => el.querySelector(`[data-f=${k}]`);
                    const domain = f('domain').value.trim(), email = f('email').value.trim();
                    if (!domain) { f('domain').focus(); return; }
                    if (!email) { f('email').focus(); return; }
                    busy(ab, '🔒 ' + t('Hole Zertifikat …'));
                    const body = { domain, email, staging: f('staging').checked };
                    if (f('target')) body.target = f('target').value;
                    try { await done(await req('POST', '/api/admin/domains', body)); } catch (x) { await done({ ok: false, message: x.message }); }
                };
                el.querySelectorAll('[data-renew]').forEach(b => b.onclick = async () => {
                    busy(b, '🔄 …'); const s = sites[b.dataset.renew];
                    try { await done(await req('POST', `/api/admin/domains/${encodeURIComponent(s.domain)}/renew`, {})); } catch (x) { await done({ ok: false, message: x.message }); }
                });
                el.querySelectorAll('[data-rm]').forEach(b => b.onclick = async () => {
                    const s = sites[b.dataset.rm];
                    if (!confirm(t('{d} entfernen? Weiterleitung und Zertifikat werden gelöscht.').replace('{d}', s.domain))) return;
                    try { await done(await req('DELETE', `/api/admin/domains/${encodeURIComponent(s.domain)}`)); } catch (x) { await done({ ok: false, message: x.message }); }
                });
                el.querySelectorAll('[data-target]').forEach(c => c.onchange = async () => {
                    const s = sites[c.dataset.target];
                    try { await done(await req('POST', `/api/admin/domains/${encodeURIComponent(s.domain)}/target`, { target: c.value })); }
                    catch (x) { c.value = s.target; await done({ ok: false, message: x.message }); }
                });
                el.querySelectorAll('[data-opt]').forEach(c => c.onchange = async () => {
                    try { await done(await req('POST', '/api/admin/domains/options', { [c.dataset.opt]: c.checked })); } catch (x) { c.checked = !c.checked; alert(x.message); }
                });
            };
            return load();
        }
    }

    // the menu structure every N8 system uses (projects fill in their items)
    const GROUPS = { betrieb: '📡 Betrieb', zugang: '👥 Benutzer & Zugang', darstellung: '🎨 Darstellung', netz: '🌐 Netz, Ports & Domains', system: '🖥️ System' };
    const SYS_ITEMS = [['sys-update', '⬆️ Update'], ['sys-services', '🧩 Dienste'], ['sys-perms', '🔐 Berechtigungen & sudo'], ['sys-keepalive', '💓 Keep-Alive'], ['sys-crashes', '💥 Abstürze']];

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
            'Nicht aktualisiert – es läuft unverändert die bisherige Version.': 'Not updated – the previous version keeps running unchanged.',
            'Diesen Befund löschen': 'Delete this record', 'Angezeigte löschen': 'Delete shown', 'Alle löschen': 'Delete all',
            'Die angezeigten Befunde samt Protokoll löschen?': 'Delete the shown records with their logs?',
            'Alle Befunde samt Protokoll löschen? Das lässt sich nicht rückgängig machen.': 'Delete all records with their logs? This cannot be undone.',
            'Diesen Befund samt Protokoll löschen?': 'Delete this record with its log?',
            'Einzelheiten im Update-Protokoll (System → Update).': 'Details in the update log (System → Update).',
            'von Hand geänderte Dateien – Update abgebrochen': 'files changed by hand – update stopped',
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
            // 1.4.0: Benutzer & Zugang, Netz, Ports & Domains
            '🌐 Netz, Ports & Domains': '🌐 Network, ports & domains', '👥 Benutzer': '👥 Users', '🔑 Sitzungen': '🔑 Sessions', '📜 Protokoll': '📜 Log',
            'Benutzer': 'User', 'Rolle': 'Role', 'Letzte Anmeldung': 'Last login', 'Bearbeiten': 'Edit', 'gesperrt': 'disabled', 'Anzeigename': 'Display name',
            'Rufzeichen': 'Callsign', 'Benutzername': 'Username', 'Passwort (min. {n})': 'Password (min. {n})', 'Neues Passwort (optional)': 'New password (optional)',
            'Benutzer anlegen': 'Add user', 'Löschen': 'Delete', 'Wirklich löschen?': 'Really delete?', 'Benutzer angelegt': 'User created', 'Benutzer gelöscht': 'User deleted',
            'nur Superadmin': 'superadmin only', 'Superadmin': 'Superadmin', 'Admin': 'Admin', 'Betrachter': 'Viewer', 'Autor': 'Author', 'Redakteur': 'Editor',
            'Wer sich anmelden darf. Admins sehen IP-Adressen und Ports und ändern Einstellungen; Benutzer sehen nur das Dashboard.': 'Who may log in. Admins see IP addresses and ports and change settings; users only see the dashboard.',
            'Alle aktuellen Anmeldungen. Mit „Abmelden“ ist das Gerät sofort abgemeldet.': 'All current logins. „Log out“ ends one at once.',
            'Keine aktiven Sitzungen.': 'No active sessions.', 'Zuletzt aktiv': 'Last active', 'Läuft ab': 'Expires', 'Abmelden': 'Log out', 'Sitzung beendet': 'Session ended', 'diese Sitzung': 'this session',
            'Anmeldungen, Fehlversuche und jede Änderung im Adminbereich – mit Zeit, Person und IP-Adresse.': 'Logins, failed attempts and every change in the admin area – with time, person and IP address.',
            'Zeit': 'Time', 'Ereignis': 'Event', 'Einzelheiten': 'Details', '🔌 Ports': '🔌 Ports', 'eingehend': 'incoming', 'ausgehend': 'outgoing', 'Ports speichern': 'Save ports',
            'Alle Ports an einer Stelle. Eingehend: in Firewall und Router freigeben, wenn das von außen erreichbar sein soll. Ausgehend: die Gegenstelle muss erreichbar sein.':
                'All ports in one place. Incoming: open in firewall and router if it should be reachable from outside. Outgoing: the other side must be reachable.',
            'Dienst neu starten': 'Restart service', 'Der Dienst startet neu – die Seite danach neu laden.': 'The service restarts – reload the page afterwards.',
            '🔒 Domains & HTTPS': '🔒 Domains & HTTPS', 'Domain': 'Domain', 'Zertifikat': 'Certificate', 'kein Zertifikat': 'no certificate', 'Test-Zertifikat': 'test certificate',
            'gültig': 'valid', 'abgelaufen': 'expired', 'nur HTTP': 'HTTP only', 'bis': 'until', 'Erneuern': 'Renew', 'Zertifikat holen': 'Get certificate', 'Entfernen': 'Remove',
            'Noch keine Domain.': 'No domain yet.', 'DNS: kein Eintrag gefunden': 'DNS: no record found', '➕ Domain hinzufügen': '➕ Add domain', 'E-Mail für Let’s Encrypt': 'E-mail for Let’s Encrypt',
            'Test-Zertifikat (Let’s-Encrypt-Staging)': 'Test certificate (Let’s Encrypt staging)', 'Domain anlegen & Zertifikat holen': 'Add domain & get certificate', 'Hole Zertifikat …': 'Getting certificate …',
            'Läuft – das kann bis zu einer Minute dauern …': 'Running – this can take up to a minute …', 'Zertifikate werden automatisch erneuert.': 'Certificates are renewed automatically.',
            'Automatische Erneuerung ist nicht eingerichtet.': 'Automatic renewal is not set up.', 'Zeigt': 'Shows', 'Eigene Domains mit kostenlosem Zertifikat von Let’s Encrypt.': 'Own domains with a free certificate from Let’s Encrypt.',
            '{d} entfernen? Weiterleitung und Zertifikat werden gelöscht.': 'Remove {d}? Forwarding and certificate are deleted.',
            // 1.3.0: crashes
            '💥 Abstürze': '💥 Crashes', 'Absturz': 'Crash', 'Watchdog': 'Watchdog', 'Speicher voll': 'Out of memory', 'Beendet': 'Exited',
            'Zeitüberschreitung': 'Timeout', 'Hänger': 'Hang', 'Teil abgestürzt': 'Part crashed', 'Thread abgestürzt': 'Thread crashed',
            'Hilfsprozess abgestürzt': 'Helper process crashed', 'Keep-Alive-Neustart': 'Keep-alive restart', 'Neustart': 'Restart', 'Fehler': 'Error',
            'neu': 'new', 'alles gelesen': 'all read', 'alle': 'all', 'Letzte 7 Tage': 'Last 7 days', 'Keine Abstürze festgehalten.': 'No crashes recorded.',
            'Alle als gelesen markieren': 'Mark all as read', 'Kein Protokoll vorhanden.': 'No log available.', '🛡️ Absturz-Wächter': '🛡️ Crash watch',
            'Jeder Absturz, Hänger und Notfall-Neustart aller Dienste wird hier festgehalten – mit dem Teil der Anwendung, in dem er passiert ist, und dem vollständigen Protokoll (Journal, Python-Stack). Der Dienst wird dabei automatisch neu gestartet. Neue Befunde erscheinen nach der Anmeldung als Hinweis, bis sie als gelesen markiert sind.':
                'Every crash, hang and emergency restart of every service is recorded here – with the part of the application where it happened and the full log (journal, Python stack). The service is restarted automatically. New findings show up as a notice after login until they are marked as read.',
            'Diese Dienste werden überwacht. Nach jedem unerwarteten Ende hält systemd den Befund fest und startet den Dienst neu; bleibt er ausgefallen, startet ihn der Keep-Alive neu.':
                'These services are watched. After every unexpected end systemd records the finding and restarts the service; if it stays down, the keep-alive restarts it.',
            'Der Absturz-Wächter ist noch nicht eingerichtet. Er wird beim nächsten Update eingerichtet – oder einmal auf der Konsole:':
                'The crash watch is not set up yet. The next update sets it up – or once on the console:',
            '1 neuer Absturz': '1 new crash', '{n} neue Abstürze': '{n} new crashes', 'weitere': 'more', 'Alle Abstürze ansehen': 'View all crashes', 'Gelesen': 'Mark as read',
            'Seit dem letzten Lesen ist ein Dienst abgestürzt oder hing. Er wurde automatisch neu gestartet. Der Befund nennt den Teil der Anwendung und enthält das vollständige Protokoll.':
                'Since you last looked, a service crashed or hung. It was restarted automatically. The finding names the part of the application and contains the full log.',
            'Die Weboberfläche wird gestoppt …': 'The web interface is being stopped …', 'Die Weboberfläche startet neu – einen Moment …': 'The web interface is restarting – one moment …',
            'Keep-Alive an': 'Keep-alive on', 'Netzdienste nach einem Internet-Ausfall neu starten': 'Restart network services after an internet outage',
            'Heartbeat-Adresse': 'Heartbeat address', 'Heartbeat bei Fehlern (optional)': 'Heartbeat on errors (optional)', '▶ Fortsetzen': '▶ Resume',
            '⏸ 1 h pausieren (Wartung)': '⏸ Pause 1 h (maintenance)', 'Speichern': 'Save', 'Keep-Alive-Protokoll': 'Keep-alive log',
            'Jede Minute als root: prüft jeden Dienst wirklich (Weboberfläche und Verbindungen der Protokolle), startet kranke Dienste nach ein paar Minuten neu (höchstens 4× je Stunde), erkennt Internet-Ausfälle und startet danach die Netzdienste neu, und meldet sich bei einer Heartbeat-Adresse (Uptime Kuma „Push“, Healthchecks.io …). Ein von Hand gestoppter Dienst bleibt gestoppt.':
                'Every minute as root: checks every service for real (web interface and the connections of the protocols), restarts sick services after a few minutes (at most 4× per hour), notices internet outages and restarts the network services afterwards, and reports to a heartbeat address (Uptime Kuma “push”, Healthchecks.io …). A service stopped by hand stays stopped.',
            'Meldung': 'Message', 'Noch kein Update über die Weboberfläche.': 'No update through the web interface yet.', 'Neu laden': 'Reload',
            '📜 Update-Protokoll': '📜 Update log',
            // 1.6: login window, user menu, language menu
            'Anmelden': 'Log in', 'Abmelden': 'Log out', 'Benutzername': 'Username', 'Passwort': 'Password', 'Passwort anzeigen': 'Show password',
            'Passwort wiederholen': 'Repeat password', 'Schließen': 'Close', 'Feststelltaste ist an': 'Caps Lock is on', 'Angemeldet bleiben': 'Stay logged in',
            'Anlegen': 'Create', 'Verschlüsselte Verbindung': 'Encrypted connection', 'Unverschlüsselte Verbindung (HTTP)': 'Unencrypted connection (HTTP)',
            'Bitte Benutzername und Passwort eingeben.': 'Please enter username and password.', 'Das Passwort ist zu kurz.': 'The password is too short.',
            'Die Passwörter stimmen nicht überein.': 'The passwords do not match.', 'Anmeldung fehlgeschlagen.': 'Login failed.', 'Mein Konto': 'My account',
            'Passwort ändern': 'Change password', 'Sprache': 'Language', 'Zu viele Fehlversuche – bitte 15 Minuten warten': 'Too many failed attempts – please wait 15 minutes',
        }
    });
    add({
        base: 'en', de: {
            'Update available': 'Update verfügbar',
            // 1.6: login window and user menu of all N8 systems
            'Log in': 'Anmelden', 'Log out': 'Abmelden', 'Login': 'Anmelden', 'My account': 'Mein Konto', 'Webmail': 'Webmail', 'Admin': 'Admin',
            'Stay logged in': 'Angemeldet bleiben', 'Stay logged in (30 days)': 'Angemeldet bleiben (30 Tage)', 'Username': 'Benutzername', 'Password': 'Passwort',
            'Log in to manage the FRN server.': 'Anmelden, um den FRN-Server zu verwalten.', 'This dashboard is private. Please log in.': 'Dieses Dashboard ist privat. Bitte anmelden.',
            'Log in to change settings.': 'Anmelden, um Einstellungen zu ändern.', 'This hotspot is private. Please log in.': 'Dieser Hotspot ist privat. Bitte anmelden.',
            'Log in to see IP addresses and the admin area.': 'Anmelden, um IP-Adressen und den Adminbereich zu sehen.',
            'Please log in to view the dashboard.': 'Bitte anmelden, um das Dashboard zu sehen.', 'Wrong username or password.': 'Benutzername oder Passwort falsch.',
            'Wrong username or password': 'Benutzername oder Passwort falsch', 'Change password': 'Passwort ändern', 'Superadmin': 'Superadmin', 'User': 'Benutzer',
            'Too many failed logins. Try again in 15 minutes.': 'Zu viele Fehlversuche. Bitte in 15 Minuten erneut versuchen.',
            'Too many wrong passwords. Try again in 15 minutes.': 'Zu viele falsche Passwörter. Bitte in 15 Minuten erneut versuchen.',
            'Too many requests – please wait a moment.': 'Zu viele Anfragen – bitte einen Moment warten.',
            'Too many failed attempts. Please wait 15 minutes.': 'Zu viele Fehlversuche. Bitte 15 Minuten warten.', "What's new?": 'Was ist neu?', 'Update now': 'Jetzt aktualisieren', 'Later': 'Später',
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
            [/^rolled back to (.+)$/, 'zurückgesetzt auf $1'], [/^noch (\d+) Tage$/, '$1 days left'], [/^rollback failed \(git reset\)$/, 'Zurücksetzen fehlgeschlagen (git reset)'],
            [/^(\d+) min ago$/, 'vor $1 Min.'], [/^(\d+) s ago$/, 'vor $1 s'], [/^(\d+) h ago$/, 'vor $1 Std.'], [/^(\d+) d ago$/, 'vor $1 T.'],
        ]
    });

    window.N8Kit = {
        version: '1.6.0',
        lang: () => lang, langs: () => LANGS.map(l => ({ code: l, name: LANG_INFO[l][0], short: LANG_INFO[l][1], locale: LANG_INFO[l][2] })),
        locale, setLang, t, langSwitch, esc, fmtTime, userMenu, dropdown,
        login: { open: loginOpen, close: loginClose },
        i18n: { add, retranslate: () => { cache.clear(); retranslate(); }, t },
        update: { banner, panel, run },
        nav: { tree, GROUPS, SYS_ITEMS },
        sys: { view, crashPopup },
        access: { view: accessView },
        net: { view: netView },
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})();
