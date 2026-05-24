#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
matcher.py — pure matching logic, no disk I/O.

Public API:
    run_matching(csv_content, source_contents) -> dict
        csv_content     : bytes | str  (the anchor CSV)
        source_contents : list[bytes | str]  (one per uploaded JSON file)
    returns {
        "consolidado":   [ ...one record per product, with a slot per source... ],
        "plano":         [ ...one row per (product x source) match... ],
        "cola_revision": [ {producto, fuente, motivo, mejor_candidato, detalle} ],
        "metricas":      { ...summary numbers... },
        "fuentes":       [ list of source names detected, e.g. labarraccu/jumbo/carrefour ],
    }
"""
import json, re, unicodedata, csv, io
from collections import defaultdict

# ------------------------------------------------------------------ #
# 0. NORMALIZATION LAYER
# ------------------------------------------------------------------ #
def fold(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.]+", " ", s.lower())).strip()

BRAND_ALIASES = {"levite": "levite", "levité": "levite", "colon": "colon",
                 "colón": "colon", "villa del sur": "villa del sur", "1888": "1888"}
def canon_brand(b):
    f = fold(b)
    return BRAND_ALIASES.get(f, f)

def parse_capacity_ml(text):
    t = fold(text).replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(l|lt|lts|litros?)\b", t)
    if m: return round(float(m.group(1)) * 1000)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(ml|cc|cm3)\b", t)
    if m: return round(float(m.group(1)))
    return None

def parse_pack(text):
    t = fold(text)
    if "sixpack" in t or "six pack" in t: return 6
    m = re.search(r"x\s*(\d{1,2})\b", t)
    if m: return int(m.group(1))
    m = re.search(r"\b(\d{1,2})\s*(u|un|unid|unidades)\b", t)
    if m: return int(m.group(1))
    m = re.search(r"pack\s*(\d{1,2})\b", t)   # "Pack 6"
    if m: return int(m.group(1))
    return None

def to_number(v):
    if v is None or v == "": return None
    if isinstance(v, (int, float)): return int(v)
    s = re.sub(r"[^\d.]", "", str(v).replace(",", "."))
    try: return int(float(s))
    except ValueError: return None

def beer_format(cap_ml, name=""):
    n = fold(name)
    if "porron" in n: return "porron"
    if "lata" in n:   return "lata"
    if cap_ml == 330: return "porron"
    if cap_ml in (473, 710, 269, 354): return "lata"
    return None

FLAVORS = ["naranja", "manzana", "pomelo", "pera", "limon", "uva",
           "frutos rojos", "durazno", "pomelo rosado", "lima"]
NEGATIVE = ["sin alcohol", "0.0", "cero", "light", "zero"]
KNOWN_BRANDS = {"heineken", "schneider", "miller", "amstel", "imperial",
                "1888", "villa del sur", "levite", "colon"}

def resolve_brands(marca, name):
    keys = {canon_brand(marca)}
    fn = fold(name)
    for b in KNOWN_BRANDS:
        if all(tok in fn for tok in b.split()):
            keys.add(b)
    return {k for k in keys if k}

STOP = {"cerveza", "cervezas", "rubia", "blanca", "negra", "botella", "lata",
        "porron", "porrones", "en", "ml", "cc", "cm3", "l", "lt", "lts", "de",
        "x", "un", "u", "unidades", "pack", "vino", "agua", "mineral",
        "saborizada", "sidra", "sin", "gas", "sifon", "pura", "malta", "stout",
        "del", "la", "el"}
def descriptor(tokens, cap_ml, pack):
    drop = set(STOP)
    return {w for w in tokens if w not in drop and not any(ch.isdigit() for ch in w)}

def jaccard(a, b):
    return len(a & b) / len(a | b) if (a | b) else 0.0

def cap_close(a, b, tol=0.02):
    if a is None or b is None: return None
    return abs(a - b) <= max(5, a * tol)

# ------------------------------------------------------------------ #
# SCORING
# ------------------------------------------------------------------ #
def score(t, c):
    reasons = []
    if t["brand"] not in c["brands"]:
        return 0, ["brand_mismatch"], True
    cc = cap_close(t["cap_ml"], c["cap_ml"])
    if cc is False:
        return 0, [f"cap {t['cap_ml']}!={c['cap_ml']}"], True
    if t["pack"] and (not c["pack"] or c["pack"] != t["pack"]):
        return 0, [f"pack target={t['pack']}, candidato={c['pack'] or 'desconocido'}"], True
    t_neg = any(k in t["fname"] for k in NEGATIVE)
    c_neg = any(k in c["fname"] for k in NEGATIVE)
    if t_neg != c_neg:
        return 0, ["alcohol/zero variant mismatch"], True
    c_flavor = next((f for f in FLAVORS if f in c["fname"]), None)
    if t["flavor"]:
        if t["flavor"] not in c["fname"]:
            return 0, [f"flavor!={t['flavor']}"], True
        reasons.append("flavor")
    elif c_flavor:
        return 0, [f"candidate flavored ({c_flavor})"], True
    s = 0.40; reasons.append("brand")
    if cc is True: s += 0.10; reasons.append("cap")
    if t["pack"] and c["pack"] and t["pack"] == c["pack"]: s += 0.10; reasons.append("pack")
    if t.get("fmt"):
        cf = beer_format(c["cap_ml"], c["name"])
        if cf == t["fmt"]: s += 0.05; reasons.append(f"fmt={t['fmt']}")
        elif cf: s -= 0.10; reasons.append("fmt!=")
    td = descriptor(t["tokens"], t["cap_ml"], t["pack"]) - {t["brand"]}
    cd = descriptor(c["tokens"], c["cap_ml"], c["pack"]) - {t["brand"]}
    if td:
        dov = len(td & cd) / len(td); s += 0.35 * dov; reasons.append(f"desc={dov:.2f}")
    else:
        s += 0.30 - min(0.12, 0.04 * len(cd)); reasons.append(f"plain(cd={len(cd)})")
    return min(s, 1.0), reasons, False

ACCEPT, REVIEW, AMBIG_GAP = 0.72, 0.55, 0.08

# ------------------------------------------------------------------ #
# HELPERS for loading uploaded content
# ------------------------------------------------------------------ #
def _text(content):
    return content.decode("utf-8") if isinstance(content, (bytes, bytearray)) else content

def _normalize_record(r, site):
    name = r.get("nombre", "")
    rec = {
        "site": site, "name": name, "fname": fold(name),
        "tokens": set(fold(name).split()),
        "brand": canon_brand(r.get("marca", "")), "brands": set(),
        "cap_ml": parse_capacity_ml(name), "pack": parse_pack(name),
        "ean": str(r.get("ean", "")).strip(), "sku": str(r.get("sku", "")).strip(),
        "priceList": to_number(r.get("precioLista")),
        "realPrice": to_number(r.get("precioFinal")),
        "url": r.get("url_producto", "") or r.get("url", ""),
        "seller": r.get("seller", site), "raw": r,
    }
    rec["brands"] = resolve_brands(r.get("marca", ""), name)
    return rec

def price_per_litre(price, cap_ml, pack):
    if not price or not cap_ml: return None
    litres = cap_ml * (pack or 1) / 1000.0
    return round(price / litres, 2) if litres else None

# ------------------------------------------------------------------ #
# MAIN ENTRY POINT
# ------------------------------------------------------------------ #
def run_matching(csv_content, source_contents, filename=""):
    # --- load + group sources by their `sitio` field (generic upload) ---
    by_site = defaultdict(list)
    for content in source_contents:
        data = json.loads(_text(content))
        if isinstance(data, dict):                       # tolerate {items:[...]}
            data = next((v for v in data.values() if isinstance(v, list)), [])
        for r in data:
            site = fold(r.get("sitio", "")) or "desconocido"
            by_site[site].append(_normalize_record(r, site))
    sites = sorted(by_site.keys())

    brand_index = {s: defaultdict(list) for s in sites}
    for s, recs in by_site.items():
        for rec in recs:
            for k in rec["brands"]:
                brand_index[s][k].append(rec)

    # --- load anchor CSV or XLSX ---
    targets = []
    if filename.endswith(".xlsx"):
        import pandas as pd
        rows = pd.read_excel(io.BytesIO(csv_content)).to_dict("records")
    else:
        rows = list(csv.DictReader(io.StringIO(_text(csv_content))))
    for row in rows:
        name = row.get("Producto", "")
        cap = parse_capacity_ml(row.get("Capacidad", ""))
        cat = row.get("Categoria", "")
        targets.append({
            "name": name, "fname": fold(name),
            "brand": canon_brand(row.get("Marca", "")),
            "cap_ml": cap, "pack": parse_pack(row.get("Unidades", "")),
            "category": cat, "tokens": set(fold(name).split()),
            "flavor": next((f for f in FLAVORS if f in fold(name)), None),
            "fmt": beer_format(cap, name) if "cerveza" in fold(cat) else None,
        })

    # --- cascade ---
    consolidado, plano, cola = [], [], []
    for t in targets:
        prod = {"producto": t["name"], "marca": t["brand"], "categoria": t["category"],
                "capacidad_ml": t["cap_ml"], "unidades": t["pack"],
                "fuentes": {}, "encontrado_en": []}
        for site in sites:
            cands = brand_index[site].get(t["brand"], [])
            scored = []
            for c in cands:
                sc, why, fail = score(t, c)
                if not fail:
                    scored.append((sc, why, c))
            scored.sort(key=lambda x: -x[0])
            if not scored:
                prod["fuentes"][site] = {"encontrado": False, "estado": "NO_CANDIDATE",
                                         "url": None, "precioLista": None, "precioFinal": None}
                cola.append({"producto": t["name"], "fuente": site, "motivo": "NO_CANDIDATE",
                             "mejor_candidato": "", "detalle": ""})
                continue
            best_sc, best_why, best = scored[0]
            runner = scored[1][0] if len(scored) > 1 else 0
            ambiguous = (best_sc - runner) < AMBIG_GAP and len(scored) > 1
            if best_sc >= ACCEPT and not ambiguous:
                ppl = price_per_litre(best["realPrice"], best["cap_ml"], best["pack"])
                prod["fuentes"][site] = {
                    "encontrado": True, "estado": "MATCH", "url": best["url"],
                    "precioLista": best["priceList"], "precioFinal": best["realPrice"],
                    "precioPorLitro": ppl, "seller": best["seller"],
                    "ean": best["ean"] or None, "sku": best["sku"] or None,
                    "match": best["name"], "score": round(best_sc, 3),
                }
                prod["encontrado_en"].append(site)
                plano.append({
                    "name": t["name"], "capacity_ml": t["cap_ml"], "units": t["pack"],
                    "brand": t["brand"], "category": t["category"], "site": site,
                    "ean": best["ean"] or None, "sku": best["sku"] or None,
                    "seller": best["seller"], "priceList": best["priceList"],
                    "realPrice": best["realPrice"], "url": best["url"],
                    "match": best["name"], "score": round(best_sc, 3),
                })
            else:
                estado = "AMBIGUOUS" if ambiguous else "LOW_SCORE"
                prod["fuentes"][site] = {
                    "encontrado": False, "estado": estado, "url": None,
                    "precioLista": None, "precioFinal": None,
                    "mejor_candidato": best["name"], "url_candidato": best["url"],
                    "score": round(best_sc, 3)}
                cola.append({"producto": t["name"], "fuente": site, "motivo": estado,
                             "mejor_candidato": f"{best['name']} ({best_sc:.2f})",
                             "detalle": " ".join(best_why)})
        consolidado.append(prod)

    metricas = {
        "productos": len(targets),
        "matches_totales": len(plano),
        "en_revision": len(cola),
        "fuentes_detectadas": sites,
        "cobertura": {f"{k}/3": sum(1 for p in consolidado if len(p["encontrado_en"]) == k)
                      for k in (3, 2, 1, 0)},
        "matches_por_fuente": {s: sum(1 for p in plano if p["site"] == s) for s in sites},
    }
    return {"consolidado": consolidado, "plano": plano,
            "cola_revision": cola, "metricas": metricas, "fuentes": sites}
