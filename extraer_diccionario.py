# extraer_diccionario.py
# Uso:
#   python extraer_diccionario.py "shiwilu-dictionary2.pdf" "diccionario_utf8.csv"

import sys, re, csv, fitz
from pathlib import Path

START_PAGE_IDX = 4  # pág humana 5
TAG_RE = re.compile(r"\b(vb|vt|vi|adj|adv|nom|prt|s)\.?\b", re.I)

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip()).replace("’","'").replace("ʼ","'")

def looks_shiwilu_head(line: str) -> bool:
    """Encabezado si empieza con *?token que parezca shiwilu."""
    L = norm(line).lstrip("* ").strip()
    if not L: return False
    first = re.split(r"[\s,;:()]+", L, 1)[0]
    # heurística: apóstrofo o guion, o todo minúsculas con ascii extendido
    if first.count("'") >= 1: return True
    if "-" in first: return True
    # muchas entradas empiezan por algo tipo a'..., y casi nunca por ¿¡
    if first and first[0] not in "¿¡" and len(first) <= 40 and re.match(r"^[A-Za-zÁÉÍÓÚÑáéíóúñ0-9'\-]+$", first):
        # evita palabras castellanas típicas
        if not re.match(r"^(el|la|los|las|de|del|y|o|que|como|para|con|sin|por|sobre)$", first, re.I):
            return True
    return False

def extract_headword(header_text: str) -> str:
    L = norm(header_text).lstrip("* ").strip()
    for tok in re.split(r"[ ,;:()]", L):
        if tok.count("'") >= 1 or "-" in tok:
            return tok
    return L.split()[0] if L.split() else L

def segment_pdf(pdf_path: Path):
    doc = fitz.open(str(pdf_path))
    entries, cur = [], None
    candidates, kept = 0, 0

    for i in range(START_PAGE_IDX, len(doc)):
        page_no = i + 1
        text = doc[i].get_text("text")  # lectura lineal robusta
        lines = [norm(ln) for ln in text.splitlines() if norm(ln)]

        j = 0
        while j < len(lines):
            ln = lines[j]
            # salta cabeceras obvias
            if re.search(r"(?i)^(diccionario shiwilu|draft document|national science foundation)$", ln):
                j += 1
                continue

            if looks_shiwilu_head(ln):
                # cerrar el anterior
                if cur and cur["entry_text"].strip():
                    entries.append(cur); kept += 1
                candidates += 1
                cur = {"headword": extract_headword(ln), "entry_text": ln, "page": page_no}
            else:
                if cur:
                    cur["entry_text"] += " " + ln
            j += 1

    if cur and cur["entry_text"].strip():
        entries.append(cur); kept += 1

    # filtro final: debe contener algún tag en algún lugar
    filtered = [e for e in entries if TAG_RE.search(e["entry_text"])]
    return filtered, candidates, kept

def main():
    if len(sys.argv) < 3:
        print('Uso: python extraer_diccionario_fallback.py "shiwilu-dictionary2.pdf" "diccionario_utf8.csv"')
        sys.exit(1)
    pdf = Path(sys.argv[1]); out = Path(sys.argv[2])

    entries, candidates, kept = segment_pdf(pdf)

    out.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["headword","entry_text","page"])
        rows = 0
        for e in entries:
            head, text = norm(e["headword"]), norm(e["entry_text"])
            key = (head, text)
            if key in seen: continue
            seen.add(key)
            w.writerow([head, text, e["page"]]); rows += 1

    print(f"Candidatos detectados: {candidates}")
    print(f"Entradas cerradas (antes de filtro): {kept}")
    print(f"Entradas con tag (guardadas): {rows} → {out}")

if __name__ == "__main__":
    main()
