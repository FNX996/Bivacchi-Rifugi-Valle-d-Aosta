import streamlit as st
import geopandas as gpd
import folium
from folium import plugins
from streamlit_folium import st_folium
import os
import requests
import math
import networkx as nx
from scipy.spatial import cKDTree
import rasterio
import gpxpy
import gpxpy.gpx
import plotly.graph_objects as go
from datetime import datetime, timedelta
from supabase import create_client, Client

# ==========================================
# CONFIGURAZIONE PAGINA E STILI
# ==========================================
st.set_page_config(page_title="Pianificazione VdA", layout="wide")

st.markdown("""
    <style>
        iframe { opacity: 1 !important; filter: none !important; transition: none !important; }
        [data-testid="stElementContainer"] { opacity: 1 !important; }
        .stTabs [data-baseweb="tab-list"] { gap: 24px; }
        .stTabs [data-baseweb="tab"] { height: 50px; font-weight: bold; font-size: 16px; }
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
# FUNZIONI GLOBALI E METEO
# ==========================================
def calcola_distanza_haversine(lon1, lat1, lon2, lat2):
    R = 6371.0 
    dLat, dLon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def stima_tempo_cai(dist_km, d_pos_m):
    """Calcola il tempo stimato secondo la formula CAI (4km/h in piano, +1h ogni 300m D+)"""
    ore_piano = dist_km / 4.0
    ore_salita = d_pos_m / 300.0
    ore_totali = ore_piano + ore_salita
    h = int(ore_totali)
    m = int((ore_totali - h) * 60)
    return f"{h}h {m}m"

def get_previsioni_meteo(lat, lon):
    """Recupera le previsioni a 3 giorni da Open-Meteo"""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Europe%2FRome&forecast_days=3"
        r = requests.get(url)
        if r.status_code == 200:
            return r.json()['daily']
    except: pass
    return None

def mappa_meteo_emoji(code):
    if code in [0, 1]: return "☀️ Sereno"
    if code in [2, 3]: return "⛅ Nuvoloso"
    if code in [45, 48]: return "🌫️ Nebbia"
    if code in [51, 53, 55, 61, 63, 65, 80, 81, 82]: return "🌧️ Pioggia"
    if code in [71, 73, 75, 77, 85, 86]: return "❄️ Neve"
    if code in [95, 96, 99]: return "⛈️ Temporale"
    return "❓ Sconosciuto"

def disegna_profilo_altimetrico(quote, dist_totale_km, titolo="Profilo Altimetrico"):
    """Genera un grafico Plotly interattivo"""
    if not quote or len(quote) < 2: return None
    
    # Crea l'asse X (distanza) spalmando i punti in modo uniforme
    step = dist_totale_km / (len(quote) - 1)
    asse_x = [i * step for i in range(len(quote))]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=asse_x, y=quote, fill='tozeroy',
        mode='lines', line=dict(color='#0055ff', width=2),
        fillcolor='rgba(0, 85, 255, 0.2)',
        hovertemplate="<b>Dist:</b> %{x:.2f} km<br><b>Quota:</b> %{y:.0f} m<extra></extra>"
    ))
    
    fig.update_layout(
        title=titolo,
        xaxis_title="Distanza (km)", yaxis_title="Quota (m)",
        height=250, margin=dict(l=20, r=20, t=40, b=20),
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig

# --- FUNZIONI SUPABASE E DATABASE ---
def fetch_profili_esistenti():
    try:
        response = supabase.table("utenti_credenziali").select("utente").execute()
        return sorted([row['utente'] for row in response.data if row.get('utente')])
    except: return []

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

def genera_gpx(coordinate_geometria, nome_itinerario="Itinerario VdA"):
    gpx = ['<?xml version="1.0" encoding="UTF-8"?>', '<gpx version="1.1" creator="VdA_Explorer" xmlns="http://www.topografix.com/GPX/1/1">', '  <trk>', f'    <name>{nome_itinerario}</name>', '    <trkseg>']
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

def calcola_profilo_dtm(traccia_coordinate, dtm_path):
    try:
        with rasterio.open(dtm_path) as dataset:
            valori_quota = [val[0] for val in dataset.sample(traccia_coordinate)]
                
        disl_pos = 0
        disl_neg = 0
        for i in range(len(valori_quota) - 1):
            diff = valori_quota[i+1] - valori_quota[i]
            if diff > 0: disl_pos += diff
            else: disl_neg += abs(diff)
        return valori_quota, int(disl_pos), int(disl_neg)
    except: return [], 0, 0

@st.cache_resource(show_spinner=False)
def prepara_motore_routing(_gdf):
    G = nx.Graph()
    for _, row in _gdf.iterrows():
        geom = row.geometry
        if geom is None: continue
        lines = [geom] if geom.geom_type == 'LineString' else geom.geoms if geom.geom_type == 'MultiLineString' else []
        for line in lines:
            coords = list(line.coords)
            for i in range(len(coords)-1):
                p1, p2 = coords[i], coords[i+1]
                dist = calcola_distanza_haversine(p1[0], p1[1], p2[0], p2[1])
                G.add_edge(p1, p2, weight=dist)
    
    nodi_lista = list(G.nodes())
    if not nodi_lista: return None, None, None
    albero = cKDTree(nodi_lista)
    
    tolleranza_gradi = 0.00027  # Snapping topologico a 30m
    pairs = albero.query_pairs(r=tolleranza_gradi)
    for i, j in pairs:
        n1, n2 = nodi_lista[i], nodi_lista[j]
        if not G.has_edge(n1, n2):
            dist = calcola_distanza_haversine(n1[0], n1[1], n2[0], n2[1])
            G.add_edge(n1, n2, weight=dist)
            
    return G, nodi_lista, albero

def trova_nodo_vicino(albero, nodi, lon, lat):
    _, idx = albero.query((lon, lat))
    return nodi[idx]

def calcola_percorso_locale(G, albero, nodi, punti_coords):
    try:
        traccia_totale = []
        distanza_km = 0.0
        
        for i in range(len(punti_coords)-1):
            p1_lon, p1_lat = punti_coords[i][1], punti_coords[i][0]
            p2_lon, p2_lat = punti_coords[i+1][1], punti_coords[i+1][0]
            
            nodo1 = trova_nodo_vicino(albero, nodi, p1_lon, p1_lat)
            nodo2 = trova_nodo_vicino(albero, nodi, p2_lon, p2_lat)
            
            path = nx.shortest_path(G, source=nodo1, target=nodo2, weight='weight')
            
            for j in range(len(path)-1):
                distanza_km += G[path[j]][path[j+1]]['weight']
                
            if i == 0: traccia_totale.extend(path)
            else: traccia_totale.extend(path[1:])
        
        return {
            'geometry': {'type': 'LineString', 'coordinates': traccia_totale},
            'distance': distanza_km * 1000
        }
    except nx.NetworkXNoPath:
        return None

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
# SIDEBAR (Gestione account e filtri)
# ==========================================
if os.path.exists("immagine_app.jpeg"):
    st.sidebar.image("immagine_app.jpeg", use_container_width=True)

st.sidebar.markdown("### 👤 Profilo Utente")
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

st.sidebar.selectbox("Scegli un profilo:", options=opzioni_menu, index=index_default, key="scelta_profilo_widget", on_change=handle_profile_change)

if st.session_state.get("profilo_attivo") and not st.session_state.autenticato:
    password_input = st.sidebar.text_input("Inserisci la password:", type="password", key="pass_field")
    if password_input:
        if verifica_password(st.session_state.profilo_attivo, password_input):
            st.session_state.autenticato = True
            st.toast("🔓 Accesso eseguito con successo!", icon="🔑")
            st.rerun()
        else: st.sidebar.error("❌ Password errata!")

if st.session_state.get("creazione_in_corso", False):
    nome_input = st.sidebar.text_input("Digita il nome del nuovo utente:", placeholder="Nome...")
    password_nuova = st.sidebar.text_input("Imposta una password:", type="password", placeholder="Password...")
    if nome_input.strip() and password_nuova.strip():
        profilo_formattato = nome_input.strip().title()
        if st.sidebar.button("Inizializza Profilo"):
            if profilo_formattato in lista_profili: st.sidebar.error("❌ Profilo già esistente!")
            else:
                if registra_nuovo_utente(profilo_formattato, password_nuova.strip()):
                    st.session_state.profilo_attivo = profilo_formattato
                    st.session_state.autenticato = True
                    st.session_state.creazione_in_corso = False
                    if "dati_caricati" in st.session_state: del st.session_state["dati_caricati"]
                    st.rerun()

if not st.session_state.get("profilo_attivo") or not st.session_state.autenticato:
    st.info("👈 Seleziona un profilo e accedi per visualizzare i dati.")
    st.stop()

# Filtri Mappa nella Sidebar
st.sidebar.markdown("---")
stati_disponibili = ["Non visitato", "Pianificato", "Visitato"]
stati_selezionati = st.sidebar.multiselect("Filtra Mappa per Stato:", options=stati_disponibili, default=stati_disponibili)


# ==========================================
# INIZIALIZZAZIONE STRUTTURA DATI E GRAFO
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
        st.error("File GeoJSON non trovati!")
        st.stop()

grafo_motore, nodi_motore, albero_motore = None, None, None
if st.session_state.sentieri is not None:
    with st.spinner("Compilazione topologia..."):
        grafo_motore, nodi_motore, albero_motore = prepara_motore_routing(st.session_state.sentieri)

dizionario_strutture = {}
for df in [st.session_state.bivacchi, st.session_state.rifugi]:
    for _, row in df.iterrows():
        nome = get_valore_colonna(row, "Name_it", "")
        if nome: dizionario_strutture[nome] = (row.geometry.y, row.geometry.x, float(get_valore_colonna(row, "ele", 0)))

mappa_bivacchi = st.session_state.bivacchi[st.session_state.bivacchi['Stato_Visita'].isin(stati_selezionati)]
mappa_rifugi = st.session_state.rifugi[st.session_state.rifugi['Stato_Visita'].isin(stati_selezionati)]

st.sidebar.markdown("<br><br>", unsafe_allow_html=True)
st.sidebar.markdown("---")

st.sidebar.markdown("""
<div style="background-color: #e9ecef; padding: 12px; border-radius: 6px; border-left: 4px solid #0055ff; margin-bottom: 15px; font-family: sans-serif;">
    <h5 style="margin-top: 0; color: #111; font-size: 13px;">💡 Guida Rapida</h5>
    <ul style="margin: 0; padding-left: 18px; font-size: 12px; color: #444; line-height: 1.4;">
        <li><b>Mappa:</b> Clicca sulle strutture per info meteo e assegnare lo stato di visita.</li>
        <li><b>Itinerari:</b> Dopo il clic, assegna partenza/tappe per calcolare percorsi e DTM.</li>
        <li><b>Registri:</b> Gestisci tutti i tuoi salvataggi cloud in tabella.</li>
        <li><b>Tracce GPX:</b> Importa, analizza e visualizza i tuoi file.</li>
    </ul>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("""
<div style="font-size: 13px; color: #555; background-color: #f8f9fa; padding: 10px; border-radius: 5px; border-left: 4px solid #333;">
    <b>App Rifugi & Bivacchi VdA</b><br>
    Versione: 4.0 beta<br>
    Autore: Nori Fabrizio
</div>
""", unsafe_allow_html=True)

# ==========================================
# COSTRUZIONE UI CON TABS
# ==========================================
tab_mappa, tab_registri, tab_gpx = st.tabs(["🗺️ Esplora & Pianifica", "📊 Registri Strutture", "📂 Analisi GPX"])

# ------------------------------------------
# TAB 3: IMPORTAZIONE E ANALISI GPX (Processo prima della mappa!)
# ------------------------------------------
with tab_gpx:
    st.subheader("📂 Analizzatore File GPX Personali")
    st.markdown("Carica un file GPX esportato dal tuo orologio GPS, Strava, o Komoot. L'app estrarrà le quote originali registrate dal tuo dispositivo e disegnerà il profilo altimetrico, visualizzando la traccia anche nella scheda Mappa principale.")
    
    uploaded_gpx = st.file_uploader("Trascina qui il tuo file .gpx", type=["gpx"], key="gpx_uploader")

    if uploaded_gpx is not None:
        # Controllo se è un file nuovo rispetto a quello salvato per evitare calcoli infiniti
        is_new_file = ("gpx_caricato" not in st.session_state) or (st.session_state.gpx_caricato.get("file_name") != uploaded_gpx.name)
        
        if is_new_file:
            try:
                gpx = gpxpy.parse(uploaded_gpx)
                gpx_points = []
                quote_gpx = []
                d_pos_gpx, d_neg_gpx, dist_gpx = 0, 0, 0
                last_pt = None
                
                for track in gpx.tracks:
                    for segment in track.segments:
                        for point in segment.points:
                            gpx_points.append((point.latitude, point.longitude))
                            if point.elevation is not None:
                                quote_gpx.append(point.elevation)
                                
                            if last_pt:
                                dist_gpx += calcola_distanza_haversine(last_pt.longitude, last_pt.latitude, point.longitude, point.latitude)
                                if point.elevation is not None and last_pt.elevation is not None:
                                    diff = point.elevation - last_pt.elevation
                                    if diff > 0: d_pos_gpx += diff
                                    else: d_neg_gpx += abs(diff)
                            last_pt = point
                
                st.session_state.gpx_caricato = {
                    "points": gpx_points,
                    "quote": quote_gpx,
                    "dist": round(dist_gpx, 2),
                    "d_pos": round(d_pos_gpx),
                    "d_neg": round(d_neg_gpx),
                    "name": gpx.tracks[0].name if gpx.tracks and gpx.tracks[0].name else "Traccia Personale GPS",
                    "file_name": uploaded_gpx.name
                }
                
                # Forza il ricaricamento dell'app per far apparire istantaneamente il GPX sulla mappa in Tab 1
                st.rerun()
                
            except Exception as e:
                st.error("Errore nella decodifica del file GPX. Controlla che il file non sia corrotto.")
        else:
            # Mostra i dati se il file è già stato processato
            st.success("✅ Lettura completata con successo! Troverai la traccia disegnata in viola nella scheda 'Mappa & Itinerari'.")
            
            c_gpx1, c_gpx2, c_gpx3, c_gpx4 = st.columns(4)
            c_gpx1.metric("Nome Traccia", st.session_state.gpx_caricato['name'])
            c_gpx2.metric("Distanza GPS", f"{st.session_state.gpx_caricato['dist']} km")
            c_gpx3.metric("Dislivello Positivo", f"D+ {st.session_state.gpx_caricato['d_pos']} m")
            c_gpx4.metric("Dislivello Negativo", f"D- {st.session_state.gpx_caricato['d_neg']} m")
            
            if st.session_state.gpx_caricato.get('quote'):
                fig_gpx = disegna_profilo_altimetrico(st.session_state.gpx_caricato['quote'], st.session_state.gpx_caricato['dist'], "Profilo Altimetrico Registrato (Sensore GPS)")
                if fig_gpx: st.plotly_chart(fig_gpx, use_container_width=True)
            else:
                st.warning("⚠️ Questo file GPX non contiene dati di quota (solo 2D). Impossibile generare il profilo altimetrico.")
                
            if st.button("❌ Rimuovi Traccia GPX dal sistema", type="secondary"):
                del st.session_state["gpx_caricato"]
                st.rerun()
    else:
        if "gpx_caricato" in st.session_state:
            del st.session_state["gpx_caricato"]
            st.rerun()

# ------------------------------------------
# TAB 1: MAPPA E ITINERARI
# ------------------------------------------
with tab_mappa:
    
    # --- PANNELLO ITINERARIO ---
    with st.container(border=True):
        st.subheader("🧭 Pianificatore Itinerario")
        
        txt_partenza = st.session_state.itinerario_struttura["partenza"][0] if st.session_state.itinerario_struttura["partenza"] else "Non impostata"
        txt_tappe = " ➔ ".join([t[0] for t in st.session_state.itinerario_struttura["tappe"]]) if st.session_state.itinerario_struttura["tappe"] else "Nessuna"
        txt_arrivo = st.session_state.itinerario_struttura["arrivo"][0] if st.session_state.itinerario_struttura["arrivo"] else "Non impostato"
        
        st.markdown(f"**Partenza:** `{txt_partenza}` | **Tappe:** `{txt_tappe}` | **Arrivo:** `{txt_arrivo}`")
        
        punti_itinerario_completo = []
        if st.session_state.itinerario_struttura["partenza"]: punti_itinerario_completo.append(st.session_state.itinerario_struttura["partenza"])
        punti_itinerario_completo.extend(st.session_state.itinerario_struttura["tappe"])
        if st.session_state.itinerario_struttura["arrivo"]: punti_itinerario_completo.append(st.session_state.itinerario_struttura["arrivo"])
        
        col_calc, col_reset = st.columns([2, 1])
        with col_calc:
            if st.button("🔄 Calcola Tracciato e Profilo", type="primary", use_container_width=True):
                if len(punti_itinerario_completo) >= 2:
                    if grafo_motore:
                        coords_solo = [(p[1], p[2]) for p in punti_itinerario_completo]
                        with st.spinner("Calcolo tracciato in corso..."):
                            rotta = calcola_percorso_locale(grafo_motore, albero_motore, nodi_motore, coords_solo)
                            
                            if rotta:
                                st.session_state.itinerario_attivo = rotta
                                distanza_km = round(rotta['distance'] / 1000, 2)
                                
                                dtm_selezionato = "DTM_vda.tif" if os.path.exists("DTM_vda.tif") else "DTM_vda" if os.path.exists("DTM_vda") else None
                                
                                if dtm_selezionato:
                                    coords_traccia = rotta['geometry']['coordinates']
                                    quote_array, d_pos, d_neg = calcola_profilo_dtm(coords_traccia, dtm_selezionato)
                                else:
                                    quote_array, d_pos, d_neg = [], 0, 0
                                    
                                tempo_stimato = stima_tempo_cai(distanza_km, d_pos)
                                
                                st.session_state.itinerario_metadati = {
                                    "dist": distanza_km, "d_pos": d_pos, "d_neg": d_neg, 
                                    "tempo": tempo_stimato, "quote": quote_array
                                }
                            else:
                                st.error("❌ Rete interrotta: Impossibile collegare le tracce.")
                    else: st.error("Rete escursionistica mancante.")
                else: st.warning("Inserisci Partenza e Arrivo dalla mappa.")
        with col_reset:
            if st.button("🗑️ Svuota Tutto", use_container_width=True):
                st.session_state.itinerario_struttura = {"partenza": None, "tappe": [], "arrivo": None}
                if "itinerario_attivo" in st.session_state: del st.session_state["itinerario_attivo"]
                if "itinerario_metadati" in st.session_state: del st.session_state["itinerario_metadati"]
                st.rerun()

        # Dati e Grafico a calcolo completato
        if st.session_state.get("itinerario_attivo") and st.session_state.get("itinerario_metadati"):
            meta = st.session_state.itinerario_metadati
            
            st.success(f"📈 **Distanza:** {meta['dist']} km | **D+** {meta['d_pos']} m / **D-** {meta['d_neg']} m | ⏱️ **Tempo Stimato:** {meta['tempo']}")
            
            if meta.get('quote'):
                fig = disegna_profilo_altimetrico(meta['quote'], meta['dist'], "Profilo Altimetrico Calcolato (DTM)")
                if fig: st.plotly_chart(fig, use_container_width=True)
            
            coords_itinerario = st.session_state.itinerario_attivo['geometry']['coordinates']
            gpx_data = genera_gpx(coords_itinerario)
            coords_maps = [(p[1], p[2]) for p in punti_itinerario_completo]
            maps_url = genera_google_maps_url(coords_maps)
            
            c1, c2 = st.columns(2)
            with c1: st.download_button("📥 Scarica .GPX", data=gpx_data, file_name="itinerario.gpx", mime="application/gpx+xml", use_container_width=True)
            with c2: st.link_button("🗺️ Apri in Google Maps", url=maps_url, use_container_width=True)

    # --- MAPPA FOLIUM ---
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
        campi_tooltip = ['name'] if 'name' in st.session_state.sentieri.columns else []
        nomi_alias = ['Nome:'] if campi_tooltip else []
        folium.GeoJson(
            st.session_state.sentieri, 
            style_function=lambda x: {'color': '#2ca02c' if x['properties'].get('fclass')=='footway' else '#e65c00', 'weight': 2.2, 'dashArray': '6, 6', 'opacity': 0.85}, 
            tooltip=folium.GeoJsonTooltip(fields=campi_tooltip, aliases=nomi_alias) if campi_tooltip else None
        ).add_to(fg_sentieri)
        fg_sentieri.add_to(m)

    if st.session_state.get("itinerario_attivo"):
        fg_itinerario = folium.FeatureGroup(name="📍 Traccia Calcolata", show=True)
        folium.GeoJson(st.session_state.itinerario_attivo['geometry'], style_function=lambda x: {'color': '#0055ff', 'weight': 5, 'opacity': 0.9}).add_to(fg_itinerario)
        fg_itinerario.add_to(m)

    if "gpx_caricato" in st.session_state and st.session_state.gpx_caricato:
        fg_gpx = folium.FeatureGroup(name="🗺️ Traccia GPX Importata", show=True)
        folium.PolyLine(locations=st.session_state.gpx_caricato["points"], color="#8e44ad", weight=6, opacity=0.8).add_to(fg_gpx)
        fg_gpx.add_to(m)

    # Indicatori Partenza/Tappa/Arrivo
    for k, icon_str, tooltip_prefix in [("partenza", "🛫", "PARTENZA"), ("arrivo", "🛬", "DESTINAZIONE")]:
        node = st.session_state.itinerario_struttura.get(k)
        if node:
            bg_color = "#0055ff" if k == "partenza" else "#ff0000"
            html = f"<div style='background-color: {bg_color}; width: 45px; height: 45px; border-radius: 50%; border: 3px solid white; display: flex; align-items: center; justify-content: center; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-size: 22px; color: white;'>{icon_str}</div>"
            folium.Marker(location=[node[1], node[2]], tooltip=f"{tooltip_prefix}: {node[0]}", icon=folium.DivIcon(html=html, icon_size=(45, 45), icon_anchor=(22, 22))).add_to(m)

    for t_node in st.session_state.itinerario_struttura.get("tappe", []):
        html = "<div style='background-color: #ff8800; width: 40px; height: 40px; border-radius: 50%; border: 3px solid white; display: flex; align-items: center; justify-content: center; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-size: 18px; color: white;'>🛑</div>"
        folium.Marker(location=[t_node[1], t_node[2]], tooltip=f"TAPPA: {t_node[0]}", icon=folium.DivIcon(html=html, icon_size=(40, 40), icon_anchor=(20, 20))).add_to(m)

    for _, row in mappa_bivacchi.iterrows():
        folium.Marker(location=[row.geometry.y, row.geometry.x], popup=folium.Popup(crea_popup(row), max_width=450), tooltip=get_valore_colonna(row, "Name_it"), icon=folium.DivIcon(html=f"<div style='background-color: {get_marker_color(row['Stato_Visita'])}; width: 30px; height: 30px; border-radius: 50%; border: 2px solid white; display: flex; align-items: center; justify-content: center; font-size:14px;'>⛺</div>", icon_size=(30, 30), icon_anchor=(15, 15))).add_to(m)

    for _, row in mappa_rifugi.iterrows():
        folium.Marker(location=[row.geometry.y, row.geometry.x], popup=folium.Popup(crea_popup(row), max_width=450), tooltip=get_valore_colonna(row, "Name_it"), icon=folium.DivIcon(html=f"<div style='background-color: {get_marker_color(row['Stato_Visita'])}; width: 30px; height: 30px; border-radius: 6px; border: 2px solid white; display: flex; align-items: center; justify-content: center; font-size:14px;'>🏠</div>", icon_size=(30, 30), icon_anchor=(15, 15))).add_to(m)

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

    map_data = st_folium(m, width="100%", height=550, key="mappa_vda", returned_objects=["last_object_clicked_tooltip", "last_clicked"])

    # --- PANNELLO CLIC E METEO ---
    struttura_cliccata = map_data.get("last_object_clicked_tooltip")
    punto_mappa_cliccato = map_data.get("last_clicked")
    nome_nodo, lat_nodo, lon_nodo, quota_nodo = None, None, None, 0

    if struttura_cliccata:
        nome_nodo = struttura_cliccata
        if nome_nodo in dizionario_strutture:
            lat_nodo, lon_nodo, quota_nodo = dizionario_strutture[nome_nodo]
    elif punto_mappa_cliccato:
        lat_nodo, lon_nodo = punto_mappa_cliccato['lat'], punto_mappa_cliccato['lng']
        nome_nodo = f"Punto Libero ({round(lat_nodo,4)}, {round(lon_nodo,4)})"
        dtm_selezionato = "DTM_vda.tif" if os.path.exists("DTM_vda.tif") else None
        if dtm_selezionato:
            try:
                with rasterio.open(dtm_selezionato) as dataset:
                    quota_nodo = [v[0] for v in dataset.sample([(lon_nodo, lat_nodo)])][0]
            except: pass

    if nome_nodo and lat_nodo and lon_nodo:
        st.markdown("---")
        c_info, c_meteo = st.columns([1.5, 1])
        
        with c_info:
            st.markdown(f"### 📍 `{nome_nodo}` (Quota: {round(quota_nodo)}m)")
            
            c_p, c_t, c_a = st.columns(3)
            with c_p:
                if st.button("🛫 Partenza", use_container_width=True):
                    st.session_state.itinerario_struttura["partenza"] = (nome_nodo, lat_nodo, lon_nodo, quota_nodo)
                    st.rerun()
            with c_t:
                if st.button("🛑 Tappa", use_container_width=True):
                    nodo_t = (nome_nodo, lat_nodo, lon_nodo, quota_nodo)
                    if nodo_t not in st.session_state.itinerario_struttura["tappe"]:
                        st.session_state.itinerario_struttura["tappe"].append(nodo_t)
                        st.rerun()
            with c_a:
                if st.button("🛬 Arrivo", use_container_width=True):
                    st.session_state.itinerario_struttura["arrivo"] = (nome_nodo, lat_nodo, lon_nodo, quota_nodo)
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
                st.selectbox("Modifica stato cloud:", options=stati_disponibili, index=stati_disponibili.index(stato_attuale), key="quick_edit_selectbox", on_change=autosave_quick_edit)

        with c_meteo:
            st.markdown("🌤️ **Previsioni a 3 giorni (Open-Meteo)**")
            with st.spinner("Cerco dati meteo..."):
                previsioni = get_previsioni_meteo(lat_nodo, lon_nodo)
                if previsioni:
                    for i in range(3):
                        data_dt = datetime.strptime(previsioni['time'][i], "%Y-%m-%d")
                        oggi = "Oggi" if i==0 else "Domani" if i==1 else data_dt.strftime("%d/%m")
                        codice = previsioni['weathercode'][i]
                        t_max = previsioni['temperature_2m_max'][i]
                        t_min = previsioni['temperature_2m_min'][i]
                        st.markdown(f"**{oggi}:** {mappa_meteo_emoji(codice)} | {t_max}°C / {t_min}°C")
                else:
                    st.caption("Dati meteo non disponibili.")


# ------------------------------------------
# TAB 2: REGISTRI DATABASE
# ------------------------------------------
with tab_registri:
    st.subheader(f"Database interattivo di {st.session_state.profilo_attivo}")
    colonne_desiderate = ["Name_it", "ele", "Accesso", "Stato_Visita"]
    col_visibili_b = colonne_reali(st.session_state.bivacchi, colonne_desiderate)
    col_visibili_r = colonne_reali(st.session_state.rifugi, colonne_desiderate)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### ⛺ Bivacchi")
        st.data_editor(st.session_state.bivacchi[col_visibili_b], column_config={"Stato_Visita": st.column_config.SelectboxColumn("Stato", options=stati_disponibili, required=True)}, use_container_width=True, hide_index=True, key="editor_b", on_change=autosave_tabella_bivacchi)
    with col2:
        st.markdown("### 🏠 Rifugi")
        st.data_editor(st.session_state.rifugi[col_visibili_r], column_config={"Stato_Visita": st.column_config.SelectboxColumn("Stato", options=stati_disponibili, required=True)}, use_container_width=True, hide_index=True, key="editor_r", on_change=autosave_tabella_rifugi)