#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_matcher.py — smoke test del matcher contra los archivos de sample_data/.

Correr:   pytest -q          (si tenés pytest)
   o:     python test_matcher.py
"""
from pathlib import Path
from matcher import run_matching

SAMPLE = Path(__file__).parent / "sample_data"

def _run():
    csv = next(SAMPLE.glob("*.csv")).read_bytes()
    sources = [p.read_bytes() for p in SAMPLE.glob("*.json")]
    return run_matching(csv, sources)

def test_metricas_basicas():
    m = _run()["metricas"]
    assert m["productos"] == 15
    assert m["matches_totales"] >= 30
    assert set(m["fuentes_detectadas"]) == {"labarraccu", "jumbo", "carrefour"}

def test_cobertura():
    cov = _run()["metricas"]["cobertura"]
    assert cov["3/3"] >= 7          # mayoría encontrada en las 3 fuentes
    assert cov["0/3"] >= 1          # "Sidra 1888" no se encuentra (ancla vaga)

def test_heineken_en_tres_fuentes_y_labarraccu_mas_barato():
    r = _run()
    h = next(p for p in r["consolidado"]
             if p["producto"] == "Heineken Lata" and p["capacidad_ml"] == 473)
    assert len(h["encontrado_en"]) == 3
    # labarraccu vende pack X24; normalizado por litro es el más barato
    assert h["mas_barato"] == "labarraccu"

def test_sidra_1888_va_a_revision():
    r = _run()
    s = next(p for p in r["consolidado"] if p["producto"] == "Sidra 1888")
    assert len(s["encontrado_en"]) == 0

def test_sin_falsos_positivos_bajo_umbral():
    # todo match aceptado debe superar el umbral de aceptación (0.72)
    assert all(row["score"] >= 0.72 for row in _run()["plano"])

if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as e:
                fails += 1; print(f"FAIL  {name}: {e}")
    print(f"\n{'TODO OK' if not fails else str(fails)+' FALLARON'}")
    sys.exit(1 if fails else 0)
