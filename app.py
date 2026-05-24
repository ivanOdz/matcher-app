#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py — Streamlit UI for the product matcher.
Run locally:  streamlit run app.py
"""
import streamlit as st
import pandas as pd
from matcher import run_matching

st.set_page_config(page_title="Matcheo de productos", layout="wide")
st.title("Matcheo de productos entre fuentes")
st.caption("Subí el CSV de productos y los JSON de las fuentes. "
           "Las fuentes se detectan solas por el campo `sitio` de cada archivo.")

# ------------------------------------------------------------------ #
# BLOCK 1 — UPLOAD
# ------------------------------------------------------------------ #
col1, col2 = st.columns(2)
with col1:
    csv_file = st.file_uploader("CSV de productos (ancla)", type=["csv"])
with col2:
    json_files = st.file_uploader("JSON de fuentes (uno o varios)",
                                  type=["json"], accept_multiple_files=True)

run = st.button("Procesar", type="primary", disabled=not (csv_file and json_files))

if not run:
    st.info("Cargá el CSV y al menos un JSON, después tocá **Procesar**.")
    st.stop()

with st.spinner("Procesando matcheos..."):
    result = run_matching(csv_file.getvalue(),
                          [f.getvalue() for f in json_files])

m = result["metricas"]
consolidado = result["consolidado"]

# ------------------------------------------------------------------ #
# BLOCK 2 — SUMMARY METRICS
# ------------------------------------------------------------------ #
st.subheader("Resumen")
c1, c2, c3, c4 = st.columns(4)
encontrados = sum(1 for p in consolidado if p["encontrado_en"])
c1.metric("Productos buscados", m["productos"])
c2.metric("Con al menos 1 match", f'{encontrados}/{m["productos"]}')
c3.metric("Matches totales", m["matches_totales"])
c4.metric("En revisión", m["en_revision"])

cov = m["cobertura"]
st.write(f'Cobertura — en las 3 fuentes: **{cov["3/3"]}**, '
         f'en 2: **{cov["2/3"]}**, en 1: **{cov["1/3"]}**, en ninguna: **{cov["0/3"]}**')
st.caption("Fuentes detectadas: " + ", ".join(m["fuentes_detectadas"]))

# ------------------------------------------------------------------ #
# BLOCK 3 — RESULTS PER PRODUCT
# ------------------------------------------------------------------ #
st.subheader("Resultados por producto")
sites = result["fuentes"]

# coverage table
rows = []
for p in consolidado:
    row = {"Producto": p["producto"],
           "Capacidad": f'{p["capacidad_ml"]} ml' if p["capacidad_ml"] else "?",
           "Unidades": p["unidades"] or "-"}
    for s in sites:
        row[s] = "si" if p["fuentes"][s]["encontrado"] else "no"
    row["Cobertura"] = f'{len(p["encontrado_en"])}/{len(sites)}'
    rows.append(row)
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.markdown("#### Detalle (precio por litro normalizado)")
for p in consolidado:
    found = len(p["encontrado_en"])
    with st.expander(f'{p["producto"]} · {p.get("capacidad_ml","?")} ml '
                     f'× {p.get("unidades","-")} u  —  {found}/{len(sites)} fuentes'):
        det = []
        for s in sites:
            f = p["fuentes"][s]
            if f["encontrado"]:
                det.append({
                    "Fuente": s, "Estado": "match",
                    "Precio final": f["precioFinal"],
                    "Precio/litro": f.get("precioPorLitro"),
                    "Matcheado como": f["match"],
                    "Score": f["score"],
                    "Link": f["url"],
                })
            else:
                det.append({
                    "Fuente": s, "Estado": f["estado"],
                    "Precio final": None, "Precio/litro": None,
                    "Matcheado como": f.get("mejor_candidato", "—"),
                    "Score": f.get("score"), "Link": None,
                })
        col_order = ["Fuente", "Estado", "Precio final", "Precio/litro", "Matcheado como", "Score", "Link"]
        df = pd.DataFrame(det).reindex(columns=col_order)
        st.dataframe(
            df, use_container_width=True, hide_index=True,
            column_config={"Link": st.column_config.LinkColumn("Link", display_text="abrir")},
        )

# ------------------------------------------------------------------ #
# BLOCK 4 — REVIEW QUEUE
# ------------------------------------------------------------------ #
st.subheader("Cola de revisión")
if result["cola_revision"]:
    st.dataframe(pd.DataFrame(result["cola_revision"]),
                 use_container_width=True, hide_index=True)
else:
    st.success("Nada para revisar.")

# downloads
st.subheader("Descargas")
import json as _json
d1, d2 = st.columns(2)
d1.download_button("Descargar consolidado (.json)",
                   _json.dumps(consolidado, ensure_ascii=False, indent=2),
                   file_name="matcheos_consolidado.json", mime="application/json")
d2.download_button("Descargar plano (.json)",
                   _json.dumps(result["plano"], ensure_ascii=False, indent=2),
                   file_name="matcheos_resultado.json", mime="application/json")
