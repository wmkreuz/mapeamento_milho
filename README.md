# Mapeamento e Estimativa Local de Área Plantada de Milho 🌽🛰️

Pipeline em Python para identificação e estimativa de hectares prováveis de milho em municípios ou polígonos no Brasil, utilizando séries temporais de imagens públicas de satélite (**Sentinel-2 L2A** via **Microsoft Planetary Computer**), análise fenológica e aprendizado de máquina (*Random Forest*).

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/wmkreuz/mapeamento_milho/blob/main/executar_colab.ipynb)

---

## 🎯 Metodologia

O milho **não é identificado por uma única imagem estática**, mas sim pelo comportamento temporal da vegetação ao longo do ciclo fenológico da safra (crescimento rápido, pico de índice de vegetação e senescência/colheita).

### Etapas do Pipeline:
1. **Área de Interesse (AOI):** Seleção do município e UF via malha oficial do IBGE (`geobr`) ou upload de polígono customizado (GeoJSON, Shapefile ou KML).
2. **Imagens Sentinel-2 L2A:** Busca e consulta automatizada no catálogo STAC do Microsoft Planetary Computer com reprojeção automática para UTM métrico.
3. **Máscara de Nuvens e Qualidade:** Filtragem de nuvens e sombras pela banda SCL (*Scene Classification Layer*).
4. **Índices Espectrais:** Cálculo multitemporal de **NDVI**, **EVI**, **NDWI**, **SAVI** e **GNDVI**.
5. **Métricas Fenológicas:** Suavização da curva temporal por pixel e extração de NDVI mínimo, máximo, amplitude, data do pico, taxas de crescimento/queda e permanência de biomassa.
6. **Classificação Fuzzy:** Grau de pertinência (0 a 1) para milho provável conforme a safra (verão, safrinha ou manual), penalizando água, áreas urbanas e vegetação perene (florestas/pastagens permanentes).
7. **Random Forest:** Refinamento por aprendizado de máquina treinado com pseudo-amostras ou amostras reais conhecidas de campo.
8. **Pós-Processamento:** Filtragem de ruídos espaciais (< 0.5 ha), cálculo de hectares, vetorização para Shapefile/GeoJSON, mapa interativo em Folium e relatório HTML executivo.

---

## ☁️ Execução na Nuvem (Google Colab)

A forma recomendada para execução sem consumir a memória RAM ou o disco da sua máquina local:

1. Abra o notebook [`executar_colab.ipynb`](executar_colab.ipynb) diretamente no Google Colab:  
   [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/wmkreuz/mapeamento_milho/blob/main/executar_colab.ipynb)
2. No notebook, o repositório é clonado automaticamente:
   ```bash
   !git clone https://github.com/wmkreuz/mapeamento_milho.git
   ```
3. Preencha os parâmetros no formulário interativo (Município, UF, datas, número de cenas) e execute as células.

---

## 💻 Instalação Local

Recomenda-se **Python 3.11 ou 3.12**.

```powershell
# Clone o repositório
git clone https://github.com/wmkreuz/mapeamento_milho.git
cd mapeamento_milho/estimativa_milho

# Crie e ative o ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Instale os pacotes
pip install -r requirements.txt
```

---

## 🚀 Como Executar Localmente

### 1. Linha de Comando (CLI)

```powershell
# Exemplo para Braço do Norte / SC (Safra de Verão)
python main.py --municipio "Braco do Norte" --uf "SC" --data-inicio "2023-09-01" --data-fim "2024-04-30" --safra "verao" --max-cenas 12
```

Para comparar com uma referência municipal conhecida (ex: dados da CONAB ou IBGE PAM em hectares):
```powershell
python main.py --municipio "Braco do Norte" --uf "SC" --data-inicio "2023-09-01" --data-fim "2024-04-30" --safra "verao" --max-cenas 12 --area-referencia-ha 1852.33
```

Para usar polígonos de talhões conhecidos de milho como treino do Random Forest:
```powershell
python main.py --municipio "Turvo" --uf "SC" --data-inicio "2025-07-20" --data-fim "2026-01-01" --safra "manual" --max-cenas 12 --amostras-milho "data/input/amostra_milho_turvo_11ha.geojson"
```

### 2. Interface Gráfica Web (Streamlit)

```powershell
streamlit run app.py
```

---

## 📁 Saídas Geradas

Os arquivos são exportados na pasta `data/output/<municipio_uf>/`:

* `resultado_milho_probabilidade.tif`: Raster com probabilidade contínua (0 a 1).
* `resultado_milho_classificado.tif`: Raster classificado (0: não milho, 1: milho possível, 2: milho provável).
* `areas_milho.geojson` e `areas_milho.shp`: Camadas vetoriais prontas para QGIS / ArcGIS.
* `resumo.csv`: Tabela com hectares calculados por categoria de certeza.
* `serie_temporal_media.csv` e `grafico_serie_temporal.png`: Comportamento médio temporal do NDVI.
* `mapa_interativo.html`: Mapa interativo navegável via navegador.
* `relatorio_estimativa.html`: Relatório completo consolidado.

---

## 📜 Licença

Distribuído sob licença livre para fins de pesquisa, monitoramento agropecuário e gestão territorial.
