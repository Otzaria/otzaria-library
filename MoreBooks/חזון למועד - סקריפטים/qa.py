"""character-level preservation check: docx text vs the book file (Hebrew masked in output)."""
import re,html,difflib,sys
import os,zipfile
REPO=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','..'))
X=zipfile.ZipFile(os.path.join(REPO,'extraBooks','ספרים פרטיים ועוד',"חזון למועד ג' שערים.docx")).read('word/document.xml').decode('utf-8')
body=X[X.index('<w:body>'):]
paras=[];depth=0;start=None
for mm in re.finditer(r'<w:p(?:\s[^>]*)?>|</w:p>',body):
    t=mm.group(0)
    if t.endswith('/>'):
        if depth==0: paras.append('')
        continue
    if t.startswith('<w:p'):
        if depth==0: start=mm.start()
        depth+=1
    else:
        depth-=1
        if depth==0: paras.append(body[start:mm.end()])
print('paras',len(paras))
def txt(px):
    px=re.sub(r'<mc:Fallback>.*?</mc:Fallback>','',px,flags=re.S)
    return ' '.join(html.unescape(t) for t in re.findall(r'<w:t(?: [^>]*)?>([^<]*)</w:t>',px))
def raw(px):
    px=re.sub(r'<mc:Fallback>.*?</mc:Fallback>','',px,flags=re.S)
    return ''.join(html.unescape(t) for t in re.findall(r'<w:t(?: [^>]*)?>([^<]*)</w:t>',px))
# paragraphs 40-101 (the book's own TOC) and TOC2 lines are dropped on purpose
src=''.join(raw(px) for i,px in enumerate(paras,1) if not (40<=i<=101 or 'w:val="TOC2"' in px))
out=open(sys.argv[1],encoding='utf-8').read().split('\n')
o=html.unescape(re.sub(r'<[^>]+>','',''.join(out[2:])))
a=re.sub(r'\s','',src); b=re.sub(r'\s','',o)
# expected: +3 list numbers (א. ב. ג.), -1 text box duplicating the intro heading
H=re.compile(r'[\u0590-\u05FF]')
for op,a1,a2,b1,b2 in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
    if op!='equal': print(op,a1,'src:',H.sub('*',a[a1:a2]),'out:',H.sub('*',b[b1:b2]))
