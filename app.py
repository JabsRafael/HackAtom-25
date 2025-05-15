import streamlit as st
import pandas as pd

def read_data(path):
  df = pd.read_csv(path)
  return df


df_locais = read_data("assets/locais.csv")
df_reatores = read_data("assets/reatores.csv")

st.title("HackAtom 2025")
st.markdown("### Análise dos Locais")
st.markdown("---")
st.dataframe(df_locais)
st.markdown("Mapa dos locais mais relevantes")
st.map(df_reatores, latitude="latitude", longitude="longitude")


