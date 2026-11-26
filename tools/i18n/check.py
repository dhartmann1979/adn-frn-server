import json, sys, os, re
chunks = json.load(open('/home/claude/i18n/chunks.json'))
langs = ['fr', 'hu', 'sv', 'nl', 'it', 'es']
for i, c in enumerate(chunks):
    st = []
    for l in langs:
        p = f'/home/claude/i18n/tr/c{i}.{l}.txt'
        if not os.path.exists(p): st.append(f'{l}:-'); continue
        lines = open(p).read().rstrip('\n').split('\n')
        bad = [k for k, (a, b) in enumerate(zip(c, lines)) if set(re.findall(r'\{\w+\}?', a)) != set(re.findall(r'\{\w+\}?', b))]
        st.append(f'{l}:{"OK" if len(lines) == len(c) else f"{len(lines)}/{len(c)}"}' + (f' ph{bad[:3]}' if bad else ''))
    print(i, ' '.join(st))
