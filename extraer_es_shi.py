# extraer_es_shi.py
# Español → Shiwilu (diccionario, desde pág. 480 hasta el final por defecto)
# Uso:
#   python extraer_es_shi.py shiwilu-dictionary2.pdf es_shi_estructurado.csv
#   (opcional) --start 480 --end 1076

import sys, re, csv, fitz
from pathlib import Path

def arg(k, default):
    for i,a in enumerate(sys.argv):
        if a==k and i+1<len(sys.argv): return sys.argv[i+1]
    return default

if len(sys.argv) < 3:
    print("Uso: python extraer_es_shi.py PDF SALIDA.csv [--start 480] [--end 1076]")
    sys.exit(1)

PDF = Path(sys.argv[1])
OUT = Path(sys.argv[2])
START = int(arg("--start","480")) - 1  # 0-based interno
END   = int(arg("--end","999999"))     # tope alto por defecto

POS = r"(vb\.|vt\.|vi\.|adj\.|adv\.|nom\.|prt\.|s\.|interj\.|interrog\.|post\.|adpos\.|conect\.|conj\.)"
HDR_SECOND = re.compile(rf"^\*?\s*(?P<shi>[A-Za-zÁÉÍÓÚÑáéíóúñ0-9'’ʼ\-]+)\s+(?P<pos>{POS})\b(?P<rest>.*)$")

TRASH_PATTERNS = (
    re.compile(r"^\d+$"),            # folios sueltos: 480, 481, ...
    re.compile(r"^yuyu'wa$", re.I),  # encabezado de corrida que aparece en páginas
)

def is_trash(line: str) -> bool:
    return any(p.match(line) for p in TRASH_PATTERNS)

def norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s.replace("’","'").replace("ʼ","'")

def looks_shi_sentence(s: str) -> bool:
    s = norm(s)
    if re.search(r"[A-Za-z0-9]+'[A-Za-z0-9]", s):  # a'cha, ma'llin…
        return True
    if s.count("-") >= 2:
        return True
    if len(re.findall(r"\b[A-Za-z0-9\-]+'[A-Za-z0-9\-]+\b", s)) >= 2:
        return True
    return False

def split_examples(rest: str):
    rest = norm(rest)
    if not rest: return "", "", ""
    sents = re.split(r"(?<=[\.\!\?])\s+", rest)
    shi, es = [], []
    for s in sents:
        if not s: continue
        (shi if looks_shi_sentence(s) else es).append(s)
    def_es = rest
    for s in shi+es: def_es = def_es.replace(s, "")
    return norm(def_es), norm(" ".join(shi)), norm(" ".join(es))

def lines_in_reading_order(page: fitz.Page):
    blocks = page.get_text("blocks")
    mid = page.rect.width/2
    L,R=[],[]
    for x0,y0,x1,y1,txt,*_ in blocks:
        (L if x0<mid else R).append((x0,y0,txt))
    def dump(arr):
        for x0,y0,txt in sorted(arr, key=lambda t:(round(t[1],1), round(t[0],1))):
            for ln in txt.splitlines():
                ln = norm(ln)
                if ln: yield ln
    for ln in dump(L): yield ln
    for ln in dump(R): yield ln

def run(pdf: Path, start_idx: int, end_page: int):
    doc = fitz.open(str(pdf))
    last = min(end_page, len(doc)) if end_page != 999999 else len(doc)

    rows=[]
    es_buf = []      # varias líneas en español (cabecera)
    cur = None       # entrada actual
    carry = ""       # unión por guion
    n_headers = 0

    for i in range(max(0,start_idx), last):
        page = doc[i]; pno = i+1

        for raw in lines_in_reading_order(page):
            ln = raw
            # unir palabra cortada con guion al final
            if carry:
                ln = norm(carry + " " + ln); carry = ""
            if raw.endswith("-") and re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]-$", raw):
                carry = raw[:-1]
                continue

            if is_trash(ln):
                continue

            # ¿Es la 2ª línea del encabezado (shi + POS)?
            m2 = HDR_SECOND.match(ln)
            if m2:
                # cerrar entrada previa
                if cur:
                    rows.append(cur); cur = None

                es_head = norm(" ".join(es_buf))
                es_buf = []
                cur = {
                    "es_head": es_head,
                    "shi_lemma": norm(m2.group("shi")),
                    "pos": norm(m2.group("pos")),
                    "rest": norm(m2.group("rest")),
                    "page": pno
                }
                n_headers += 1
                continue

            # si hay entrada abierta, todo lo que siga es su contenido
            if cur:
                cur["rest"] = norm(cur["rest"] + " " + ln)
            else:
                # seguimos acumulando español de cabecera (puede ocupar varias líneas)
                es_buf.append(ln)

        # limpiar buffer de cabecera al pasar de página (evita arrastre)
        es_buf = []

    if cur:
        rows.append(cur)

    # Postproceso: separar definición y ejemplos, y deduplicar
    out=[]; seen=set()
    for e in rows:
        def_es, ex_shi, ex_es = split_examples(e["rest"])
        key=(e["es_head"], e["shi_lemma"], e["pos"], def_es, e["page"])
        if key in seen: continue
        seen.add(key)
        out.append(dict(
            es_head=e["es_head"],
            shi_lemma=e["shi_lemma"],
            pos=e["pos"],
            def_es=def_es,
            examples_shi=ex_shi,
            examples_es=ex_es,
            page=e["page"]
        ))

    print(f"Rango leído: {start_idx+1}–{last} | Detectados encabezados (ES→SHI): {n_headers} | Filas finales: {len(out)}")
    return out

if __name__=="__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = run(PDF, START, END)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["es_head","shi_lemma","pos","def_es","examples_shi","examples_es","page"])
        w.writeheader()
        w.writerows(data)
    print(f"OK: {len(data)} filas → {OUT}")
