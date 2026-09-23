import subprocess,os,re,collections,sys
SK='/Users/david/Documents/otzaria-books/otzaria-library/.claude/skills/otzaria-book-format/scripts/validate_book.py'
os.chdir(sys.argv[1])
for f in sorted(os.listdir('.')):
    r=subprocess.run(['python3','-X','utf8',SK,f],capture_output=True,text=True)
    tail=[l for l in (r.stdout+r.stderr).splitlines() if l.strip()][-2:]
    L=open(f,encoding='utf-8').read().split('\n')
    h=collections.Counter(re.match(r'<(h\d)',l).group(1) for l in L if l.startswith('<h'))
    bad=[i+1 for i,l in enumerate(L) if re.search('[?][א-ת]|<\\?|`|[‎‏]',l)]
    b=sum(l.startswith('<b>') for l in L)
    fh3=next((i for i,l in enumerate(L) if l.startswith('<h3')),None); h2s=[i for i,l in enumerate(L) if l.startswith('<h2')]
    orphan = fh3 is not None and (not h2s or h2s[0]>fh3)
    print(f[15:-4].ljust(4),'rc',r.returncode,dict(h),'bold',b,'residue',bad[:5],'orphan',orphan,'|',' / '.join(tail)[:140])
