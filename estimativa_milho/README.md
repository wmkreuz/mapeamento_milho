# Estimativa local de area plantada de milho

Primeira versao funcional para estimar hectares provaveis de milho em um municipio ou poligono, usando imagens publicas, Python e analise multitemporal.

## Metodologia

A solucao adapta a logica do estudo **"Identificacao e mapeamento de areas de milho na regiao noroeste do Estado do Rio Grande do Sul"**: o milho nao e identificado por uma unica cena, mas pelo comportamento temporal da vegetacao ao longo da safra.

O pipeline executa:

1. Leitura da area de interesse por municipio/UF via malha municipal publica (`geobr`/IBGE) ou por GeoJSON/Shapefile/KML.
2. Busca de imagens Sentinel-2 L2A no Microsoft Planetary Computer por STAC.
3. Recorte da area, reprojecao para UTM local, mascara de nuvem/sombra pelo SCL e padronizacao de reflectancia.
4. Calculo de NDVI, EVI, NDWI, SAVI e GNDVI.
5. Serie temporal por pixel, com suavizacao simples e metricas fenologicas: NDVI minimo, maximo, amplitude, pico, crescimento, queda, area media sob a curva e permanencia de vegetacao alta.
6. Classificacao fuzzy de 0 a 1 para milho provavel, penalizando agua, urbano/solo exposto, vegetacao permanente e comportamento temporal fora da janela esperada.
7. Pseudo-amostras de alta/baixa confianca para treinar Random Forest opcional.
8. Consenso fuzzy + Random Forest, limpeza de manchas pequenas e estimativa em hectares.
9. Saidas raster, vetoriais, CSV, mapa interativo e relatorio HTML.

## Fontes publicas usadas

- Sentinel-2 L2A / Copernicus, acessado via STAC publico do Microsoft Planetary Computer.
- Malha municipal oficial via `geobr`, derivada das bases publicas do IBGE.
- OpenStreetMap apenas como fundo do mapa interativo.

Fontes recomendadas para evolucao:

- Brazil Data Cube / INPE para cubos ARD no Brasil.
- Landsat 8/9 como alternativa em periodos com muita nuvem.
- MapBiomas para mascaras auxiliares de agua, urbano, floresta e agricultura anual.
- CONAB, IBGE PAM/SIDRA para comparacao municipal aproximada.

## Instalar no Windows

Use Python 3.11 ou 3.12. Em ambiente novo:

```powershell
cd "C:\Users\willhan.kreuz\Documents\Projetos python\mapeamento\estimativa_milho"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Se `geopandas`, `rasterio` ou `GDAL` falharem no `pip`, use Conda/Mamba:

```powershell
conda create -n estimativa_milho python=3.12 geopandas rasterio rioxarray scikit-learn scikit-image matplotlib folium pyyaml jinja2 -c conda-forge
conda activate estimativa_milho
pip install pystac-client planetary-computer stackstac odc-stac geobr
```

## Exemplo por municipio

```powershell
python main.py --municipio "Braco do Norte" --uf "SC" --data-inicio "2023-09-01" --data-fim "2024-04-30" --safra "verao" --max-cenas 12
```

Para comparar com uma referencia externa municipal, informe a area conhecida em hectares:

```powershell
python main.py --municipio "Braco do Norte" --uf "SC" --data-inicio "2025-09-01" --data-fim "2026-04-30" --safra "verao" --max-cenas 12 --area-referencia-ha 1852.33
```

Evite estimar milho com uma unica imagem ou com apenas um mes. A classificacao depende de serie temporal; por padrao o programa exige pelo menos 5 datas validas para nao entregar um falso zero como resultado.

## Usar amostras conhecidas

Quando houver talhoes conhecidos de milho, informe um GeoJSON/Shapefile com esses poligonos. O Random Forest passa a usar essas amostras reais junto com pseudo-amostras de nao milho:

```powershell
python main.py --municipio "Turvo" --uf "SC" --data-inicio "2025-07-20" --data-fim "2026-01-01" --safra "manual" --max-cenas 12 --amostras-milho "data/input/amostra_milho_turvo_11ha.geojson"
```

O arquivo `data/input/amostra_milho_turvo_11ha.geojson` e uma aproximacao criada a partir da imagem/link informado pelo usuario e foi escalado para 11 ha. Para maior precisao, substitua por um poligono medido em campo, QGIS, Google Earth ou outro editor GIS.

Para usar a amostra de Turvo como assinatura transferivel em outro municipio, acrescente `--treino-regional`. Nesse modo o programa processa tambem a area da amostra, extrai a assinatura temporal dela e usa esses pixels como milho conhecido no Random Forest aplicado a area-alvo:

```powershell
python main.py --municipio "Braco do Norte" --uf "SC" --data-inicio "2025-07-20" --data-fim "2026-01-01" --safra "manual" --max-cenas 12 --amostras-milho "data/input/amostra_milho_turvo_11ha.geojson" --treino-regional --area-referencia-ha 1852.33
```

Sem `--treino-regional`, uma amostra real so entra diretamente no Random Forest se ela cruzar o raster processado.

## Exemplo por poligono

```powershell
python main.py --poligono "data/input/area.geojson" --data-inicio "2023-09-01" --data-fim "2024-04-30" --safra "manual"
```

## Exemplo com imagens locais

Baixe manualmente GeoTIFFs Sentinel-2/Copernicus/INPE e nomeie os arquivos com data e banda, por exemplo:

```text
2023-10-01_B04.tif
2023-10-01_B08.tif
2023-10-01_B11.tif
2023-11-15_B04.tif
```

Depois rode:

```powershell
python main.py --poligono "data/input/area.geojson" --stack-local "data/raw/minhas_imagens" --data-inicio "2023-09-01" --data-fim "2024-04-30"
```

## Saidas geradas

Na pasta `data/output/<area>/`:

- `resultado_milho_probabilidade.tif`
- `resultado_milho_classificado.tif`
- `areas_milho.geojson`
- `areas_milho.shp`
- `relatorio_estimativa.html`
- `resumo.csv`
- `serie_temporal_media.csv`
- `grafico_serie_temporal.png`
- `mapa_interativo.html`
- `area_interesse.geojson`

Classes do raster classificado:

- `0`: nao milho
- `1`: milho possivel
- `2`: milho provavel

## Ajustes principais

Edite `config.yaml` ou passe parametros no CLI:

- `limiar_provavel`: aumenta/reduz rigor para milho provavel.
- `limiar_possivel`: controla areas candidatas.
- `area_minima_ha`: remove manchas pequenas.
- `max_cenas`: limita o numero de cenas Sentinel-2.
- `fenologia`: janelas de pico esperadas para verao, safrinha ou manual.

## Observacao sobre GDAL no Windows

Em alguns ambientes Windows, o GDAL/rasterio pode falhar ao ler URLs HTTPS do Planetary Computer com erro semelhante a `SEC_E_NO_CREDENTIALS`. O projeto tenta primeiro o modo remoto eficiente com `stackstac`; se essa leitura falhar por esse erro, cai para um fallback por download local via `requests`.

Esse fallback contorna o problema de credenciais do Schannel, mas baixa GeoTIFFs Sentinel-2 completos para `data/raw/planetary_cache/`, entao pode consumir bastante tempo e disco. Para testes, use `--max-cenas 1` ou `--max-cenas 2`; para processamento real, prefira corrigir o acesso remoto do GDAL, usar Conda/conda-forge, ou informar uma pasta de imagens ja baixadas com `--stack-local`.

## Limitacoes

Esta versao nao substitui levantamento de campo. Sem amostras reais, a classificacao depende de regras fenologicas e pseudo-amostras. Milho pode ser confundido com soja, feijao, arroz, pastagens temporarias e outras culturas anuais quando as curvas de NDVI/EVI forem parecidas. Nuvens, sombras, falhas temporais e pequenas propriedades tambem reduzem a confianca.

O relatorio separa a incerteza em alta, media e baixa conforme quantidade de datas validas e proporcao de pixels provaveis.

## Melhorias recomendadas

- Integrar MapBiomas para excluir agua, urbano, floresta e culturas permanentes com mais robustez.
- Adicionar Brazil Data Cube / INPE como fonte prioritaria para o Brasil.
- Criar biblioteca de assinaturas temporais por regiao e safra.
- Adicionar inspeção visual assistida para corrigir pseudo-amostras.
- Comparar automaticamente com IBGE PAM/SIDRA ou CONAB.
- Adicionar Landsat 8/9 como fallback para periodos com nuvem persistente.
- Gerar PDF alem do HTML.
