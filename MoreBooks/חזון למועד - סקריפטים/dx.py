"""docx run extraction for the conversion (fields, text boxes, deleted runs)."""
import re
from lxml import etree
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
H=re.compile(r'[֐-׿]+'); mask=lambda s:H.sub('*',s)
import os,zipfile
REPO=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','..'))
DOCX=os.path.join(REPO,'extraBooks','ספרים פרטיים ועוד',"חזון למועד ג' שערים.docx")
XML=zipfile.ZipFile(DOCX).read('word/document.xml')
doc=etree.fromstring(XML).getroottree(); body=doc.getroot().find(W+'body')
PARAS=body.findall(W+'p')
def style(p):
    e=p.find(W+'pPr/'+W+'pStyle'); return e.get(W+'val') if e is not None else ''
def rprop(r,tag):
    e=r.find(W+'rPr/'+W+tag); return e
def runs(p, skip_txbx=True):
    """yield (text,bold,sz,kind) for direct runs of p, honoring fields; excludes textbox content"""
    out=[]; state=[]  # field stack: 'instr' or 'result'
    for r in p.iter(W+'r'):
        # skip runs inside textboxes / drawings
        a=r.getparent(); inside=False
        while a is not None and a is not p:
            if a.tag in (W+'txbxContent',) or a.tag.endswith('}txbxContent') or a.tag.endswith('}drawing') or a.tag.endswith('}pict') or a.tag.endswith('}AlternateContent'):
                inside=True;break
            a=a.getparent()
        if inside and skip_txbx: continue
        if a is None: pass
        # deleted
        if r.getparent().tag==W+'del': continue
        b=rprop(r,'b'); bold=b is not None and b.get(W+'val') not in ('0','false')
        s=rprop(r,'sz'); sz=int(s.get(W+'val')) if s is not None else None
        for ch in r:
            t=ch.tag
            if t==W+'fldChar':
                ty=ch.get(W+'fldCharType')
                if ty=='begin': state.append('instr')
                elif ty=='separate' and state: state[-1]='result'
                elif ty=='end' and state: state.pop()
            elif t==W+'instrText': continue
            elif t==W+'t':
                if state and state[-1]=='instr': continue
                out.append((ch.text or '',bold,sz,'t'))
            elif t==W+'tab': out.append(('\t',bold,sz,'tab'))
            elif t==W+'br':
                out.append(('',bold,sz,'br:'+(ch.get(W+'type') or 'line')))
            elif t==W+'sym': out.append(('?SYM',bold,sz,'sym'))
    return out
def txbx_paras(p):
    seen=[]
    for tb in p.iter():
        if tb.tag.endswith('}txbxContent'):
            # avoid duplicates from mc:Fallback
            anc=tb.getparent(); fb=False
            while anc is not None and anc is not p:
                if anc.tag.endswith('}Fallback'): fb=True;break
                anc=anc.getparent()
            if fb: continue
            seen.extend(tb.findall(W+'p'))
    return seen
