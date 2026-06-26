import geopandas as gpd

# 1. Carica il file GeoJSON grezzo che hai scaricato da Geofabrik
# (Sostituisci il nome del file con quello reale se diverso)
gdf_grezzo = gpd.read_file("Strade_vda.geojson")

# 2. Ispeziona i tipi di strutture presenti nel dataset
# Di solito Geofabrik usa la colonna 'fclass' o 'type' per classificare le linee
print("Classi stradali trovate:", gdf_grezzo['fclass'].unique())

# 3. Filtra solo i sentieri escursionistici, le mulattiere e i percorsi pedonali
# Tipicamente in OpenStreetMap le classi utili sono 'path', 'footway', 'track'
classi_utili = ['path', 'footway', 'track']
gdf_sentieri = gdf_grezzo[gdf_grezzo['fclass'].isin(classi_utili)].copy()

# 4. Elimina le colonne inutili che appesantiscono il database (es. codici interni, tunnel, ponti)
# Mantieni solo le informazioni essenziali per la mappa, come il nome o il numero del sentiero
colonne_da_tenere = ['name', 'ref', 'fclass', 'geometry'] 
colonne_presenti = [c for c in colonne_da_tenere if c in gdf_sentieri.columns]
gdf_sentieri = gdf_sentieri[colonne_presenti]

# 5. Semplificazione geometrica (FONDAMENTALE)
# Riduce il numero di punti delle linee senza alterare visivamente il percorso sulla mappa.
# Una tolleranza di 0.0001 è un ottimo compromesso per la scala escursionistica in EPSG:4326
gdf_sentieri['geometry'] = gdf_sentieri['geometry'].simplify(tolerance=0.0001, preserve_topology=True)

# 6. Salva il nuovo file ottimizzato nella cartella dell'applicazione
gdf_sentieri.to_file("sentieri_vda_ottimizzati.geojson", driver="GeoJSON")
print("Ottimizzazione completata! File salvato come 'sentieri_vda_ottimizzati.geojson'")