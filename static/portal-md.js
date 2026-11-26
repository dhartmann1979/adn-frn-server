/* adn-frn-server – small Markdown subset for the 📰 portal news (portal page and admin preview).
 * Everything is HTML-escaped first; only the formatting below is turned into tags, so no author HTML ever reaches a visitor.
 *   # / ## / ### headings · **bold** · *italic* · `code` · [text](https://…) · - lists · 1. lists · > quotes · --- rule
 *   empty line = new paragraph · URLs (https://…) become links */
(function () {
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const safeUrl = u => /^(https?:\/\/|mailto:|\/(?!\/))/i.test(u) ? u : '';
    function inline(t) {
        let s = esc(t);
        const codes = [];
        s = s.replace(/`([^`]+)`/g, (m, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
        s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, txt, url) => {
            const u = safeUrl(url.replace(/&amp;/g, '&'));
            return u ? `<a href="${esc(u)}"${/^https?:/i.test(u) ? ' target="_blank" rel="noopener noreferrer"' : ''}>${txt}</a>` : m;
        });
        s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, (m, pre, url) => `${pre}<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);
        s = s.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<i>$2</i>');
        return s.replace(/\u0000(\d+)\u0000/g, (m, i) => `<code>${codes[i]}</code>`);
    }
    function render(src) {
        const lines = String(src || '').replace(/\r\n?/g, '\n').split('\n');
        const out = [];
        let para = [], list = null;
        const flushPara = () => { if (para.length) { out.push(`<p>${para.map(inline).join('<br>')}</p>`); para = []; } };
        const flushList = () => { if (list) { out.push(`<${list.tag}>${list.items.map(i => `<li>${inline(i)}</li>`).join('')}</${list.tag}>`); list = null; } };
        for (const raw of lines) {
            const l = raw.trimEnd();
            let m;
            if (!l.trim()) { flushPara(); flushList(); continue; }
            if ((m = l.match(/^(#{1,3})\s+(.*)$/))) { flushPara(); flushList(); const n = m[1].length + 2; out.push(`<h${n}>${inline(m[2])}</h${n}>`); continue; }
            if (/^\s*(---|\*\*\*)\s*$/.test(l)) { flushPara(); flushList(); out.push('<hr>'); continue; }
            if ((m = l.match(/^>\s?(.*)$/))) { flushPara(); flushList(); out.push(`<blockquote>${inline(m[1])}</blockquote>`); continue; }
            if ((m = l.match(/^\s*[-*•]\s+(.*)$/)) || (m = l.match(/^\s*\d+[.)]\s+(.*)$/))) {
                flushPara();
                const tag = /^\s*\d/.test(l) ? 'ol' : 'ul';
                if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
                list.items.push(m[1]); continue;
            }
            flushList(); para.push(l);
        }
        flushPara(); flushList();
        return out.join('');
    }
    window.PortalMD = { render, esc };
})();
