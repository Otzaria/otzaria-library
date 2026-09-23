import json,re,sys,os,difflib,collections
# usage: qa_preserve.py <src dir> <out dir>
# every source token (minus deliberately deleted lines) must reach the output
# in order; the only expected differences are the lost_chars fixes
SRC,OUT=sys.argv[1],sys.argv[2]
H=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,H); import build_books as B
plan=json.load(open(H+'/structure_plan.json'))
miss=json.load(open(H+'/missing_simanim.json'))
tok=lambda s: re.findall(r"[^\s<>]+", s)
tot=collections.Counter()
for vol in B.VOLS:
    P=plan[vol]
    raw=open(f"{SRC}/משנה הלכות חלק {vol}.txt",encoding='utf-8').read().splitlines()
    dele={d['line'] for d in P['delete_lines']}
    src=[]
    for i,l in enumerate(raw[2:],start=3):
        if i in dele or l.startswith('<h2>'): continue
        src+=tok(B.normalize(l))
    out=open(f"{OUT}/שות משנה הלכות חלק {vol}.txt",encoding='utf-8').read().splitlines()
    insnums={B.gematria(int(k.split(':')[1])) for k in miss if int(k.split(':')[0])==B.VOL_NUM[vol]}
    body=[];skip=False
    for l in out[2:]:
        m=re.match(r'<h([23])>(?:סימן )?([^<]*)</h',l)
        if m:
            if l.startswith('<h3>') or 'סימן' in l: skip = m.group(2) in insnums
            continue
        if not skip: body.append(re.sub(r'</?b>','',l))
    o=[]
    for l in body: o+=tok(l)
    sm=difflib.SequenceMatcher(None,src,o,autojunk=False)
    ops=[x for x in sm.get_opcodes() if x[0]!='equal']
    kinds=collections.Counter(x[0] for x in ops)
    print(vol,'src',len(src),'out',len(o),'diff ops',dict(kinds), 'tokens changed', sum(max(x[2]-x[1],x[4]-x[3]) for x in ops))
