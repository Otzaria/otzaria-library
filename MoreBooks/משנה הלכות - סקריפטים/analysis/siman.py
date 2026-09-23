# Extract one siman (by print number) as file-style lines.
import re,json,collections,pdflines
HB='/private/tmp/claude-501/-Users-david-Documents-otzaria-books-otzaria-library/4c8380de-bafb-4867-b3cc-dae974308691/scratchpad/pdf/txt/heads.json'
H={int(k):v for k,v in json.load(open(HB)).items()}
V={'א':1,'ב':2,'ג':3,'ד':4,'ה':5,'ו':6,'ז':7,'ח':8,'ט':9,'י':10,'כ':20,'ל':30,'מ':40,'נ':50,'ס':60,'ע':70,'פ':80,'צ':90,'ק':100,'ר':200,'ש':300,'ת':400}
def dom(x): return max(x['sizes'],key=x['sizes'].get)
def domfont(x): return max(x['fonts'],key=x['fonts'].get)
def is_header(x):
    return x['y']<66 and (22.8 in x['sizes'] or dom(x) in (15.8,13.9,14.9))
def heading_num(x):
    if dom(x)!=15.8: return None
    t=re.sub(r'[^א-ת]','',x['text'])
    if not t.startswith('סימן') or len(t)>9: return None
    return sum(V.get(c,0) for c in t[4:])
def stream(v,p0,p1):
    for pn in range(p0,p1+1):
        for x in pdflines.page_lines(v,pn):
            if is_header(x): continue
            x['p']=pn; yield x
def classify(x):
    d=dom(x); f=domfont(x)
    if heading_num(x) is not None: return 'head'
    if f.startswith('FrankRuehl'): return 'addr'
    if f=='DWVilna,Bold' and d==11.8: return 'addr2'
    if d==13.4: return 'sig'
    if f=='DWVilna,Bold' and d==12.7: return 'topic'
    if d in (14.9,15.8,17.8,18.7,20.9,21.8,28.8) and f.startswith(('DWVilna','S-')): return 'bigtitle'
    return 'body'
def extract(v,num,stop_before_index=True):
    heads=H[v]; nums=[h[0] for h in heads]
    a=nums.index(num); p0=heads[a][1]
    p1=heads[a+1][1] if a+1<len(heads) else pdflines.doc(v).page_count
    items=[];state=0;prev=None
    for x in stream(v,p0,p1):
        hn=heading_num(x)
        if state==0:
            if hn==num: state=1
            continue
        if hn is not None and hn!=num: break
        if stop_before_index and re.sub(r'[^א-ת]','',x['text']).startswith('מפתח') and dom(x)>=15: break
        x['kind']=classify(x); items.append(x)
    return items
def to_lines(items):
    """merge visual lines into paragraphs."""
    paras=[];cur=None
    colW={'R':None}
    for i,x in enumerate(items):
        k=x['kind']
        if k=='body':
            prev=items[i-1] if i else None
            newp=False
            if cur is None or cur['kind']!='body': newp=True
            else:
                same_col=prev is not None and prev['p']==x['p'] and prev['col']==x['col']
                if same_col and x['y']-prev['y']>17: newp=True
                if 16.3 in x['sizes'] or 13.9 in x['sizes']: newp=True
                # previous line centred/short (paragraph end) -> new para
                cl=41 if prev is not None and prev['col']=='L' else 286; cr=cl+223
                if same_col and prev['kind']=='body' and prev['x0']>cl+8 and prev['x1']<cr-8 and x['y']-prev['y']<=17: newp=True
            if newp:
                cur={'kind':'body','parts':[x['text']]}; paras.append(cur)
            else: cur['parts'].append(x['text'])
        else:
            seen_body=any(p['kind']=='body' for p in paras)
            if cur is not None and cur['kind']==k and (k in('addr','addr2','sig','bigtitle') or (k=='topic' and seen_body)): cur['parts'].append(x['text'])
            else:
                cur={'kind':k,'parts':[x['text']]}; paras.append(cur)
    out=[]
    for p in paras:
        s=''
        for part in p['parts']:
            if s.endswith('-') and len(s)>1 and re.match(r'[א-ת]',s[-2]) : s=s[:-1]+part
            elif s: s+=' '+part
            else: s=part
        out.append((p['kind'],re.sub(' +',' ',s).strip()))
    return out
