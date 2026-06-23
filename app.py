import streamlit as st
import geopandas as gpd
import folium
from folium import plugins
from streamlit_folium import st_folium
import os
from supabase import create_client, Client

# ==========================================
# CONFIGURAZIONE PAGINA E INTESTAZIONE
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
# 1. GESTIONE DATI GEOGRAFICI E STATI CLOUD
# ==========================================
def fetch_stati_dal_db():
    try:
        response = supabase.table("stato_visite").select("*").execute()
        return {row['nome_struttura']: row['stato'] for row in response.data}
    except Exception as e:
        st.warning("Impossibile caricare gli stati dal cloud. Verrà usato lo stato 'Non visitato' di default.")
        return {}

def get_valore_colonna(row, nome_colonna_base, default="N/D"):
    for col in row.index:
        if col.lower() == nome_colonna_base.lower():
            valore = row[col]
            return valore if (valore is not None and str(valore).strip() not in ["", "None", "nan"]) else default
    return default

if "dati_caricati" not in st.session_state:
    stati_cloud = fetch_stati_dal_db()
    
    if os.path.exists("bivacchi_vda.geojson") and os.path.exists("rifugi_vda.geojson"):
        gdf_b = gpd.read_file("bivacchi_vda.geojson")
        gdf_r = gpd.read_file("rifugi_vda.geojson")
        
        stati_b = [stati_cloud.get(get_valore_colonna(r, "Name_it"), "Non visitato") for _, r in gdf_b.iterrows()]
        stati_r = [stati_cloud.get(get_valore_colonna(r, "Name_it"), "Non visitato") for _, r in gdf_r.iterrows()]
        
        gdf_b["Stato_Visita"] = stati_b
        gdf_r["Stato_Visita"] = stati_r
        
        st.session_state.bivacchi = gdf_b
        st.session_state.rifugi = gdf_r
        st.session_state.dati_caricati = True
    else:
        st.error("File GeoJSON non trovati!")
        st.stop()

def get_marker_color(stato):
    if stato == "Visitato": return "#28a745"
    if stato == "Pianificato": return "#ffc107"
    return "#dc3545"

def crea_popup(row, is_rifugio=False):
    lat, lon = row.geometry.y, row.geometry.x
    meteo_url = f"https://www.meteoblue.com/it/tempo/settimana/{round(lat, 4)}N{round(lon, 4)}E"
    
    nome = get_valore_colonna(row, "Name_it", "Struttura Sconosciuta")
    quota = get_valore_colonna(row, "ele", "N/D")
    accesso = get_valore_colonna(row, "Accesso", "N/D")
    stato = get_valore_colonna(row, "Stato_Visita", "Non visitato")
    link = get_valore_colonna(row, "link1_href", "#")
    desc = get_valore_colonna(row, "Desc_IT", "Nessuna descrizione.")
    
    return f"""
    <div style="font-family: sans-serif; font-size: 14px; min-width: 250px;">
        <h3 style="margin-top: 0; color: #333;">{nome}</h3>
        <p style="margin: 4px 0;"><b>Quota:</b> {quota} m</p>
        <p style="margin: 4px 0;"><b>Accesso:</b> {accesso}</p>
        <p style="margin: 4px 0;"><b>Stato Attuale:</b> <span style="color:{get_marker_color(stato)}; font-weight:bold;">{stato.upper()}</span></p>
        <p style="margin: 8px 0 4px 0;"><a href="{link}" target="_blank" style="color: #0066cc;"><b>🔗 Apri sito web</b></a></p>
        <p style="margin: 4px 0;"><a href="{meteo_url}" target="_blank" style="color: #ff6600;"><b>☀️ Previsioni Meteoblue</b></a></p>
        <hr style="border: 0; border-bottom: 1px solid #ccc; margin: 8px 0;">
        <p style="margin: 4px 0; font-size: 12px; line-height: 1.4;"><b>Descrizione:</b><br>{desc}</p>
    </div>
    """

# ==========================================
# 2. LOGO E FILTRI
# ==========================================
if os.path.exists("Immagine_app.jpeg"):
    st.sidebar.image("Immagine_app.jpeg", use_container_width=True)
    st.sidebar.markdown("<br>", unsafe_allow_html=True) 

stati_disponibili = ["Non visitato", "Pianificato", "Visitato"]
stati_selezionati = st.sidebar.multiselect("Filtra Mappa per Stato:", options=stati_disponibili, default=stati_disponibili)

mappa_bivacchi = st.session_state.bivacchi[st.session_state.bivacchi['Stato_Visita'].isin(stati_selezionati)]
mappa_rifugi = st.session_state.rifugi[st.session_state.rifugi['Stato_Visita'].isin(stati_selezionati)]

st.sidebar.markdown("<br><br><br><br><br>", unsafe_allow_html=True) 
st.sidebar.markdown("---")
st.sidebar.markdown("""
<div style="font-size: 13px; color: #555; background-color: #f8f9fa; padding: 10px; border-radius: 5px; border-left: 4px solid #333;">
    <b>App Rifugi & Bivacchi VdA</b><br>
    Versione: 2.1_beta<br>
    Autore: Nori Fabrizio
</div>
""", unsafe_allow_html=True)

# ==========================================
# 3. MAPPA
# ==========================================
m = folium.Map(location=[45.73, 7.32], zoom_start=9, tiles=None)

folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Satellite (Esri)', overlay=False, control=True).add_to(m)
folium.TileLayer('OpenStreetMap', name='Topografica (OSM)', overlay=False, control=True).add_to(m)

plugins.Fullscreen(position='topleft', title='Espandi a schermo intero', title_cancel='Esci', force_separate_button=True).add_to(m)

for _, row in mappa_bivacchi.iterrows():
    popup_html = folium.Popup(crea_popup(row, False), max_width=350)
    colore = get_marker_color(row["Stato_Visita"])
    nome_tooltip = get_valore_colonna(row, "Name_it", "Bivacco")
    icon_html = f"<div style='background-color: {colore}; width: 32px; height: 32px; border-radius: 50%; border: 2px solid white; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; font-size: 16px;'>⛺</div>"
    folium.Marker([row.geometry.y, row.geometry.x], popup=popup_html, tooltip=nome_tooltip, icon=folium.DivIcon(html=icon_html, icon_size=(32, 32), icon_anchor=(16, 16))).add_to(m)

for _, row in mappa_rifugi.iterrows():
    popup_html = folium.Popup(crea_popup(row, True), max_width=350)
    colore = get_marker_color(row["Stato_Visita"])
    nome_tooltip = get_valore_colonna(row, "Name_it", "Rifugio")
    icon_html = f"<div style='background-color: {colore}; width: 32px; height: 32px; border-radius: 6px; border: 2px solid white; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; font-size: 16px;'>🏠</div>"
    folium.Marker([row.geometry.y, row.geometry.x], popup=popup_html, tooltip=nome_tooltip, icon=folium.DivIcon(html=icon_html, icon_size=(32, 32), icon_anchor=(16, 16))).add_to(m)

folium.LayerControl(position='topright').add_to(m)

st.markdown("Clicca su una struttura nella mappa o modificala tramite le tabelle in basso.")
map_data = st_folium(m, width="100%", height=600, returned_objects=["last_object_clicked_tooltip"])
struttura_cliccata = map_data.get("last_object_clicked_tooltip")

# ==========================================
# 4. PANNELLO CONTROLLI (SOTTO LA MAPPA)
# ==========================================
if struttura_cliccata:
    st.info(f"📍 Hai selezionato sulla mappa: **{struttura_cliccata}**")
    
    # Divisione in 3 colonne per affiancare il menu e i due pulsanti
    col1, col2, col3 = st.columns([1.5, 1, 1])
    
    with col1:
        nuovo_stato = st.selectbox("Cambia lo stato per questa struttura:", stati_disponibili, key="quick_edit")
        
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("✓ Aggiorna in Sessione", use_container_width=True):
            for df, nome_df in [(st.session_state.bivacchi, "bivacchi"), (st.session_state.rifugi, "rifugi")]:
                col_nome = [c for c in df.columns if c.lower() == "name_it"]
                if col_nome:
                    idx = df[df[col_nome[0]] == struttura_cliccata].index
                    if not idx.empty:
                        st.session_state[nome_df].loc[idx, "Stato_Visita"] = nuovo_stato
                        st.rerun()

    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        # Pulsante spostato qui, colorato di default per risaltare
        if st.button("☁️ Salva in Cloud", type="primary", use_container_width=True):
            records_da_aggiornare = []
            
            # Raccoglie i dati per il salvataggio
            for df in [st.session_state.bivacchi, st.session_state.rifugi]:
                col_nome = [c for c in df.columns if c.lower() == "name_it"]
                if col_nome:
                    for _, row in df.iterrows():
                        nome_struttura = str(row[col_nome[0]]).strip()
                        if nome_struttura and nome_struttura != "nan":
                            records_da_aggiornare.append({
                                "nome_struttura": nome_struttura,
                                "stato": row["Stato_Visita"]
                            })
            
            # Esegue l'Upsert su Supabase
            try:
                response = supabase.table("stato_visite").upsert(records_da_aggiornare).execute()
                st.success("✅ Modifiche salvate nel database Cloud!")
            except Exception as e:
                st.error(f"Errore durante l'aggiornamento SQL: {e}")

# ==========================================
# 5. TABELLE GLOBALI
# ==========================================
st.markdown("---")
st.subheader("Database Completo")

def colonne_reali(df, colonne_cercate):
    df_cols_lower = {c.lower(): c for c in df.columns}
    return [df_cols_lower[c.lower()] for c in colonne_cercate if c.lower() in df_cols_lower]

colonne_desiderate = ["Name_it", "ele", "Accesso", "Stato_Visita"]
col_visibili_b = colonne_reali(st.session_state.bivacchi, colonne_desiderate)
col_visibili_r = colonne_reali(st.session_state.rifugi, colonne_desiderate)

col1, col2 = st.columns(2)
with col1:
    st.markdown("### ⛺ Bivacchi")
    bivacchi_edit = st.data_editor(st.session_state.bivacchi[col_visibili_b], column_config={"Stato_Visita": st.column_config.SelectboxColumn("Stato", options=stati_disponibili, required=True)}, use_container_width=True, hide_index=True, key="editor_b")
    st.session_state.bivacchi["Stato_Visita"] = bivacchi_edit["Stato_Visita"]

with col2:
    st.markdown("### 🏠 Rifugi")
    rifugi_edit = st.data_editor(st.session_state.rifugi[col_visibili_r], column_config={"Stato_Visita": st.column_config.SelectboxColumn("Stato", options=stati_disponibili, required=True)}, use_container_width=True, hide_index=True, key="editor_r")
    st.session_state.rifugi["Stato_Visita"] = rifugi_edit["Stato_Visita"]