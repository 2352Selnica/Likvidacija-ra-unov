# app.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from parser import (
    preberi_eracun,
    preberi_prevzemnico,
    preberi_narocilnico,
    primerjaj,
)

st.set_page_config(page_title="Primerjava računa", page_icon="📑", layout="wide")

st.title("📑 Primerjava eRačuna, prevzemnice in naročilnice")
st.caption(
    "Naložite tri datoteke – aplikacija samodejno poveže postavke in "
    "prikaže morebitna odstopanja v količinah, cenah in popustih."
)

col1, col2, col3 = st.columns(3)
with col1:
    f_eracun = st.file_uploader("1) eRačun (XML, eSLOG)", type=["xml"])
with col2:
    f_prevzemnica = st.file_uploader("2) Prevzemnica (XML)", type=["xml"])
with col3:
    f_narocilnica = st.file_uploader("3) Naročilnica (TXT)", type=["txt"])

if st.button("🔍 Primerjaj", type="primary", use_container_width=True):
    if not (f_eracun and f_prevzemnica and f_narocilnica):
        st.warning("Prosimo, naložite vse tri datoteke.")
        st.stop()

    try:
        with st.spinner("Berem in primerjam ..."):
            eracun = preberi_eracun(f_eracun)
            prevzemnica = preberi_prevzemnico(f_prevzemnica)
            narocilnica = preberi_narocilnico(f_narocilnica)
            rezultati = primerjaj(eracun, prevzemnica, narocilnica)

        df = pd.DataFrame(rezultati)

        # Povzetek
        st.subheader("📊 Povzetek")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Postavk na računu", len(df))
        c2.metric("Brez opozoril", (df['Opozorila'] == 'OK').sum())
        c3.metric("Z opozorili", (df['Opozorila'] != 'OK').sum())
        c4.metric("Manjkajoče postavke",
                  df['Opozorila'].str.contains('NI V', na=False).sum())

        # Barvanje vrstic
        def obarvaj(vrstica):
            if vrstica['Opozorila'] == 'OK':
                return ['background-color: #d4edda'] * len(vrstica)
            return ['background-color: #f8d7da'] * len(vrstica)

        st.subheader("📋 Primerjalna tabela")
        st.dataframe(
            df.style.apply(obarvaj, axis=1),
            use_container_width=True,
            hide_index=True,
        )

        # Prenos CSV
        csv = df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button(
            "⬇️ Prenesi rezultat (CSV)",
            data=csv,
            file_name="primerjava_racuna.csv",
            mime="text/csv",
            use_container_width=True,
        )

    except Exception as e:
        st.error(f"Napaka pri obdelavi: {e}")
        st.exception(e)
