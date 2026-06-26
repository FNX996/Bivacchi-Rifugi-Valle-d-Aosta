Esplorazione e Pianificazione VdA 🏔️

Una WebGIS App avanzata per l'esplorazione, la pianificazione degli itinerari e la gestione delle visite ai Rifugi e Bivacchi della Valle d'Aosta.

Progettata per gli amanti del trekking, l'applicazione unisce cartografia interattiva, calcolo topologico dei percorsi offline e analisi altimetrica ad alta precisione.

🌟 Funzionalità Principali (Versione 4.0)

Mappa Interattiva: Visualizzazione dinamica di rifugi, bivacchi e rete sentieristica tramite Folium e OpenStreetMap.

Gestione Profili Cloud: Sistema di autenticazione e salvataggio in cloud (tramite Supabase) per tenere traccia dello stato di visita di ogni struttura (Visitato, Pianificato, Non Visitato).

Motore di Routing Offline (A):* Calcolo istantaneo degli itinerari escursionistici basato su un file GeoJSON locale. L'algoritmo utilizza lo snapping topologico (30 metri) per riparare in automatico le interruzioni di rete.

Analisi Altimetrica DTM: Estrazione precisa delle quote da un Digital Terrain Model (raster .tif) per il calcolo del dislivello positivo (D+) e negativo (D-).

Grafici e Stime: Generazione di profili altimetrici interattivi tramite Plotly e stima dei tempi di percorrenza tramite la Formula CAI.

Importazione GPX: Modulo integrato per caricare file .gpx personali, analizzarne le quote, visualizzarne il profilo altimetrico ed esplorarli sulla mappa.

Meteo Live: Integrazione con le API gratuite di Open-Meteo per fornire previsioni a 3 giorni sul punto della mappa cliccato.

Esportazione: Possibilità di scaricare le rotte calcolate in formato .gpx o di aprirle direttamente in Google Maps.

🛠️ Requisiti di Sistema e Installazione Locale

Per far girare l'applicazione in locale, assicurati di avere Python installato e procedi con i seguenti passaggi.

1. Clona il repository

git clone https://github.com/FNX996/Bivacchi-Rifugi-Valle-d-Aosta.git
cd Bivacchi-Rifugi-Valle-d-Aosta


2. Installa le librerie

Installa le dipendenze elencate nel file requirements.txt:

pip install -r requirements.txt


Le librerie principali includono: streamlit, geopandas, folium, networkx, scipy, rasterio, gpxpy, plotly, supabase.

3. File Dati (Non inclusi in repo se superiori a 100MB)

Assicurati che i seguenti file siano presenti nella cartella principale dell'app:

bivacchi_vda.geojson

rifugi_vda.geojson

sentieri_vda_ottimizzati.geojson

DTM_vda.tif (Modello altimetrico raster per il calcolo dei dislivelli)

4. Configurazione Database (Supabase)

Crea una cartella nascosta .streamlit nella root del progetto, crea un file secrets.toml all'interno e inserisci le tue credenziali Supabase:

[supabase]
url = "IL_TUO_URL_SUPABASE"
key = "LA_TUA_CHIAVE_ANON_PUBLIC"


5. Avvio dell'App

Avvia il server locale di Streamlit:

streamlit run app.py


👨‍💻 Autore

Nori Fabrizio (@FNX996) - Sviluppo App, Analisi Dati e Integrazione GIS.