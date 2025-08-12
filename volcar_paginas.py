# volcar_paginas.py
# Uso: python volcar_paginas.py shiwilu-dictionary2.pdf 482 485 > dump.txt
import sys, fitz, re
def norm(s): 
    return re.sub(r"\s+", " ", s.strip()).replace("’","'").replace("ʼ","'")
def lines_in_page(p):
    blocks = p.get_text("blocks")
    mid = p.rect.width/2
    L,R=[],[]
    for x0,y0,x1,y1,txt,*_ in blocks:
        (L if x0<mid else R).append((x0,y0,txt))
    for arr in (sorted(L,key=lambda t:(round(t[1],1),round(t[0],1))),
                sorted(R,key=lambda t:(round(t[1],1),round(t[0],1)))):
        for _,_,txt in arr:
            for ln in txt.splitlines():
                ln = norm(ln)
                if ln: yield ln
pdf=sys.argv[1]; a=int(sys.argv[2]); b=int(sys.argv[3])
doc=fitz.open(pdf)
for pno in range(a-1, min(b, len(doc))):
    print(f"\n=== PAG {pno+1} ===")
    for i,ln in enumerate(lines_in_page(doc[pno]),1):
        print(f"{i:03d}: {ln}")
