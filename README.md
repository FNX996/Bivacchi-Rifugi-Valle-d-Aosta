# Esplorazione e Pianificazione VdA 🏔️

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://bivacchi-rifugi-vda.streamlit.app/)

Una WebGIS App avanzata per l'esplorazione, la pianificazione degli itinerari e la gestione delle visite ai Rifugi e Bivacchi della Valle d'Aosta. 

Progettata per gli amanti del trekking, l'applicazione unisce cartografia interattiva, calcolo topologico dei percorsi offline, analisi altimetrica ad alta precisione e un hub social per la condivisione delle esperienze.

---

## 🌟 Funzionalità Principali (Versione 5.0)

* **Mappa Interattiva & Mobile-Friendly:** Visualizzazione dinamica di rifugi, bivacchi e rete sentieristica tramite `Folium` e `OpenStreetMap`. Include una legenda a scomparsa ottimizzata per la navigazione da smartphone.
* **Dashboard KPI & Profili Cloud:** Sistema di autenticazione e salvataggio in cloud (tramite **Supabase**) con contatori in tempo reale per tenere traccia dello stato di visita di ogni struttura (*Visitato, Pianificato, Non Visitato*). Ricerca predittiva dei profili integrata.
* **Motore di Routing Offline (A*):** Calcolo istantaneo degli itinerari escursionistici basato su un file GeoJSON locale. L'algoritmo utilizza lo *snapping topologico* (30 metri) per riparare in automatico le interruzioni di rete.
* **Radar di Esplorazione & Smart Links:** Analisi spaziale istantanea al clic per individuare le 3 strutture più vicine. Integrazione di deep-link georeferenziati per aprire le coordinate selezionate direttamente su **Komoot, Wikiloc e Gulliver**.
* **Archivio GPX Personale Cloud:** Caricamento, salvataggio e gestione permanente di file `.gpx` multipli nel database. È possibile rinominare le tracce, visualizzarne le quote e gestirne lo stato (Pianificata/Svolta).
* **Hub Community & Social Sharing:** Condivisione pubblica dei propri itinerari in un feed condiviso. Ogni post include la descrizione dell'escursionista, le strutture toccate, il grafico altimetrico e una mini-mappa autonoma della traccia.
* **Galleria Fotografica con Compressione:** Modulo di upload per le foto delle escursioni. L'app comprime e ridimensiona automaticamente le immagini (tramite `Pillow`) prima di caricarle sul cloud (Supabase Storage), organizzandole in una griglia di miniature espandibili (Lightbox).
* **Analisi Altimetrica & Grafici:** Estrazione precisa delle quote da un Digital Terrain Model (raster `.tif`) per il calcolo dei dislivelli. Generazione di profili altimetrici interattivi tramite `Plotly` e stima dei tempi (Formula CAI).
* **Meteo Live:** Integrazione con le API gratuite di *Open-Meteo* per fornire previsioni a 3 giorni sul punto della mappa cliccato.

---

## 🛠️ Requisiti di Sistema e Installazione Locale

Per far girare l'applicazione in locale, assicurati di avere Python installato e procedi con i seguenti passaggi.

### 1. Clona il repository
```bash
git clone [https://github.com/FNX996/Bivacchi-Rifugi-Valle-d-Aosta.git](https://github.com/FNX996/Bivacchi-Rifugi-Valle-d-Aosta.git)
cd Bivacchi-Rifugi-Valle-d-Aosta

2. Installa le librerie

Installa le dipendenze elencate nel file requirements.txt:
Bash

pip install -r requirements.txt

Le librerie principali includono: streamlit, geopandas, folium, networkx, scipy, rasterio, gpxpy, plotly, supabase, Pillow.
3. File Dati (Non inclusi in repo se superiori a 100MB)

Assicurati che i seguenti file siano presenti nella root folder dell'app:

    bivacchi_vda.geojson

    rifugi_vda.geojson

    sentieri_vda_ottimizzati.geojson

    DTM_vda.tif (Modello altimetrico raster per il calcolo dei dislivelli)

4. Configurazione Database (Supabase)

Per far funzionare l'archiviazione profili, le tracce e la galleria immagini, è necessario configurare Supabase (Database SQL e un Bucket Storage pubblico nominato foto_tracce).

Crea una cartella nascosta .streamlit nella root del progetto, crea un file secrets.toml all'interno e inserisci le tue credenziali Supabase:
Ini, TOML

[supabase]
url = "IL_TUO_URL_SUPABASE"
key = "LA_TUA_CHIAVE_ANON_PUBLIC"

5. Avvio dell'App

Avvia il server locale di Streamlit:
Bash

streamlit run app.py

👨‍💻 Autore
Nori Fabrizio (@FNX996) - Sviluppo App, Analisi Dati e Integrazione GIS.