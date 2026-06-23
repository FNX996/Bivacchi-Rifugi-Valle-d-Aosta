import streamlit as st
import geopandas as gpd
import folium
from folium import plugins
from streamlit_folium import st_folium
import os
from supabase import create_client, Client

# ==========================================
# CONFIGURAZIONE PAGINA E STILI
# ==========================================
st.set_page_config(page_title="Pianificazione VdA", layout="wide")

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
# FUNZIONI DI LETTURA DATABASE E CREDENZIALI
# ==========================================
def fetch_profili_esistenti():
    try:
        response = supabase.table("utenti_credenziali").select("utente").execute()
        profili = [row['utente'] for row in response.data if row.get('utente')]
        return sorted(profili)
    except Exception as e:
        return []

def verifica_password(utente, password_inserita):
    try:
        response = supabase.table("utenti_credenziali").select("password").eq("utente", utente).execute()
        if response.data:
            return response.data[0]["password"] == password_inserita
        return False
    except Exception as e:
        return False

def registra_nuovo_utente(utente, password):
    try:
        supabase.table("utenti_credenziali").insert({"utente": utente, "password": password}).execute()
        return True
    except Exception as e:
        return False

def fetch_stati_dal_db(utente):
    try:
        response = supabase.table("stato_visite").select("*").eq("utente", utente).execute()
        return {row['nome_struttura']: row['stato'] for row in response.data}
    except Exception as e:
        st.warning("Impossibile caricare gli stati dal cloud. Uso configurazione di default.")
        return {}

def get_valore_colonna(row, nome_colonna_base, default="N/D"):
    for col in row.index:
        if col.lower() == nome_colonna_base.lower():
            valore = row[col]
            return valore if (valore is not None and str(valore).strip() not in ["", "None", "nan"]) else default
    return default

def colonne_reali(df, colonne_cercate):
    df_cols_lower = {c.lower(): c for c in df.columns}
    return [df_cols_lower[c.lower()] for c in colonne_cercate if c.lower() in df_cols_lower]

# ==========================================
# CALLBACKS DI AUTOSALVATAGGIO AUTOMATICO
# ==========================================
def handle_profile_change():
    scelta = st.session_state.scelta_profilo_widget
    st.session_state.autenticato = False  # Reset autenticazione al cambio di profilo
    if scelta == "➕ Crea Nuovo Profilo...":
        st.session_state.profilo_attivo = None
        st.session_state.creazione_in_corso = True
    elif scelta == "-- Seleziona un profilo --":
        st.session_state.profilo_attivo = None
        st.session_state.creazione_in_corso = False
    else:
        st.session_state.profilo_attivo = scelta
        st.session_state.creazione_in_corso = False
        if "dati_caricati" in st.session_state:
            del st.session_state["dati_caricati"]

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
        supabase.table("stato_visite").upsert({
            "nome_struttura": struttura,
            "stato": nuovo_stato,
            "utente": profilo
        }).execute()
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
                
                st.session_state.bivacchi.loc[row_idx, "Stato_Visita"] = nuevo_stato
                records_upsert.append({
                    "nome_struttura": nome_struttura,
                    "stato": nuovo_stato,
                    "utente": st.session_state.profilo_attivo
                })
        if records_upsert:
            try:
                supabase.table("stato_visite").upsert(records_upsert).execute()
                st.toast(f"☁️ Sincronizzati {len(records_upsert)} bivacchi nel Cloud!", icon="⛺")
            except Exception as e:
                st.error(f"Errore durante il salvataggio automatico: {e}")

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
                records_upsert.append({
                    "nome_struttura": nome_struttura,
                    "stato": nuovo_stato,
                    "utente": st.session_state.profilo_attivo
                })
        if records_upsert:
            try:
                supabase.table("stato_visite").upsert(records_upsert).execute()
                st.toast(f"☁️ Sincronizzati {len(records_upsert)} rifugi nel Cloud!", icon="🏠")
            except Exception as e:
                st.error(f"Errore durante il salvataggio automatico: {e}")

# ==========================================
# DISPOSIZIONE INTERFACCIA UTENTE (SIDEBAR)
# ==========================================
if os.path.exists("immagine_app.jpeg"):
    st.sidebar.image("immagine_app.jpeg", use_container_width=True)
    st.sidebar.markdown("<br>", unsafe_allow_html=True)

st.sidebar.markdown("### 👤 Gestione Profili")
lista_profili = fetch_profili_esistenti()
opzioni_menu = ["-- Seleziona un profilo --"] + lista_profili + ["➕ Crea Nuovo Profilo..."]

if "autenticato" not in st.session_state:
    st.session_state.autenticato = False

index_default = 0
if "profilo_attivo" in st.session_state and st.session_state.profilo_attivo in lista_profili:
    index_default = opzioni_menu.index(st.session_state.profilo_attivo)
elif st.session_state.get("creazione_in_corso", False):
    index_default = opzioni_menu.index("➕ Crea Nuovo Profilo...")

st.sidebar.selectbox(
    "Scegli un profilo esistente:", 
    options=opzioni_menu, 
    index=index_default,
    key="scelta_profilo_widget",
    on_change=handle_profile_change
)

# Gestione inserimento Password per profili esistenti
if st.session_state.get("profilo_attivo") and not st.session_state.autenticato:
    password_input = st.sidebar.text_input("Inserisci la password del profilo:", type="password", key="pass_field")
    if password_input:
        if verifica_password(st.session_state.profilo_attivo, password_input):
            st.session_state.autenticato = True
            st.toast("🔓 Accesso eseguito con successo!", icon="🔑")
            st.rerun()
        else:
            st.sidebar.error("❌ Password errata!")

# Interfaccia dinamica per la creazione di un nuovo profilo con password
if st.session_state.get("creazione_in_corso", False):
    nome_input = st.sidebar.text_input("Digita il nome del nuovo utente:", placeholder="Nome...")
    password_nuova = st.sidebar.text_input("Imposta una password per il profilo:", type="password", placeholder="Password...")
    
    if nome_input.strip() and password_nuova.strip():
        profilo_formattato = nome_input.strip().title()
        if st.sidebar.button("Inizializza Nuovo Profilo"):
            if profilo_formattato in lista_profili:
                st.sidebar.error("❌ Questo profilo esiste già!")
            else:
                if registra_nuovo_utente(profilo_formattato, password_nuova.strip()):
                    st.session_state.profilo_attivo = profilo_formattato
                    st.session_state.autenticato = True
                    st.session_state.creazione_in_corso = False
                    if "dati_caricati" in st.session_state:
                        del st.session_state["dati_caricati"]
                    st.toast("✅ Nuovo profilo registrato e protetto!", icon="🎉")
                    st.rerun()
                else:
                    st.sidebar.error("❌ Errore durante la registrazione nel database.")

# Rimozione profilo con messaggio di conferma esplicito e cancellazione credenziali
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
                    st.toast(f"Profilo {st.session_state.profilo_attivo} rimosso dal database.", icon="🗑️")
                    del st.session_state["profilo_attivo"]
                    st.session_state.autenticato = False
                    if "dati_caricati" in st.session_state:
                        del st.session_state["dati_caricati"]
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore di eliminazione: {e}")

# Blocco di sicurezza se non autenticato
if not st.session_state.get("profilo_attivo") or not st.session_state.autenticato:
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
        st.session_state.dati_caricati = True
    else:
        st.error("File cartografici GeoJSON non individuati nel repository sorgente!")
        st.stop()

stati_disponibili = ["Non visitato", "Pianificato", "Visitato"]
stati_selezionati = st.sidebar.multiselect("Filtra Mappa per Stato:", options=stati_disponibili, default=stati_disponibili)

mappa_bivacchi = st.session_state.bivacchi[st.session_state.bivacchi['Stato_Visita'].isin(stati_selezionati)]
mappa_rifugi = st.session_state.rifugi[st.session_state.rifugi['Stato_Visita'].isin(stati_selezionati)]

st.sidebar.markdown("<br><br>", unsafe_allow_html=True)
st.sidebar.markdown("---")
# MODIFICA: Aggiornato testo informativo con versione 2.0 beta
st.sidebar.markdown("""
<div style="font-size: 13px; color: #555; background-color: #f8f9fa; padding: 10px; border-radius: 5px; border-left: 4px solid #333;">
    <b>App Rifugi & Bivacchi VdA</b><br>
    Versione: 2.0 beta<br>
    Autore: Nori Fabrizio
</div>
""", unsafe_allow_html=True)

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
        <p style="margin: 0; font-size: 12px; line-height: 1.5; color: #444;">
            <b>Descrizione:</b><br>{desc}
        </p>
    </div>
    """

for _, row in mappa_bivacchi.iterrows():
    folium.Marker(
        location=[row.geometry.y, row.geometry.x], 
        popup=folium.Popup(crea_popup(row), max_width=450), 
        tooltip=get_valore_colonna(row, "Name_it"), 
        icon=folium.DivIcon(html=f"<div style='background-color: {get_marker_color(row['Stato_Visita'])}; width: 30px; height: 30px; border-radius: 50%; border: 2px solid white; display: flex; align-items: center; justify-content: center; box-shadow: 1px 1px 4px rgba(0,0,0,0.3); font-size:14px;'>⛺</div>", icon_size=(30, 30), icon_anchor=(15, 15))
    ).add_to(m)

for _, row in mappa_rifugi.iterrows():
    folium.Marker(
        location=[row.geometry.y, row.geometry.x], 
        popup=folium.Popup(crea_popup(row), max_width=450), 
        tooltip=get_valore_colonna(row, "Name_it"), 
        icon=folium.DivIcon(html=f"<div style='background-color: {get_marker_color(row['Stato_Visita'])}; width: 30px; height: 30px; border-radius: 6px; border: 2px solid white; display: flex; align-items: center; justify-content: center; box-shadow: 1px 1px 4px rgba(0,0,0,0.3); font-size:14px;'>🏠</div>", icon_size=(30, 30), icon_anchor=(15, 15))
    ).add_to(m)

folium.LayerControl(position='topright').add_to(m)

st.markdown(f"Mappa attiva collegata al profilo: **{st.session_state.profilo_attivo}**")
map_data = st_folium(m, width="100%", height=550, returned_objects=["last_object_clicked_tooltip"])
struttura_cliccata = map_data.get("last_object_clicked_tooltip")

# ==========================================
# PANNELLO DI AGGIORNAMENTO RAPIDO (AUTOSAVE)
# ==========================================
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
    
    st.markdown(f"🎰 **Modifica rapida struttura:** {struttura_cliccata}")
    st.selectbox(
        "Seleziona il nuovo stato (il salvataggio nel database Cloud è immediato):",
        options=stati_disponibili,
        index=idx_default,
        key="quick_edit_selectbox",
        on_change=autosave_quick_edit
    )

# ==========================================
# SEZIONE REGISTRI TABELLARI (DATAFRAME EDITORS)
# ==========================================
st.markdown("---")
st.subheader(f"Database interattivo di {st.session_state.profilo_attivo}")

colonne_desiderate = ["Name_it", "ele", "Accesso", "Stato_Visita"]
col_visibili_b = colonne_reali(st.session_state.bivacchi, colonne_desiderate)
col_visibili_r = colonne_reali(st.session_state.rifugi, colonne_desiderate)

col1, col2 = st.columns(2)
with col1:
    st.markdown("### ⛺ Registro Bivacchi")
    st.data_editor(
        st.session_state.bivacchi[col_visibili_b],
        column_config={"Stato_Visita": st.column_config.SelectboxColumn("Stato", options=stati_disponibili, required=True)},
        use_container_width=True,
        hide_index=True,
        key="editor_b",
        on_change=autosave_tabella_bivacchi
    )

with col2:
    st.markdown("### 🏠 Registro Rifugi")
    st.data_editor(
        st.session_state.rifugi[col_visibili_r],
        column_config={"Stato_Visita": st.column_config.SelectboxColumn("Stato", options=stati_disponibili, required=True)},
        use_container_width=True,
        hide_index=True,
        key="editor_r",
        on_change=autosave_tabella_rifugi
    )