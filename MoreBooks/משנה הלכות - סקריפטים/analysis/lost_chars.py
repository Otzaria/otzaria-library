# Resolve '?' / '<?...>' placeholders in the scraped files against the PDF text by letter-only context anchors.
import re,glob,json,collections
D='/Users/david/Downloads/משנה הלכות/'
VOLN={'א':1,'ב':2,'ג':3,'ד':4,'ה':5,'ו':6,'ז':7,'ח':8,'ט':9,'י':10,'יא':11,'יב':12,'יג':13,'יד':14,'טו':15,'טז':16,'יז':17}
FIN=str.maketrans('ךםןףץ','כמנפצ')
def letters(s,keepq=False):
    idx=[];out=[]
    for i,c in enumerate(s):
        if 'א'<=c<='ת' or (keepq and c=='?'): out.append(c.translate(FIN)); idx.append(i)
    return ''.join(out),idx
def rx(ctx): return ''.join('[א-ת]?' if c=='?' else re.escape(c) for c in ctx)
class _M:
    def __init__(s,st,N,L,R):
        m=re.match('('+rx(L)+')([א-ת]{0,6})('+rx(R)+')',N[st:]); s._s=st; s.le=st+m.end(1); s.rs=st+m.start(3); s._e=st+m.end()
    def start(s): return s._s
    def end(s): return s._e
PDF={}
def pdf(v):
    if v not in PDF:
        raw=open(f'vol{v}.txt').read(); n,idx=letters(raw); PDF[v]=(raw,n,idx)
    return PDF[v]
res=[];stats=collections.Counter()
for f in sorted(glob.glob(D+'*.txt')):
    vol=f.split('חלק ')[1][:-4]; v=VOLN[vol]
    lines=open(f).read().split('\n')
    cum=[0]
    for x in lines: cum.append(cum[-1]+len(x)+1)
    total=cum[-1]
    for ln,l in enumerate(lines,1):
        occ=[(m.start(),m.end()) for m in re.finditer(r'<\?+>|\?+',l)]
        for k,(s,e) in enumerate(occ):
            prev_e=0; next_s=len(l)
            lt,li=letters(re.sub(r'<\?+>','??',l[prev_e:s]) if False else l[prev_e:s],True); rt,ri=letters(l[e:next_s],True)
            rec={'vol':vol,'line':ln}
            found=None
            for K in (20,14,10,7):
                L=lt[-K:]; R=rt[:K]
                if len(L)<5 or len(R)<5:
                    if len(L)+len(R)<12: continue
                raw,N,idx=pdf(v)
                ms=[m for m in re.finditer('(?='+rx(L)+'([א-ת]{0,6})'+rx(R)+')',N)]
                ms=[re.match(rx(L)+'([א-ת]{0,6})'+rx(R),N[m.start():]) and _M(m.start(),N,L,R) for m in ms]
                if len(ms)==1: found=(ms[0],L,R); break
                if len(ms)>1:
                    rel=cum[ln-1]/total
                    ds=sorted((abs(m.start()/len(N)-rel),i) for i,m in enumerate(ms))
                    if ds[0][0]<0.03 and ds[1][0]-ds[0][0]>0.05: found=(ms[ds[0][1]],L,R); found=found+('by-position',); break
                    found=('ambig',len(ms)); break
            if found is None or found[0]=='ambig' or (found and not L) :
                rec.update(old=l[max(0,s-12):e+12],new=None,reason='no unique PDF match' if found is None else f'ambiguous ({found[1]} matches)' if found[0]=='ambig' else 'no left context')
                stats['unresolved']+=1; res.append(rec); continue
            m,L,R=found[:3]; bypos=len(found)>3
            raw,N,idx=pdf(v)
            pl=idx[m.le-1]
            if R: pr=idx[m.rs]
            else:
                pr=idx[m.rs] if m.rs<len(idx) else len(raw)
                while pr>pl+1 and raw[pr-1] in ' ': pr-=1
                # stop at first space after punctuation run
                sp=raw.find(' ',pl+1,pr); pr=sp if sp!=-1 else pr
            gap=raw[pl+1:pr].replace('t','פ')  # Rashi-font glyph 0x74 = pe (dagesh) in Yiddish/loanwords
            # file side anchors (absolute positions)
            fl=prev_e+li[len(lt)-1] if lt else s-1
            fr=e+ri[0] if rt else (l.find(' ',e) if l.find(' ',e)!=-1 else len(l))
            fgap=l[fl+1:fr]
            if '?' in gap and not re.search('[א-ת]',gap):
                stats['real_question_mark']+=1; continue
            if gap==fgap: stats['identical']+=1; continue
            a=max(0,fl-8); b=min(len(l),fr+9)
            # widen until unique
            while l.count(l[a:b])>1 and (a>0 or b<len(l)): a=max(0,a-4); b=min(len(l),b+4)
            old=l[a:b]; new=l[a:fl+1]+gap+l[fr:b]
            rec.update(old=old,new=new,pdf_gap=gap,file_gap=fgap,anchor=len(L),_fl=fl,_fr=fr)
            if bypos: rec['note']='context occurs twice in PDF; chosen by relative position'
            if gap.strip()=='' : rec['note']=rec.get('note','')+' PDF has no character here; placeholder removed'
            stats['resolved']+=1; res.append(rec)
# manual: vol י line 2496 — right context unique in PDF, preceded by the same tractate name; PDF daf differs from garbled file text
for r in res:
    if r['vol']=='י' and r['line']==2496 and r.get('new') is None:
        l=open(D+'משנה הלכות חלק י.txt').read().split('\n')[2495]; i=l.find('ב"ב?')
        if i>=0 and l.count('ב"ב?')==1:
            r.update(old='ב"ב?',new='נ"ב',note='file has garbled daf + placeholder; PDF (unique right-context match, same tractate) reads nun-bet',pdf_gap='נ"ב',file_gap='ב"ב?',_fl=i-1,_fr=i+4)
            r.pop('reason',None); stats['unresolved']-=1; stats['resolved_manual']+=1
# merge overlapping windows within a line so sequential application is safe
merged=[];bykey=collections.defaultdict(list)
for r in res: bykey[(r['vol'],r['line'])].append(r)
for (vol,ln),rs in bykey.items():
    ok=[r for r in rs if r.get('new') is not None]; bad=[r for r in rs if r.get('new') is None]
    merged+=bad
    if not ok: continue
    l=open(D+f'משנה הלכות חלק {vol}.txt').read().split('\n')[ln-1]
    ok.sort(key=lambda r:r['_fl'])
    groups=[[ok[0]]]
    for r in ok[1:]:
        if r['_fl']-groups[-1][-1]['_fr']<24: groups[-1].append(r)
        else: groups.append([r])
    for g in groups:
        a=max(0,g[0]['_fl']-8); b=min(len(l),g[-1]['_fr']+9)
        while l.count(l[a:b])>1 and (a>0 or b<len(l)): a=max(0,a-4); b=min(len(l),b+4)
        new='';pos=a
        for r in g: new+=l[pos:r['_fl']+1]+r['pdf_gap']; pos=r['_fr']
        new+=l[pos:b]
        rec={'vol':vol,'line':ln,'old':l[a:b],'new':new}
        notes=[r['note'].strip() for r in g if r.get('note')]
        if notes: rec['note']='; '.join(sorted(set(notes)))
        rec['occurrences']=len(g)
        assert l.count(rec['old'])==1
        merged.append(rec)
merged.sort(key=lambda r:(list(VOLN).index(r['vol']),r['line']))
json.dump(merged,open('lost_chars.json','w'),ensure_ascii=False,indent=1)
res=merged
print(stats)
print('records',len(res),'occurrences resolved',sum(r.get('occurrences',0) for r in res),'unresolved',[ (r['vol'],r['line']) for r in res if r.get('new') is None])
print('notes',[(r['vol'],r['line'],r['note'][:50]) for r in res if r.get('note')])
print('max old len',max(len(r['old']) for r in res))
