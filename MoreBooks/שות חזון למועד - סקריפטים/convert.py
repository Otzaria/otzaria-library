# docx -> Otzaria. usage: python3 convert.py <source.docx> <out.txt>
# (h2=headings, h5 "ענף X" -> h3, h4 שאלה/תשובה -> bold line, other headings -> body)
import re,zipfile,sys
from xml.etree import ElementTree as ET
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
z=zipfile.ZipFile(sys.argv[1])
st=ET.fromstring(z.read('word/styles.xml'))
names={}
for s in st.iter(W+'style'):
    n=s.find(W+'name'); names[s.get(W+'styleId')]=(n.get(W+'val') if n is not None else '')
doc=ET.fromstring(z.read('word/document.xml'))
body=doc.find(W+'body')
paras=[]
for p in body.iter(W+'p'):
    ps=p.find(W+'pPr/'+W+'pStyle'); sid=ps.get(W+'val') if ps is not None else ''
    runs=[]
    for r in p.iter(W+'r'):
        t=''.join((x.text or '') if x.tag==W+'t' else ('\t' if x.tag==W+'tab' else ('\n' if x.tag==W+'br' else '')) for x in r)
        b=r.find(W+'rPr/'+W+'b') is not None
        sz=r.find(W+'rPr/'+W+'sz'); sz=sz.get(W+'val') if sz is not None else ''
        runs.append((t,b,sz))
    paras.append((sid,runs))

import re,html,os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
TITLE='שו"ת חזון למועד'
AUTHOR='מרדכי דוב איידעלבערג'
ANAF=re.compile(r'^ענף\s+\S+$')
def norm(s): return re.sub(r'\s+',' ',s)
def ptext(runs): return norm(''.join(t for t,b,s in runs)).strip()
def render(runs):
    # merge adjacent runs by bold flag
    segs=[]
    for t,b,s in runs:
        t=norm(t)
        if not t: continue
        if segs and segs[-1][1]==b: segs[-1][0]+=t
        else: segs.append([t,b])
    out=''
    for t,b in segs:
        e=html.escape(t,quote=False)
        if b and t.strip():
            lead=e[:len(e)-len(e.lstrip())]; trail=e[len(e.rstrip()):]
            out+=lead+'<b>'+e.strip()+'</b>'+trail
        else: out+=e
    out=re.sub(r'</b>(\s*)<b>',r'\1',out)
    return re.sub(r'\s+',' ',out).strip()
lines=['<h1>'+TITLE+'</h1>',AUTHOR]
for i,(sid,runs) in enumerate(paras):
    t=ptext(runs)
    if not t: continue
    e=html.escape(t,quote=False)
    if sid=='2': lines.append('<h2>'+e+'</h2>')
    elif sid=='5' and ANAF.match(t) and len(t)<=12: lines.append('<h3>'+e+'</h3>')
    elif sid=='4' and re.sub(r'[.:!]+$','',t) in ('תשובה','שאלה'): lines.append('<b>'+e+'</b>')
    else: lines.append(render(runs))
open(sys.argv[2],'w',encoding='utf-8').write('\n'.join(lines)+'\n')
print(len(lines))
