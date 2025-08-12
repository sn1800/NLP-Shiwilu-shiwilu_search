# limpiar_entradas_v2.py
import sys, re, csv
from pathlib import Path

ABBR = ("vb.", "vt.", "vi.", "adj.", "adv.", "nom.", "prt.", "s.")
ABBR_RE = re.compile(r"\b(" + "|".join(re.escape(x) for x in ABBR) + r")\b", re.I)

# Ruido y metadatos del diccionario
NOISE_PAT = re.compile(
    r"(?i)\b(?:cf:|val\.?:|clf:|comp\.?\s+of|nprop\.?|hom:|superlatat:|pi\d|mek\d|nan\.?|dan\.?|dek\d|pi\b|nan\b|dan\b)\b"
)
# tokens raros de OCR / residuos
TRASH = re.compile(r'["“”]{1,}|!{1,}|^\W+$|^\d{1,4}\s*$')

SPAN_COMMON = r"\b(el|la|los|las|un|una|unos|unas|de|del|y|o|que|como|para|con|sin|por|sobre|entre|cuando|donde|quien|quién|cómo|cuándo|dónde|yo|tú|usted|él|ella|ellos|ellas|esto|eso|estos|esas|aquí|allí|ayer|hoy|mañana|porque|pero|también)\b"

def norm(s: str) -> str:
    s = s.replace("’","'").replace("ʼ","'")
    s = re.sub(r"\s+", " ", s.strip())
    return s

def split_header(entry_text: str):
    """Devuelve (pos_tag, body_desde_etiqueta). Si no halla etiqueta, body = texto normalizado."""
    t = norm(entry_text)
    m = ABBR_RE.search(t)
    if not m:
        return ("", t)
    pos = m.group(1).lower().rstrip(".")
    return (pos, t[m.start():])

def clean_noise(s: str) -> str:
    s = NOISE_PAT.sub("", s)
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" ,;:")
    return s

def is_spanish(s: str) -> bool:
    if re.search(r"[áéíóúñÁÉÍÓÚÑ¿¡]", s):
        return True
    if re.search(SPAN_COMMON, s, re.I):
        return True
    # tiene dígitos/medidas y pocas comillas → suele ser ES
    if re.search(r"\d", s) and s.count("'") < 2:
        return True
    return False

def is_shiwilu(s: str) -> bool:
    # ≥2 apóstrofos y sin signos españoles
    return (s.count("'") >= 2) and ("¿" not in s and "¡" not in s)

def split_units(text: str):
    """
    Divide el body en unidades:
    - primero por ' || ' si existe,
    - si no, por oraciones aproximadas.
    """
    if "||" in text:
        parts = [norm(x) for x in text.split("||")]
    else:
        parts = re.split(r"(?<=[\.\?\!])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])", text)
        if len(parts) == 1:
            parts = re.split(r"\s*(?<=\.)\s*", text)
    # limpia residuos
    out = []
    for p in parts:
        p = norm(p)
        if not p or TRASH.match(p):
            continue
        out.append(p)
    return out

def strip_headword_echo(text: str, head: str) -> str:
    """Quita repeticiones tipo 'headword 478 ! !' al inicio."""
    t = text
    # borra headword suelto + números/puntuación pegados
    t = re.sub(rf"^{re.escape(head)}\b[\s\d\W]*", "", t, flags=re.I)
    return norm(t)

def extract_senses(body: str):
    """Devuelve lista de sentidos en ES detectando '1) ... 2) ...' """
    senses = []
    # normaliza numeradores 1) 2)
    chunks = re.split(r"\s(?=\d\))", body)
    for ch in chunks:
        c = clean_noise(norm(ch))
        if len(c) > 1:
            senses.append(c)
    return senses if len(senses) > 1 else []

def process_row(row, cols):
    head = norm(row[cols["headword"]])
    raw  = norm(row[cols["entry_text"]])
    page = row.get(cols["page"], "") if cols["page"] else ""

    # 1) cortar hasta la etiqueta y extraer POS
    pos, body = split_header(raw)
    # quitar eco de headword al inicio si aparece
    body = strip_headword_echo(body, head)
    body = clean_noise(body)

    # 2) si hay sentidos numerados, construye gloss desde ellos
    senses = extract_senses(body)
    units = split_units(body)

    es_units, shi_units = [], []
    for u in units:
        u_clean = clean_noise(u)
        if not u_clean:
            continue
        if is_shiwilu(u_clean) and not is_spanish(u_clean):
            shi_units.append(u_clean)
        elif is_spanish(u_clean):
            es_units.append(u_clean)
        else:
            # ambiguos: decide por número de apóstrofos
            (shi_units if u_clean.count("'") >= 2 else es_units).append(u_clean)

    # 3) gloss_es: prioriza sentidos numerados; si no, usa ES units
    if senses:
        gloss_es = " ".join([s for s in senses if is_spanish(s)])
    else:
        gloss_es = " ".join(es_units)

    # 4) ejemplos: mantenlos separados
    examples_shi = " || ".join(shi_units)
    examples_es  = " || ".join([e for e in es_units if e not in senses])  # excluye definiciones si ya fueron a gloss

    return {
        "headword": head,
        "pos": pos,
        "gloss_es": gloss_es.strip(" ."),
        "examples_shi": examples_shi,
        "examples_es": examples_es,
        "page": page
    }, shi_units, [e for e in es_units if e not in senses]

def align_pairs(shi_list, es_list):
    n = min(len(shi_list), len(es_list))
    return [(shi_list[i], es_list[i]) for i in range(n)]

def open_csv_any(path: Path):
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            f = path.open("r", encoding=enc, newline="")
            rdr = csv.DictReader(f)
            hdrs = [h.strip() for h in rdr.fieldnames] if rdr.fieldnames else []
            return f, rdr, hdrs
        except UnicodeDecodeError:
            continue
    raise RuntimeError("No se pudo abrir el CSV (convierte a UTF-8).")

def expect_cols(hdrs):
    m = {h.lower(): h for h in hdrs}
    need = {}
    for k in ("headword","entry_text","page"):
        need[k] = m.get(k) if k in m else (None if k=="page" else (_ for _ in ()).throw(KeyError(f"Falta columna: {k}")))
    return need

def main():
    if len(sys.argv) < 3:
        print('Uso: python limpiar_entradas_v2.py "diccionario_utf8.csv" "diccionario_limpio.csv"')
        sys.exit(1)
    inp = Path(sys.argv[1]); out = Path(sys.argv[2])
    out_pairs = out.with_suffix(".pairs.tsv")

    f, rdr, hdrs = open_csv_any(inp)
    try:
        cols = expect_cols(hdrs)
        cleaned, all_pairs, seen = [], [], set()
        for row in rdr:
            c, shi_list, es_list = process_row(row, cols)
            key = (c["headword"], c["gloss_es"], c["page"])
            if key in seen: 
                continue
            seen.add(key)
            cleaned.append(c)
            for s,e in align_pairs(shi_list, es_list):
                all_pairs.append((c["headword"], s, e, c["page"]))

        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as fo:
            w = csv.DictWriter(fo, fieldnames=["headword","pos","gloss_es","examples_shi","examples_es","page"])
            w.writeheader()
            for c in cleaned:
                w.writerow(c)

        if all_pairs:
            with out_pairs.open("w", encoding="utf-8", newline="") as fp:
                fp.write("headword\tshi\tes\tpage\n")
                for hw, shi, es, pg in all_pairs:
                    fp.write(f"{hw}\t{shi}\t{es}\t{pg}\n")

        print(f"OK: {len(cleaned)} filas → {out}")
        print(f"Pares paralelos: {len(all_pairs)} → {out_pairs}")
    finally:
        f.close()

if __name__ == "__main__":
    main()
