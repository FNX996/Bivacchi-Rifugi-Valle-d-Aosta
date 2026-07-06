import osmnx as ox
import geopandas as gpd
import warnings

# Ignoriamo i warning per mantenere l'output del terminale pulito
warnings.filterwarnings("ignore")

print("⏳ Connessione a Overpass API in corso...")
print("Scaricamento della rete sentieristica per la Valle d'Aosta (potrebbe richiedere un paio di minuti)...")

# Definiamo i tag OSM di nostro interesse per il routing escursionistico
tags = {
    "highway": ["path", "track", "footway"],
    "route": ["hiking", "foot"]
}

# osmnx interroga automaticamente Overpass e costruisce le geometrie
gdf = ox.features_from_place("Valle d'Aosta, Italy", tags)

print(f"✅ Scaricati {len(gdf)} elementi. Filtraggio delle geometrie lineari in corso...")

# Manteniamo esclusivamente le linee, scartando i nodi singoli (es. cartelli) o i poligoni
gdf_lines = gdf[gdf.geometry.type.isin(['LineString', 'MultiLineString'])]

# Selezioniamo solo le colonne utili per snellire il peso del file JSON
colonne_da_mantenere = ['osmid', 'name', 'highway', 'surface', 'sac_scale', 'geometry']
colonne_presenti = [col for col in colonne_da_mantenere if col in gdf_lines.columns]
gdf_clean = gdf_lines[colonne_presenti].copy()

# Sostituiamo eventuali valori nulli o liste per evitare errori di decodifica JSON
for col in gdf_clean.columns:
    if col != 'geometry':
        gdf_clean[col] = gdf_clean[col].astype(str).replace('nan', '')

# Salvataggio del nuovo file
output_file = "sentieri_vda_ottimizzati.geojson"
gdf_clean.to_file(output_file, driver="GeoJSON")

print(f"🎉 Fatto! Rete esportata con successo in '{output_file}'.")
print(f"Trovati {len(gdf_clean)} segmenti pronti per il calcolo topologico.")