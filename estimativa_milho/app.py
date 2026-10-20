from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import streamlit as st


st.set_page_config(page_title="Estimativa de milho", layout="wide")
st.title("Estimativa local de areas de milho")

with st.sidebar:
    municipio = st.text_input("Municipio", "Braco do Norte")
    uf = st.text_input("UF", "SC", max_chars=2)
    data_inicio = st.date_input("Data inicial")
    data_fim = st.date_input("Data final")
    safra = st.selectbox("Safra", ["verao", "safrinha", "manual"])
    limiar = st.slider("Limiar provavel", 0.50, 0.90, 0.70, 0.01)
    max_cenas = st.slider("Maximo de cenas", 4, 30, 12)
    executar = st.button("Executar")

if executar:
    cmd = [
        sys.executable,
        "main.py",
        "--municipio",
        municipio,
        "--uf",
        uf,
        "--data-inicio",
        data_inicio.isoformat(),
        "--data-fim",
        data_fim.isoformat(),
        "--safra",
        safra,
        "--limiar-provavel",
        str(limiar),
        "--max-cenas",
        str(max_cenas),
    ]
    with st.status("Processando imagens e classificando...", expanded=True):
        proc = subprocess.run(cmd, cwd=Path(__file__).parent, capture_output=True, text=True)
        st.code(proc.stdout or proc.stderr)
    if proc.returncode == 0:
        st.success("Processamento concluido.")
    else:
        st.error("Falha no processamento. Veja o log acima.")
