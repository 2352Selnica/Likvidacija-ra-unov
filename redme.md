# Primerjava eRačuna, prevzemnice in naročilnice

Streamlit aplikacija za hitro likvidacijo računov.

## Namestitev

```bash
git clone https://github.com/<vaš-uporabnik>/racun-primerjava.git
cd racun-primerjava
pip install -r requirements.txt
```

## Zagon

```bash
streamlit run app.py
```

Aplikacija se odpre na `http://localhost:8501`.

## Uporaba

1. Naložite **eRačun** (XML, eSLOG 2.0).
2. Naložite **prevzemnico** (XML iz informacijskega sistema).
3. Naložite **naročilnico** (TXT).
4. Kliknite **Primerjaj**.

Rezultat je mogoče prenesti kot CSV.

## Struktura

- `app.py` – Streamlit vmesnik
- `parser.py` – branje in primerjava datotek
- `samples/` – primeri datotek za testiranje

## Opombe

- Podprt je eSLOG 2.0. Za druge formate je treba prilagoditi `preberi_eracun`.
- Naročilnica mora imeti stolpce ločene s presledki v formatu, kot ga izvaža vaš IS.
