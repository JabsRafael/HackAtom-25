"""
Dashboard – Seleção preliminar de locais para SMRs no Brasil
Execute com:  streamlit run app.py
"""

# ------------------------------------------------------------------
# 0. Imports
# ------------------------------------------------------------------
import streamlit as st
import geopandas as gpd
import pandas as pd
import leafmap.foliumap as leafmap
from shapely.geometry import Point

# ------------------------------------------------------------------
# 1. Configurações básicas
# ------------------------------------------------------------------
st.set_page_config(page_title="SMR – Siting Dashboard", layout="wide")

# Caminhos ‑ ajuste para onde estão seus arquivos .gpkg --------------
PATHS = {
    "grid":        ("data/energia.gpkg", 0),   # layer index ou nome
    "rivers":      ("data/rios-80m3.gpkg", 0),
    "highways":    ("data/rodovias.gpkg", 0),
    "flood":       ("data/inundacao.gpkg", 0),
    "cities":      ("data/mapa_brasil.gpkg", 0),
    "airports":    ("data/aeroportos.gpkg", 0),
}

CSV_NAMES = "data/tabela.csv"   # <-- caminho do CSV FID↔nome  

TARGET_CRS = "EPSG:3857"        # projeção métrica (metros)  

# ---- campos na camada de municípios --------------------------------  
CITY_ID_FIELD   = "fid"   # id que casa com o CSV  
CITY_NAME_FIELD = "nome"  # coluna no CSV com o nome do município  

# ------------------------------------------------------------------  
# 2. Parâmetros de pontuação  
# ------------------------------------------------------------------  
def distance_score(dist_m, thr3, thr2, thr1):  
    if dist_m <= thr3:  
        return 3  
    elif dist_m <= thr2:  
        return 2  
    elif dist_m <= thr1:  
        return 1  
    return 0  

THRESHOLDS = {  
    "water":   (5_000, 10_000, 32_000),  
    "grid":    (5_000, 10_000, 32_000),  
    "highway": (5_000, 10_000, 32_000),  
    "airport": (8_000, 16_000, 40_000),  
}  

# ------------------------------------------------------------------  
# 3. Carregamento dos dados  
# ------------------------------------------------------------------  
@st.cache_data(show_spinner=False)  
def load_geodata():  
    gdfs = {}  
    for key, (path, layer) in PATHS.items():  
        gdf = gpd.read_file(path, layer=layer).to_crs(TARGET_CRS)  
        gdfs[key] = gdf  
    return gdfs  

@st.cache_data(show_spinner=False)  
def load_city_names(csv_path: str):  
    df = pd.read_csv(csv_path, encoding="utf-8")[ [CITY_ID_FIELD, CITY_NAME_FIELD] ]  
    return df  

gdf        = load_geodata()  
names_df   = load_city_names(CSV_NAMES)  

# ------------------------------------------------------------------  
# 4. Construção da tabela de scores  
# ------------------------------------------------------------------  
def build_score_table(_gdf, _names_df):  
    gdf        = _gdf  
    names_df   = _names_df.rename(              # ← renomeia aqui  
        columns={CITY_NAME_FIELD: "nome_csv"}  
    )  

    cities = gdf["cities"].copy()  
    if CITY_ID_FIELD not in cities.columns:  
        cities[CITY_ID_FIELD] = cities.index  

    # merge com sufixos controlados  
    cities = cities.merge(  
        names_df[[CITY_ID_FIELD, "nome_csv"]],  
        on=CITY_ID_FIELD,  
        how="left"  
    )  

    # qual coluna usar como nome oficial?  
    if "nome_csv" in cities.columns:  
        cities["nome_final"] = cities["nome_csv"].fillna(  
            cities.get(CITY_NAME_FIELD)         # pega do layer se o CSV veio nulo  
        )  
    else:  
        cities["nome_final"] = cities[CITY_NAME_FIELD]  

    # ---------- restante da função permanece igual ---------------  
    rivers   = gdf["rivers"];   grid   = gdf["grid"]  
    highways = gdf["highways"]; airports = gdf["airports"]  
    flood    = gdf["flood"]  

    rivers_sindex, grid_sindex = rivers.sindex, grid.sindex  
    highway_sindex, airport_sindex = highways.sindex, airports.sindex  

    def closest_distance(pt, sindex, ref_gdf):  
        try:  
            idx, dist = sindex.nearest(pt, return_distance=True)  
            return float(dist[0])  
        except TypeError:  
            idx = next(sindex.nearest(pt.bounds, 1))  
            return pt.distance(ref_gdf.geometry.iloc[idx])  

    results = []  
    for _, city in cities.iterrows():  
        pt = city.geometry.centroid  
        dist_water = closest_distance(pt, rivers_sindex, rivers)  
        dist_grid  = closest_distance(pt, grid_sindex, grid)  
        dist_hw    = closest_distance(pt, highway_sindex, highways)  
        dist_ap    = closest_distance(pt, airport_sindex, airports)  

        score_water = distance_score(dist_water, *THRESHOLDS["water"])  
        score_grid  = distance_score(dist_grid,  *THRESHOLDS["grid"])  
        score_hw    = distance_score(dist_hw,    *THRESHOLDS["highway"])  
        score_ap    = distance_score(dist_ap,    *THRESHOLDS["airport"])  
        score_flood = 0 if flood.intersects(pt).any() else 3  

        total = score_water + score_grid + score_hw + score_ap + score_flood  
        if total == 0:  
            continue  

        results.append({  
            "Município": city["nome_final"],     # ← usa a coluna unificada  
            "Score_Total": total,  
            "Score_Médio": round(total / 5, 2),  
            "Água": score_water,  
            "Transmissão": score_grid,  
            "Rodovia": score_hw,  
            "Aeroporto": score_ap,  
            "Inundação": score_flood,  
            "geometry": pt  
        })  

    return gpd.GeoDataFrame(results, crs=TARGET_CRS)

scores = build_score_table(gdf, names_df)  

# ------------------------------------------------------------------  
# 5. Interface Streamlit  
# ------------------------------------------------------------------  
st.title("Seleção preliminar de locais para SMRs – Brasil")  

# ---- Sidebar ------------------------------------------------------  
st.sidebar.header("Camadas no mapa")  
show_grid     = st.sidebar.checkbox("Linhas de transmissão", True)  
show_rivers   = st.sidebar.checkbox("Rios (>80 m³/s)", True)  
show_highways = st.sidebar.checkbox("Rodovias", False)  
show_flood    = st.sidebar.checkbox("Áreas de inundação", False)  
show_airports = st.sidebar.checkbox("Aeroportos", False)  

min_avg = st.sidebar.slider(  
    "Score médio mínimo exibido",  
    0.0, 3.0, 1.0, 0.1  
)  

# ---- Mapa ---------------------------------------------------------  
m = leafmap.Map(center=[-15, -55], zoom=4)  

if show_grid:  
    m.add_gdf(gdf["grid"], layer_name="Transmissão",  
              style={"color": "#FFA500", "weight": 2})  
if show_rivers:  
    m.add_gdf(gdf["rivers"], layer_name="Rios",  
              style={"color": "#1f78b4"})  
if show_highways:  
    m.add_gdf(gdf["highways"], layer_name="Rodovias",  
              style={"color": "gray", "weight": 1})  
if show_flood:  
    m.add_gdf(gdf["flood"], layer_name="Inundação",  
              style={"color": "cyan", "fillOpacity": 0.3})  
if show_airports:  
    m.add_gdf(gdf["airports"], layer_name="Aeroportos",  
              marker_type="circle", marker_color="black", marker_radius=3)  

palette = {3: "green", 2: "orange", 1: "red"}  
for _, row in scores.query("Score_Médio >= @min_avg").iterrows():  
    color = palette[round(row["Score_Médio"])]  
    popup = (  
        f"<b>{row['Município']}</b><br>"  
        f"Score médio: {row['Score_Médio']}<br>"  
        f"Água: {row['Água']} | Tx: {row['Transmissão']} | "  
        f"Rod: {row['Rodovia']} | Apt: {row['Aeroporto']} | "  
        f"Inund.: {row['Inundação']}"  
    )  
    m.add_marker(  
        location=(row.geometry.y, row.geometry.x),  
        popup=popup,  
        icon_color=color,  
        layer_name="Cidades elegíveis"  
    )  

# --- renderiza (com fallback Windows/CP-1252) ----------------------  
import streamlit.components.v1 as components  
try:  
    m.to_streamlit(height=650)  
except Exception:  
    components.html(m._repr_html_(), height=650, scrolling=False)  
    st.warning("Mapa renderizado em modo de compatibilidade (Windows/CP-1252).")  

# ---- Tabela -------------------------------------------------------  
st.subheader("Municípios que atendem aos critérios")  
table = (  
    scores  
    .query("Score_Médio >= @min_avg")  
    .drop(columns="geometry")  
    .sort_values("Score_Total", ascending=False)  
)  
st.dataframe(  
    table,  
    height=400,  
    use_container_width=True,  
)  

st.sidebar.markdown("---")  
st.sidebar.markdown(  
    "Edite os limiares no dicionário `THRESHOLDS` caso deseje "  
    "critérios de distância diferentes."  
)