import streamlit as st
import pandas as pd
import re
import io
import pdfplumber # Za branje besedila iz PDF
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image

# Nastavitve strani
st.set_page_config(page_title="Likvidacija Računov", layout="wide")

st.title("🧾 Pomočnik pri likvidaciji računov")
st.markdown("""
Ta aplikacija primerja podatke iz **Naročila (Excel)** s podatki na **Računu (PDF)**.
""")

# --- STRANSKA PLOŠČA (SIDEBAR) ---
st.sidebar.header("⚙️ Nastavitve")
nacin_branja = st.sidebar.radio(
    "Način branja PDF:",
    ["Samodejno (najprej digitalno, nato OCR)", "Samo OCR (za skenirane dokumente)"],
    index=0
)
jezik_ocr = st.sidebar.selectbox("Jezik OCR", ["slv+eng", "slv", "eng"], index=0)

# --- GLAVNI DEL APLIKACIJE ---

# 1. Nalaganje Excel datoteke (Naročilo)
st.header("1. Naloži Naročilo (Excel)")
excel_file = st.file_uploader("Naloži Excel datoteko z naročilom", type=["xlsx", "xls"])

df_narocilo = None
if excel_file is not None:
    try:
        df_narocilo = pd.read_excel(excel_file)
        st.success("Excel uspešno naložen!")
        st.dataframe(df_narocilo.head()) 
    except Exception as e:
        st.error(f"Napaka pri branju Excela: {e}")

# 2. Nalaganje PDF Računov
st.header("2. Naloži Račune (PDF)")
pdf_files = st.file_uploader("Naloži PDF račune (lahko več hkrati)", type=["pdf"], accept_multiple_files=True)

if pdf_files and df_narocilo is not None:
    if st.button("🚀 Začni primerjavo"):
        st.info("Prosim počakajte, analiziram dokumente...")
        
        for pdf_file in pdf_files:
            st.subheader(f"📄 Analiza dokumenta: {pdf_file.name}")
            
            celotno_besedilo = ""
            
            try:
                # --- POSKUS 1: Branje digitalnega besedila iz PDF ---
                if nacin_branja.startswith("Samodejno"):
                    with pdfplumber.open(pdf_file) as pdf:
                        for page in pdf.pages:
                            tekst_strani = page.extract_text()
                            if tekst_strani:
                                celotno_besedilo += tekst_strani + "\n"
                
                # --- POSKUS 2: OCR, če digitalno branje ni uspelo ali je bilo izbrano ---
                if not celotno_besedilo.strip() or nacin_branja == "Samo OCR (za skenirane dokumente)":
                    st.info("Izvajam OCR (optično branje)... To lahko traja nekaj sekund.")
                    pdf_file.seek(0) # Ponastavimo kazalec datoteke
                    images = convert_from_bytes(pdf_file.read(), dpi=300)
                    
                    for img in images:
                        tekst = pytesseract.image_to_string(img, lang=jezik_ocr)
                        celotno_besedilo += tekst + "\n"
                
                if not celotno_besedilo.strip():
                    st.error("Ni bilo mogoče prebrati nobenega besedila iz dokumenta.")
                    continue

                # --- ISKANJE PODATKOV V BESEDILU ---
                # Iskanje številke naročila (Regex za format npr. P25-18358-01)
                najdene_reference = re.findall(r'[A-Z]{1,3}\d{2}-\d{4,6}-\d{2}', celotno_besedilo)
                
                opozorila = []
                ujemanja = 0
                
                # Preverjanje referenc naročila
                if najdene_reference:
                    st.write(f"🔍 Najdene reference na računu: **{', '.join(set(najdene_reference))}**")
                else:
                    opozorila.append("Na računu ni bilo mogoče najti številke naročila (npr. P25-xxxxx-xx).")

                # Preverjanje artiklov iz Excela
                stolpec_sifra = None
                for col in df_narocilo.columns:
                    if 'šifra' in col.lower() or 'koda' in col.lower() or 'artikel' in col.lower():
                        stolpec_sifra = col
                        break
                
                if stolpec_sifra:
                    for index, row in df_narocilo.iterrows():
                        sifra = str(row[stolpec_sifra]).strip()
                        if sifra in celotno_besedilo:
                            ujemanja += 1
                        else:
                            opozorila.append(f"Šifra artikla **{sifra}** iz naročila ni bila najdena na računu (možna napaka branja ali artikel manjka).")
                else:
                    st.warning("V Excelu ni bilo mogoče najti stolpca s šifro artikla (npr. 'Šifra', 'Koda').")

                # --- PRIKAZ REZULTATOV ---
                if not opozorila:
                    st.success(f"✅ Vsi preverjeni podatki se ujemajo! Najdenih ujemanj: {ujemanja}.")
                else:
                    st.warning(f"⚠️ Zaznanih je {len(opozorila)} morebitnih neskladnosti:")
                    for op in opozorila:
                        st.write(f"- {op}")
                
                with st.expander("Prikaži surovo prebrano besedilo"):
                    st.text(celotno_besedilo)

            except Exception as e:
                st.error(f"Napaka pri obdelavi datoteke {pdf_file.name}: {e}")

elif not pdf_files and df_narocilo is not None:
    st.info("Excel je naložen. Prosimo, naložite še PDF račune.")
