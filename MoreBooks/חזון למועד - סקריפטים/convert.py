"""docx -> MoreBooks/ספרים/אוצריא/ספרי מוסר/אחרונים/חזון למועד.txt"""
import sys,re,html; sys.path.insert(0,__file__.rsplit('/',1)[0])
from dx import *
TITLE='חזון למועד'; AUTHOR='מרדכי דוב איידעלבערג'
SKIP=set(range(40,102))            # the book's own detailed TOC (bold line + TOC2 summary pairs)
HEB=['א','ב','ג','ד','ה','ו','ז','ח','ט','י']
HLEVEL={'1':2,'2':3,'3':4}
def ws(s): return re.sub(r'\s+',' ',s).strip()
def inline(rs, small_ok):
    segs=[]  # (text,bold,small)
    for t,b,z,k in rs:
        if k=='tab': t=' '
        elif k.startswith('br:'):
            if k=='br:line' or k=='br:textWrapping': t='\n'
            else: continue
        elif k!='t': continue
        segs.append((t,b,small_ok and z is not None and z<=20))
    # merge
    m=[]
    for t,b,s in segs:
        if m and m[-1][1]==b and m[-1][2]==s: m[-1][0]+=t
        else: m.append([t,b,s])
    out=''
    for t,b,s in m:
        t=re.sub(r'[ \t]+',' ',html.escape(t,quote=False))
        lead=t[:len(t)-len(t.lstrip(' '))]; trail=t[len(t.rstrip(' ')):]; core=t.strip(' ')
        if not core: out+=t; continue
        if s: core=f'<small>{core}</small>'
        if b: core=f'<b>{core}</b>'
        out+=lead+core+trail
    out=re.sub(r' +',' ',out).strip()
    out=re.sub(r'</b> ?<b>',lambda mm:mm.group(0).replace('</b>','').replace('<b>',''),out)
    return out.replace('\n','<br>').strip()
lines=[f'<h1>{TITLE}</h1>',AUTHOR]
prev=1; numc=0
for i,p in enumerate(PARAS,1):
    if i in SKIP: continue
    s=style(p)
    if s=='TOC2': continue
    rs=runs(p)
    own=ws(''.join(x[0] if x[3]=='t' else ' ' for x in rs))
    if s in HLEVEL:
        if own:
            lv=min(HLEVEL[s],prev+1); prev=lv
            lines.append(f'<h{lv}>{html.escape(own,quote=False)}</h{lv}>')
    else:
        txt=inline(rs, small_ok=(i>=35))
        np_=p.find(W+'pPr/'+W+'numPr')
        if np_ is not None and txt:
            txt=HEB[numc]+'. '+txt; numc+=1
        if txt: lines.append(txt)
    for q in txbx_paras(p):
        t=ws(''.join(x[0] for x in runs(q) if x[3]=='t'))
        if t and t!=own: lines.append(html.escape(t,quote=False))
OUT=sys.argv[1] if len(sys.argv)>1 else os.path.join(REPO,'MoreBooks','ספרים','אוצריא','ספרי מוסר','אחרונים',TITLE+'.txt')
open(OUT,'w',encoding='utf-8').write('\n'.join(lines)+'\n')
print('lines',len(lines))
