# Esplorazione e Pianificazione VdA 🏔️

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://bivacchi-rifugi-vda.streamlit.app/)

Una WebGIS App avanzata per l'esplorazione, la pianificazione degli itinerari e la gestione delle visite ai Rifugi e Bivacchi della Valle d'Aosta. 

Progettata per gli amanti del trekking, l'applicazione unisce cartografia interattiva, calcolo topologico dei percorsi offline, analisi altimetrica ad alta precisione e un hub social per la condivisione delle esperienze.

---

## 🌟 Novità della Versione 7.1
* **Hub Community Potenziato:** Nuovo sistema di **Kudos (Applausi)** per apprezzare le tracce pubbliche degli altri esploratori.
* **Performance Mappa Fulminee:** Aggiunto un toggle rapido per nascondere/mostrare la rete sentieristica, garantendo un'interazione istantanea senza cali di frame-rate.
* **Rete Sentieristica Estesa:** Nuovo layer vettoriale ottimizzato topologicamente estrapolato direttamente da OpenStreetMap (tramite Overpass API).
* **Gestione Account Avanzata:** Nuovo menu dedicato per il cambio password (tramite PIN di sicurezza) e l'eliminazione definitiva del profilo e dei dati associati.
* **Changelog Integrato:** Menu dedicato all'interno dell'app per restare sempre aggiornati sulle ultime novità introdotte.

---

## 🚀 Funzionalità Principali

* **Mappa Interattiva & Mobile-Friendly:** Visualizzazione dinamica di rifugi, bivacchi e sentieri (Folium e OSM) con legenda a scomparsa ottimizzata per smartphone.
* **Dashboard KPI & Profili Cloud:** Sistema di autenticazione e salvataggio in cloud (Supabase) per tracciare lo stato delle visite (Visitato, Pianificato, Non visitato).
* **Motore di Routing (A*):** Calcolo istantaneo degli itinerari basato sui nodi della rete OSM. L'algoritmo ripara automaticamente le micro-interruzioni di rete grazie al `cKDTree` (tolleranza 30m).
* **Radar Esplorazione & Smart Links:** Individuazione rapida delle 3 strutture più vicine e deep-link georeferenziati per Komoot, Wikiloc e Gulliver.
* **Archivio GPX Cloud & Galleria Fotografica:** Caricamento, modifica e condivisione pubblica di percorsi GPX personali. Include la compressione automatica delle foto (tramite Pillow) per ottimizzare lo storage su Supabase.
* **Analisi Altimetrica & Meteo Live:** Estrazione precisa delle quote da DTM locale (raster .tif), calcolo tempi stimati (Formula CAI) e previsioni meteo a 3 giorni (Open-Meteo).

---

## 🛠️ Requisiti di Sistema e Installazione Locale

Per far girare l'applicazione in locale, assicurati di avere Python installato e procedi con i seguenti passaggi.

### 1. Clona il repository
```bash
git clone https://github.com/FNX996/Bivacchi-Rifugi-Valle-d-Aosta.git
cd Bivacchi-Rifugi-Valle-d-Aosta
```

### 2. Installa le librerie
Installa le dipendenze elencate nel file `requirements.txt`:
```bash
pip install -r requirements.txt
```
*Le librerie principali includono: `streamlit`, `geopandas`, `folium`, `networkx`, `scipy`, `rasterio`, `gpxpy`, `plotly`, `supabase`, `Pillow`.*

### 3. File Dati (Non inclusi nel repository per limiti di dimensione)
Assicurati che i seguenti file siano presenti nella root folder dell'app:
* `bivacchi_vda.geojson`
* `rifugi_vda.geojson`
* `sentieri_vda_ottimizzati.geojson`
* `DTM_vda.tif` (Modello altimetrico raster)

### 4. Configurazione Database (Supabase)
Crea una cartella nascosta `.streamlit` nella root del progetto, crea un file `secrets.toml` all'interno e inserisci le tue credenziali Supabase:
```toml
[supabase]
url = "IL_TUO_URL_SUPABASE"
key = "LA_TUA_CHIAVE_ANON_PUBLIC"
```

### 5. Avvio dell'App
Avvia il server locale di Streamlit:
```bash
streamlit run app.py
```

---

👨‍💻 **Sviluppato da:**
Fabrizio Nori (Bizzietto / @FNX996) - Analisi Dati, Integrazione GIS e Sviluppo App.
