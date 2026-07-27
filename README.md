\# Esplorazione e Pianificazione VdA 🏔️



\*\*App Rifugi, Bivacchi e Vette della Valle d'Aosta\*\*  

\*Versione 9.5\* | Autore: Fabrizio Nori



Un'applicazione GIS web interattiva, sviluppata in Python con Streamlit, per esplorare la rete sentieristica della Valle d'Aosta, pianificare itinerari, collezionare vette e gestire le proprie tracce GPX in un ambiente 3D. 



L'app si appoggia a un database in cloud (Supabase) per il salvataggio dei progressi personali e include un hub di condivisione per la Community.



\## 🌟 Funzionalità Principali



\*   🗺️ \*\*Mappa Interattiva \& Radar:\*\* Esplora la mappa topografica con i layer di Bivacchi, Rifugi e Vette (Cime > 3000m e > 4000m). Clicca su un punto per attivare il radar distanze, consultare il meteo e collegarti ai principali portali (Gulliver, Wikiloc, Komoot).

\*   🧭 \*\*Pianificatore di Itinerari (Motore A\*):\*\* Inserisci Partenza, Tappe e Arrivo direttamente dalla mappa. Il motore topologico calcolerà il percorso esatto agganciandosi alla rete sentieristica ufficiale, restituendo distanza, dislivello reale (tramite DTM) e tempi stimati CAI.

\*   🚁 \*\*Esploratore 3D Interattivo:\*\* Visualizza qualsiasi traccia GPX o itinerario calcolato in un ambiente 3D. Muovi il cursore per scorrere la traccia, vedere la pendenza istantanea e ammirare il percorso renderizzato direttamente sul modello digitale del terreno (DTM) della montagna.

\*   📊 \*\*Database \& Registri Cloud:\*\* Tieni traccia delle tue conquiste. Spunta le strutture e le vette come \*Visitate\*, \*Pianificate\* o \*Non Visitate\*. I dati vengono salvati in modo sicuro e persistente sul tuo profilo cloud personale.

\*   📂 \*\*Archivio GPX \& Editor:\*\* Carica i tuoi file GPX grezzi. L'app li comprime (a tua scelta), ne genera il profilo altimetrico e ti permette di modificarli rimandandoli al Pianificatore per agganciarli ai sentieri ufficiali.

\*   🌐 \*\*Feed della Community:\*\* Condividi pubblicamente le tue tracce migliori con data, strutture visitate, racconti e fotografie. Lascia un applauso (Kudos) agli itinerari degli altri esploratori.

\*   👑 \*\*Pannello Admin:\*\* Sistema integrato per la segnalazione di bug o suggerimenti direttamente dall'app, gestibile tramite un pannello di controllo esclusivo per l'amministratore.



\## 🛠️ Stack Tecnologico



\*   \*\*Frontend / Framework:\*\* Python, Streamlit

\*   \*\*Motore GIS / Dati Spaziali:\*\* Geopandas, Folium, Rasterio, Shapely

\*   \*\*Routing \& Pathfinding:\*\* NetworkX, SciPy (cKDTree per saldatura topologica locale)

\*   \*\*Visualizzazione Dati \& 3D:\*\* Plotly Graph Objects, Branca

\*   \*\*Backend \& Cloud Storage:\*\* Supabase (Database PostgreSQL e Storage Immagini)

\*   \*\*Elaborazione GPX:\*\* Gpxpy



\## 🚀 Utilizzo



1\. Registrati o accedi con il tuo profilo dal menu laterale. Se è il primo accesso, dovrai impostare anche un PIN segreto per il recupero password.

2\. Utilizza i filtri ("Mostra Rete Sentieristica" o "Mostra Vette > 3000m") sotto la mappa principale per attivare o disattivare i livelli in base alle tue esigenze (disattivare i sentieri rende la mappa più fluida).

3\. Salva i tuoi percorsi e goditi le tue esplorazioni!

