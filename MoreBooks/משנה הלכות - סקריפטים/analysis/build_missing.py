# Build missing_simanim.json for print simanim absent from the scraped files, with quality gates.
import siman,re,json,glob,collections,unicodedata,pdflines
V=collections.Counter()
for f in glob.glob('/Users/david/Downloads/משנה הלכות/*.txt'):
    V.update(re.findall(r'[א-ת]+(?:["\'`][א-ת]+)*["\'`]?',open(f).read().replace('`',"'")))
out={};gates={}
for v,n in [(12,403),(16,136),(16,137),(17,73)]:
    it=siman.extract(v,n); L=siman.to_lines(it)
    lines=[t for k,t in L]
    txt='\n'.join(lines)
    ws=re.findall(r'[א-ת]+(?:["\'][א-ת]+)*["\']?',txt)
    inv=sum(1 for w in ws if V[w] or V[w.rstrip('\'"')])/max(1,len(ws))
    bad=[c for c in txt if (0xE000<=ord(c)<=0xF8FF) or unicodedata.category(c) in('Cc','Cf') and c!='\n' or re.match('[A-Za-z]',c) or c=='�']
    cnt=lambda w:len(re.findall(r'(?<![א-ת])'+w+r'(?![א-ת])',txt))
    order={w:(cnt(w),cnt(w[::-1])) for w in ['של','זה','והנה','אבל','דהנה']}
    # boundary: what follows in print after last item
    last=it[-1]
    heads=siman.H[v]; nums=[h[0] for h in heads]; a=nums.index(n)
    nxt=heads[a+1][:2] if a+1<len(heads) else 'end-of-volume'
    gates[f'{v}:{n}']=dict(lines=len(lines),kinds=dict(collections.Counter(k for k,t in L)),words=len(ws),invocab=round(inv,4),bad_chars=len(bad),order=order,
        pages=f"{it[0]['p']}-{last['p']}",next_heading=nxt,digits=len(re.findall(r'\d',txt)),hyphens=txt.count('-'))
    out[f'{v}:{n}']=lines
json.dump(out,open('missing_simanim.json','w'),ensure_ascii=False,indent=1)
for k,g in gates.items(): print(k,g)
