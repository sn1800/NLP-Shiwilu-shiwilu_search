# extraer_diccionario_dual.py
# Uso:
#   python extraer_diccionario_dual.py shiwilu-dictionary2.pdf --mode shi --from 5 --to 479 -o diccionario_shi_es.csv
#   python extraer_diccionario_dual.py shiwilu-dictionary2.pdf --mode es  --from 480 --to 1076 -o diccionario_es_shi.csv

import sys, re, csv, fitz, argparse
from pathlib import Path

TAG_RE = re.compile(r"\b(vb|vt|vi|adj|adv|nom|prt|s)\.?\b", re.I)

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip()).replace("’","'").replace("ʼ","'")

def looks_shiwilu_token(tok: str) -> bool:
    if not tok: 
        return False
    # si empieza con signos/puntuación, NO es headword
    if tok[0] in "¿¡\"'“”‘’([{•–—-":
        return False
    if len(tok) > 40:
        return False
    return ("'" in tok or "-" in tok)

def looks_shiwilu_head(line: str) -> bool:
    L = norm(line).lstrip("* ").strip()
    if not L: return False
    first = re.split(r"[\s,;:()]+", L, 1)[0]
    return looks_shiwilu_token(first)

def looks_spanish_head(line: str) -> bool:
    L = norm(line).lstrip("* ").strip()
    if not L: 
        return False
    first = re.split(r"[\s,;:()]+", L, 1)[0]
    if first and first[0] in "¿¡\"'“”‘’([{•–—-":
        return False
    if "'" in first:
        return False
    return bool(re.match(r"^[A-Za-zÁÉÍÓÚÑáéíóúñ]+(?:[- ][A-Za-zÁÉÍÓÚÑáéíóúñ]+)*$", first))

def is_header_line(line: str, mode: str) -> bool:
    line_n = norm(line)
    # exige etiqueta gramatical en la MISMA línea
    if not TAG_RE.search(line_n[:120]):
        return False
    if mode == "shi":
        first = re.split(r"[\s,;:()]+", line_n.lstrip("* ").strip(), 1)[0]
        return looks_shiwilu_token(first)
    else:
        return looks_spanish_head(line_n)
    
def extract_headword(header_text: str) -> str:
    L = norm(header_text).lstrip("* ").strip()
    for tok in re.split(r"[ ,;:()]", L):
        t = tok.strip()
        if looks_shiwilu_token(t): return t
    return L.split()[0] if L.split() else L

def lines_in_reading_order(page: fitz.Page):
    """Devuelve líneas en orden: columna izq (arriba->abajo), luego der."""
    blocks = page.get_text("blocks")  # (x0,y0,x1,y1,text, block_no, ... )
    mid_x = page.rect.width / 2
    left, right = [], []
    for b in blocks:
        x0,y0,x1,y1,text,*_ = b
        (left if x0 < mid_x else right).append((x0,y0,x1,y1,text))

    def dump(blks):
        blks.sort(key=lambda t: (round(t[1],1), round(t[0],1)))
        for x0,y0,x1,y1,text in blks:
            for ln in text.splitlines():
                ln = norm(ln)
                if ln: yield ln

    # primero toda la izquierda, luego toda la derecha
    for ln in dump(left):
        yield ln
    for ln in dump(right):
        yield ln

def segment_pdf(pdf_path: Path, start_human: int, end_human: int, mode: str):
    doc = fitz.open(str(pdf_path))
    start = max(0, start_human - 1)
    end = min(len(doc)-1, end_human - 1)
    if end < start: raise ValueError("Rango de páginas inválido.")

    entries, cur = [], None
    candidates = kept = 0

    for i in range(start, end + 1):
        page_no_human = i + 1
        for ln in lines_in_reading_order(doc[i]):

            # ignora cabeceras editoriales
            if re.search(r"(?i)^(diccionario shiwilu|draft document|national science foundation)$", ln):
                continue

            is_header = is_header_line(ln, mode)
            if is_header:
                if cur and cur["entry_text"].strip():
                    entries.append(cur); kept += 1
                candidates += 1
                cur = {"headword": extract_headword(ln), "entry_text": ln, "page": page_no_human}
            else:
                if cur:
                    # une guiones de fin de línea (palabra- \n siguente)
                    if cur["entry_text"].endswith("-"):
                        cur["entry_text"] = cur["entry_text"][:-1] + ln
                    else:
                        cur["entry_text"] += " " + ln

    if cur and cur["entry_text"].strip():
        entries.append(cur); kept += 1

    # Filtros finales
    filtered = []
    for e in entries:
        txt = e["entry_text"]
        has_tag = bool(TAG_RE.search(txt))
        if mode == "shi":
            if has_tag: filtered.append(e)
        else:
            has_shi_token = bool(re.search(r"[A-Za-z0-9]+'[A-Za-z0-9]+", txt))
            if has_tag and has_shi_token: filtered.append(e)

    return filtered, candidates, kept

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=str)
    ap.add_argument("--mode", choices=["shi","es"], required=True)
    ap.add_argument("--from", dest="from_page", type=int, required=True)
    ap.add_argument("--to", dest="to_page", type=int, required=True)
    ap.add_argument("-o", "--out", type=str, required=True)
    args = ap.parse_args()

    rows, cand, closed = segment_pdf(Path(args.pdf), args.from_page, args.to_page, args.mode)

    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["headword","entry_text","page","mode"])
        kept = 0
        for e in rows:
            head = norm(e["headword"]); text = norm(e["entry_text"])
            key = (head, text)
            if key in seen: continue
            seen.add(key)
            w.writerow([head, text, e["page"], args.mode]); kept += 1

    print(f"[{args.mode}] Candidatos: {cand} | Cerradas: {closed} | Guardadas: {kept} → {out}")

if __name__ == "__main__":
    main()
