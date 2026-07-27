\# Esplorazione e Pianificazione VdA 🏔️



\*\*App Rifugi, Bivacchi e Vette della Valle d'Aosta\*\*  

\*Versione 9.5 | Autore: Fabrizio Nori\*



Un'applicazione GIS web interattiva, sviluppata in Python con Streamlit, per esplorare la rete sentieristica della Valle d'Aosta, pianificare itinerari, collezionare vette e gestire le proprie tracce GPX in un ambiente 3D. 



L'app si appoggia a un database in cloud (Supabase) per il salvataggio dei progressi personali e include un hub di condivisione per la Community.



\## 🌟 Funzionalità Principali



\* 🗺️ \*\*Mappa Interattiva \& Radar:\*\* Esplora la mappa topografica con i layer di Bivacchi, Rifugi e Vette. Clicca su un punto per attivare il radar distanze, consultare il meteo e collegarti ai principali portali.

\* 🧭 \*\*Pianificatore di Itinerari (Motore A\*):\*\* Inserisci Partenza, Tappe e Arrivo direttamente dalla mappa. Il motore topologico calcolerà il percorso esatto agganciandosi alla rete sentieristica ufficiale.

\* 🚁 \*\*Esploratore 3D Interattivo:\*\* Visualizza qualsiasi traccia GPX o itinerario in un ambiente 3D, esplorando la pendenza istantanea direttamente sul modello digitale del terreno (DTM).

\* 📊 \*\*Database \& Registri Cloud:\*\* Spunta le strutture e le vette come Visitate, Pianificate o Non Visitate. I dati vengono salvati in modo sicuro e persistente sul tuo profilo cloud personale.

\* 📂 \*\*Archivio GPX \& Editor:\*\* Carica i tuoi file GPX grezzi, comprimili e modificali rimandandoli al Pianificatore per agganciarli ai sentieri ufficiali.

\* 🌐 \*\*Feed della Community:\*\* Condividi pubblicamente le tue tracce migliori con data, racconti e fotografie, e lascia un applauso (Kudos) agli itinerari degli altri esploratori.

\* 👑 \*\*Pannello Admin:\*\* Sistema integrato per la segnalazione di bug o suggerimenti direttamente dall'app.



\## 🛠️ Stack Tecnologico



\* \*\*Frontend:\*\* Python, Streamlit

\* \*\*Motore GIS:\*\* Geopandas, Folium, Rasterio, Shapely

\* \*\*Routing \& Pathfinding:\*\* NetworkX, SciPy

\* \*\*Visualizzazione 3D:\*\* Plotly Graph Objects, Branca

\* \*\*Backend:\*\* Supabase (Database PostgreSQL e Storage Immagini)

\* \*\*Elaborazione GPX:\*\* Gpxpy



\## 🚀 Utilizzo



1\. Registrati o accedi con il tuo profilo dal menu laterale. 

2\. Utilizza i filtri sotto la mappa principale per attivare o disattivare i livelli di Sentieri e Vette. Disattivare i layer volumetrici rende la mappa istantanea e fluida.

3\. Salva i tuoi percorsi e goditi le tue esplorazioni!

