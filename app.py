import streamlit as st
import pandas as pd
import pdfplumber
import re
import io

# Nastavitve strani
st.set_page_config(page_title="Asistent za likvidacijo računov", layout="wide")

st.title("🧾 Asistent za likvidacijo računov")
st.markdown("""
Ta aplikacija referentu pomaga pri primerjavi **Računa (PDF)** z **Naročilnico** in **Prejemnico**.
Aplikacija iz PDF računa izlušči podatke in jih primerja s podatki iz vašega sistema.
""")

# --- STRANSKA PLOŠČA ---
st.sidebar.header("📌 Navodila za uporabo")
st.sidebar.info("""
1. Naložite PDF račun.
2. Naložite Excel naročilnice (ali prilepite podatke).
3. Naložite Excel prejemnice (ali prilepite podatke).
4. Kliknite 'Primerjaj dokumente'.
""")

# Funkcija za pretvorbo vstavljenega besedila (iz Excela) v DataFrame
def pretvori_besedilo_v_df(besedilo):
    if not besedilo.strip():
        return None
    try:
        # Predpostavimo, da je besedilo ločeno s tabulatorji (standardni copy/paste iz Excela)
        df = pd.read_csv(io.StringIO(besedilo), sep='\t')
        return df
    except Exception as e:
        st.error(f"Napaka pri branju prilepljenega besedila: {e}")
        return None

# --- GLAVNI DEL ---

# 1. Nalaganje Računa (PDF)
st.header("1. Naloži Račun (PDF)")
pdf_file = st.file_uploader("Naloži eRačun (PDF)", type=["pdf"])

# 2. Nalaganje Naročilnice in Prejemnice
st.header("2. Naloži Naročilnico in Prejemnico")
st.write("Podatke lahko naložite kot Excel datoteko ali jih preprosto prilepite iz vašega sistema (Ctrl+C / Ctrl+V).")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Naročilnica (Cene)")
    excel_narocilnica = st.file_uploader("Naloži Excel Naročilnico", type=["xlsx", "xls"], key="nar")
    paste_narocilnica = st.text_area("Ali prilepite podatke Naročilnice tukaj:", height=150)

with col2:
    st.subheader("Prejemnica (Količine)")
    excel_prejemnica = st.file_uploader("Naloži Excel Prejemnico", type=["xlsx", "xls"], key="pre")
    paste_prejemnica = st.text_area("Ali prilepite podatke Prejemnice tukaj:", height=150)

# Priprava DataFrame-ov
df_nar = None
if excel_narocilnica:
    df_nar = pd.read_excel(excel_narocilnica)
elif paste_narocilnica:
    df_nar = pretvori_besedilo_v_df(paste_narocilnica)

df_pre = None
if excel_prejemnica:
    df_pre = pd.read_excel(excel_prejemnica)
elif paste_prejemnica:
    df_pre = pretvori_besedilo_v_df(paste_prejemnica)

# 3. Gumb za primerjavo
st.markdown("---")
if st.button("🚀 Primerjaj dokumente", type="primary"):
    if not pdf_file:
        st.error("Prosimo, naložite PDF račun.")
    elif df_nar is None or df_pre is None:
        st.error("Prosimo, naložite ali prilepite podatke za Naročilnico in Prejemnico.")
    else:
        with st.spinner("Analiziram račun in primerjam podatke..."):
            try:
                # --- BRANJE PDF RAČUNA ---
                vsebina_racuna = ""
                with pdfplumber.open(pdf_file) as pdf:
                    for page in pdf.pages:
                        tekst = page.extract_text()
                        if tekst:
                            vsebina_racuna += tekst + "\n"
                
                # --- LUŠČENJE PODATKOV IZ RAČUNA (Regex) ---
                # Iskanje vrstic, ki vsebujejo šifro (6 števk), količino in ceno
                # Primer vrstice na računu: "1 024036 100424 HUMALOG KwikPen ... KOS D918660 0627 SC 1 24,13 1,56 23,75 9,5"
                # Poiskali bomo šifre (6 mest) in poskusili najti pripadajoče količine in cene.
                
                # Za namene demonstracije bomo poiskali vse 6-mestne šifre v PDF-ju
                najdene_sifre_racun = re.findall(r'\b\d{6}\b', vsebina_racuna)
                # Odstranimo morebitne duplikate, ki niso šifre artiklov (npr. številke računov)
                # V vašem primeru so šifre: 024036, 024038, 024039, 1227848 (7 mest?), 100075981 (9 mest?)
                # Ker so šifre različno dolge, bomo poiskali vse številke, ki so daljše od 5 znakov
                najdene_sifre_racun = list(set(re.findall(r'\b\d{5,9}\b', vsebina_racuna)))
                
                st.success("PDF uspešno prebran!")
                
                # --- PRIPRAVA PRIMERJALNE TABELE ---
                st.subheader("📊 Primerjalna tabela")
                
                # Poskusimo najti skupni stolpec za šifro v vseh treh virih
                # (Predpostavljamo, da imate v Excelih stolpce 'Šifra' ali 'Artikel')
                sifra_col_nar = next((c for c in df_nar.columns if 'šifra' in c.lower() or 'artikel' in c.lower()), df_nar.columns[0])
                sifra_col_pre = next((c for c in df_pre.columns if 'šifra' in c.lower() or 'artikel' in c.lower()), df_pre.columns[0])
                
                # Ustvarimo novo tabelo za prikaz
                primerjava = []
                
                # Vzamemo unikatne šifre iz Naročilnice kot osnovo
                unikatne_sifre = df_nar[sifra_col_nar].astype(str).unique()
                
                for sifra in unikatne_sifre:
                    # Podatki iz Naročilnice
                    vrstica_nar = df_nar[df_nar[sifra_col_nar].astype(str) == sifra]
                    kolicina_nar = vrstica_nar['Količina'].values[0] if 'Količina' in vrstica_nar.columns else 'N/A'
                    cena_nar = vrstica_nar['Cena'].values[0] if 'Cena' in vrstica_nar.columns else 'N/A'
                    
                    # Podatki iz Prejemnice
                    vrstica_pre = df_pre[df_pre[sifra_col_pre].astype(str) == sifra]
                    kolicina_pre = vrstica_pre['Količina'].values[0] if 'Količina' in vrstica_pre.columns else 'N/A'
                    
                    # Podatki iz Računa (preverimo, ali se šifra pojavi v PDF-ju)
                    # Opomba: To je le preverjanje prisotnosti, za natančno količino bi potrebovali naprednejši parser
                    najdena_na_racunu = "Da" if sifra in vsebina_racuna else "NE"
                    
                    primerjava.append({
                        "Šifra": sifra,
                        "Naročeno (Nar.)": kolicina_nar,
                        "Prevzeto (Pre.)": kolicina_pre,
                        "Na računu": najdena_na_racunu,
                        "Cena (Nar.)": cena_nar
                    })
                
                df_primerjava = pd.DataFrame(primerjava)
                
                # --- OZNAČEVANJE NAPAK ---
                def oznaci_napake(vrstica):
                    opozorila = []
                    if vrstica['Na računu'] == 'NE':
                        opozorila.append("Manjka na računu!")
                    if vrstica['Naročeno (Nar.)'] != vrstica['Prevzeto (Pre.)']:
                        opozorila.append("Količina se ne ujema!")
                    return ", ".join(opozorila)

                df_primerjava['Opozorila'] = df_primerjava.apply(oznaci_napake, axis=1)
                
                # Prikaz tabele z barvanjem
                st.dataframe(df_primerjava.style.applymap(
                    lambda x: 'background-color: #ffcccc' if x != "" else '', 
                    subset=['Opozorila']
                ), use_container_width=True)
                
                # --- PRIKAZ SUROVEGA BESEDILA (Za debug) ---
                with st.expander("Prikaži surovo prebrano besedilo iz PDF računa"):
                    st.text(vsebina_racuna)
                    
            except Exception as e:
                st.error(f"Prišlo je do napake: {e}")
