# 🏔️ Aosta Valley Refuges & Bivouacs Explorer

**[🚀 CLICCA QUI PER APRIRE LA WEB APP](https://INSERISCI-QUI-IL-TUO-LINK-STREAMLIT)**

A web-based GIS application built with Python and Streamlit to explore, map, and track visits to mountain refuges and bivouacs in the Aosta Valley (Italy).

The app features an interactive map and a cloud-synchronized database to persistently save the visitation status of each location.

## ✨ Key Features
* **Interactive Mapping:** Full-screen map powered by Folium with toggleable base layers (Esri Satellite and OSM Topographic).
* **Smart Popups:** Click on any location to view elevation, access difficulty, external links, and direct [Meteoblue](https://www.meteoblue.com) weather forecasts.
* **Cloud Database:** Real-time synchronization with **Supabase** (PostgreSQL) to securely save and load the status of each structure (`Visited`, `Planned`, `Not Visited`).
* **In-App Editing:** Update the status of a location directly from the map popup or through the global interactive data tables.
* **Data Filtering:** Quickly filter the map markers based on your visitation status.

## 🛠️ Technologies Used
* **Python 3**
* **Streamlit** (Web framework & UI)
* **GeoPandas** (Geospatial data processing)
* **Folium & Streamlit-Folium** (Interactive maps)
* **Supabase** (Cloud PostgreSQL database)

## 🚀 Local Setup & Installation

1. Clone the repository:
   ```bash
   git clone [https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git](https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git)
   cd YOUR_REPOSITORY_NAME

    Install the required dependencies:
    Bash

    pip install -r requirements.txt

    Set up your Supabase connection. Create a .streamlit/secrets.toml file in the root directory and add your credentials:
    Ini, TOML

    [supabase]
    url = "[https://your-project.supabase.co](https://your-project.supabase.co)"
    key = "your-anon-public-key"

    Run the application:
    Bash

    streamlit run app.py

👤 Author

Fabrizio Nori - Version 2.1_beta
