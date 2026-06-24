import streamlit as st
import geopandas as gpd
import folium
from folium import plugins
from streamlit_folium import st_folium
import os
import requests
from supabase import create_client, Client

# ==========================================
# CONFIGURAZIONE PAGINA E STILI
# ==========================================
st.set_page_config(page_title="Pianificazione VdA", layout="wide")

# Forza la visualizzazione corretta e fluida degli elementi cartografici
st.markdown("""
    <style>
        iframe { opacity: 1 !important; filter: none !important; transition: none !important; }
        [data-testid="stElementContainer"] { opacity: 1 !important; }
    </style>
""", unsafe_allow_html=True)

st.title("Esplorazione e Pianificazione VdA 🏔️")

# ==========================================
# CONNESSIONE A SUPABASE CLOUD DB
# ==========================================
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Errore di connessione a Supabase: Verifica i Secrets. Dettaglio: {e}")
    st.stop()

# ==========================================
# FUNZIONI DI SERVIZIO ED ESPORTAZIONE
# ==========================================
def fetch_profili_esistenti():
    try:
        response = supabase.table("utenti_credenziali").select("utente").execute()
        return sorted([row['utente'] for row in response.data if row.get('utente')])
    except:
        return []

def verifica_password(utente, password_inserita):
    try:
        response = supabase.table("utenti_credenziali").select("password").eq("utente", utente).execute()
        if response.data: return response.data[0]["password"] == password_inserita
        return False
    except: return False

def registra_nuovo_utente(utente, password):
    try:
        supabase.table("utenti_credenziali").insert({"utente": utente, "password": password}).execute()
        return True
    except: return False

def fetch_stati_dal_db(utente):
    try:
        response = supabase.table("stato_visite").select("*").eq("utente", utente).execute()
        return {row['nome_struttura']: row['stato'] for row in response.data}
    except: return {}

def get_valore_colonna(row, nome_colonna_base, default="N/D"):
    for col in row.index:
        if col.lower() == nome_colonna_base.lower():
            valore = row[col]
            return valore if (valore is not None and str(valore).strip() not in ["", "None", "nan"]) else default
    return default

def colonne_reali(df, colonne_cercate):
    df_cols_lower = {c.lower(): c for c in df.columns}
    return [df_cols_lower[c.lower()] for c in colonne_cercate if c.lower() in df_cols_lower]

def get_elevation_api(lat, lon):
    try:
        r = requests.get(f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}")
        if r.status_code == 200: return r.json()['elevation'][0]
    except: pass
    return 0

def calcola_percorso_osrm_multi(punti_coords):
    stringa_locs = ";".join([f"{lon},{lat}" for lat, lon in punti_coords])
    url = f"http://router.project-osrm.org/route/v1/foot/{stringa_locs}?overview=full&geometries=geojson"
    try:
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            if data['code'] == 'Ok': return data['routes'][0]
    except: pass
    return None

def genera_gpx(coordinate_geometria, nome_itinerario="Itinerario VdA"):
    gpx = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="VdA_Explorer" xmlns="http://www.topografix.com/GPX/1/1">',
        '  <trk>',
        f'    <name>{nome_itinerario}</name>',
        '    <trkseg>'
    ]
    for lon, lat in coordinate_geometria:
        gpx.append(f'      <trkpt lat="{lat}" lon="{lon}"></trkpt>')
    gpx.extend(['    </trkseg>', '  </trk>', '</gpx>'])
    return "\n".join(gpx)

def genera_google_maps_url(punti_coords):
    if len(punti_coords) < 2: return "#"
    origine = f"{punti_coords[0][0]},{punti_coords[0][1]}"
    destinazione = f"{punti_coords[-1][0]},{punti_coords[-1][1]}"
    url = f"https://www.google.com/maps/dir/?api=1&origin={origine}&destination={destinazione}&travelmode=walking"
    if len(punti_coords) > 2:
        tappe = "%7C".join([f"{lat},{lon}" for lat, lon in punti_coords[1:-1]])
        url += f"&waypoints={tappe}"
    return url

# ==========================================
# CALLBACKS DI PROFILO
# ==========================================
def handle_profile_change():
    scelta = st.session_state.scelta_profilo_widget
    st.session_state.autenticato = False  
    if scelta == "➕ Crea Nuovo Profilo...":
        st.session_state.profilo_attivo = None
        st.session_state.creazione_in_corso = True
    elif scelta == "-- Seleziona un profilo --":
        st.session_state.profilo_attivo = None
        st.session_state.creazione_in_corso = False
    else:
        st.session_state.profilo_attivo = scelta
        st.session_state.creazione_in_corso = False
        if "dati_caricati" in st.session_state: del st.session_state["dati_caricati"]

def autosave_quick_edit():
    nuovo_stato = st.session_state.quick_edit_selectbox
    struttura = st.session_state.struttura_attiva
    profilo = st.session_state.profilo_attivo
    for df_name in ["bivacchi", "rifugi"]:
        df = st.session_state[df_name]
        col_nome = [c for c in df.columns if c.lower() == "name_it"][0]
        idx = df[df[col_nome] == struttura].index
        if not idx.empty:
            st.session_state[df_name].loc[idx, "Stato_Visita"] = nuovo_stato
            break
    try:
        supabase.table("stato_visite").upsert({"nome_struttura": struttura, "stato": nuovo_stato, "utente": profilo}).execute()
        st.toast(f"☁️ Autosave Cloud: {struttura} → {nuovo_stato}", icon="✅")
    except Exception as e:
        st.error(f"Errore di sincronizzazione Cloud: {e}")

def autosave_tabella_bivacchi():
    edits = st.session_state.editor_b.get("edited_rows", {})
    if edits:
        df = st.session_state.bivacchi
        col_nome = [c for c in df.columns if c.lower() == "name_it"][0]
        records_upsert = []
        for row_idx_str, changes in edits.items():
            if "Stato_Visita" in changes:
                row_idx = int(row_idx_str)
                nuovo_stato = changes["Stato_Visita"]
                nome_struttura = df.loc[row_idx, col_nome]
                st.session_state.bivacchi.loc[row_idx, "Stato_Visita"] = nuovo_stato
                records_upsert.append({"nome_struttura": nome_struttura, "stato": nuovo_stato, "utente": st.session_state.profilo_attivo})
        if records_upsert: supabase.table("stato_visite").upsert(records_upsert).execute()

def autosave_tabella_rifugi():
    edits = st.session_state.editor_r.get("edited_rows", {})
    if edits:
        df = st.session_state.rifugi
        col_nome = [c for c in df.columns if c.lower() == "name_it"][0]
        records_upsert = []
        for row_idx_str, changes in edits.items():
            if "Stato_Visita" in changes:
                row_idx = int(row_idx_str)
                nuovo_stato = changes["Stato_Visita"]
                nome_struttura = df.loc[row_idx, col_nome]
                st.session_state.rifugi.loc[row_idx, "Stato_Visita"] = nuovo_stato
                records_upsert.append({"nome_struttura": nome_struttura, "stato": nuovo_stato, "utente": st.session_state.profilo_attivo})
        if records_upsert: supabase.table("stato_visite").upsert(records_upsert).execute()

# ==========================================
# DISPOSIZIONE STRUTTURA SIDEBAR
# ==========================================
if os.path.exists("immagine_app.jpeg"):
    st.sidebar.image("immagine_app.jpeg", use_container_width=True)

st.sidebar.markdown("""
<div style="background-color: #f1f3f5; padding: 12px; border-radius: 6px; border-left: 4px solid #0055ff; margin-bottom: 15px; font-family: sans-serif;">
    <h5 style="margin-top: 0; color: #111; font-size: 14px;">🗺️ Come creare un itinerario:</h5>
    <ol style="margin: 0; padding-left: 18px; font-size: 12px; color: #444; line-height: 1.4;">
        <li>Fai <b>clic sulla mappa</b> o su un <b>rifugio/bivacco</b>.</li>
        <li>Usa i pulsanti sotto la mappa per impostarlo come <b>Partenza</b>, <b>Tappa</b> o <b>Arrivo</b>.</li>
        <li>I punti scelti appariranno evidenziati in grande sulla mappa.</li>
        <li>Usa il pannello in alto per calcolare i dati e scaricare la traccia.</li>
    </ol>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("### 👤 Gestione Profili")
lista_profili = fetch_profili_esistenti()
opzioni_menu = ["-- Seleziona un profilo --"] + lista_profili + ["➕ Crea Nuovo Profilo..."]

if "autenticato" not in st.session_state: st.session_state.autenticato = False
if "itinerario_struttura" not in st.session_state:
    st.session_state.itinerario_struttura = {"partenza": None, "tappe": [], "arrivo": None}

index_default = 0
if "profilo_attivo" in st.session_state and st.session_state.profilo_attivo in lista_profili:
    index_default = opzioni_menu.index(st.session_state.profilo_attivo)
elif st.session_state.get("creazione_in_corso", False):
    index_default = opzioni_menu.index("➕ Crea Nuovo Profilo...")

st.sidebar.selectbox("Scegli un profilo esistente:", options=opzioni_menu, index=index_default, key="scelta_profilo_widget", on_change=handle_profile_change)

if st.session_state.get("profilo_attivo") and not st.session_state.autenticato:
    password_input = st.sidebar.text_input("Inserisci la password del profilo:", type="password", key="pass_field")
    if password_input:
        if verifica_password(st.session_state.profilo_attivo, password_input):
            st.session_state.autenticato = True
            st.toast("🔓 Accesso eseguito con successo!", icon="🔑")
            st.rerun()
        else: st.sidebar.error("❌ Password errata!")

if st.session_state.get("creazione_in_corso", False):
    nome_input = st.sidebar.text_input("Digita il nome del nuovo utente:", placeholder="Nome...")
    password_nuova = st.sidebar.text_input("Imposta una password per il profilo:", type="password", placeholder="Password...")
    if nome_input.strip() and password_nuova.strip():
        profilo_formattato = nome_input.strip().title()
        if st.sidebar.button("Inizializza Nuovo Profilo"):
            if profilo_formattato in lista_profili: st.sidebar.error("❌ Questo profilo esiste già!")
            else:
                if registra_nuovo_utente(profilo_formattato, password_nuova.strip()):
                    st.session_state.profilo_attivo = profilo_formattato
                    st.session_state.autenticato = True
                    st.session_state.creazione_in_corso = False
                    if "dati_caricati" in st.session_state: del st.session_state["dati_caricati"]
                    st.rerun()

if "profilo_attivo" in st.session_state and st.session_state.profilo_attivo in lista_profili and st.session_state.autenticato:
    st.sidebar.markdown("<br>", unsafe_allow_html=True)
    with st.sidebar.expander("⚠️ Zona Pericolo"):
        st.warning(f"Attenzione: stai per eliminare tutti i salvataggi e le credenziali di **{st.session_state.profilo_attivo}**.")
        spunta_conferma = st.checkbox("Sì, voglio eliminare definitivamente i dati dal cloud", value=False, key="check_conferma_eliminazione")
        if spunta_conferma:
            if st.button(f"🔥 Elimina Profilo {st.session_state.profilo_attivo}", type="secondary", use_container_width=True):
                try:
                    supabase.table("stato_visite").delete().eq("utente", st.session_state.profilo_attivo).execute()
                    supabase.table("utenti_credenziali").delete().eq("utente", st.session_state.profilo_attivo).execute()
                    del st.session_state["profilo_attivo"]
                    st.session_state.autenticato = False
                    if "dati_caricati" in st.session_state: del st.session_state["dati_caricati"]
                    st.rerun()
                except Exception as e: st.error(f"Errore di eliminazione: {e}")

if not st.session_state.get("profilo_attivo") or not st.session_state.autenticato:
    st.sidebar.markdown("<br><br>", unsafe_allow_html=True)
    st.sidebar.markdown("---")
    st.sidebar.markdown("""
    <div style="font-size: 13px; color: #555; background-color: #f8f9fa; padding: 10px; border-radius: 5px; border-left: 4px solid #333;">
        <b>App Rifugi & Bivacchi VdA</b><br>
        Versione: 3.0 beta<br>
        Autore: Nori Fabrizio
    </div>
    """, unsafe_allow_html=True)
    st.info("👈 Seleziona un profilo e immetti la password corretta nel menu laterale per sbloccare i dati cartografici.")
    st.stop()

# ==========================================
# INIZIALIZZAZIONE STRUTTURA DATI GEOGRAFICI
# ==========================================
if "dati_caricati" not in st.session_state:
    stati_cloud = fetch_stati_dal_db(st.session_state.profilo_attivo)
    if os.path.exists("bivacchi_vda.geojson") and os.path.exists("rifugi_vda.geojson"):
        gdf_b = gpd.read_file("bivacchi_vda.geojson")
        gdf_r = gpd.read_file("rifugi_vda.geojson")
        gdf_b["Stato_Visita"] = [stati_cloud.get(get_valore_colonna(r, "Name_it"), "Non visitato") for _, r in gdf_b.iterrows()]
        gdf_r["Stato_Visita"] = [stati_cloud.get(get_valore_colonna(r, "Name_it"), "Non visitato") for _, r in gdf_r.iterrows()]
        st.session_state.bivacchi = gdf_b
        st.session_state.rifugi = gdf_r
        if os.path.exists("sentieri_vda_ottimizzati.geojson"):
            st.session_state.sentieri = gpd.read_file("sentieri_vda_ottimizzati.geojson")
        else: st.session_state.sentieri = None
        st.session_state.dati_caricati = True
    else:
        st.error("File cartografici GeoJSON non individuati nel repository sorgente!")
        st.stop()

dizionario_strutture = {}
for df in [st.session_state.bivacchi, st.session_state.rifugi]:
    for _, row in df.iterrows():
        nome = get_valore_colonna(row, "Name_it", "")
        if nome: dizionario_strutture[nome] = (row.geometry.y, row.geometry.x, float(get_valore_colonna(row, "ele", 0)))

stati_disponibili = ["Non visitato", "Pianificato", "Visitato"]
stati_selezionati = st.sidebar.multiselect("Filtra Mappa per Stato:", options=stati_disponibili, default=stati_disponibili)

mappa_bivacchi = st.session_state.bivacchi[st.session_state.bivacchi['Stato_Visita'].isin(stati_selezionati)]
mappa_rifugi = st.session_state.rifugi[st.session_state.rifugi['Stato_Visita'].isin(stati_selezionati)]

# Sezione info in basso a sinistra della barra laterale per utenti loggati
st.sidebar.markdown("<br><br>", unsafe_allow_html=True)
st.sidebar.markdown("---")
st.sidebar.markdown("""
<div style="font-size: 13px; color: #555; background-color: #f8f9fa; padding: 10px; border-radius: 5px; border-left: 4px solid #333;">
    <b>App Rifugi & Bivacchi VdA</b><br>
    Versione: 3.0 beta<br>
    Autore: Nori Fabrizio
</div>
""", unsafe_allow_html=True)

# ==========================================
# PANNELLO ITINERARIO SEMPRE VISIBILE
# ==========================================
with st.container(border=True):
    st.subheader("🧭 Pianificatore Itinerario")
    
    txt_partenza = st.session_state.itinerario_struttura["partenza"][0] if st.session_state.itinerario_struttura["partenza"] else "Non impostata"
    txt_tappe = " ➔ ".join([t[0] for t in st.session_state.itinerario_struttura["tappe"]]) if st.session_state.itinerario_struttura["tappe"] else "Nessuna"
    txt_arrivo = st.session_state.itinerario_struttura["arrivo"][0] if st.session_state.itinerario_struttura["arrivo"] else "Non impostato"
    
    st.markdown(f"**Partenza:** `{txt_partenza}` | **Tappe Intermedie:** `{txt_tappe}` | **Arrivo:** `{txt_arrivo}`")
    
    punti_itinerario_completo = []
    if st.session_state.itinerario_struttura["partenza"]: punti_itinerario_completo.append(st.session_state.itinerario_struttura["partenza"])
    punti_itinerario_completo.extend(st.session_state.itinerario_struttura["tappe"])
    if st.session_state.itinerario_struttura["arrivo"]: punti_itinerario_completo.append(st.session_state.itinerario_struttura["arrivo"])
    
    col_calc, col_reset = st.columns(2)
    with col_calc:
        if st.button("🔄 Calcola e Genera Tracciato Lineare", type="primary", use_container_width=True):
            if len(punti_itinerario_completo) >= 2:
                coords_solo = [(p[1], p[2]) for p in punti_itinerario_completo]
                with st.spinner("Interrogazione rete OSRM..."):
                    rotta = calcola_percorso_osrm_multi(coords_solo)
                    if rotta:
                        st.session_state.itinerario_attivo = rotta
                        distanza_km = round(rotta['distance'] / 1000, 2)
                        quota_p = punti_itinerario_completo[0][3]
                        quota_a = punti_itinerario_completo[-1][3]
                        dislivello_netto = round(quota_a - quota_p)
                        st.session_state.itinerario_metadati = {"dist": distanza_km, "disl": dislivello_netto}
                    else: st.error("Impossibile connettere i punti scelti tramite sentiero.")
            else: st.warning("Inserisci almeno Partenza e Arrivo cliccando sulla mappa per calcolare.")
    with col_reset:
        if st.button("🗑️ Svuota Tutto l'Itinerario", use_container_width=True):
            st.session_state.itinerario_struttura = {"partenza": None, "tappe": [], "arrivo": None}
            if "itinerario_attivo" in st.session_state: del st.session_state["itinerario_attivo"]
            if "itinerario_metadati" in st.session_state: del st.session_state["itinerario_metadati"]
            st.rerun()

    if st.session_state.get("itinerario_attivo") and st.session_state.get("itinerario_metadati"):
        meta = st.session_state.itinerario_metadati
        st.info(f"📊 **Statistiche dell'Itinerario:** Distanza Totale: **{meta['dist']} km** | Dislivello Netto: **{meta['disl']} metri**")
        
        coords_itinerario = st.session_state.itinerario_attivo['geometry']['coordinates']
        gpx_data = genera_gpx(coords_itinerario)
        coords_maps = [(p[1], p[2]) for p in punti_itinerario_completo]
        maps_url = genera_google_maps_url(coords_maps)
        
        st.markdown("#### 📥 Esporta la traccia:")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button(label="📥 Scarica file .GPX (Garmin/Earth)", data=gpx_data, file_name="itinerario_vda.gpx", mime="application/gpx+xml", use_container_width=True)
        with c2:
            st.link_button("🗺️ Apri in Google Maps", url=maps_url, use_container_width=True)
        with c3:
            st.caption("ℹ *Il file .GPX scaricato può essere importato direttamente anche in Google Earth Pro per lo studio del terreno 3D.*")

# ==========================================
# GENERAZIONE INTERFACCIA MAPPA (FOLIUM)
# ==========================================
m = folium.Map(location=[45.73, 7.32], zoom_start=9, tiles=None)
folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Satellite (Esri)', overlay=False).add_to(m)
folium.TileLayer('OpenStreetMap', name='Topografica (OSM)', overlay=False).add_to(m)
plugins.Fullscreen(position='topleft', force_separate_button=True).add_to(m)

def get_marker_color(stato):
    if stato == "Visitato": return "#28a745"
    if stato == "Pianificato": return "#ffc107"
    return "#dc3545"

def crea_popup(row):
    lat, lon = row.geometry.y, row.geometry.x
    meteo_url = f"https://www.meteoblue.com/it/tempo/settimana/{round(lat, 4)}N{round(lon, 4)}E"
    nome = get_valore_colonna(row, "Name_it", "Struttura")
    quota = get_valore_colonna(row, "ele", "N/D")
    accesso = get_valore_colonna(row, "Accesso", "N/D")
    stato = get_valore_colonna(row, "Stato_Visita", "Non visitato")
    link = get_valore_colonna(row, "link1_href", "#")
    desc = get_valore_colonna(row, "Desc_IT", "Nessuna descrizione disponibile.")
    
    return f"""
    <div style="font-family: sans-serif; font-size: 14px; min-width: 320px; color: #333;">
        <h3 style="margin: 0 0 8px 0; color: #111;">{nome}</h3>
        <p style="margin: 4px 0;"><b>Quota:</b> {quota} m</p>
        <p style="margin: 4px 0;"><b>Accesso:</b> {accesso}</p>
        <p style="margin: 4px 0;"><b>Stato:</b> <span style="color:{get_marker_color(stato)}; font-weight:bold;">{stato.upper()}</span></p>
        <div style="margin: 12px 0;">
            <a href="{link}" target="_blank" style="text-decoration: none; color: white; background-color: #0066cc; padding: 6px 12px; border-radius: 4px; font-size: 12px; margin-right: 5px; font-weight: bold; display: inline-block;">🔗 Sito Web</a>
            <a href="{meteo_url}" target="_blank" style="text-decoration: none; color: white; background-color: #ff6600; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; display: inline-block;">☀️ Meteo</a>
        </div>
        <hr style="border: 0; border-bottom: 1px solid #ccc; margin: 10px 0;">
        <p style="margin: 0; font-size: 12px; line-height: 1.5; color: #444;"><b>Descrizione:</b><br>{desc}</p>
    </div>
    """

if st.session_state.get("sentieri") is not None:
    fg_sentieri = folium.FeatureGroup(name="🥾 Rete Sentieristica", show=True)
    def stile_sentiero(feature):
        fclass = feature['properties'].get('fclass', 'path')
        if fclass == 'footway': colore = '#2ca02c'
        elif fclass == 'track': colore = '#8c564b'
        else: colore = '#e65c00'
        return {'color': colore, 'weight': 2.2, 'dashArray': '6, 6', 'opacity': 0.85}

    folium.GeoJson(st.session_state.sentieri, style_function=stile_sentiero, highlight_function=lambda x: {'color': '#ff3300', 'weight': 4.0}, tooltip=folium.GeoJsonTooltip(fields=['name', 'ref'], aliases=['Nome:', 'N°:']) if 'name' in st.session_state.sentieri.columns else None).add_to(fg_sentieri)
    fg_sentieri.add_to(m)

if st.session_state.get("itinerario_attivo"):
    fg_itinerario = folium.FeatureGroup(name="📍 Traccia Itinerario", show=True)
    folium.GeoJson(st.session_state.itinerario_attivo['geometry'], style_function=lambda x: {'color': '#0055ff', 'weight': 5, 'opacity': 0.9}).add_to(fg_itinerario)
    fg_itinerario.add_to(m)

# Indicatori di rotta in formato GIGANTE con DivIcon (45x45 px)
p_node = st.session_state.itinerario_struttura.get("partenza")
if p_node:
    icon_html_p = "<div style='background-color: #0055ff; width: 45px; height: 45px; border-radius: 50%; border: 3px solid white; display: flex; align-items: center; justify-content: center; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-size: 22px; color: white;'>🛫</div>"
    folium.Marker(location=[p_node[1], p_node[2]], tooltip=f"PARTENZA: {p_node[0]}", icon=folium.DivIcon(html=icon_html_p, icon_size=(45, 45), icon_anchor=(22, 22))).add_to(m)

for t_node in st.session_state.itinerario_struttura.get("tappe", []):
    icon_html_t = "<div style='background-color: #ff8800; width: 40px; height: 40px; border-radius: 50%; border: 3px solid white; display: flex; align-items: center; justify-content: center; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-size: 18px; color: white;'>🛑</div>"
    folium.Marker(location=[t_node[1], t_node[2]], tooltip=f"TAPPA: {t_node[0]}", icon=folium.DivIcon(html=icon_html_t, icon_size=(40, 40), icon_anchor=(20, 20))).add_to(m)

a_node = st.session_state.itinerario_struttura.get("arrivo")
if a_node:
    icon_html_a = "<div style='background-color: #ff0000; width: 45px; height: 45px; border-radius: 50%; border: 3px solid white; display: flex; align-items: center; justify-content: center; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-size: 22px; color: white;'>🛬</div>"
    folium.Marker(location=[a_node[1], a_node[2]], tooltip=f"DESTINAZIONE: {a_node[0]}", icon=folium.DivIcon(html=icon_html_a, icon_size=(45, 45), icon_anchor=(22, 22))).add_to(m)

# Disegno dei marker per Bivacchi e Rifugi
for _, row in mappa_bivacchi.iterrows():
    folium.Marker(location=[row.geometry.y, row.geometry.x], popup=folium.Popup(crea_popup(row), max_width=450), tooltip=get_valore_colonna(row, "Name_it"), icon=folium.DivIcon(html=f"<div style='background-color: {get_marker_color(row['Stato_Visita'])}; width: 30px; height: 30px; border-radius: 50%; border: 2px solid white; display: flex; align-items: center; justify-content: center; box-shadow: 1px 1px 4px rgba(0,0,0,0.3); font-size:14px;'>⛺</div>", icon_size=(30, 30), icon_anchor=(15, 15))).add_to(m)

for _, row in mappa_rifugi.iterrows():
    folium.Marker(location=[row.geometry.y, row.geometry.x], popup=folium.Popup(crea_popup(row), max_width=450), tooltip=get_valore_colonna(row, "Name_it"), icon=folium.DivIcon(html=f"<div style='background-color: {get_marker_color(row['Stato_Visita'])}; width: 30px; height: 30px; border-radius: 6px; border: 2px solid white; display: flex; align-items: center; justify-content: center; box-shadow: 1px 1px 4px rgba(0,0,0,0.3); font-size:14px;'>🏠</div>", icon_size=(30, 30), icon_anchor=(15, 15))).add_to(m)

# Iniezione Legenda HTML
legend_html = """
<div style="position: fixed; bottom: 20px; left: 20px; width: 180px; z-index:9999; background-color: rgba(255, 255, 255, 0.90); padding: 12px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.2); font-family: sans-serif; font-size: 11px; color: #333; line-height: 1.4;">
    <b style="font-size: 12px; display: block; margin-bottom: 5px;">🗺️ Legenda</b>
    <div style="margin-bottom: 6px;">
        <span style="font-weight: bold; display: block; font-size: 9px; color: #666; text-transform: uppercase;">Tracciati (Tratteggiati)</span>
        <div style="display: flex; align-items: center; margin-top: 2px;"><span style="border-top: 2px dashed #e65c00; width: 18px; display: inline-block; margin-right: 6px;"></span> Sentiero (Path)</div>
        <div style="display: flex; align-items: center; margin-top: 2px;"><span style="border-top: 2px dashed #8c564b; width: 18px; display: inline-block; margin-right: 6px;"></span> Sterrata (Track)</div>
        <div style="display: flex; align-items: center; margin-top: 2px;"><span style="border-top: 2px dashed #2ca02c; width: 18px; display: inline-block; margin-right: 6px;"></span> Pedonale (Footway)</div>
    </div>
    <div style="margin-bottom: 6px;">
        <span style="font-weight: bold; display: block; font-size: 9px; color: #666; text-transform: uppercase;">Strutture</span>
        <div style="display: flex; align-items: center; margin-top: 2px;"><div style="background-color: #999; width: 14px; height: 14px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 6px; font-size: 8px; color: white;">⛺</div> Bivacco</div>
        <div style="display: flex; align-items: center; margin-top: 2px;"><div style="background-color: #999; width: 14px; height: 14px; border-radius: 3px; display: flex; align-items: center; justify-content: center; margin-right: 6px; font-size: 8px; color: white;">🏠</div> Rifugio</div>
    </div>
    <div>
        <span style="font-weight: bold; display: block; font-size: 9px; color: #666; text-transform: uppercase;">Stato Visita</span>
        <div style="display: flex; align-items: center; margin-top: 2px;"><span style="background: #28a745; width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 8px;"></span> Visitato</div>
        <div style="display: flex; align-items: center; margin-top: 2px;"><span style="background: #ffc107; width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 8px;"></span> Pianificato</div>
        <div style="display: flex; align-items: center; margin-top: 2px;"><span style="background: #dc3545; width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 8px;"></span> Non visitato</div>
    </div>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))
folium.LayerControl(position='topright').add_to(m)

st.markdown(f"Mappa attiva: **{st.session_state.profilo_attivo}**")

# st_folium con chiave statica per bloccare i reset di iFrame
map_data = st_folium(m, width="100%", height=550, key="mappa_vda", returned_objects=["last_object_clicked_tooltip", "last_clicked"])

# ==========================================
# PANNELLO DI INTERCETTAZIONE CLIC SOTTO MAPPA
# ==========================================
struttura_cliccata = map_data.get("last_object_clicked_tooltip")
punto_mappa_cliccato = map_data.get("last_clicked")

nome_nodo, lat_nodo, lon_nodo, quota_nodo = None, None, None, 0

if struttura_cliccata:
    nome_nodo = struttura_cliccata
    if nome_nodo in dizionario_strutture:
        lat_nodo, lon_nodo, quota_nodo = dizionario_strutture[nome_nodo]
elif punto_mappa_cliccato:
    lat_nodo = punto_mappa_cliccato['lat']
    lon_nodo = punto_mappa_cliccato['lng']
    nome_nodo = f"Punto Libero ({round(lat_nodo,4)}, {round(lon_nodo,4)})"
    quota_nodo = get_elevation_api(lat_nodo, lon_nodo)

if nome_nodo and lat_nodo and lon_nodo:
    st.markdown(f"### 📍 Elemento selezionato sulla mappa: `{nome_nodo}` (Quota: {round(quota_nodo)} m)")
    
    col_p, col_t, col_d = st.columns(3)
    with col_p:
        if st.button("🛫 Imposta come Partenza", use_container_width=True):
            st.session_state.itinerario_struttura["partenza"] = (nome_nodo, lat_nodo, lon_nodo, quota_nodo)
            st.toast(f"🛫 Partenza impostata: {nome_nodo}")
            st.rerun()
    with col_t:
        if st.button("🛑 Aggiungi come Tappa Intermedia", use_container_width=True):
            nodo_tappa = (nome_nodo, lat_nodo, lon_nodo, quota_nodo)
            if nodo_tappa not in st.session_state.itinerario_struttura["tappe"]:
                st.session_state.itinerario_struttura["tappe"].append(nodo_tappa)
                st.toast(f"🛑 Tappa aggiunta: {nome_nodo}")
                st.rerun()
    with col_d:
        if st.button("🛬 Imposta come Destinazione", use_container_width=True):
            st.session_state.itinerario_struttura["arrivo"] = (nome_nodo, lat_nodo, lon_nodo, quota_nodo)
            st.toast(f"🛬 Destinazione impostata: {nome_nodo}")
            st.rerun()

    if struttura_cliccata:
        st.session_state.struttura_attiva = struttura_cliccata
        stato_attuale = "Non visitato"
        for df in [st.session_state.bivacchi, st.session_state.rifugi]:
            col_nome = [c for c in df.columns if c.lower() == "name_it"][0]
            match = df[df[col_nome] == struttura_cliccata]
            if not match.empty:
                stato_attuale = match.iloc[0]["Stato_Visita"]
                break
        idx_default = stati_disponibili.index(stato_attuale)
        st.selectbox("Modifica lo stato di visita della struttura (Salvataggio cloud automatico):", options=stati_disponibili, index=idx_default, key="quick_edit_selectbox", on_change=autosave_quick_edit)

# ==========================================
# SEZIONE REGISTRI TABELLARI
# ==========================================
st.markdown("---")
st.subheader(f"Database interattivo di {st.session_state.profilo_attivo}")

colonne_desiderate = ["Name_it", "ele", "Accesso", "Stato_Visita"]
col_visibili_b = colonne_reali(st.session_state.bivacchi, colonne_desiderate)
col_visibili_r = colonne_reali(st.session_state.rifugi, colonne_desiderate)

col1, col2 = st.columns(2)
with col1:
    st.markdown("### ⛺ Registro Bivacchi")
    st.data_editor(st.session_state.bivacchi[col_visibili_b], column_config={"Stato_Visita": st.column_config.SelectboxColumn("Stato", options=stati_disponibili, required=True)}, use_container_width=True, hide_index=True, key="editor_b", on_change=autosave_tabella_bivacchi)
with col2:
    st.markdown("### 🏠 Registro Rifugi")
    st.data_editor(st.session_state.rifugi[col_visibili_r], column_config={"Stato_Visita": st.column_config.SelectboxColumn("Stato", options=stati_disponibili, required=True)}, use_container_width=True, hide_index=True, key="editor_r", on_change=autosave_tabella_rifugi)