import streamlit as st
import geopandas as gpd
import folium
from folium import plugins
from branca.element import Template, MacroElement
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
from datetime import datetime
import json
from supabase import create_client, Client

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

def calcola_distanza_haversine(lon1, lat1, lon2, lat2):
    R = 6371.0 
    dLat, dLon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def euristica_astar(nodo1, nodo2):
    return calcola_distanza_haversine(nodo1[0], nodo1[1], nodo2[0], nodo2[1])

def stima_tempo_cai(dist_km, d_pos_m):
    ore_totali = (dist_km / 4.0) + (d_pos_m / 300.0)
    h = int(ore_totali)
    m = int((ore_totali - h) * 60)
    return f"{h}h {m}m"

@st.cache_data(ttl=3600)
def get_previsioni_meteo(lat, lon):
    try:
        lat_r, lon_r = round(lat, 2), round(lon, 2)
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat_r}&longitude={lon_r}&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Europe%2FRome&forecast_days=3"
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            return r.json().get('daily')
    except: pass
    return None

def mappa_meteo_emoji(code):
    mappa = {
        0: "☀️ Sereno", 1: "☀️ Sereno", 2: "⛅ Nuvoloso", 3: "⛅ Nuvoloso",
        45: "🌫️ Nebbia", 48: "🌫️ Nebbia", 
        51: "🌧️ Pioggia", 53: "🌧️ Pioggia", 55: "🌧️ Pioggia", 61: "🌧️ Pioggia", 63: "🌧️ Pioggia", 65: "🌧️ Pioggia", 80: "🌧️ Pioggia", 81: "🌧️ Pioggia", 82: "🌧️ Pioggia",
        71: "❄️ Neve", 73: "❄️ Neve", 75: "❄️ Neve", 77: "❄️ Neve", 85: "❄️ Neve", 86: "❄️ Neve",
        95: "⛈️ Temporale", 96: "⛈️ Temporale", 99: "⛈️ Temporale"
    }
    return mappa.get(code, "❓ Sconosciuto")

def disegna_profilo_altimetrico(quote, dist_totale_km, titolo="Profilo Altimetrico"):
    if not quote or len(quote) < 2: return None
    step = dist_totale_km / (len(quote) - 1)
    asse_x = [i * step for i in range(len(quote))]
    fig = go.Figure(go.Scatter(
        x=asse_x, y=quote, fill='tozeroy', mode='lines', line=dict(color='#0055ff', width=2),
        fillcolor='rgba(0, 85, 255, 0.2)', hovertemplate="<b>Dist:</b> %{x:.2f} km<br><b>Quota:</b> %{y:.0f} m<extra></extra>"
    ))
    fig.update_layout(title=titolo, xaxis_title="Distanza (km)", yaxis_title="Quota (m)", height=250, margin=dict(l=20, r=20, t=40, b=20), hovermode="x unified", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

def calcola_profilo_dtm(traccia_coordinate, dtm_path):
    try:
        with rasterio.open(dtm_path) as dataset:
            valori_quota = [val[0] for val in dataset.sample(traccia_coordinate)]
        disl_pos = sum(max(0, valori_quota[i+1] - valori_quota[i]) for i in range(len(valori_quota) - 1))
        disl_neg = sum(max(0, valori_quota[i] - valori_quota[i+1]) for i in range(len(valori_quota) - 1))
        return valori_quota, int(disl_pos), int(disl_neg)
    except: return [], 0, 0

@st.cache_resource(show_spinner=False)
def prepara_motore_routing(_gdf):
    G = nx.Graph()
    for _, row in _gdf.iterrows():
        if row.geometry is None: continue
        lines = [row.geometry] if row.geometry.geom_type == 'LineString' else row.geometry.geoms if row.geometry.geom_type == 'MultiLineString' else []
        for line in lines:
            coords = list(line.coords)
            for i in range(len(coords)-1):
                p1, p2 = coords[i], coords[i+1]
                G.add_edge(p1, p2, weight=calcola_distanza_haversine(p1[0], p1[1], p2[0], p2[1]))
    
    nodi_lista = list(G.nodes())
    if not nodi_lista: return None, None, None
    albero = cKDTree(nodi_lista)
    
    pairs = albero.query_pairs(r=0.00027) # Snapping a 30m
    for i, j in pairs:
        n1, n2 = nodi_lista[i], nodi_lista[j]
        if not G.has_edge(n1, n2):
            G.add_edge(n1, n2, weight=calcola_distanza_haversine(n1[0], n1[1], n2[0], n2[1]))
            
    return G, nodi_lista, albero

def calcola_percorso_locale(G, albero, nodi, punti_coords):
    try:
        traccia_totale, distanza_km = [], 0.0
        for i in range(len(punti_coords)-1):
            nodo1 = nodi[albero.query((punti_coords[i][1], punti_coords[i][0]))[1]]
            nodo2 = nodi[albero.query((punti_coords[i+1][1], punti_coords[i+1][0]))[1]]
            path = nx.astar_path(G, source=nodo1, target=nodo2, heuristic=euristica_astar, weight='weight')
            distanza_km += sum(G[path[j]][path[j+1]]['weight'] for j in range(len(path)-1))
            traccia_totale.extend(path if i == 0 else path[1:])
            
        return {'geometry': {'type': 'LineString', 'coordinates': traccia_totale}, 'distance': distanza_km * 1000}
    except nx.NetworkXNoPath: return None

def fetch_profili_esistenti():
    try: return sorted([row['utente'] for row in supabase.table("utenti_credenziali").select("utente").execute().data if row.get('utente')])
    except: return []

def verifica_password(utente, password_inserita):
    try:
        res = supabase.table("utenti_credenziali").select("password").eq("utente", utente).execute()
        return res.data and res.data[0]["password"] == password_inserita
    except: return False

def registra_nuovo_utente(utente, password):
    try: return supabase.table("utenti_credenziali").insert({"utente": utente, "password": password}).execute() is not None
    except: return False

def fetch_stati_dal_db(utente):
    try: return {row['nome_struttura']: row['stato'] for row in supabase.table("stato_visite").select("*").eq("utente", utente).execute().data}
    except: return {}

def get_val(row, col, default="N/D"):
    val = row.get(col)
    return val if val is not None and str(val).strip() not in ["", "None", "nan"] else default

def genera_gpx(coordinate_geometria, nome_itinerario="Itinerario VdA"):
    gpx = ['<?xml version="1.0" encoding="UTF-8"?>', '<gpx version="1.1" creator="VdA_Explorer" xmlns="http://www.topografix.com/GPX/1/1">', '  <trk>', f'    <name>{nome_itinerario}</name>', '    <trkseg>']
    gpx.extend([f'      <trkpt lat="{lat}" lon="{lon}"></trkpt>' for lon, lat in coordinate_geometria])
    gpx.extend(['    </trkseg>', '  </trk>', '</gpx>'])
    return "\n".join(gpx)

def carica_tracce_gpx_cloud(utente):
    try:
        res = supabase.table("tracce_gpx").select("*").eq("utente", utente).execute()
        tracce = {}
        if res.data:
            for row in res.data:
                tracce[row['nome']] = {
                    "descrizione": row.get('descrizione', ""),
                    "visibile": row.get('visibile', True),
                    "dati": row.get('dati_json', {})
                }
        return tracce
    except Exception as e:
        st.error(f"Errore caricamento GPX cloud: {e}")
        return {}

def salva_traccia_gpx(utente, nome, descrizione, visibile, dati_json):
    try:
        dati_puliti = json.loads(json.dumps(dati_json, allow_nan=False))
        # Verifica se esiste per fare Update o Insert (simula Upsert)
        res = supabase.table("tracce_gpx").select("id").eq("utente", utente).eq("nome", nome).execute()
        if res.data:
            supabase.table("tracce_gpx").update({
                "descrizione": descrizione,
                "visibile": visibile,
                "dati_json": dati_puliti
            }).eq("id", res.data[0]["id"]).execute()
        else:
            supabase.table("tracce_gpx").insert({
                "utente": utente,
                "nome": nome,
                "descrizione": descrizione,
                "visibile": visibile,
                "dati_json": dati_puliti
            }).execute()
        return True
    except Exception as e:
        st.error(f"Errore di salvataggio GPX cloud: {e}")
        return False

def aggiorna_metadati_gpx(utente, nome, campo, valore):
    try:
        supabase.table("tracce_gpx").update({campo: valore}).eq("utente", utente).eq("nome", nome).execute()
    except Exception as e:
        st.error(f"Errore aggiornamento {campo}: {e}")

def autosave_quick_edit():
    nuovo_stato = st.session_state.quick_edit_selectbox
    struttura, profilo = st.session_state.struttura_attiva, st.session_state.profilo_attivo
    for df_name in ["bivacchi", "rifugi"]:
        df = st.session_state[df_name]
        idx = df[df["name_it"] == struttura].index
        if not idx.empty:
            st.session_state[df_name].loc[idx, "stato_visita"] = nuovo_stato
            break
    try:
        supabase.table("stato_visite").upsert({"nome_struttura": struttura, "stato": nuovo_stato, "utente": profilo}).execute()
        st.toast(f"☁️ Autosave Cloud: {struttura} → {nuovo_stato}", icon="✅")
    except: st.error("Errore di sincronizzazione Cloud")

def sync_tables_cloud(df_name, editor_key):
    edits = st.session_state[editor_key].get("edited_rows", {})
    if edits:
        df, records = st.session_state[df_name], []
        for row_idx_str, changes in edits.items():
            if "stato_visita" in changes:
                row_idx, nuovo_stato = int(row_idx_str), changes["stato_visita"]
                st.session_state[df_name].loc[row_idx, "stato_visita"] = nuovo_stato
                records.append({"nome_struttura": df.loc[row_idx, "name_it"], "stato": nuovo_stato, "utente": st.session_state.profilo_attivo})
        if records: supabase.table("stato_visite").upsert(records).execute()

if os.path.exists("immagine_app.jpeg"): st.sidebar.image("immagine_app.jpeg", use_container_width=True)

st.sidebar.markdown("### 👤 Profilo Utente")
lista_profili = fetch_profili_esistenti()

if "autenticato" not in st.session_state: st.session_state.autenticato = False
if "itinerario_struttura" not in st.session_state: st.session_state.itinerario_struttura = {"partenza": None, "tappe": [], "arrivo": None}

profilo_input = st.sidebar.text_input("Cerca o digita il tuo profilo:")

if profilo_input:
    match = [p for p in lista_profili if p.lower().startswith(profilo_input.lower())]
    if match:
        scelta = st.sidebar.radio("Profili trovati:", match)
        if st.sidebar.button("Accedi con questo profilo"):
            st.session_state.scelta_profilo_widget = scelta
            st.session_state.creazione_in_corso = False
            st.session_state.profilo_attivo = scelta
            st.session_state.autenticato = False
            if "dati_caricati" in st.session_state: del st.session_state["dati_caricati"]
            st.rerun()
    else:
        st.sidebar.info("Profilo non trovato. Vuoi crearne uno nuovo?")
        if st.sidebar.button("➕ Crea Nuovo Profilo"):
            st.session_state.scelta_profilo_widget = "➕ Crea Nuovo Profilo..."
            st.session_state.creazione_in_corso = True
            st.session_state.profilo_attivo = None
            st.rerun()

if st.session_state.get("profilo_attivo") and not st.session_state.autenticato:
    if pwd := st.sidebar.text_input(f"Inserisci la password per {st.session_state.profilo_attivo}:", type="password", key="pass_field"):
        if verifica_password(st.session_state.profilo_attivo, pwd):
            st.session_state.autenticato = True
            st.toast("🔓 Accesso eseguito!", icon="🔑")
            st.rerun()
        else: st.sidebar.error("❌ Password errata!")

if st.session_state.get("creazione_in_corso"):
    nome_nuovo = st.sidebar.text_input("Nome del nuovo utente:", placeholder="Nome completo...")
    password_nuova = st.sidebar.text_input("Imposta una password:", type="password", placeholder="Password...")
    if nome_nuovo.strip() and password_nuova.strip() and st.sidebar.button("Inizializza Profilo"):
        p_fmt = nome_nuovo.strip().title()
        if p_fmt in lista_profili: st.sidebar.error("❌ Profilo già esistente!")
        elif registra_nuovo_utente(p_fmt, password_nuova.strip()):
            st.session_state.profilo_attivo, st.session_state.autenticato, st.session_state.creazione_in_corso = p_fmt, True, False
            if "dati_caricati" in st.session_state: del st.session_state["dati_caricati"]
            st.rerun()

if not st.session_state.get("profilo_attivo") or not st.session_state.autenticato:
    st.info("👈 Digita il tuo profilo per accedere o creane uno nuovo.")
    st.stop()

st.sidebar.markdown("---")
stati_disponibili = ["Non visitato", "Pianificato", "Visitato"]
stati_selezionati = st.sidebar.multiselect("Filtra Mappa per Stato:", options=stati_disponibili, default=stati_disponibili)

st.sidebar.markdown("<br><br>", unsafe_allow_html=True)
st.sidebar.markdown("""
<div style="background-color: #1e293b; padding: 15px; border-radius: 8px; border-left: 5px solid #3b82f6; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
    <h5 style="margin-top: 0; color: #f8fafc; font-size: 15px; font-weight: 600;">💡 Guida Rapida</h5>
    <ul style="margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.6; color: #cbd5e1;">
        <li><b>Mappa:</b> Clicca sulle strutture per info, sito web, meteo ed edita lo stato. Radar esplorazione attivo!</li>
        <li><b>Itinerari:</b> Assegna punti sulla mappa per calcolare percorsi e DTM.</li>
        <li><b>GPX:</b> Importa, analizza e visualizza le tue tracce cloud.</li>
    </ul>
</div>
<div style="font-size: 13px; color: #555; background-color: #f8f9fa; padding: 10px; border-radius: 5px; border-left: 4px solid #333;">
    <b>App Rifugi & Bivacchi VdA</b><br>Versione: 4.2 beta<br>Autore: Nori Fabrizio
</div>
""", unsafe_allow_html=True)

if "dati_caricati" not in st.session_state:
    stati_cloud = fetch_stati_dal_db(st.session_state.profilo_attivo)
    
    # Carica le tracce GPX salvate nel Cloud per questo utente
    st.session_state.tracce_gpx = carica_tracce_gpx_cloud(st.session_state.profilo_attivo)
    
    if os.path.exists("bivacchi_vda.geojson") and os.path.exists("rifugi_vda.geojson"):
        gdf_b, gdf_r = gpd.read_file("bivacchi_vda.geojson"), gpd.read_file("rifugi_vda.geojson")
        gdf_b.columns, gdf_r.columns = gdf_b.columns.str.lower(), gdf_r.columns.str.lower()
        gdf_b["stato_visita"] = [stati_cloud.get(r.get("name_it"), "Non visitato") for _, r in gdf_b.iterrows()]
        gdf_r["stato_visita"] = [stati_cloud.get(r.get("name_it"), "Non visitato") for _, r in gdf_r.iterrows()]
        
        st.session_state.bivacchi, st.session_state.rifugi = gdf_b, gdf_r
        st.session_state.sentieri = gpd.read_file("sentieri_vda_ottimizzati.geojson") if os.path.exists("sentieri_vda_ottimizzati.geojson") else None
        st.session_state.dati_caricati = True
    else:
        st.error("File GeoJSON non trovati!")
        st.stop()

grafo_motore, nodi_motore, albero_motore = None, None, None
if st.session_state.sentieri is not None:
    with st.spinner("Inizializzazione Motore A*..."):
        grafo_motore, nodi_motore, albero_motore = prepara_motore_routing(st.session_state.sentieri)

dizionario_strutture = {
    row.get("name_it"): (row.geometry.y, row.geometry.x, float(row.get("ele", 0))) 
    for df in [st.session_state.bivacchi, st.session_state.rifugi] for _, row in df.iterrows() if row.get("name_it")
}

mappa_bivacchi = st.session_state.bivacchi[st.session_state.bivacchi['stato_visita'].isin(stati_selezionati)]
mappa_rifugi = st.session_state.rifugi[st.session_state.rifugi['stato_visita'].isin(stati_selezionati)]

# ==========================================
# UI TABS
# ==========================================
tab_mappa, tab_registri, tab_gpx = st.tabs(["🗺️ Esplora & Pianifica", "📊 Registri Strutture", "📂 Archivio GPX"])

with tab_gpx:
    st.subheader("📂 Il tuo Archivio GPX")
    st.markdown("Carica i tuoi file GPX. Verranno salvati nel tuo profilo cloud. Potrai gestirne la visibilità in mappa, analizzarne le quote e aggiungere descrizioni.")
    
    if "tracce_gpx" in st.session_state and st.session_state.tracce_gpx:
        st.info(f"📊 **Totale Tracce nel tuo archivio:** {len(st.session_state.tracce_gpx)}")
    
    uploaded_files = st.file_uploader("Trascina o seleziona una o più tracce .gpx", type=["gpx"], accept_multiple_files=True)

    if uploaded_files:
        for uploaded_gpx in uploaded_files:
            content = uploaded_gpx.getvalue()
            if len(content) > 0:
                base_nome = uploaded_gpx.name
                
                # Evita elaborazioni inutili se già in memoria
                if base_nome not in st.session_state.tracce_gpx:
                    try:
                        try:
                            gpx_string = content.decode('utf-8')
                        except UnicodeDecodeError:
                            gpx_string = content.decode('ISO-8859-1')
                        
                        gpx = gpxpy.parse(gpx_string)
                        pts, quote, d_pos, d_neg, dist = [], [], 0, 0, 0
                        last_pt = None
                        
                        for t in gpx.tracks:
                            for s in t.segments:
                                for p in s.points:
                                    pts.append((p.latitude, p.longitude))
                                    if p.elevation is not None: quote.append(p.elevation)
                                    if last_pt:
                                        dist += calcola_distanza_haversine(last_pt.longitude, last_pt.latitude, p.longitude, p.latitude)
                                        if p.elevation is not None and last_pt.elevation is not None:
                                            diff = p.elevation - last_pt.elevation
                                            if diff > 0: d_pos += diff
                                            else: d_neg += abs(diff)
                                    last_pt = p
                        
                        dati_gpx = {"points": pts, "quote": quote, "dist": round(dist, 2), "d_pos": round(d_pos), "d_neg": round(d_neg), "stato": "Pianificata"}
                        
                        st.session_state.tracce_gpx[base_nome] = {
                            "descrizione": "",
                            "visibile": True,
                            "dati": dati_gpx
                        }
                        
                        # Salvataggio nel database Supabase
                        salva_traccia_gpx(st.session_state.profilo_attivo, base_nome, "", True, dati_gpx)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Errore decodifica GPX {base_nome}: {e}")

    st.markdown("---")
    
    # Rendering dell'elenco espandibile per le tracce caricate in cloud
    if st.session_state.get("tracce_gpx"):
        for nome_traccia, info in list(st.session_state.tracce_gpx.items()):
            stato_traccia = info["dati"].get("stato", "Pianificata")
            icona_stato = "✅" if stato_traccia == "Svolta" else "⏳"
            
            with st.expander(f"{icona_stato} 🗺️ {nome_traccia}", expanded=False):
                c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
                c1.metric("Distanza", f"{info['dati']['dist']} km")
                c2.metric("Dislivello +", f"D+ {info['dati']['d_pos']} m")
                c3.metric("Dislivello -", f"D- {info['dati']['d_neg']} m")
                
                visibile = c4.toggle("Mostra in Mappa", value=info.get("visibile", True), key=f"vis_{nome_traccia}")
                if visibile != info.get("visibile", True):
                    st.session_state.tracce_gpx[nome_traccia]["visibile"] = visibile
                    aggiorna_metadati_gpx(st.session_state.profilo_attivo, nome_traccia, "visibile", visibile)
                    st.rerun()

                c_stato, c_desc = st.columns([1, 2])
                with c_stato:
                    nuovo_stato = st.selectbox("Stato Traccia:", ["Pianificata", "Svolta"], index=0 if stato_traccia=="Pianificata" else 1, key=f"stato_{nome_traccia}")
                    if nuovo_stato != stato_traccia:
                        st.session_state.tracce_gpx[nome_traccia]["dati"]["stato"] = nuovo_stato
                        salva_traccia_gpx(st.session_state.profilo_attivo, nome_traccia, info.get("descrizione", ""), info.get("visibile", True), st.session_state.tracce_gpx[nome_traccia]["dati"])
                        st.rerun()

                with c_desc:
                    desc = st.text_area("Descrizione della traccia:", value=info.get("descrizione", ""), key=f"desc_{nome_traccia}", label_visibility="collapsed")
                    if desc != info.get("descrizione", ""):
                        st.session_state.tracce_gpx[nome_traccia]["descrizione"] = desc
                        aggiorna_metadati_gpx(st.session_state.profilo_attivo, nome_traccia, "descrizione", desc)

                if info["dati"].get("quote"):
                    fig_gpx = disegna_profilo_altimetrico(info["dati"]["quote"], info["dati"]["dist"], "Profilo Altimetrico")
                    if fig_gpx: st.plotly_chart(fig_gpx, use_container_width=True)
                    
                if st.button("❌ Elimina definitivamente", key=f"del_{nome_traccia}", type="secondary"):
                    try:
                        supabase.table("tracce_gpx").delete().eq("utente", st.session_state.profilo_attivo).eq("nome", nome_traccia).execute()
                        del st.session_state.tracce_gpx[nome_traccia]
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore eliminazione dal database: {e}")

with tab_mappa:
    with st.container(border=True):
        st.subheader("🧭 Pianificatore Itinerario")
        txt_part = st.session_state.itinerario_struttura["partenza"][0] if st.session_state.itinerario_struttura["partenza"] else "Non impostata"
        txt_tappe = " ➔ ".join([t[0] for t in st.session_state.itinerario_struttura["tappe"]]) if st.session_state.itinerario_struttura["tappe"] else "Nessuna"
        txt_arr = st.session_state.itinerario_struttura["arrivo"][0] if st.session_state.itinerario_struttura["arrivo"] else "Non impostato"
        
        st.markdown(f"**Partenza:** `{txt_part}` | **Tappe:** `{txt_tappe}` | **Arrivo:** `{txt_arr}`")
        
        punti_it = [p for p in [st.session_state.itinerario_struttura["partenza"]] + st.session_state.itinerario_struttura["tappe"] + [st.session_state.itinerario_struttura["arrivo"]] if p]
        
        c_calc, c_reset = st.columns([2, 1])
        with c_calc:
            if st.button("🔄 Calcola Tracciato", type="primary", use_container_width=True):
                if len(punti_it) >= 2 and grafo_motore:
                    with st.spinner("Calcolo rotta ultrarapido..."):
                        if rotta := calcola_percorso_locale(grafo_motore, albero_motore, nodi_motore, [(p[1], p[2]) for p in punti_it]):
                            st.session_state.itinerario_attivo = rotta
                            dist = round(rotta['distance'] / 1000, 2)
                            dtm_file = "DTM_vda.tif" if os.path.exists("DTM_vda.tif") else "DTM_vda" if os.path.exists("DTM_vda") else None
                            q_arr, d_pos, d_neg = calcola_profilo_dtm(rotta['geometry']['coordinates'], dtm_file) if dtm_file else ([], 0, 0)
                            st.session_state.itinerario_metadati = {"dist": dist, "d_pos": d_pos, "d_neg": d_neg, "tempo": stima_tempo_cai(dist, d_pos), "quote": q_arr}
                        else: st.error("❌ Rete interrotta.")
                elif not grafo_motore: st.error("Rete escursionistica mancante.")
                else: st.warning("Inserisci Partenza e Arrivo.")
        with c_reset:
            if st.button("🗑️ Svuota Tutto", use_container_width=True):
                st.session_state.itinerario_struttura = {"partenza": None, "tappe": [], "arrivo": None}
                for k in ["itinerario_attivo", "itinerario_metadati"]: st.session_state.pop(k, None)
                st.rerun()

        if meta := st.session_state.get("itinerario_metadati"):
            st.success(f"📈 **Distanza:** {meta['dist']} km | **D+** {meta['d_pos']} m / **D-** {meta['d_neg']} m | ⏱️ **Tempo Stimato:** {meta['tempo']}")
            if meta.get('quote'):
                if fig := disegna_profilo_altimetrico(meta['quote'], meta['dist'], "Profilo Altimetrico Calcolato (DTM)"): st.plotly_chart(fig, use_container_width=True)
            
            c1, c2 = st.columns(2)
            c1.download_button("📥 Scarica .GPX", data=genera_gpx(st.session_state.itinerario_attivo['geometry']['coordinates']), file_name="itinerario.gpx", mime="application/gpx+xml", use_container_width=True)

    m = folium.Map(location=[45.73, 7.32], zoom_start=9, tiles=None)
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Satellite (Esri)', overlay=False).add_to(m)
    folium.TileLayer('OpenStreetMap', name='Topografica (OSM)', overlay=False).add_to(m)
    plugins.Fullscreen(position='topleft').add_to(m)

    def col_st(s): return "#28a745" if s == "Visitato" else "#ffc107" if s == "Pianificato" else "#dc3545"

    def crea_popup_veloce(row):
        n, q, a, s = get_val(row, "name_it"), get_val(row, "ele"), get_val(row, "accesso"), get_val(row, "stato_visita", "Non visitato")
        link = get_val(row, "link1_href", "#")
        desc = get_val(row, "desc_it", "")
        lat, lon = row.geometry.y, row.geometry.x
        meteo_url = f"https://www.meteoblue.com/it/tempo/settimana/{round(lat, 4)}N{round(lon, 4)}E"
        
        return f"""
        <div style='font-family: sans-serif; font-size: 14px; min-width: 280px; color: #333;'>
            <h3 style='margin: 0 0 8px 0; color: #111;'>{n}</h3>
            <p style='margin: 4px 0;'><b>Quota:</b> {q} m | <b>Accesso:</b> {a}</p>
            <p style='margin: 4px 0;'><b>Stato:</b> <span style='color:{col_st(s)};font-weight:bold;'>{s.upper()}</span></p>
            <div style='margin: 12px 0;'>
                <a href="{link}" target="_blank" style="text-decoration: none; color: white; background-color: #0066cc; padding: 6px 12px; border-radius: 4px; font-size: 12px; margin-right: 5px; font-weight: bold; display: inline-block;">🔗 Sito Web</a>
                <a href="{meteo_url}" target="_blank" style="text-decoration: none; color: white; background-color: #ff6600; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; display: inline-block;">☀️ Meteo</a>
            </div>
            <hr style='border: 0; border-bottom: 1px solid #ccc; margin: 10px 0;'>
            <p style='margin: 0; font-size: 12px; line-height: 1.4; color: #444;'>{desc}</p>
        </div>
        """

    if st.session_state.get("sentieri") is not None:
        fg_s = folium.FeatureGroup(name="🥾 Rete Sentieristica", show=True)
        folium.GeoJson(st.session_state.sentieri, style_function=lambda x: {'color': '#2ca02c' if x['properties'].get('fclass')=='footway' else '#e65c00', 'weight': 2, 'dashArray': '6, 6', 'opacity': 0.8}, tooltip=folium.GeoJsonTooltip(fields=['name'], aliases=['Nome:']) if 'name' in st.session_state.sentieri.columns else None).add_to(fg_s)
        fg_s.add_to(m)

    if st.session_state.get("itinerario_attivo"):
        folium.GeoJson(st.session_state.itinerario_attivo['geometry'], style_function=lambda x: {'color': '#0055ff', 'weight': 5, 'opacity': 0.9}, name="📍 Traccia Calcolata").add_to(m)

    # Render Multiple GPX Tracks from Cloud Session
    if "tracce_gpx" in st.session_state:
        colori_gpx = ["#8e44ad", "#e74c3c", "#3498db", "#16a085", "#d35400", "#c0392b"]
        idx_colore = 0
        for nome_traccia, info in st.session_state.tracce_gpx.items():
            if info.get("visibile", True):
                colore = colori_gpx[idx_colore % len(colori_gpx)]
                stato_t = info["dati"].get("stato", "Pianificata")
                folium.PolyLine(
                    locations=info["dati"]["points"], 
                    color=colore, 
                    weight=5, 
                    opacity=0.8, 
                    tooltip=f"GPX: {nome_traccia} ({stato_t})", 
                    name=nome_traccia
                ).add_to(m)
                idx_colore += 1

    # Indicatori Partenza/Tappa/Arrivo
    for k, ic, col in [("partenza", "🛫", "#0055ff"), ("arrivo", "🛬", "#ff0000")]:
        if node := st.session_state.itinerario_struttura.get(k):
            folium.Marker([node[1], node[2]], tooltip=f"{k.upper()}: {node[0]}", icon=folium.DivIcon(html=f"<div style='background:{col}; width:45px; height:45px; border-radius:50%; border:3px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-size:22px; color:white;'>{ic}</div>", icon_size=(45, 45), icon_anchor=(22, 22))).add_to(m)

    for t in st.session_state.itinerario_struttura.get("tappe", []):
        folium.Marker([t[1], t[2]], tooltip=f"TAPPA: {t[0]}", icon=folium.DivIcon(html="<div style='background:#ff8800; width:40px; height:40px; border-radius:50%; border:3px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-size:18px; color:white;'>🛑</div>", icon_size=(40, 40), icon_anchor=(20, 20))).add_to(m)

    for _, r in mappa_bivacchi.iterrows(): folium.Marker([r.geometry.y, r.geometry.x], popup=folium.Popup(crea_popup_veloce(r)), tooltip=get_val(r, "name_it"), icon=folium.DivIcon(html=f"<div style='background:{col_st(get_val(r, 'stato_visita'))}; width:30px; height:30px; border-radius:50%; border:2px solid white; display:flex; align-items:center; justify-content:center; font-size:14px;'>⛺</div>", icon_size=(30, 30), icon_anchor=(15, 15))).add_to(m)
    for _, r in mappa_rifugi.iterrows(): folium.Marker([r.geometry.y, r.geometry.x], popup=folium.Popup(crea_popup_veloce(r)), tooltip=get_val(r, "name_it"), icon=folium.DivIcon(html=f"<div style='background:{col_st(get_val(r, 'stato_visita'))}; width:30px; height:30px; border-radius:6px; border:2px solid white; display:flex; align-items:center; justify-content:center; font-size:14px;'>🏠</div>", icon_size=(30, 30), icon_anchor=(15, 15))).add_to(m)

    # FIX LEGENDA: Color forced to #333 and #000 to prevent invisible text
    legend_template = """
    {% macro html(this, kwargs) %}
    <div style="position: fixed; bottom: 30px; left: 30px; width: 220px; z-index: 99999; background-color: rgba(255, 255, 255, 0.95); padding: 15px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); font-family: sans-serif; font-size: 12px; border: 1px solid #ccc; pointer-events: auto;">
        <b style="font-size: 14px; display: block; margin-bottom: 8px; border-bottom: 1px solid #ddd; padding-bottom: 4px; color: #000;">🗺️ Legenda</b>
        <div style="margin-bottom: 8px;">
            <span style="font-weight: bold; display: block; font-size: 10px; color: #666; text-transform: uppercase;">Tracciati</span>
            <div style="display: flex; align-items: center; margin-top: 4px;"><span style="border-top: 3px dashed #e65c00; width: 20px; display: inline-block; margin-right: 8px;"></span><span style="color: #333;">Sentiero</span></div>
            <div style="display: flex; align-items: center; margin-top: 4px;"><span style="border-top: 3px dashed #8c564b; width: 20px; display: inline-block; margin-right: 8px;"></span><span style="color: #333;">Sterrata</span></div>
            <div style="display: flex; align-items: center; margin-top: 4px;"><span style="border-top: 3px dashed #2ca02c; width: 20px; display: inline-block; margin-right: 8px;"></span><span style="color: #333;">Pedonale</span></div>
        </div>
        <div style="margin-bottom: 8px;">
            <span style="font-weight: bold; display: block; font-size: 10px; color: #666; text-transform: uppercase;">Strutture</span>
            <div style="display: flex; align-items: center; margin-top: 4px;"><div style="background-color: #999; width: 16px; height: 16px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 8px; font-size: 10px; color: white;">⛺</div><span style="color: #333;">Bivacco</span></div>
            <div style="display: flex; align-items: center; margin-top: 4px;"><div style="background-color: #999; width: 16px; height: 16px; border-radius: 4px; display: flex; align-items: center; justify-content: center; margin-right: 8px; font-size: 10px; color: white;">🏠</div><span style="color: #333;">Rifugio</span></div>
        </div>
        <div>
            <span style="font-weight: bold; display: block; font-size: 10px; color: #666; text-transform: uppercase;">Stato Visita</span>
            <div style="display: flex; align-items: center; margin-top: 4px;"><span style="background: #28a745; width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 8px;"></span><span style="color: #333;">Visitato</span></div>
            <div style="display: flex; align-items: center; margin-top: 4px;"><span style="background: #ffc107; width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 8px;"></span><span style="color: #333;">Pianificato</span></div>
            <div style="display: flex; align-items: center; margin-top: 4px;"><span style="background: #dc3545; width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 8px;"></span><span style="color: #333;">Non visitato</span></div>
        </div>
    </div>
    {% endmacro %}
    """
    macro = MacroElement()
    macro._template = Template(legend_template)
    m.get_root().add_child(macro)
    
    folium.LayerControl(position='topright').add_to(m)

    map_data = st_folium(m, width="100%", height=550, key="mappa_vda", returned_objects=["last_object_clicked_tooltip", "last_clicked"])

    n_cliccato, clk_t, clk_m = None, map_data.get("last_object_clicked_tooltip"), map_data.get("last_clicked")
    
    if clk_t and clk_t in dizionario_strutture:
        n_cliccato, (lat_n, lon_n, q_n) = clk_t, dizionario_strutture[clk_t]
    elif clk_m:
        lat_n, lon_n = clk_m['lat'], clk_m['lng']
        n_cliccato, q_n = f"Punto ({round(lat_n,4)}, {round(lon_n,4)})", 0
        dtm_sel = "DTM_vda.tif" if os.path.exists("DTM_vda.tif") else None
        if dtm_sel:
            try:
                with rasterio.open(dtm_sel) as ds: q_n = [v[0] for v in ds.sample([(lon_n, lat_n)])][0]
            except: pass

    if n_cliccato:
        st.markdown("---")
        ci, cm = st.columns([1.5, 1])
        with ci:
            st.markdown(f"### 📍 `{n_cliccato}` (Quota: {round(q_n)}m)")
            cp, ct, ca = st.columns(3)
            if cp.button("🛫 Partenza", use_container_width=True): st.session_state.itinerario_struttura["partenza"] = (n_cliccato, lat_n, lon_n, q_n); st.rerun()
            if ct.button("🛑 Tappa", use_container_width=True) and (n_cliccato, lat_n, lon_n, q_n) not in st.session_state.itinerario_struttura["tappe"]: st.session_state.itinerario_struttura["tappe"].append((n_cliccato, lat_n, lon_n, q_n)); st.rerun()
            if ca.button("🛬 Arrivo", use_container_width=True): st.session_state.itinerario_struttura["arrivo"] = (n_cliccato, lat_n, lon_n, q_n); st.rerun()

            if clk_t:
                st.session_state.struttura_attiva = clk_t
                st_corr = next((r["stato_visita"] for df in [st.session_state.bivacchi, st.session_state.rifugi] for _, r in df.iterrows() if r["name_it"] == clk_t), "Non visitato")
                st.selectbox("Modifica stato cloud:", options=stati_disponibili, index=stati_disponibili.index(st_corr), key="quick_edit_selectbox", on_change=autosave_quick_edit)

            st.markdown("#### 🎯 Radar Esplorazione")
            distanze = []
            for nome_str, (lat_s, lon_s, q_s) in dizionario_strutture.items():
                if nome_str != n_cliccato:
                    d = calcola_distanza_haversine(lon_n, lat_n, lon_s, lat_s)
                    distanze.append((nome_str, d, q_s))
            
            distanze.sort(key=lambda x: x[1])
            for i, (nm, d, q) in enumerate(distanze[:3]):
                dist_txt = f"{round(d*1000)} m" if d < 1 else f"{round(d, 1)} km"
                st.markdown(f"**{i+1}. {nm}** ({round(q)}m) a 📏 {dist_txt}")

        with cm:
            st.markdown("🌤️ **Previsioni a 3 giorni**")
            with st.spinner("Cerco..."):
                if prev := get_previsioni_meteo(lat_n, lon_n):
                    for i in range(3):
                        data_str = "Oggi" if i==0 else "Domani" if i==1 else datetime.strptime(prev['time'][i], "%Y-%m-%d").strftime("%d/%m")
                        st.markdown(f"**{data_str}:** {mappa_meteo_emoji(prev['weathercode'][i])} | {prev['temperature_2m_max'][i]}°C / {prev['temperature_2m_min'][i]}°C")
                else: st.caption("Meteo non disponibile.")
                
            st.markdown("#### 🌐 Smart Links Community")
            bb_offset = 0.02
            url_wikiloc = f"https://it.wikiloc.com/percorsi/outdoor?t=&d=&lfr=&lto=&a=outdoor&q=&s=id&f=&u=0&k=1&m=&p=&act=&n=&c=&map={lat_n-bb_offset},{lon_n-bb_offset},{lat_n+bb_offset},{lon_n+bb_offset},4&rd=1"
            st.link_button("🟢 Cerca in area su Wikiloc", url=url_wikiloc, use_container_width=True)
            
            url_komoot = f"https://www.komoot.com/it-it/discover/Location/@{lat_n},{lon_n}/tours?sport=hike"
            st.link_button("🌲 Cerca in area su Komoot", url=url_komoot, use_container_width=True)
            
            url_gulliver = f"https://www.gulliver.it/?s={n_cliccato.replace(' ', '+')}" if clk_t else "https://www.gulliver.it/itinerari/?paese=italia&regione=valle-daosta"
            st.link_button("🏔️ Cerca su Gulliver", url=url_gulliver, use_container_width=True)

with tab_registri:
    st.subheader(f"Database interattivo di {st.session_state.profilo_attivo}")
    
    # KPI DASHBOARD (Indented properly)
    tot_biv = len(st.session_state.bivacchi)
    vis_biv = len(st.session_state.bivacchi[st.session_state.bivacchi['stato_visita'] == 'Visitato'])
    plan_biv = len(st.session_state.bivacchi[st.session_state.bivacchi['stato_visita'] == 'Pianificato'])
    
    tot_rif = len(st.session_state.rifugi)
    vis_rif = len(st.session_state.rifugi[st.session_state.rifugi['stato_visita'] == 'Visitato'])
    plan_rif = len(st.session_state.rifugi[st.session_state.rifugi['stato_visita'] == 'Pianificato'])
    
    st.markdown(f"""
    <div style="display: flex; gap: 20px; margin-bottom: 20px;">
        <div style="flex: 1; background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-top: 4px solid #6c757d; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <h4 style="margin-top: 0; text-align: center; color: #333;">⛺ Riepilogo Bivacchi</h4>
            <div style="display: flex; justify-content: space-around; margin-top: 10px;">
                <div style="text-align: center;"><b style="color: #007bff; font-size: 20px;">{tot_biv}</b><br><span style="color:#555;">Totali</span></div>
                <div style="text-align: center;"><b style="color: #28a745; font-size: 20px;">{vis_biv}</b><br><span style="color:#555;">Visitati</span></div>
                <div style="text-align: center;"><b style="color: #ffc107; font-size: 20px;">{plan_biv}</b><br><span style="color:#555;">Pianificati</span></div>
            </div>
        </div>
        <div style="flex: 1; background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-top: 4px solid #6c757d; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <h4 style="margin-top: 0; text-align: center; color: #333;">🏠 Riepilogo Rifugi</h4>
            <div style="display: flex; justify-content: space-around; margin-top: 10px;">
                <div style="text-align: center;"><b style="color: #007bff; font-size: 20px;">{tot_rif}</b><br><span style="color:#555;">Totali</span></div>
                <div style="text-align: center;"><b style="color: #28a745; font-size: 20px;">{vis_rif}</b><br><span style="color:#555;">Visitati</span></div>
                <div style="text-align: center;"><b style="color: #ffc107; font-size: 20px;">{plan_rif}</b><br><span style="color:#555;">Pianificati</span></div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Colonne in minuscolo standardizzato
    colonne_desiderate = ["name_it", "ele", "accesso", "stato_visita"]
    cb = [c for c in colonne_desiderate if c in st.session_state.bivacchi.columns]
    cr = [c for c in colonne_desiderate if c in st.session_state.rifugi.columns]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### ⛺ Bivacchi")
        st.data_editor(st.session_state.bivacchi[cb], column_config={"stato_visita": st.column_config.SelectboxColumn("Stato", options=stati_disponibili, required=True)}, use_container_width=True, hide_index=True, key="editor_b", on_change=lambda: sync_tables_cloud("bivacchi", "editor_b"))
    with col2:
        st.markdown("### 🏠 Rifugi")
        st.data_editor(st.session_state.rifugi[cr], column_config={"stato_visita": st.column_config.SelectboxColumn("Stato", options=stati_disponibili, required=True)}, use_container_width=True, hide_index=True, key="editor_r", on_change=lambda: sync_tables_cloud("rifugi", "editor_r"))