# app.py
import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import re
import io
import pdfplumber

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
    """Poenostavi naziv za boljše ujemanje (odstrani ločila, naredi male črke)."""
    if not n: return ""
    n = n.lower()
    n = re.sub(r'[^a-z0-9]+', ' ', n)
    return ' '.join(n.split())

def poisci_po_imenu(ciljni_naziv, slovar_postavk):
    """Poišče postavko v slovarju, ki se najbolje ujema z ciljnim nazivom."""
    if not ciljni_naziv: return None
    norm_cilj = normaliziraj_naziv(ciljni_naziv)
    
    # 1. Poskusimo najprej z direktnim ujemanjem normaliziranega imena
    for k, v in slovar_postavk.items():
        if normaliziraj_naziv(v['naziv']) == norm_cilj:
            return v
            
    # 2. Če direktnega ni, poskusimo po ključnih besedah (npr. samo prva beseda)
    ciljne_besede = set(norm_cilj.split())
    najboljse_ujemanje = None
    najvec_besed = 0
    
    for k, v in slovar_postavk.items():
        norm_v = normaliziraj_naziv(v['naziv'])
        v_besede = set(norm_v.split())
        skupne = ciljne_besede.intersection(v_besede)
        # Če se ujema vsaj ena ključna beseda (dolžine vsaj 4 črke)
        kljucne_ujemajoce = [b for b in skupne if len(b) >= 4]
        if len(kljucne_ujemajoce) > najvec_besed:
            najvec_besed = len(kljucne_ujemajoce)
            najboljse_ujemanje = v
            
    return najboljse_ujemanje if najvec_besed >= 1 else None

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
        qty = sg26.find('eslog:S_QTY/eslog:C_C186', ns)
        if qty is not None:
            kolicina = _f(qty.findtext('eslog:D_6060', default='0', namespaces=ns))
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
            'kolicina': kolicina, 'cena_brez': cena_brez, 'cena_z': cena_z,
            'popust': popust, 'ddv': ddv, 'znesek_brez': znesek_brez, 'znesek_z': znesek_z,
        }
    return postavke

def preberi_prevzemnico_pdf(stream):
    postavke = {}
    with pdfplumber.open(stream) as pdf:
        vse_besedilo = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                vse_besedilo += text + "\n"
    
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
            
            if i + 1 < len(vrstice):
                naslednja = vrstice[i+1]
                m2 = re.search(r'^\d+\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', naslednja)
                if m2:
                    cena_brez = _f(m2.group(1))
                    ddv = _f(m2.group(2))
                    popust = _f(m2.group(3))
                else:
                    cena_brez, ddv, popust = 0.0, 0.0, 0.0
            else:
                cena_brez, ddv, popust = 0.0, 0.0, 0.0
                
            postavke[sifra] = {
                'sifra': sifra, 'naziv': naziv,
                'kolicina': kolicina, 'cena_brez': cena_brez, 'cena_z': cena,
                'popust': popust, 'ddv': ddv, 'znesek_brez': vrednost, 'znesek_z': vrednost,
            }
            i += 1
        i += 1
    return postavke

def preberi_prevzemnico_xml(stream):
    vsebina = stream.read()
    if isinstance(vsebina, bytes):
        vsebina = vsebina.decode('utf-8', errors='replace')
    vsebina_ociscena = vsebina.replace('$', '_')
    stream_ociscen = io.BytesIO(vsebina_ociscena.encode('utf-8'))
    tree = ET.parse(stream_ociscen)
    root = tree.getroot()
    postavke = {}
    for post in root.findall('.//CG_G_POST'):
        sifra = post.findtext('ART_S_ARTIKLA', default='').strip()
        postavke[sifra] = {
            'sifra': sifra, 'naziv': post.findtext('ART_N_ARTIKLA', default='').strip(),
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
    if isinstance(vsebina, bytes):
        vsebina = vsebina.decode('utf-8', errors='replace')
    for vrstica in vsebina.splitlines():
        if not vrstica.strip(): continue
        m = re.match(r'^\s*\d+\s+([0-9A-Za-z]+)\s+(.+?)\s+(\d+(?:[.,]\d+)?)\s*(KOS|SC)\s+(\d+(?:[.,]\d+)?)', vrstica)
        if not m: continue
        sifra = m.group(1).strip()
        postavke[sifra] = {
            'sifra': sifra, 'naziv': m.group(2).strip(),
            'kolicina': _f(m.group(3)), 'cena': _f(m.group(5)),
        }
    return postavke

# ---------------------------------------------------------------------------
# 3. PRIMERJAVA
# ---------------------------------------------------------------------------
def primerjaj(eracun, prevzemnica, narocilnica):
    rezultati = []
    
    for _, e in eracun.items():
        # Povezovanje s prevzemnico
        p = None
        if e['sifra_in'] and e['sifra_in'] in prevzemnica: 
            p = prevzemnica[e['sifra_in']]
        else:
            # Če šifra ne dela, poskusimo po imenu
            p = poisci_po_imenu(e['naziv'], prevzemnica)

        # Povezovanje z naročilnico
        n = None
        if e['sifra_in'] and e['sifra_in'] in narocilnica: 
            n = narocilnica[e['sifra_in']]
        else:
            n = poisci_po_imenu(e['naziv'], narocilnica)
        
        opozorila = []
        
        # Primerjava s prevzemnico
        if p is None: 
            opozorila.append('NI V PREVZEMNICI')
        else:
            if abs(e['kolicina'] - p['kolicina']) > 0.001: 
                opozorila.append(f"KOLIČINA (račun {e['kolicina']} ≠ prevzem {p['kolicina']})")
            if abs(e['cena_brez'] - p['cena_brez']) > 0.01: 
                opozorila.append(f"CENA BREZ DDV (račun {e['cena_brez']:.4f} ≠ prevzem {p['cena_brez']:.4f})")
            if abs(e['znesek_brez'] - p['znesek_brez']) > 0.01: 
                opozorila.append(f"ZNESEK (račun {e['znesek_brez']:.2f} ≠ prevzem {p['znesek_brez']:.2f})")
        
        # Primerjava z naročilnico
        if n is None: 
            opozorila.append('NI V NAROČILNICI')
        else:
            if abs(e['kolicina'] - n['kolicina']) > 0.001: 
                opozorila.append(f"KOLIČINA (račun {e['kolicina']} ≠ naročilo {n['kolicina']})")
            if abs(e['cena_brez'] - n['cena']) > 0.01: 
                opozorila.append(f"CENA (račun {e['cena_brez']:.4f} ≠ naročilo {n['cena']:.4f})")
        
        rezultati.append({
            'Šifra (interna)': e['sifra_in'], 'Šifra (dobavitelj)': e['sifra_sa'], 'Naziv': e['naziv'],
            'Kol. račun': e['kolicina'], 'Kol. prevzem': p['kolicina'] if p else None, 'Kol. naročilo': n['kolicina'] if n else None,
            'Cena račun': round(e['cena_brez'], 4), 'Cena prevzem': round(p['cena_brez'], 4) if p else None, 'Cena naročilo': round(n['cena'], 4) if n else None,
            'Znesek račun': round(e['znesek_brez'], 2), 'Znesek prevzem': round(p['znesek_brez'], 2) if p else None,
            'Opozorila': '; '.join(opozorila) if opozorila else 'OK',
        })
    return rezultati

# ---------------------------------------------------------------------------
# 4. STREAMLIT VMESNIK
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Primerjava računa", page_icon="📑", layout="wide")
st.title("📑 Primerjava eRačuna, prevzemnice in naročilnice")
st.caption("Naložite tri datoteke – aplikacija samodejno poveže postavke in prikaže morebitna odstopanja.")

col1, col2, col3 = st.columns(3)
with col1: f_eracun = st.file_uploader("1) eRačun (XML, eSLOG)", type=["xml"])
with col2: f_prevzemnica = st.file_uploader("2) Prevzemnica (XML ali PDF)", type=["xml", "pdf"])
with col3: f_narocilnica = st.file_uploader("3) Naročilnica (TXT)", type=["txt"])

if st.button("🔍 Primerjaj", type="primary", use_container_width=True):
    if not (f_eracun and f_prevzemnica and f_narocilnica):
        st.warning("Prosimo, naložite vse tri datoteke.")
        st.stop()

    try:
        with st.spinner("Berem in primerjam ..."):
            eracun = preberi_eracun(f_eracun)
            
            if f_prevzemnica.name.lower().endswith('.pdf'):
                prevzemnica = preberi_prevzemnico_pdf(f_prevzemnica)
            else:
                prevzemnica = preberi_prevzemnico_xml(f_prevzemnica)
            
            narocilnica = preberi_narocilnico(f_narocilnica)
            rezultati = primerjaj(eracun, prevzemnica, narocilnica)

        df = pd.DataFrame(rezultati)
        st.subheader("📊 Povzetek")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Postavk na računu", len(df))
        c2.metric("Brez opozoril", (df['Opozorila'] == 'OK').sum())
        c3.metric("Z opozorili", (df['Opozorila'] != 'OK').sum())
        c4.metric("Manjkajoče postavke", df['Opozorila'].str.contains('NI V', na=False).sum())

        def obarvaj(vrstica):
            if vrstica['Opozorila'] == 'OK':
                return ['background-color: #d4edda'] * len(vrstica)
            return ['background-color: #f8d7da'] * len(vrstica)

        st.subheader("📋 Primerjalna tabela")
        st.dataframe(df.style.apply(obarvaj, axis=1), use_container_width=True, hide_index=True)

        csv = df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button("⬇️ Prenesi rezultat (CSV)", data=csv, file_name="primerjava_racuna.csv", mime="text/csv", use_container_width=True)

    except Exception as e:
        st.error(f"Napaka pri obdelavi: {e}")
        st.exception(e)
