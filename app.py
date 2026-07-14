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
from PIL import Image
import io
import uuid
import warnings

# Ignoriamo i warning innocui di Geopandas/Pyogrio sugli ID duplicati nei GeoJSON
warnings.filterwarnings("ignore", message=".*Several features with id.*")

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

def fetch_profili_esistenti():
    try: return sorted([row['utente'] for row in supabase.table("utenti_credenziali").select("utente").execute().data if row.get('utente')])
    except: return []

def verifica_password(utente, password_inserita):
    try:
        res = supabase.table("utenti_credenziali").select("*").eq("utente", utente).execute()
        if res.data and res.data[0]["password"] == password_inserita:
            return True, res.data[0].get("pin_recupero")
        return False, None
    except: return False, None

def registra_nuovo_utente(utente, password, pin):
    try: 
        return supabase.table("utenti_credenziali").insert({
            "utente": utente, 
            "password": password,
            "pin_recupero": pin
        }).execute() is not None
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

def comprimi_e_salva_foto(file_uploader_objects):
    urls = []
    for file in file_uploader_objects:
        try:
            img = Image.open(file)
            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
            
            img.thumbnail((1024, 1024))
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=75)
            img_bytes = img_byte_arr.getvalue()
            
            nome_file = f"{uuid.uuid4().hex}.jpg"
            
            supabase.storage.from_("foto_tracce").upload(path=nome_file, file=img_bytes, file_options={"content-type": "image/jpeg"})
            url_pubblico = supabase.storage.from_("foto_tracce").get_public_url(nome_file)
            urls.append(url_pubblico)
        except Exception as e:
            st.error(f"Errore caricamento foto {file.name}: {e}")
    return urls

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
        res = supabase.table("tracce_gpx").select("id").eq("utente", utente).eq("nome", nome).execute()
        if res.data:
            supabase.table("tracce_gpx").update({"descrizione": descrizione, "visibile": visibile, "dati_json": dati_puliti}).eq("id", res.data[0]["id"]).execute()
        else:
            supabase.table("tracce_gpx").insert({"utente": utente, "nome": nome, "descrizione": descrizione, "visibile": visibile, "dati_json": dati_puliti}).execute()
        return True
    except Exception as e:
        st.error(f"Errore salvataggio GPX in cloud: {e}")
        return False

def rinomina_traccia_gpx(utente, vecchio_nome, nuovo_nome):
    try:
        res = supabase.table("tracce_gpx").select("id").eq("utente", utente).eq("nome", vecchio_nome).execute()
        if res.data:
            supabase.table("tracce_gpx").update({"nome": nuovo_nome}).eq("id", res.data[0]["id"]).execute()
            return True
        return False
    except Exception as e:
        return False

@st.cache_data(ttl=30)
def fetch_community_tracks():
    try:
        res = supabase.table("tracce_gpx").select("*").execute()
        shared = [row for row in res.data if row.get("dati_json", {}).get("condivisa", False)]
        shared.sort(key=lambda x: x.get("dati_json", {}).get("data_svolgimento", ""), reverse=True)
        return shared
    except:
        return []

def fetch_feedback_admin():
    try:
        res = supabase.table("feedback_utenti").select("*").order("created_at", desc=True).execute()
        return res.data
    except:
        return []

def delete_feedback_admin(id_fb):
    try:
        supabase.table("feedback_utenti").delete().eq("id", id_fb).execute()
        return True
    except:
        return False

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
    
    # Saldatura topologica locale con KDTree
    pairs = albero.query_pairs(r=0.00027)
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

if os.path.exists("immagine_app.jpeg"): st.sidebar.image("immagine_app.jpeg", use_container_width=True)

st.sidebar.markdown("### 👤 Profilo Utente")
lista_profili = fetch_profili_esistenti()

if "autenticato" not in st.session_state: st.session_state.autenticato = False
if "itinerario_struttura" not in st.session_state: st.session_state.itinerario_struttura = {"partenza": None, "tappe": [], "arrivo": None}

tab_login, tab_reg = st.sidebar.tabs(["🔑 Accedi", "📝 Registrati"])

with tab_login:
    profilo_input = st.text_input("Cerca o digita il tuo profilo:")

    if profilo_input:
        match = [p for p in lista_profili if p.lower().startswith(profilo_input.lower())]
        if match:
            scelta = st.radio("Profili trovati:", match)
            st.session_state.profilo_attivo = scelta
        else:
            st.info("Profilo non trovato.")
            st.session_state.profilo_attivo = None

    if st.session_state.get("profilo_attivo") and not st.session_state.autenticato:
        if pwd := st.text_input(f"Inserisci la password per {st.session_state.profilo_attivo}:", type="password", key="pass_field"):
            valido, pin_esistente = verifica_password(st.session_state.profilo_attivo, pwd)
            if valido:
                if not pin_esistente:
                    st.warning("⚠️ Aggiornamento di Sicurezza")
                    st.markdown("Per proteggere il tuo account, imposta un PIN Segreto per il recupero della password.")
                    nuovo_pin = st.text_input("Scegli un PIN Segreto", type="password", key="new_pin_upgrade")
                    if st.button("Salva PIN e Accedi"):
                        if nuovo_pin:
                            supabase.table("utenti_credenziali").update({"pin_recupero": nuovo_pin}).eq("utente", st.session_state.profilo_attivo).execute()
                            st.session_state.autenticato = True
                            st.success("PIN salvato! Accesso eseguito.")
                            st.rerun()
                        else:
                            st.error("Inserisci un PIN valido.")
                else:
                    st.session_state.autenticato = True
                    st.toast("🔓 Accesso eseguito!", icon="🔑")
                    st.rerun()
            else: st.error("❌ Password errata!")

    with st.expander("Hai dimenticato la password?"):
        st.markdown("Reimposta la tua password usando il tuo PIN segreto.")
        rec_nome = st.text_input("Nome del Profilo da recuperare")
        rec_pin = st.text_input("Il tuo PIN segreto", type="password")
        rec_nuova_pass = st.text_input("Scegli una Nuova Password", type="password")
        
        if st.button("Reimposta Password"):
            if rec_nome and rec_pin and rec_nuova_pass:
                try:
                    response = supabase.table("utenti_credenziali").select("*").eq("utente", rec_nome).eq("pin_recupero", rec_pin).execute()
                    if len(response.data) > 0:
                        supabase.table("utenti_credenziali").update({"password": rec_nuova_pass}).eq("utente", rec_nome).execute()
                        st.success("Password aggiornata con successo! Ora puoi fare il login.")
                    else:
                        st.error("Nome profilo o PIN segreto errati.")
                except Exception as e:
                    st.error("Errore durante il recupero.")
            else:
                st.warning("Compila tutti i campi per reimpostare la password.")

with tab_reg:
    st.markdown("### Crea un nuovo profilo")
    nome_nuovo = st.text_input("Nome Profilo", placeholder="Nome completo...")
    password_nuova = st.text_input("Imposta una password", type="password")
    pin_sicurezza = st.text_input("PIN Segreto (serve per recuperare la password!)", type="password")
    
    if st.button("Inizializza Profilo"):
        if nome_nuovo.strip() and password_nuova.strip() and pin_sicurezza.strip():
            p_fmt = nome_nuovo.strip().title()
            if p_fmt in lista_profili: 
                st.error("❌ Profilo già esistente!")
            elif registra_nuovo_utente(p_fmt, password_nuova.strip(), pin_sicurezza.strip()):
                st.session_state.profilo_attivo, st.session_state.autenticato = p_fmt, True
                if "dati_caricati" in st.session_state: del st.session_state["dati_caricati"]
                st.success("Profilo creato! Ora sei loggato.")
                st.rerun()
        else:
            st.error("Compila tutti i campi, incluso il PIN di sicurezza.")

if not st.session_state.get("profilo_attivo") or not st.session_state.autenticato:
    st.info("👈 Digita il tuo profilo per accedere o creane uno nuovo.")
    st.stop()

if st.session_state.get("autenticato"):
    st.sidebar.divider()
    with st.sidebar.expander("⚙️ Impostazioni Account"):
        st.markdown("**Cambio Password**")
        vecchia_pwd = st.text_input("Password attuale", type="password")
        nuova_pwd = st.text_input("Nuova password", type="password")
        if st.button("Aggiorna Password", width="stretch"):
            if verifica_password(st.session_state.profilo_attivo, vecchia_pwd)[0]:
                supabase.table("utenti_credenziali").update({"password": nuova_pwd}).eq("utente", st.session_state.profilo_attivo).execute()
                st.success("Password aggiornata!")
            else:
                st.error("Password attuale errata.")
        
        st.divider()
        st.markdown("**Zona Pericolosa**")
        conferma_eliminazione = st.checkbox("Sono sicuro di voler eliminare il mio profilo e i miei dati.")
        if st.button("🗑️ Elimina Profilo Definitivamente", type="primary", disabled=not conferma_eliminazione, width="stretch"):
            try:
                supabase.table("utenti_credenziali").delete().eq("utente", st.session_state.profilo_attivo).execute()
                st.session_state.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Errore durante l'eliminazione: {e}")

    with st.sidebar.expander("📣 Feedback & Suggerimenti"):
        st.markdown("Hai trovato un bug o hai un'idea per migliorare l'app? Faccelo sapere!")
        tipo_fb = st.selectbox("Tipo:", ["Suggerimento", "Problema/Bug", "Altro"])
        testo_fb = st.text_area("Il tuo messaggio:")
        if st.button("Invia Messaggio", width="stretch"):
            if testo_fb:
                try:
                    supabase.table("feedback_utenti").insert({"utente": st.session_state.profilo_attivo, "tipo": tipo_fb, "testo": testo_fb}).execute()
                    st.success("Grazie! Il tuo feedback è stato inviato a Fabrizio.")
                except Exception as e:
                    st.warning("Servizio DB temporaneamente non disponibile. Scrivici una mail!")
                    st.markdown(f"[📩 Invia via Mail (Clicca qui)](mailto:feedback@vda-explorer.com?subject=Feedback:{tipo_fb}&body={testo_fb})")
            else:
                st.error("Il testo non può essere vuoto.")

st.sidebar.markdown("---")
stati_disponibili = ["Non visitato", "Pianificato", "Visitato"]
stati_selezionati = st.sidebar.multiselect("Filtra Mappa per Stato:", options=stati_disponibili, default=stati_disponibili)

st.sidebar.markdown("<br><br>", unsafe_allow_html=True)
st.sidebar.markdown("""
<div style="background-color: #1e293b; padding: 15px; border-radius: 8px; border-left: 5px solid #3b82f6; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
    <h5 style="margin-top: 0; color: #f8fafc; font-size: 15px; font-weight: 600;">💡 Guida Rapida</h5>
    <ul style="margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.6; color: #cbd5e1;">
        <li><b>Mappa:</b> Clicca sulle strutture per info, sito web, meteo ed edita lo stato. Radar esplorazione attivo!</li>
        <li><b>Itinerari:</b> Assegna punti sulla mappa per calcolare percorsi e DTM. Salva la traccia in archivio.</li>
        <li><b>GPX & Community:</b> Archivio tracce, modifica manuale e condivisione pubblica con foto.</li>
    </ul>
</div>
<div style="font-size: 13px; color: #555; background-color: #f8f9fa; padding: 10px; border-radius: 5px; border-left: 4px solid #333; margin-bottom: 15px;">
    <b>App Rifugi & Bivacchi VdA</b><br>Versione: 7.3<br>Autore: Nori Fabrizio
</div>
""", unsafe_allow_html=True)

with st.sidebar.expander("🆕 Changelog & Novità", expanded=False):
    st.markdown("""
    **Versione 7.3**
    * 👑 **Admin Mode:** Pannello nascosto per la gestione dei feedback utenti.
    * ✏️ **Editor Tracce GPX:** Ora puoi inviare un tuo GPX sulla mappa, regolarlo e "snapparlo" ai sentieri ufficiali!
    * 💾 **Salva Itinerario:** Puoi salvare nel tuo profilo le tracce create dalla mappa.
    * 📣 **Feedback In-App:** Segnala bug o idee tramite l'apposito menu.
    """)

if "dati_caricati" not in st.session_state:
    stati_cloud = fetch_stati_dal_db(st.session_state.profilo_attivo)
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

# Controllo Admin
is_admin = st.session_state.get("profilo_attivo", "").strip().lower() in ["fabrizio", "fabrizio nori", "nori fabrizio", "bizzietto"]

# Tabs dinamici
tabs_names = ["🗺️ Mappa & Itinerari", "📊 Registri", "📂 Archivio GPX", "🌐 Community"]
if is_admin:
    tabs_names.append("👑 Pannello Admin")

tabs = st.tabs(tabs_names)
tab_mappa, tab_registri, tab_gpx, tab_community = tabs[0], tabs[1], tabs[2], tabs[3]

if is_admin:
    tab_admin = tabs[4]
    with tab_admin:
        st.subheader("👑 Pannello di Controllo Riservato")
        st.markdown("Benvenuto Fabrizio! Qui puoi leggere e gestire i feedback inviati dagli utenti.")
        
        if st.button("🔄 Ricarica Feedback", width="content"):
            st.rerun()

        feedbacks = fetch_feedback_admin()
        
        if not feedbacks:
            st.info("Nessun feedback presente nel database al momento.")
        else:
            for fb in feedbacks:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    data_fb = fb.get("created_at", "")[:10] if fb.get("created_at") else "Data N/D"
                    c1.markdown(f"**Utente:** {fb.get('utente', 'Sconosciuto')} | **Tipo:** {fb.get('tipo', 'N/D')} | **Data:** {data_fb}")
                    c1.markdown(f"> *{fb.get('testo', '')}*")
                    
                    if c2.button("🗑️ Segna Risolto (Elimina)", key=f"del_fb_{fb.get('id')}", width="stretch"):
                        if delete_feedback_admin(fb.get("id")):
                            st.toast("Feedback eliminato!", icon="✅")
                            st.rerun()
                        else:
                            st.error("Errore durante l'eliminazione.")

with tab_gpx:
    st.subheader("📂 Il tuo Archivio GPX Personale")
    st.markdown("Carica i tuoi file GPX. Verranno salvati nel tuo profilo cloud in modo permanente. Rinomina, descrivi e scegli se condividerli con la Community (anche con Foto!).")
    
    if "tracce_gpx" in st.session_state and st.session_state.tracce_gpx:
        st.info(f"📊 **Totale Tracce nel tuo archivio:** {len(st.session_state.tracce_gpx)}")
    
    st.markdown("#### ⚙️ Impostazioni Caricamento GPX")
    st.caption("Il calcolo dei chilometri e del dislivello viene effettuato con la massima precisione sui dati grezzi, per poi ottimizzare e salvare il file limitando i rallentamenti.")
    tipo_comp = st.radio(
        "Scegli il metodo di compressione file:",
        ["Distanza (1 punto ogni 25m)", "Distanza (1 punto ogni 50m)", "Bilanciato (Max 500 punti)", "Originale (Nessuna)"],
        horizontal=True,
        label_visibility="collapsed"
    )

    uploaded_files = st.file_uploader("Trascina o seleziona una o più tracce .gpx", type=["gpx"], accept_multiple_files=True)

    if uploaded_files:
        tracce_aggiunte = False
        for uploaded_gpx in uploaded_files:
            content = uploaded_gpx.getvalue()
            if len(content) > 0:
                base_nome = uploaded_gpx.name.replace(".gpx", "")
                
                if base_nome not in st.session_state.tracce_gpx:
                    try:
                        try: gpx_string = content.decode('utf-8')
                        except UnicodeDecodeError: gpx_string = content.decode('ISO-8859-1')
                        
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
                        
                        # Downsampling (ottimizzazione dati salvati su DB)
                        if "Distanza" in tipo_comp and len(pts) > 2:
                            soglia = 25 if "25m" in tipo_comp else 50
                            new_pts, new_quote = [pts[0]], [quote[0]] if quote else []
                            last_p = pts[0]
                            for i in range(1, len(pts)):
                                d_m = calcola_distanza_haversine(last_p[1], last_p[0], pts[i][1], pts[i][0]) * 1000
                                if d_m >= soglia:
                                    new_pts.append(pts[i])
                                    if quote: new_quote.append(quote[i])
                                    last_p = pts[i]
                            pts, quote = new_pts, new_quote
                        
                        elif "Bilanciato" in tipo_comp:
                            max_punti = 500
                            if len(pts) > max_punti:
                                step = len(pts) // max_punti
                                pts = pts[::step]
                                if quote: quote = quote[::step]

                        dati_gpx = {"points": pts, "quote": quote, "dist": round(dist, 2), "d_pos": round(d_pos), "d_neg": round(d_neg), "stato": "Pianificata", "condivisa": False, "foto": []}
                        
                        st.session_state.tracce_gpx[base_nome] = {"descrizione": "", "visibile": True, "dati": dati_gpx}
                        salva_traccia_gpx(st.session_state.profilo_attivo, base_nome, "", True, dati_gpx)
                        tracce_aggiunte = True
                    except Exception as e: st.error(f"Errore decodifica GPX {base_nome}: {e}")
        
        if tracce_aggiunte:
            st.rerun()

    st.markdown("---")
    
    if st.session_state.get("tracce_gpx"):
        for nome_traccia, info in list(st.session_state.tracce_gpx.items()):
            stato_traccia = info["dati"].get("stato", "Pianificata")
            icona_stato = "✅" if stato_traccia == "Svolta" else "⏳"
            
            with st.expander(f"{icona_stato} 🗺️ {nome_traccia}", expanded=False):
                c_ren, c_btn = st.columns([3, 1])
                nuovo_nome = c_ren.text_input("Nuovo nome traccia:", value=nome_traccia, key=f"ren_{nome_traccia}", label_visibility="collapsed")
                if c_btn.button("✏️ Rinomina", key=f"btn_ren_{nome_traccia}", width="stretch"):
                    if nuovo_nome != nome_traccia and nuovo_nome.strip() != "":
                        if rinomina_traccia_gpx(st.session_state.profilo_attivo, nome_traccia, nuovo_nome):
                            st.session_state.tracce_gpx[nuovo_nome] = st.session_state.tracce_gpx.pop(nome_traccia)
                            st.rerun()
                
                # Strumenti Traccia Avanzati (Editor su Mappa)
                st.markdown("#### 🛠️ Strumenti Traccia")
                c_mod, c_dl = st.columns(2)
                with c_mod:
                    if st.button("✏️ Modifica e Adatta su Mappa", key=f"edit_plan_{nome_traccia}", width="stretch"):
                        pts = info["dati"].get("points", [])
                        if len(pts) >= 2:
                            # Prendiamo il primo, l'ultimo e un paio di punti centrali per abbozzare le tappe
                            start = (f"Inizio ({nome_traccia})", pts[0][0], pts[0][1], 0)
                            end = (f"Fine ({nome_traccia})", pts[-1][0], pts[-1][1], 0)
                            tappe = []
                            if len(pts) > 40:
                                step = len(pts) // 4
                                for i in range(1, 4):
                                    tappe.append((f"Tappa {i} ({nome_traccia})", pts[i*step][0], pts[i*step][1], 0))
                            st.session_state.itinerario_struttura = {"partenza": start, "tappe": tappe, "arrivo": end}
                            st.toast("Traccia inviata al Pianificatore! Vai alla Mappa per ricalcolarla sui sentieri ufficiali.", icon="🧭")
                        else:
                            st.error("La traccia non ha abbastanza punti per essere modificata.")
                
                with c_dl:
                    st.download_button(
                        "📥 Scarica questo GPX", 
                        data=genera_gpx([(p[1], p[0]) for p in info["dati"]["points"]], nome_traccia), 
                        file_name=f"{nome_traccia}.gpx", 
                        mime="application/gpx+xml", 
                        key=f"dl_{nome_traccia}",
                        width="stretch"
                    )

                st.markdown("<br>", unsafe_allow_html=True)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Distanza", f"{info['dati']['dist']} km")
                c2.metric("Dislivello +", f"D+ {info['dati']['d_pos']} m")
                c3.metric("Dislivello -", f"D- {info['dati']['d_neg']} m")
                
                visibile = c4.toggle("Mostra in Mappa", value=info.get("visibile", True), key=f"vis_{nome_traccia}")
                if visibile != info.get("visibile", True):
                    st.session_state.tracce_gpx[nome_traccia]["visibile"] = visibile
                    salva_traccia_gpx(st.session_state.profilo_attivo, nome_traccia, info.get("descrizione", ""), visibile, info["dati"])
                    st.rerun()

                c_stato, c_desc = st.columns([1, 2])
                with c_stato:
                    nuovo_stato = st.selectbox("Stato Personale:", ["Pianificata", "Svolta"], index=0 if stato_traccia=="Pianificata" else 1, key=f"stato_{nome_traccia}")
                    if nuovo_stato != stato_traccia:
                        st.session_state.tracce_gpx[nome_traccia]["dati"]["stato"] = nuovo_stato
                        salva_traccia_gpx(st.session_state.profilo_attivo, nome_traccia, info.get("descrizione", ""), info.get("visibile", True), st.session_state.tracce_gpx[nome_traccia]["dati"])
                        st.rerun()

                with c_desc:
                    desc = st.text_area("Appunti Personali:", value=info.get("descrizione", ""), key=f"desc_{nome_traccia}", label_visibility="collapsed")
                    if desc != info.get("descrizione", ""):
                        st.session_state.tracce_gpx[nome_traccia]["descrizione"] = desc
                        salva_traccia_gpx(st.session_state.profilo_attivo, nome_traccia, desc, info.get("visibile", True), info["dati"])

                st.markdown("---")
                st.markdown("#### 🌐 Condivisione Community & Foto")
                is_shared = info["dati"].get("condivisa", False)
                condivisa_toggle = st.toggle("Condividi questa traccia pubblicamente", value=is_shared, key=f"share_{nome_traccia}")
                
                if condivisa_toggle:
                    sd = info["dati"].get("data_svolgimento")
                    def_date = datetime.strptime(sd, "%Y-%m-%d").date() if sd else datetime.today().date()
                    data_sv = st.date_input("Data svolgimento:", value=def_date, key=f"date_{nome_traccia}")
                    
                    lista_strutture = list(dizionario_strutture.keys())
                    strutture_visitate = st.multiselect("Strutture visitate in questo giro:", options=lista_strutture, default=info["dati"].get("strutture_visitate", []), key=f"strut_{nome_traccia}")
                    
                    desc_pubblica = st.text_area("Racconto o info utili per la Community:", value=info["dati"].get("descrizione_pubblica", ""), key=f"desc_pub_{nome_traccia}")
                    
                    foto_caricate = st.file_uploader("Aggiungi foto alla traccia (Max 1024px automatico)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True, key=f"foto_{nome_traccia}")
                    foto_esistenti = info["dati"].get("foto", [])
                    if foto_esistenti:
                        st.caption(f"📸 {len(foto_esistenti)} foto attualmente condivise.")

                    c_agg, c_del = st.columns([3, 1])
                    if c_agg.button("💾 Aggiorna Dati di Condivisione", key=f"btn_share_{nome_traccia}", type="primary", width="stretch"):
                        with st.spinner("Salvataggio e caricamento foto in corso (potrebbe volerci qualche istante)..."):
                            nuove_foto_urls = []
                            if foto_caricate: nuove_foto_urls = comprimi_e_salva_foto(foto_caricate)
                            tutte_le_foto = foto_esistenti + nuove_foto_urls
                            st.session_state.tracce_gpx[nome_traccia]["dati"]["condivisa"] = True
                            st.session_state.tracce_gpx[nome_traccia]["dati"]["data_svolgimento"] = data_sv.strftime("%Y-%m-%d")
                            st.session_state.tracce_gpx[nome_traccia]["dati"]["strutture_visitate"] = strutture_visitate
                            st.session_state.tracce_gpx[nome_traccia]["dati"]["descrizione_pubblica"] = desc_pubblica
                            st.session_state.tracce_gpx[nome_traccia]["dati"]["foto"] = tutte_le_foto
                            salva_traccia_gpx(st.session_state.profilo_attivo, nome_traccia, info["descrizione"], info["visibile"], st.session_state.tracce_gpx[nome_traccia]["dati"])
                            st.success("Condivisione e foto aggiornate con successo!")
                            st.rerun()

                    if foto_esistenti and c_del.button("🗑️ Rimuovi Foto", key=f"btn_del_foto_{nome_traccia}", width="stretch"):
                        st.session_state.tracce_gpx[nome_traccia]["dati"]["foto"] = []
                        salva_traccia_gpx(st.session_state.profilo_attivo, nome_traccia, info["descrizione"], info["visibile"], st.session_state.tracce_gpx[nome_traccia]["dati"])
                        st.rerun()
                else:
                    if is_shared:
                        st.session_state.tracce_gpx[nome_traccia]["dati"]["condivisa"] = False
                        salva_traccia_gpx(st.session_state.profilo_attivo, nome_traccia, info["descrizione"], info["visibile"], st.session_state.tracce_gpx[nome_traccia]["dati"])
                        st.rerun()

                if info["dati"].get("quote"):
                    fig_gpx = disegna_profilo_altimetrico(info["dati"]["quote"], info["dati"]["dist"], "Profilo Altimetrico")
                    if fig_gpx: st.plotly_chart(fig_gpx, width="stretch", key=f"plot_gpx_{nome_traccia}")
                    
                if st.button("❌ Elimina definitivamente la traccia", key=f"del_{nome_traccia}"):
                    try:
                        supabase.table("tracce_gpx").delete().eq("utente", st.session_state.profilo_attivo).eq("nome", nome_traccia).execute()
                        del st.session_state.tracce_gpx[nome_traccia]
                        st.rerun()
                    except Exception as e: st.error(f"Errore eliminazione: {e}")

with tab_community:
    st.subheader("🌐 Feed Tracce della Community")
    st.markdown("Esplora gli itinerari, i racconti e le foto condivise pubblicamente dagli altri esploratori.")
    
    with st.spinner("Caricamento tracce condivise..."):
        tracce_feed = fetch_community_tracks()
        
        if not tracce_feed:
            st.info("Nessuna traccia condivisa al momento. Sii il primo a condividerne una dal tuo Archivio GPX!")
        else:
            for t in tracce_feed:
                dati = t.get("dati_json", {})
                with st.container(border=True):
                    st.markdown(f"<h3 style='color: #0055ff; margin-bottom:0;'>🚶‍♂️ {t['nome']}</h3>", unsafe_allow_html=True)
                    st.markdown(f"**Esploratore:** <span style='color:#28a745; font-weight:bold;'>{t['utente']}</span> | 📅 **Data:** `{dati.get('data_svolgimento', 'N/D')}`", unsafe_allow_html=True)
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Distanza", f"{dati.get('dist', 0)} km")
                    c2.metric("Dislivello +", f"D+ {dati.get('d_pos', 0)} m")
                    c3.metric("Dislivello -", f"D- {dati.get('d_neg', 0)} m")
                    
                    desc_pub = dati.get("descrizione_pubblica", "")
                    if desc_pub:
                        st.markdown(f"<div style='background-color:rgba(130, 130, 130, 0.1); padding:15px; border-left:4px solid #0055ff; font-style:italic; border-radius:4px; color:inherit;'>{desc_pub}</div>", unsafe_allow_html=True)
                    
                    strutture = dati.get("strutture_visitate", [])
                    if strutture:
                        st.markdown(f"<br>⛺ **Strutture Toccate:** " + ", ".join([f"<span style='color:#16a085; font-weight:bold;'>{s}</span>" for s in strutture]), unsafe_allow_html=True)
                    
                    foto_urls = dati.get("foto", [])
                    if foto_urls:
                        st.markdown("<br>📸 **Galleria Fotografica:** <span style='font-size: 12px; color: #888;'>(Clicca sulle foto per ingrandirle)</span>", unsafe_allow_html=True)
                        cols = st.columns(5)
                        for i, url in enumerate(foto_urls):
                            with cols[i % 5]: st.image(url, width="stretch")

                    if dati.get("quote"):
                        fig_gpx_comm = disegna_profilo_altimetrico(dati["quote"], dati.get("dist", 0), "Altimetria dell'itinerario")
                        if fig_gpx_comm: st.plotly_chart(fig_gpx_comm, width="stretch", key=f"plot_comm_{t.get('id', uuid.uuid4().hex)}")
                    
                    if dati.get("points"):
                        lats = [p[0] for p in dati['points']]
                        lons = [p[1] for p in dati['points']]
                        fig_map = go.Figure(go.Scattermap(lat=lats, lon=lons, mode="lines", line=dict(width=4, color="#e63946")))
                        fig_map.update_layout(
                            map_style="open-street-map",
                            map_center={"lat": sum(lats)/len(lats), "lon": sum(lons)/len(lons)},
                            map_zoom=10,
                            margin={"r":0,"t":0,"l":0,"b":0},
                            height=300
                        )
                        st.plotly_chart(fig_map, width="stretch", key=f"map_comm_{t.get('id', uuid.uuid4().hex)}")

                    # Sistema di Applausi (Kudos) e visualizzazione nomi
                    st.divider()
                    kudos = dati.get("kudos", [])
                    has_kudo = st.session_state.profilo_attivo in kudos
                    c_kudo, c_names = st.columns([1, 3])
                    
                    with c_kudo:
                        # Cambio stile se ha già applaudito per suggerire la rimozione
                        kudo_label = f"❤️ Rimuovi Applauso" if has_kudo else f"👏 Applaudi ({len(kudos)})"
                        if st.button(kudo_label, key=f"kudo_{t.get('id', t['nome'])}", width="stretch"):
                            if has_kudo: kudos.remove(st.session_state.profilo_attivo)
                            else: kudos.append(st.session_state.profilo_attivo)
                            dati["kudos"] = kudos
                            try:
                                supabase.table("tracce_gpx").update({"dati_json": dati}).eq("id", t["id"]).execute()
                                st.rerun()
                            except Exception as e: st.error("Errore nel salvataggio dell'applauso.")
                    
                    with c_names:
                        if kudos:
                            st.markdown(f"<div style='font-size: 13px; color: #555; margin-top: 8px;'><b>👏 Apprezzato da:</b> {', '.join(kudos)}</div>", unsafe_allow_html=True)

with tab_mappa:
    with st.container(border=True):
        st.subheader("🧭 Pianificatore e Editor Itinerario")
        
        c_p, c_t, c_a = st.columns(3)
        txt_part = st.session_state.itinerario_struttura["partenza"][0] if st.session_state.itinerario_struttura["partenza"] else "Non impostata"
        txt_arr = st.session_state.itinerario_struttura["arrivo"][0] if st.session_state.itinerario_struttura["arrivo"] else "Non impostato"
        c_p.markdown(f"**Partenza:** `{txt_part}`")
        c_a.markdown(f"**Arrivo:** `{txt_arr}`")
        
        with c_t:
            st.markdown("**Tappe Intermedie:**")
            if not st.session_state.itinerario_struttura["tappe"]:
                st.caption("Nessuna tappa impostata")
            else:
                for idx_t, tappa in enumerate(st.session_state.itinerario_struttura["tappe"]):
                    c_txt, c_del_t = st.columns([4, 1])
                    c_txt.caption(f"🛑 {tappa[0]}")
                    if c_del_t.button("X", key=f"del_tappa_{idx_t}", help="Rimuovi tappa"):
                        st.session_state.itinerario_struttura["tappe"].pop(idx_t)
                        st.rerun()
        
        punti_it = [p for p in [st.session_state.itinerario_struttura["partenza"]] + st.session_state.itinerario_struttura["tappe"] + [st.session_state.itinerario_struttura["arrivo"]] if p]
        
        st.markdown("<br>", unsafe_allow_html=True)
        c_calc, c_reset = st.columns([2, 1])
        with c_calc:
            if st.button("🔄 Calcola e Adatta Tracciato", type="primary", width="stretch"):
                if len(punti_it) >= 2 and grafo_motore:
                    with st.spinner("Calcolo rotta sulla rete sentieristica..."):
                        if rotta := calcola_percorso_locale(grafo_motore, albero_motore, nodi_motore, [(p[1], p[2]) for p in punti_it]):
                            st.session_state.itinerario_attivo = rotta
                            dist = round(rotta['distance'] / 1000, 2)
                            dtm_file = "DTM_vda.tif" if os.path.exists("DTM_vda.tif") else "DTM_vda" if os.path.exists("DTM_vda") else None
                            q_arr, d_pos, d_neg = calcola_profilo_dtm(rotta['geometry']['coordinates'], dtm_file) if dtm_file else ([], 0, 0)
                            st.session_state.itinerario_metadati = {"dist": dist, "d_pos": d_pos, "d_neg": d_neg, "tempo": stima_tempo_cai(dist, d_pos), "quote": q_arr}
                        else: st.error("❌ Rete interrotta o punti troppo distanti.")
                elif not grafo_motore: st.error("Rete escursionistica mancante.")
                else: st.warning("Inserisci almeno Partenza e Arrivo.")
        with c_reset:
            if st.button("🗑️ Svuota Tutto", width="stretch"):
                st.session_state.itinerario_struttura = {"partenza": None, "tappe": [], "arrivo": None}
                for k in ["itinerario_attivo", "itinerario_metadati"]: st.session_state.pop(k, None)
                st.rerun()

        if meta := st.session_state.get("itinerario_metadati"):
            st.success(f"📈 **Distanza:** {meta['dist']} km | **D+** {meta['d_pos']} m / **D-** {meta['d_neg']} m | ⏱️ **Tempo Stimato:** {meta['tempo']}")
            if meta.get('quote'):
                if fig := disegna_profilo_altimetrico(meta['quote'], meta['dist'], "Profilo Altimetrico Calcolato (DTM)"): st.plotly_chart(fig, width="stretch", key="plot_calc")
            
            c_dl_gpx, c_save_gpx = st.columns(2)
            with c_dl_gpx:
                st.download_button("📥 Scarica .GPX", data=genera_gpx(st.session_state.itinerario_attivo['geometry']['coordinates']), file_name="itinerario.gpx", mime="application/gpx+xml", width="stretch")
            
            with c_save_gpx:
                with st.popover("💾 Salva in Archivio Cloud"):
                    nuovo_nome_it = st.text_input("Nome Itinerario:", value="Nuovo Itinerario Pianificato")
                    if st.button("Conferma Salvataggio", type="primary", width="stretch"):
                        dati_da_salvare = {
                            "points": [(p[1], p[0]) for p in st.session_state.itinerario_attivo['geometry']['coordinates']],
                            "quote": meta.get('quote', []), "dist": meta['dist'], "d_pos": meta['d_pos'], "d_neg": meta['d_neg'],
                            "stato": "Pianificata", "condivisa": False, "foto": []
                        }
                        if salva_traccia_gpx(st.session_state.profilo_attivo, nuovo_nome_it, "Traccia creata tramite Pianificatore", True, dati_da_salvare):
                            st.session_state.tracce_gpx = carica_tracce_gpx_cloud(st.session_state.profilo_attivo)
                            st.success("Salvato con successo in Archivio!")

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

    show_trails = st.session_state.get("mostra_sentieri_toggle", False)
    if st.session_state.get("sentieri") is not None and show_trails:
        fg_s = folium.FeatureGroup(name="🥾 Rete Sentieristica", show=True)
        folium.GeoJson(st.session_state.sentieri, style_function=lambda x: {'color': '#2ca02c' if x['properties'].get('fclass')=='footway' else '#e65c00', 'weight': 2, 'dashArray': '6, 6', 'opacity': 0.8}).add_to(fg_s)
        fg_s.add_to(m)

    if st.session_state.get("itinerario_attivo"):
        folium.GeoJson(st.session_state.itinerario_attivo['geometry'], style_function=lambda x: {'color': '#0055ff', 'weight': 5, 'opacity': 0.9}, name="📍 Traccia Calcolata").add_to(m)

    if "tracce_gpx" in st.session_state:
        colori_gpx = ["#8e44ad", "#e74c3c", "#3498db", "#16a085", "#d35400"]
        idx_col = 0
        for nome_traccia, info in st.session_state.tracce_gpx.items():
            if info.get("visibile", True):
                colore = colori_gpx[idx_col % len(colori_gpx)]
                stato_t = info["dati"].get("stato", "Pianificata")
                folium.PolyLine(locations=info["dati"]["points"], color=colore, weight=5, opacity=0.8, tooltip=f"GPX: {nome_traccia} ({stato_t})", name=nome_traccia).add_to(m)
                idx_col += 1

    for k, ic, col in [("partenza", "🛫", "#0055ff"), ("arrivo", "🛬", "#ff0000")]:
        if node := st.session_state.itinerario_struttura.get(k):
            folium.Marker([node[1], node[2]], tooltip=f"{k.upper()}: {node[0]}", icon=folium.DivIcon(html=f"<div style='background:{col}; width:45px; height:45px; border-radius:50%; border:3px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-size:22px; color:white;'>{ic}</div>", icon_size=(45, 45), icon_anchor=(22, 22))).add_to(m)

    for t in st.session_state.itinerario_struttura.get("tappe", []):
        folium.Marker([t[1], t[2]], tooltip=f"TAPPA: {t[0]}", icon=folium.DivIcon(html="<div style='background:#ff8800; width:40px; height:40px; border-radius:50%; border:3px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-size:18px; color:white;'>🛑</div>", icon_size=(40, 40), icon_anchor=(20, 20))).add_to(m)

    for _, r in mappa_bivacchi.iterrows(): folium.Marker([r.geometry.y, r.geometry.x], popup=folium.Popup(crea_popup_veloce(r)), tooltip=get_val(r, "name_it"), icon=folium.DivIcon(html=f"<div style='background:{col_st(get_val(r, 'stato_visita'))}; width:30px; height:30px; border-radius:50%; border:2px solid white; display:flex; align-items:center; justify-content:center; font-size:14px;'>⛺</div>", icon_size=(30, 30), icon_anchor=(15, 15))).add_to(m)
    for _, r in mappa_rifugi.iterrows(): folium.Marker([r.geometry.y, r.geometry.x], popup=folium.Popup(crea_popup_veloce(r)), tooltip=get_val(r, "name_it"), icon=folium.DivIcon(html=f"<div style='background:{col_st(get_val(r, 'stato_visita'))}; width:30px; height:30px; border-radius:6px; border:2px solid white; display:flex; align-items:center; justify-content:center; font-size:14px;'>🏠</div>", icon_size=(30, 30), icon_anchor=(15, 15))).add_to(m)

    legend_template = """
    {% macro html(this, kwargs) %}
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 99999; pointer-events: auto;">
        <button onclick="var el=document.getElementById('legenda-mappa-vda'); el.style.display=(el.style.display==='none')?'block':'none';" style="background-color: white; border: 2px solid #ccc; padding: 8px 15px; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.3); font-weight: bold; font-family: sans-serif; font-size: 14px; color: #333; display: flex; align-items: center; justify-content: center;">
            🗺️ Legenda
        </button>
        <div id="legenda-mappa-vda" style="display: none; margin-top: 10px; width: 220px; background-color: rgba(255, 255, 255, 0.95); padding: 15px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); font-family: sans-serif; font-size: 12px; border: 1px solid #ccc; color: #333;">
            <b style="font-size: 14px; display: block; margin-bottom: 8px; border-bottom: 1px solid #ddd; padding-bottom: 4px; color: #000;">Dettagli</b>
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
    </div>
    {% endmacro %}
    """
    macro = MacroElement()
    macro._template = Template(legend_template)
    m.get_root().add_child(macro)
    
    folium.LayerControl(position='topright').add_to(m)

    map_data = st_folium(m, width="100%", height=550, key="mappa_vda", returned_objects=["last_object_clicked_tooltip", "last_clicked"])

    st.markdown("---")
    st.toggle("🕸️ Mostra Rete Sentieristica sulla Mappa", key="mostra_sentieri_toggle")
    st.caption("💡 **Suggerimento:** Attiva la rete sentieristica solo quando vuoi esplorarla visivamente. Tenerla disattivata renderà la mappa fluida e i tuoi clic saranno istantanei!")

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
            if cp.button("🛫 Partenza", width="stretch"): st.session_state.itinerario_struttura["partenza"] = (n_cliccato, lat_n, lon_n, q_n); st.rerun()
            if ct.button("🛑 Tappa", width="stretch") and (n_cliccato, lat_n, lon_n, q_n) not in st.session_state.itinerario_struttura["tappe"]: st.session_state.itinerario_struttura["tappe"].append((n_cliccato, lat_n, lon_n, q_n)); st.rerun()
            if ca.button("🛬 Arrivo", width="stretch"): st.session_state.itinerario_struttura["arrivo"] = (n_cliccato, lat_n, lon_n, q_n); st.rerun()

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
            st.link_button("🟢 Cerca in area su Wikiloc", url=url_wikiloc, width="stretch")
            
            url_komoot = f"https://www.komoot.com/it-it/discover/Location/@{lat_n},{lon_n}/tours?sport=hike"
            st.link_button("🌲 Cerca in area su Komoot", url=url_komoot, width="stretch")
            
            url_gulliver = f"https://www.gulliver.it/?s={n_cliccato.replace(' ', '+')}" if clk_t else "https://www.gulliver.it/itinerari/?paese=italia&regione=valle-daosta"
            st.link_button("🏔️ Cerca su Gulliver", url=url_gulliver, width="stretch")

with tab_registri:
    st.subheader(f"Database interattivo di {st.session_state.profilo_attivo}")
    
    tot_biv = len(st.session_state.bivacchi)
    vis_biv = len(st.session_state.bivacchi[st.session_state.bivacchi['stato_visita'] == 'Visitato'])
    plan_biv = len(st.session_state.bivacchi[st.session_state.bivacchi['stato_visita'] == 'Pianificato'])
    
    tot_rif = len(st.session_state.rifugi)
    vis_rif = len(st.session_state.rifugi[st.session_state.rifugi['stato_visita'] == 'Visitato'])
    plan_rif = len(st.session_state.rifugi[st.session_state.rifugi['stato_visita'] == 'Pianificato'])
    
    st.markdown(f"""
    <div style="display: flex; gap: 20px; margin-bottom: 20px;">
        <div style="flex: 1; background-color: rgba(130,130,130,0.1); padding: 15px; border-radius: 8px; border-top: 4px solid #6c757d; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <h4 style="margin-top: 0; text-align: center;">⛺ Riepilogo Bivacchi</h4>
            <div style="display: flex; justify-content: space-around; margin-top: 10px;">
                <div style="text-align: center;"><b style="color: #007bff; font-size: 20px;">{tot_biv}</b><br><span style="font-size: 13px;">Totali</span></div>
                <div style="text-align: center;"><b style="color: #28a745; font-size: 20px;">{vis_biv}</b><br><span style="font-size: 13px;">Visitati</span></div>
                <div style="text-align: center;"><b style="color: #ffc107; font-size: 20px;">{plan_biv}</b><br><span style="font-size: 13px;">Pianificati</span></div>
            </div>
        </div>
        <div style="flex: 1; background-color: rgba(130,130,130,0.1); padding: 15px; border-radius: 8px; border-top: 4px solid #6c757d; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <h4 style="margin-top: 0; text-align: center;">🏠 Riepilogo Rifugi</h4>
            <div style="display: flex; justify-content: space-around; margin-top: 10px;">
                <div style="text-align: center;"><b style="color: #007bff; font-size: 20px;">{tot_rif}</b><br><span style="font-size: 13px;">Totali</span></div>
                <div style="text-align: center;"><b style="color: #28a745; font-size: 20px;">{vis_rif}</b><br><span style="font-size: 13px;">Visitati</span></div>
                <div style="text-align: center;"><b style="color: #ffc107; font-size: 20px;">{plan_rif}</b><br><span style="font-size: 13px;">Pianificati</span></div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    colonne_desiderate = ["name_it", "ele", "accesso", "stato_visita"]
    cb, cr = [c for c in colonne_desiderate if c in st.session_state.bivacchi.columns], [c for c in colonne_desiderate if c in st.session_state.rifugi.columns]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### ⛺ Bivacchi")
        st.data_editor(st.session_state.bivacchi[cb], column_config={"stato_visita": st.column_config.SelectboxColumn("Stato", options=stati_disponibili, required=True)}, width="stretch", hide_index=True, key="editor_b", on_change=lambda: sync_tables_cloud("bivacchi", "editor_b"))
    with col2:
        st.markdown("### 🏠 Rifugi")
        st.data_editor(st.session_state.rifugi[cr], column_config={"stato_visita": st.column_config.SelectboxColumn("Stato", options=stati_disponibili, required=True)}, width="stretch", hide_index=True, key="editor_r", on_change=lambda: sync_tables_cloud("rifugi", "editor_r"))