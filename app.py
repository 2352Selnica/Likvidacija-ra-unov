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
""")

# --- STRANSKA PLOŠČA ---
st.sidebar.header("📌 Navodila za uporabo")
st.sidebar.info("""
1. Naložite PDF račun.
2. Podatke iz Naročilnice in Prejemnice preprosto **označite v vašem sistemu (MAOP), kopirajte (Ctrl+C) in prilepite (Ctrl+V)** v ustrezna polja.
3. Kliknite 'Primerjaj dokumente'.
""")

# Pametna funkcija za pretvorbo prilepljenega besedila v DataFrame
def pametno_branje_besedila(besedilo, ime_dokumenta):
    if not besedilo.strip():
        return None
    
    # Poskusimo ugotoviti, kateri ločilec je uporabljen (tab, podpičje, vejica)
    # Preštejemo pojavitve v prvi vrstici
    prva_vrstica = besedilo.split('\n')[0]
    locila = {'\t': prva_vrstica.count('\t'), ';': prva_vrstica.count(';'), ',': prva_vrstica.count(',')}
    najbolj_pogost = max(locila, key=locila.get)
    
    try:
        if locila[najbolj_pogost] > 0:
            # Če najdemo ločilo, ga uporabimo
            df = pd.read_csv(io.StringIO(besedilo), sep=najbolj_pogost)
        else:
            # Če ni jasnega ločila, poskusimo ločiti po 2 ali več presledkih
            df = pd.read_csv(io.StringIO(besedilo), sep=r'\s{2,}', engine='python')
            
        # Počistimo imena stolpcev (odstranimo morebitne presledke)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Napaka pri branju prilepljenih podatkov za {ime_dokumenta}: {e}")
        st.info("Nasvet: Poskusite podatke kopirati tako, da boste zajeli celotno tabelo (vključno z glavo), ali jih izvozite v Excel.")
        return None

# --- GLAVNI DEL ---

# 1. Nalaganje Računa (PDF)
st.header("1. Naloži Račun (PDF)")
pdf_file = st.file_uploader("Naloži eRačun (PDF)", type=["pdf"])

# 2. Nalaganje Naročilnice in Prejemnice
st.header("2. Naloži Naročilnico in Prejemnico")
st.write("Podatke lahko naložite kot Excel datoteko ali jih preprosto prilepite iz vašega sistema.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Naročilnica (Cene)")
    excel_narocilnica = st.file_uploader("Naloži Excel Naročilnico", type=["xlsx", "xls"], key="nar")
    paste_narocilnica = st.text_area("Ali prilepite podatke Naročilnice tukaj (označite tabelo v MAOP in Ctrl+C):", height=150)

with col2:
    st.subheader("Prejemnica (Količine)")
    excel_prejemnica = st.file_uploader("Naloži Excel Prejemnico", type=["xlsx", "xls"], key="pre")
    paste_prejemnica = st.text_area("Ali prilepite podatke Prejemnice tukaj (označite tabelo v MAOP in Ctrl+C):", height=150)

# Priprava DataFrame-ov
df_nar = None
if excel_narocilnica:
    df_nar = pd.read_excel(excel_narocilnica)
elif paste_narocilnica:
    df_nar = pametno_branje_besedila(paste_narocilnica, "Naročilnica")

df_pre = None
if excel_prejemnica:
    df_pre = pd.read_excel(excel_prejemnica)
elif paste_prejemnica:
    df_pre = pametno_branje_besedila(paste_prejemnica, "Prejemnica")

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
                
                st.success("PDF uspešno prebran!")
                
                # --- ISKANJE KLJUČNIH STOLPCEV V PRILEPLJENIH PODATKIH ---
                # Ker so prilepljeni podatki lahko neurejeni, poskusimo najti prave stolpce
                def najdi_stolpec(df, iskani_izrazi):
                    for col in df.columns:
                        if any(izraz in str(col).lower() for izraz in iskani_izrazi):
                            return col
                    return None
                
                # V Naročilnici iščemo Šifro, Količino in Ceno
                nar_sifra = najdi_stolpec(df_nar, ['šifra', 'artikel', 'koda'])
                nar_kolicina = najdi_stolpec(df_nar, ['količina', 'kol.', 'kolicina'])
                nar_cena = najdi_stolpec(df_nar, ['cena', 'nabavna'])
                
                # V Prejemnici iščemo Šifro in Količino
                pre_sifra = najdi_stolpec(df_pre, ['šifra', 'artikel', 'koda'])
                pre_kolicina = najdi_stolpec(df_pre, ['količina', 'kol.', 'kolicina'])

                # Če stolpcev ne najdemo po imenu, privzamemo, da je prvi stolpec šifra, drugi pa količina
                if not nar_sifra or not pre_sifra:
                    st.warning("Nisem mogel samodejno prepoznati stolpcev s šiframi. Privzamem, da je prvi stolpec šifra.")
                    nar_sifra = df_nar.columns[0]
                    pre_sifra = df_pre.columns[0]

                # --- PRIPRAVA PRIMERJALNE TABELE ---
                st.subheader("📊 Primerjalna tabela")
                primerjava = []
                
                # Vzamemo unikatne šifre iz Naročilnice kot osnovo
                unikatne_sifre = df_nar[nar_sifra].astype(str).unique()
                
                for sifra in unikatne_sifre:
                    # Podatki iz Naročilnice
                    vrstica_nar = df_nar[df_nar[nar_sifra].astype(str) == sifra]
                    kolicina_nar = vrstica_nar[nar_kolicina].values[0] if nar_kolicina else 'N/A'
                    cena_nar = vrstica_nar[nar_cena].values[0] if nar_cena else 'N/A'
                    
                    # Podatki iz Prejemnice
                    vrstica_pre = df_pre[df_pre[pre_sifra].astype(str) == sifra]
                    kolicina_pre = vrstica_pre[pre_kolicina].values[0] if pre_kolicina and not vrstica_pre.empty else 'Ni v prejemnici'
                    
                    # Podatki iz Računa
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
                    # Preverimo ujemanje količin (pretvorimo v float za varno primerjavo)
                    try:
                        k_nar = float(str(vrstica['Naročeno (Nar.)']).replace(',', '.'))
                        k_pre = float(str(vrstica['Prevzeto (Pre.)']).replace(',', '.'))
                        if k_nar != k_pre:
                            opozorila.append("Količina se ne ujema!")
                    except:
                        pass # Če ne moremo pretvoriti, preskočimo
                    return ", ".join(opozorila)

                df_primerjava['Opozorila'] = df_primerjava.apply(oznaci_napake, axis=1)
                
                # Prikaz tabele z barvanjem (POPRAVLJENO za novejše verzije Pandas)
                def obarvanje_vrstice(val):
                    if val != "":
                        return 'background-color: #ffcccc; color: #cc0000; font-weight: bold;'
                    return ''

                st.dataframe(
                    df_primerjava.style.map(obarvanje_vrstice, subset=['Opozorila']), 
                    use_container_width=True
                )
                
                # --- PRIKAZ SUROVEGA BESEDILA ---
                with st.expander("Prikaži surovo prebrano besedilo iz PDF računa"):
                    st.text(vsebina_racuna)
                    
            except Exception as e:
                st.error(f"Prišlo je do napake: {e}")
