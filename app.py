import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import re
import io

# Nastavitve strani
st.set_page_config(page_title="Asistent za likvidacijo računov", layout="wide")

st.title("🧾 Asistent za likvidacijo računov (XML)")
st.markdown("""
Ta aplikacija primerja **eRačun (XML)** z **Naročilnico** in **Prejemnico** na podlagi **imena artikla**.
""")

# --- STRANSKA PLOŠČA ---
st.sidebar.header("📌 Navodila")
st.sidebar.info("""
1. Naložite **XML datoteko eRačuna** (ne PDF!).
2. Prilepite podatke iz Naročilnice in Prejemnice (označite tabelo v MAOP in Ctrl+C).
3. Kliknite 'Primerjaj dokumente'.
""")

# Funkcija za pametno branje prilepljenega besedila
def pametno_branje_besedila(besedilo, ime_dokumenta):
    if not besedilo.strip():
        return None
    
    prva_vrstica = besedilo.split('\n')[0]
    locila = {'\t': prva_vrstica.count('\t'), ';': prva_vrstica.count(';'), ',': prva_vrstica.count(',')}
    najbolj_pogost = max(locila, key=locila.get)
    
    try:
        if locila[najbolj_pogost] > 0:
            df = pd.read_csv(io.StringIO(besedilo), sep=najbolj_pogost)
        else:
            df = pd.read_csv(io.StringIO(besedilo), sep=r'\s{2,}', engine='python')
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Napaka pri branju {ime_dokumenta}: {e}")
        return None

# --- FUNKCIJA ZA BRANJE XML RAČUNA ---
def preberi_xml_racun(xml_file):
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Definiramo namespace, ker je XML v standardu UBL/ebInterface
        # Poiščemo glavni element Invoice
        ns = {'inv': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2'}
        
        podatki = {
            "Stevilka_racuna": "Neznano",
            "Stevilka_narocila": "Neznano",
            "Postavke": []
        }
        
        # Iskanje številke računa (ID)
        id_elem = root.find('.//{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}ID')
        if id_elem is not None:
            podatki["Stevilka_racuna"] = id_elem.text
            
        # Iskanje številke naročila (OrderReference)
        order_ref = root.find('.//{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}OrderReference/{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}ID')
        if order_ref is not None:
            podatki["Stevilka_narocila"] = order_ref.text

        # Iskanje postavk (InvoiceLine)
        for line in root.findall('.//{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}InvoiceLine'):
            ime = "Neznano"
            kolicina = 0.0
            cena = 0.0
            
            # Ime artikla
            item_name = line.find('.//{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Item/{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Name')
            if item_name is not None:
                ime = item_name.text
            
            # Količina (InvoicedQuantity)
            qty = line.find('.//{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}InvoicedQuantity')
            if qty is not None:
                kolicina = float(qty.text)
                
            # Cena na enoto (PriceAmount)
            price = line.find('.//{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Price/{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}PriceAmount')
            if price is not None:
                cena = float(price.text)
                
            podatki["Postavke"].append({
                "Ime": ime,
                "Kolicina": kolicina,
                "Cena": cena
            })
            
        return podatki
    except Exception as e:
        st.error(f"Napaka pri branju XML datoteke: {e}")
        return None

# --- GLAVNI DEL ---

st.header("1. Naloži Račun (XML)")
xml_file = st.file_uploader("Naloži eRačun (XML)", type=["xml"])

st.header("2. Naloži Naročilnico in Prejemnico")
st.write("Ker se šifre razlikujejo, bomo primerjali **imena artiklov**.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Naročilnica")
    excel_narocilnica = st.file_uploader("Naloži Excel Naročilnico", type=["xlsx", "xls"], key="nar")
    paste_narocilnica = st.text_area("Ali prilepite podatke Naročilnice (Ctrl+C):", height=150)

with col2:
    st.subheader("Prejemnica")
    excel_prejemnica = st.file_uploader("Naloži Excel Prejemnico", type=["xlsx", "xls"], key="pre")
    paste_prejemnica = st.text_area("Ali prilepite podatke Prejemnice (Ctrl+C):", height=150)

df_nar = None
if excel_narocilnica: df_nar = pd.read_excel(excel_narocilnica)
elif paste_narocilnica: df_nar = pametno_branje_besedila(paste_narocilnica, "Naročilnica")

df_pre = None
if excel_prejemnica: df_pre = pd.read_excel(excel_prejemnica)
elif paste_prejemnica: df_pre = pametno_branje_besedila(paste_prejemnica, "Prejemnica")

st.markdown("---")
if st.button("🚀 Primerjaj dokumente", type="primary"):
    if not xml_file or df_nar is None or df_pre is None:
        st.error("Prosimo, naložite XML ter podatke za Naročilnico in Prejemnico.")
    else:
        with st.spinner("Analiziram XML in primerjam..."):
            try:
                # --- 1. BRANJE XML RAČUNA ---
                racun_podatki = preberi_xml_racun(xml_file)
                
                if not racun_podatki:
                    st.stop()
                
                st.success(f"XML uspešno prebran! Št. računa: **{racun_podatki['Stevilka_racuna']}** (Naročilo: {racun_podatki['Stevilka_narocila']})")
                
                # --- 2. ISKANJE KLJUČNIH STOLPCEV V PRILEPLJENIH PODATKIH ---
                def najdi_stolpec(df, iskani_izrazi):
                    for col in df.columns:
                        if any(izraz in str(col).lower() for izraz in iskani_izrazi):
                            return col
                    return None
                
                # Iščemo Naziv/Artikel, Količino in Ceno
                nar_naziv = najdi_stolpec(df_nar, ['naziv', 'artikel', 'ime', 'opis'])
                nar_kolicina = najdi_stolpec(df_nar, ['količina', 'kol.', 'kolicina'])
                nar_cena = najdi_stolpec(df_nar, ['cena', 'nabavna'])
                
                pre_naziv = najdi_stolpec(df_pre, ['naziv', 'artikel', 'ime', 'opis'])
                pre_kolicina = najdi_stolpec(df_pre, ['količina', 'kol.', 'kolicina'])

                if not nar_naziv or not pre_naziv:
                    st.error("V prilepljenih podatkih ne najdem stolpca z imenom artikla ('Naziv', 'Artikel'). Preverite, ali ste kopirali vključno z glavo tabele.")
                    st.stop()

                # --- 3. PRIPRAVA PRIMERJALNE TABELE ---
                st.subheader("📊 Primerjalna tabela")
                primerjava = []
                
                # Za osnovo vzamemo postavke iz XML računa (ker so točne)
                for postavka_racun in racun_podatki["Postavke"]:
                    ime_racun = postavka_racun["Ime"]
                    kolicina_racun = postavka_racun["Kolicina"]
                    cena_racun = postavka_racun["Cena"]
                    
                    # Poiščemo ujemajoče ime v Naročilnici (pametno iskanje po prvih dveh besedah)
                    iskalni_niz = " ".join(ime_racun.split()[:2]) 
                    
                    # Iskanje v Naročilnici
                    vrstica_nar = df_nar[df_nar[nar_naziv].astype(str).str.contains(iskalni_niz, case=False, na=False)]
                    if not vrstica_nar.empty:
                        ime_nar = vrstica_nar[nar_naziv].values[0]
                        kolicina_nar = vrstica_nar[nar_kolicina].values[0] if nar_kolicina else 'N/A'
                        cena_nar = vrstica_nar[nar_cena].values[0] if nar_cena else 'N/A'
                    else:
                        ime_nar = "Ni v naročilnici"
                        kolicina_nar = "N/A"
                        cena_nar = "N/A"
                        
                    # Iskanje v Prejemnici
                    vrstica_pre = df_pre[df_pre[pre_naziv].astype(str).str.contains(iskalni_niz, case=False, na=False)]
                    if not vrstica_pre.empty:
                        kolicina_pre = vrstica_pre[pre_kolicina].values[0] if pre_kolicina else 'N/A'
                    else:
                        kolicina_pre = "Ni v prejemnici"
                    
                    primerjava.append({
                        "Ime artikla (Račun)": ime_racun,
                        "Naročeno": kolicina_nar,
                        "Prevzeto": kolicina_pre,
                        "Fakturirano": kolicina_racun,
                        "Cena (Nar.)": cena_nar,
                        "Cena (Račun)": cena_racun
                    })
                
                df_primerjava = pd.DataFrame(primerjava)
                
                # --- 4. OZNAČEVANJE NAPAK ---
                def oznaci_napake(vrstica):
                    opozorila = []
                    
                    # Preverjanje količin (Naročeno vs Fakturirano)
                    try:
                        k_nar = float(str(vrstica['Naročeno']).replace(',', '.'))
                        k_rac = float(vrstica['Fakturirano'])
                        if k_nar != k_rac:
                            opozorila.append(f"Količina (Nar: {k_nar} vs Rač: {k_rac})")
                    except:
                        pass
                        
                    # Preverjanje količin (Prevzeto vs Fakturirano)
                    try:
                        k_pre = float(str(vrstica['Prevzeto']).replace(',', '.'))
                        k_rac = float(vrstica['Fakturirano'])
                        if k_pre != k_rac:
                            opozorila.append(f"Količina (Pre: {k_pre} vs Rač: {k_rac})")
                    except:
                        pass
                        
                    # Preverjanje cen (Naročeno vs Fakturirano)
                    try:
                        c_nar = float(str(vrstica['Cena (Nar.)']).replace(',', '.'))
                        c_rac = float(vrstica['Cena (Račun)'])
                        # Dovolimo majhno odstopanje zaradi zaokroževanja (npr. 0.01)
                        if abs(c_nar - c_rac) > 0.01:
                            opozorila.append(f"Cena (Nar: {c_nar} vs Rač: {c_rac})")
                    except:
                        pass
                        
                    return ", ".join(opozorila)

                df_primerjava['Opozorila'] = df_primerjava.apply(oznaci_napake, axis=1)
                
                # Prikaz tabele
                def obarvanje_vrstice(val):
                    if val != "": return 'background-color: #ffcccc; color: #cc0000; font-weight: bold;'
                    return ''

                st.dataframe(
                    df_primerjava.style.map(obarvanje_vrstice, subset=['Opozorila']), 
                    use_container_width=True
                )
                
            except Exception as e:
                st.error(f"Prišlo je do napake: {e}")
