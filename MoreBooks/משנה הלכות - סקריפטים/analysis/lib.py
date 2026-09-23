# Shared loaders for the structure plan. No book text is printed by anything here.
import json, re, collections
S = '/private/tmp/claude-501/-Users-david-Documents-otzaria-books-otzaria-library/4c8380de-bafb-4867-b3cc-dae974308691/scratchpad'
D = '/Users/david/Downloads/משנה הלכות/'
VOLS = 'א ב ג ד ה ו ז ח ט י יא יב יג יד טו טז יז'.split()
GV = {'א':1,'ב':2,'ג':3,'ד':4,'ה':5,'ו':6,'ז':7,'ח':8,'ט':9,'י':10,'כ':20,'ל':30,'מ':40,'נ':50,
      'ס':60,'ע':70,'פ':80,'צ':90,'ק':100,'ר':200,'ש':300,'ת':400,
      'ך':20,'ם':40,'ן':50,'ף':80,'ץ':90}
FIN = str.maketrans('ךםןףץ', 'כמנפצ')

def gval(s):
    return sum(GV.get(c, 0) for c in s)

def norm(s):
    s = re.sub(r'<[^>]*>', '', s)
    return re.sub(r'[^א-ת]', '', s.translate(FIN))

def load_file(vi):
    v = VOLS[vi-1]
    lines = open(f'{D}משנה הלכות חלק {v}.txt', encoding='utf-8').read().splitlines()
    h2 = []
    for i, l in enumerate(lines, 1):
        m = re.fullmatch(r'<h2>(.*)</h2>', l)
        if m:
            h2.append({'line': i, 'label': m.group(1), 'val': gval(m.group(1))})
    for a, h in enumerate(h2):
        h['end'] = (h2[a+1]['line'] - 1) if a+1 < len(h2) else len(lines)
    return lines, h2

HEADS = {int(k): v for k, v in json.load(open(f'{S}/pdf/txt/heads.json')).items()}

def load_pdf(vi):
    L = [json.loads(x) for x in open(f'{S}/pdf/txt/mh{vi}.jsonl')]
    for j, x in enumerate(L):
        x['j'] = j
        x['hdr'] = x['y'] < 55 and x['size'] in (22.8, 15.8, 13.9)
    heads = HEADS[vi]
    P = []
    for a, h in enumerate(heads):
        k = h[2]; end = heads[a+1][2] if a+1 < len(heads) else len(L)
        seg = [x for x in L[k+1:end] if not x['hdr']]
        # topic: DWVilna,Bold 12.7 lines before any other content
        topic = []
        for x in seg:
            if x['font'] == 'DWVilna,Bold' and x['size'] == 12.7:
                topic.append(x)
            else:
                break
        P.append({'n': h[0], 'page': h[1], 'k': k, 'lines': seg, 'topic': topic})
    return L, P

def stream(lines_):
    """normalized letter stream + per-char owner index into lines_"""
    s = []; own = []
    for idx, x in enumerate(lines_):
        t = norm(x['t'])
        s.append(t); own.extend([idx]*len(t))
    return ''.join(s), own

N = 8
def grams(s, n=N):
    return {s[j:j+n] for j in range(max(0, len(s)-n+1))}
