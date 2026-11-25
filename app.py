# app.py
import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import re
import io
import pdfplumber
from datetime import datetime

# ---------------------------------------------------------------------------
# 1. POMOŽNE FUNKCIJE
# ---------------------------------------------------------------------------
def _f(vrednost, privzeto=0.0):
    if vrednost is None:
        return privzeto
    vrednost = str(vrednost).strip().replace(' ', '').replace(',', '.')
    try:
        return float(vrednost)
    except ValueError:
        return privzeto

def normaliziraj_naziv(n):
    if not n: return ""
    n = n.lower()
    n = re.sub(r'[^a-z0-9]+', ' ', n)
    return ' '.join(n.split())

def poisci_po_imenu(ciljni_naziv, slovar_postavk):
    if not ciljni_naziv: return None
    norm_cilj = normaliziraj_naziv(ciljni_naziv)
    for k, v in slovar_postavk.items():
        if normaliziraj_naziv(v['naziv']) == norm_cilj:
            return v
    ciljne_besede = set(norm_cilj.split())
    najboljse_ujemanje = None
    najvec_besed = 0
    for k, v in slovar_postavk.items():
        norm_v = normaliziraj_naziv(v['naziv'])
        v_besede = set(norm_v.split())
        skupne = ciljne_besede.intersection(v_besede)
        kljucne_ujemajoce = [b for b in skupne if len(b) >= 4]
        if len(kljucne_ujemajoce) > najvec_besed:
            najvec_besed = len(kljucne_ujemajoce)
            najboljse_ujemanje = v
    return najboljse_ujemanje if najvec_besed >= 1 else None

def pretvori_v_osnovno_enoto(kolicina, enota, naziv):
    if pd.isna(kolicina): return 0.0, "KOS"
    enota = str(enota).upper()
    if enota in ['SC', 'ŠK', 'SK']:
        m = re.search(r'(?:sc|šk)\s*=\s*(\d+)\s*kos', str(naziv), re.IGNORECASE)
        if m:
            faktor = float(m.group(1))
            return kolicina * faktor, "KOS"
    return kolicina, enota

# ---------------------------------------------------------------------------
# 2. BRANJE DATOTEK
# ---------------------------------------------------------------------------
def preberi_eracun(stream):
    ns = {'eslog': 'urn:eslog:2.00'}
    tree = ET.parse(stream)
    root = tree.getroot()
    postavke = {}
    for sg26 in root.findall('.//eslog:G_SG26', ns):
        sifra_sa = sifra_in = ''
        for pia in sg26.findall('eslog:S_PIA', ns):
            c212 = pia.find('eslog:C_C212', ns)
            if c212 is None: continue
            vrednost = c212.findtext('eslog:D_7140', default='', namespaces=ns)
            tip = c212.findtext('eslog:D_7143', default='', namespaces=ns)
            if tip == 'SA': sifra_sa = vrednost
            elif tip == 'IN': sifra_in = vrednost
        naziv = ''
        imd = sg26.find('eslog:S_IMD', ns)
        if imd is not None:
            naziv = imd.findtext('eslog:C_C273/eslog:D_7008', default='', namespaces=ns)
        
        kolicina = 0.0
        enota = 'KOS'
        qty = sg26.find('eslog:S_QTY/eslog:C_C186', ns)
        if qty is not None:
            kolicina = _f(qty.findtext('eslog:D_6060', default='0', namespaces=ns))
            enota = qty.findtext('eslog:D_6411', default='KOS', namespaces=ns)
            if enota == 'H87': 
                if 'sc=' in naziv.lower(): enota = 'SC'
                else: enota = 'KOS'

        cena_brez = cena_z = 0.0
        for pri in sg26.findall('eslog:G_SG29/eslog:S_PRI/eslog:C_C509', ns):
            tip = pri.findtext('eslog:D_5125', default='', namespaces=ns)
            vred = _f(pri.findtext('eslog:D_5118', default='0', namespaces=ns))
            if tip == 'AAA': cena_brez = vred
            elif tip == 'AAB': cena_z = vred
        popust = 0.0
        pcd = sg26.find('.//eslog:G_SG39/eslog:G_SG41/eslog:S_PCD/eslog:C_C501', ns)
        if pcd is not None:
            popust = _f(pcd.findtext('eslog:D_5482', default='0', namespaces=ns))
        ddv = 0.0
        tax = sg26.find('.//eslog:G_SG34/eslog:S_TAX/eslog:C_C243', ns)
        if tax is not None:
            ddv = _f(tax.findtext('eslog:D_5278', default='0', namespaces=ns))
        znesek_brez = znesek_z = 0.0
        for moa in sg26.findall('eslog:G_SG27/eslog:S_MOA/eslog:C_C516', ns):
            tip = moa.findtext('eslog:D_5025', default='', namespaces=ns)
            vred = _f(moa.findtext('eslog:D_5004', default='0', namespaces=ns))
            if tip == '203': znesek_brez = vred
            elif tip == '38': znesek_z = vred
        kljuc = sifra_in or sifra_sa or naziv
        postavke[kljuc] = {
            'sifra_sa': sifra_sa, 'sifra_in': sifra_in, 'naziv': naziv,
            'kolicina': kolicina, 'enota': enota, 'cena_brez': cena_brez, 'cena_z': cena_z,
            'popust': popust, 'ddv': ddv, 'znesek_brez': znesek_brez, 'znesek_z': znesek_z,
        }
    return postavke

def preberi_prevzemnico_pdf(stream):
    postavke = {}
    with pdfplumber.open(stream) as pdf:
        vse_besedilo = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text: vse_besedilo += text + "\n"
    vrstice = vse_besedilo.split('\n')
    i = 0
    while i < len(vrstice):
        vrstica = vrstice[i]
        m = re.search(r'^(\d+)\s+(\d{6})\s+(.+?)\s+KOS\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', vrstica)
        if m:
            sifra = m.group(2)
            naziv = m.group(3).strip()
            kolicina = _f(m.group(4))
            cena = _f(m.group(5))
            vrednost = _f(m.group(6))
            cena_brez, ddv, popust = 0.0, 0.0, 0.0
            if i + 1 < len(vrstice):
                naslednja = vrstice[i+1]
                m2 = re.search(r'^\d+\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', naslednja)
                if m2:
                    cena_brez = _f(m2.group(1))
                    ddv = _f(m2.group(2))
                    popust = _f(m2.group(3))
            postavke[sifra] = {
                'sifra': sifra, 'naziv': naziv, 'enota': 'KOS',
                'kolicina': kolicina, 'cena_brez': cena_brez, 'cena_z': cena,
                'popust': popust, 'ddv': ddv, 'znesek_brez': vrednost, 'znesek_z': vrednost,
            }
            i += 1
        i += 1
    return postavke

def preberi_prevzemnico_xml(stream):
    vsebina = stream.read()
    if isinstance(vsebina, bytes): vsebina = vsebina.decode('utf-8', errors='replace')
    vsebina_ociscena = vsebina.replace('$', '_')
    stream_ociscen = io.BytesIO(vsebina_ociscena.encode('utf-8'))
    tree = ET.parse(stream_ociscen)
    root = tree.getroot()
    postavke = {}
    for post in root.findall('.//CG_G_POST'):
        sifra = post.findtext('ART_S_ARTIKLA', default='').strip()
        postavke[sifra] = {
            'sifra': sifra, 'naziv': post.findtext('ART_N_ARTIKLA', default='').strip(), 'enota': 'KOS',
            'kolicina': _f(post.findtext('POST_KOLICINA', default='0')),
            'cena_brez': _f(post.findtext('CF_CENA_BREZ_DDV', default='0')),
            'cena_z': _f(post.findtext('CF_CENA_Z_DDV', default='0')),
            'popust': _f(post.findtext('RABAT_DOB', default='0')),
            'ddv': _f(post.findtext('POST_O_PDAVKA', default='0')),
            'znesek_brez': _f(post.findtext('POST_VR_BREZ_DDV', default='0')),
            'znesek_z': _f(post.findtext('POST_VR_Z_DDV', default='0')),
        }
    return postavke

def preberi_narocilnico(stream):
    postavke = {}
    vsebina = stream.read()
    if isinstance(vsebina, bytes): vsebina = vsebina.decode('utf-8', errors='replace')
    for vrstica in vsebina.splitlines():
        if not vrstica.strip(): continue
        m = re.match(r'^\s*\d+\s+([0-9A-Za-z]+)\s+(.+?)\s+(\d+)\s*(KOS|SC)\s+([\d.,]+)', vrstica, re.IGNORECASE)
        if not m: continue
        sifra = m.group(1).strip()
        postavke[sifra] = {
            'sifra': sifra, 'naziv': m.group(2).strip(),
            'kolicina': _f(m.group(3)), 'enota': m.group(4).upper(),
            'cena': _f(m.group(5)),
        }
    return postavke

# ---------------------------------------------------------------------------
# 3. PRIMERJAVA
# ---------------------------------------------------------------------------
def izracunaj_opozorila(racun_kol, prevzem_kol, racun_cena, narocilo_cena, racun_znesek, narocilo_znesek):
    opozorila = []
    
    # 1. Primerjava količin: Zaračunana količina se mora ujemati s prevzemom
    if pd.notna(racun_kol) and pd.notna(prevzem_kol):
        if abs(racun_kol - prevzem_kol) > 0.001:
            opozorila.append(f"KOLIČINA (račun {racun_kol} ≠ prevzem {prevzem_kol})")
            
    # 2. Primerjava cen: Zaračunana cena se mora ujemati s ceno iz naročilnice
    if pd.notna(racun_cena) and pd.notna(narocilo_cena) and narocilo_cena > 0:
        if round(racun_cena, 4) != round(narocilo_cena, 4):
            opozorila.append(f"CENA (račun {racun_cena:.4f} ≠ naročilo {narocilo_cena:.4f})")
            
    # 3. Preverjanje skupnega zneska
    if pd.notna(racun_znesek) and pd.notna(narocilo_znesek) and narocilo_znesek > 0:
        if round(racun_znesek, 2) != round(narocilo_znesek, 2):
            opozorila.append(f"ZNESEK (račun {racun_znesek:.2f} ≠ naročilo {narocilo_znesek:.2f})")
            
    return '; '.join(opozorila) if opozorila else 'OK'

def primerjaj(eracun, prevzemnica, narocilnica):
    rezultati = []
    for _, e in eracun.items():
        p = prevzemnica.get(e['sifra_in']) if e['sifra_in'] else None
        if not p: p = poisci_po_imenu(e['naziv'], prevzemnica)

        n = narocilnica.get(e['sifra_in']) if e['sifra_in'] else None
        if not n: n = poisci_po_imenu(e['naziv'], narocilnica)
        
        ident = e['sifra_in']
        if p and p['sifra']: ident = p['sifra']
        elif n and n['sifra']: ident = n['sifra']

        # Pretvorba količin v KOS
        kol_r, enota_r = pretvori_v_osnovno_enoto(e['kolicina'], e['enota'], e['naziv'])
        kol_p, enota_p = pretvori_v_osnovno_enoto(p['kolicina'] if p else 0.0, p['enota'] if p else '', p['naziv'] if p else '')
        kol_n, enota_n = pretvori_v_osnovno_enoto(n['kolicina'] if n else 0.0, n['enota'] if n else '', n['naziv'] if n else '')

        cena_n = n['cena'] if n else 0.0
        if n and n['enota'] in ['SC', 'ŠK']:
            m = re.search(r'(?:sc|šk)\s*=\s*(\d+)\s*kos', n['naziv'], re.IGNORECASE)
            if m: cena_n = cena_n / float(m.group(1))

        # KLJUČNA SPREMEMBA: Znesek naročila se izračuna iz PREJETE količine (kol_p), ne naročene!
        # Če prevzema ni, uporabimo 0.0, da ne vlečemo napačnih podatkov iz naročilnice
        osnova_za_znesek = kol_p if p else 0.0
        znesek_n = round(osnova_za_znesek * cena_n, 2)
        
        opozorila = izracunaj_opozorila(
            kol_r, kol_p, e['cena_brez'], cena_n, e['znesek_brez'], znesek_n
        )
        
        rezultati.append({
            'Ident': ident, 
            'Šifra dob.': e['sifra_sa'],
            'Naziv': e['naziv'],
            'Em račun': e['enota'],
            'Kol. račun': round(kol_r, 2), 
            'Em prevzem': p['enota'] if p else '',
            'Kol. prevzem': round(kol_p, 2) if p else None, 
            'Em naročilo': n['enota'] if n else '',
            'Kol. naročilo': round(kol_n, 2), 
            'Cena račun': round(e['cena_brez'], 4), 
            'Cena naročilo': round(cena_n, 4),
            'Znesek račun': round(e['znesek_brez'], 2), 
            'Znesek naročilo': znesek_n,
            'Opozorila': opozorila,
        })
    return rezultati

# ---------------------------------------------------------------------------
# 4. STREAMLIT VMESNIK
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Primerjava računa", page_icon="📑", layout="wide")
st.title("📑 Primerjava eRačuna, prevzemnice in naročilnice")

if 'zgodovina' not in st.session_state:
    st.session_state['zgodovina'] = []

with st.container(border=True):
    st.markdown("### 📂 Vnos podatkov")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**1. eRačun**")
        f_eracun = st.file_uploader("Naložite eRačun (XML, eSLOG)", type=["xml"], label_visibility="collapsed")
    with col2:
        st.markdown("**2. Prevzemnica**")
        f_prevzemnica = st.file_uploader("Naložite prevzemnico (XML ali PDF)", type=["xml", "pdf"], label_visibility="collapsed")
    with col3:
        st.markdown("**3. Naročilnica**")
        f_narocilnica = st.file_uploader("Naložite naročilnico (TXT)", type=["txt"], label_visibility="collapsed")

st.markdown("---")

if st.button("🔍 Zaženi primerjavo", type="primary", use_container_width=True):
    if not (f_eracun and f_prevzemnica and f_narocilnica):
        st.warning("Prosimo, naložite vse tri datoteke.")
        st.stop()

    try:
        with st.spinner("Berem in primerjam ..."):
            eracun = preberi_eracun(f_eracun)
            prevzemnica = preberi_prevzemnico_pdf(f_prevzemnica) if f_prevzemnica.name.lower().endswith('.pdf') else preberi_prevzemnico_xml(f_prevzemnica)
            narocilnica = preberi_narocilnico(f_narocilnica)
            rezultati = primerjaj(eracun, prevzemnica, narocilnica)
            
            st.session_state['df_rezultati'] = pd.DataFrame(rezultati)
            
            cas = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            sestevek_racun = sum([r['Znesek račun'] for r in rezultati])
            st.session_state['zgodovina'].append({
                "Čas": cas,
                "Št. postavk": len(rezultati),
                "Skupaj račun (brez DDV)": f"{sestevek_racun:.2f} €",
                "Opozorila": sum([1 for r in rezultati if r['Opozorila'] != 'OK'])
            })
    except Exception as e:
        st.error(f"Napaka pri obdelavi: {e}")
        st.exception(e)

if 'df_rezultati' in st.session_state:
    df = st.session_state['df_rezultati']
    
    st.subheader("📊 Povzetek")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Postavk na računu", len(df))
    c2.metric("Brez opozoril", (df['Opozorila'] == 'OK').sum())
    c3.metric("Z opozorili", (df['Opozorila'] != 'OK').sum())
    c4.metric("Manjkajoče postavke", df['Opozorila'].str.contains('NI V', na=False).sum())

    st.subheader("📋 Primerjalna tabela")
    st.info("💡 Namig: Kliknite na celico v stolpcu **'Cena naročilo'**, da ročno popravite ceno. Če se bo cena ujemala z računom, bo opozorilo izginilo.")
    
    def obarvaj_vrstico(vrstica):
        if vrstica['Opozorila'] == 'OK':
            return ['background-color: #d4edda'] * len(vrstica)
        return ['background-color: #f8d7da'] * len(vrstica)

    edited_df = st.data_editor(
        df,
        column_config={
            "Ident": st.column_config.TextColumn("Ident", disabled=True),
            "Šifra dob.": st.column_config.TextColumn("Šifra dob.", disabled=True),
            "Naziv": st.column_config.TextColumn("Naziv", width="large", disabled=True),
            "Em račun": st.column_config.TextColumn("Em račun", disabled=True),
            "Kol. račun": st.column_config.NumberColumn("Kol. račun", format="%.2f", disabled=True),
            "Em prevzem": st.column_config.TextColumn("Em prevzem", disabled=True),
            "Kol. prevzem": st.column_config.NumberColumn("Kol. prevzem", format="%.2f", disabled=True),
            "Em naročilo": st.column_config.TextColumn("Em naročilo", disabled=True),
            "Kol. naročilo": st.column_config.NumberColumn("Kol. naročilo", format="%.2f", disabled=True), 
            "Cena račun": st.column_config.NumberColumn("Cena račun", format="%.4f", disabled=True),
            "Cena naročilo": st.column_config.NumberColumn("Cena naročilo", format="%.4f", step=0.0001), 
            "Znesek račun": st.column_config.NumberColumn("Znesek račun", format="%.2f", disabled=True),
            "Znesek naročilo": st.column_config.NumberColumn("Znesek naročilo", format="%.2f", disabled=True),
            "Opozorila": st.column_config.TextColumn("Opozorila", width="medium", disabled=True),
        },
        hide_index=True,
        use_container_width=True,
        key="editor"
    )

    if not edited_df.equals(df):
        for idx, row in edited_df.iterrows():
            # Preračunamo znesek naročila iz PREJETE količine
            if pd.notna(row['Kol. prevzem']) and pd.notna(row['Cena naročilo']):
                edited_df.at[idx, 'Znesek naročilo'] = round(row['Kol. prevzem'] * row['Cena naročilo'], 2)
            
            edited_df.at[idx, 'Opozorila'] = izracunaj_opozorila(
                row['Kol. račun'], row['Kol. prevzem'], 
                row['Cena račun'], row['Cena naročilo'], 
                row['Znesek račun'], edited_df.at[idx, 'Znesek naročilo']
            )

        st.session_state['df_rezultati'] = edited_df
        st.rerun()

    st.markdown("##### Predogled barvnega stanja (po morebitnih popravkih):")
    # Odstranimo stolpce z enotami iz spodnjega prikaza za večjo preglednost
    df_predogled = edited_df.drop(columns=['Em račun', 'Em prevzem', 'Em naročilo', 'Šifra dob.'], errors='ignore')
    st.dataframe(
        df_predogled.style.apply(obarvaj_vrstico, axis=1).format(precision=2, na_rep="-"),
        use_container_width=True,
        hide_index=True
    )

    skupaj_racun = edited_df['Znesek račun'].sum()
    skupaj_narocilo = edited_df['Znesek naročilo'].sum()
    
    st.markdown("### 💰 Skupni seštevki")
    col_s1, col_s2 = st.columns(2)
    col_s1.metric("Skupaj račun (brez DDV)", f"{skupaj_racun:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'))
    col_s2.metric("Skupaj naročilo (brez DDV)", f"{skupaj_narocilo:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'))

    df_export = edited_df.drop(columns=['Em račun', 'Em prevzem', 'Em naročilo', 'Šifra dob.'], errors='ignore').copy()
    df_export.columns = ['Ident', 'Naziv', 'Kol. račun', 'Kol. prevzem', 'Kol. naročilo', 
                         'Cena račun (EUR)', 'Cena naročilo (EUR)', 'Znesek račun (EUR)', 
                         'Znesek naročilo (EUR)', 'Opozorila']
    
    csv = df_export.to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig').encode('utf-8-sig')
    st.download_button(
        label="⬇️ Prenesi rezultat (CSV)",
        data=csv,
        file_name="primerjava_racuna.csv",
        mime="text/csv",
        use_container_width=True
    )

st.markdown("---")
st.subheader("🕒 Zgodovina primerjav")
if st.session_state['zgodovina']:
    st.dataframe(pd.DataFrame(st.session_state['zgodovina']), use_container_width=True, hide_index=True)
