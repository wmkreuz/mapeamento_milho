from __future__ import annotations

import os
from pathlib import Path

matplotlib_cache = Path(".matplotlib_cache")
matplotlib_cache.mkdir(exist_ok=True)
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache.resolve()))

import pandas as pd
from jinja2 import Template


def plot_temporal_curve(curve: pd.DataFrame, output_dir: str | Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output = Path(output_dir) / "grafico_serie_temporal.png"
    fig, ax = plt.subplots(figsize=(9, 4.8))
    if not curve.empty:
        for name, grp in curve.groupby("indice"):
            ax.plot(pd.to_datetime(grp["data"]), grp["valor"], marker="o", linewidth=1.5, label=name)
    ax.set_title("Serie temporal media da area analisada")
    ax.set_ylabel("Indice")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def make_interactive_map(aoi, polygons, output_dir: str | Path) -> Path:
    import folium

    output = Path(output_dir) / "mapa_interativo.html"
    aoi4326 = aoi.to_crs("EPSG:4326")
    center = aoi4326.geometry.iloc[0].centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=11, tiles="OpenStreetMap")
    folium.GeoJson(aoi4326, name="Area de interesse", style_function=lambda _: {"color": "#1f2937", "weight": 2, "fillOpacity": 0}).add_to(m)
    if polygons is not None and not polygons.empty:
        colors = {1: "#f59e0b", 2: "#16a34a"}
        folium.GeoJson(
            polygons.to_crs("EPSG:4326"),
            name="Areas classificadas",
            style_function=lambda feat: {
                "color": colors.get(feat["properties"].get("classe"), "#666"),
                "weight": 1,
                "fillOpacity": 0.55,
            },
            tooltip=folium.GeoJsonTooltip(fields=["descricao", "area_ha"]),
        ).add_to(m)
    folium.LayerControl().add_to(m)
    m.save(output)
    return output


def write_html_report(
    output_dir: str | Path,
    area_name: str,
    period: str,
    images_used: int,
    summary: pd.DataFrame,
    confidence: str,
    limitations: list[str],
    curve_png: Path,
    map_html: Path,
    reference: pd.DataFrame | None = None,
) -> Path:
    output = Path(output_dir) / "relatorio_estimativa.html"
    values = {row["categoria"]: row["valor"] for _, row in summary.iterrows()}
    template = Template(
        """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <title>Relatorio de estimativa de milho</title>
  <style>
    body{font-family:Arial,sans-serif;margin:32px;color:#17202a;line-height:1.45}
    h1{font-size:24px;margin-bottom:4px}
    h2{font-size:18px;margin-top:28px}
    table{border-collapse:collapse;margin-top:12px;min-width:420px}
    th,td{border:1px solid #d7dde5;padding:8px 10px;text-align:left}
    th{background:#f3f6f8}
    .metric{font-size:20px;font-weight:bold}
    .note{background:#fff7e6;border-left:4px solid #f59e0b;padding:10px 14px}
    img{max-width:900px;width:100%;border:1px solid #d7dde5}
  </style>
</head>
<body>
  <h1>Estimativa de area de milho</h1>
  <p><strong>Area analisada:</strong> {{ area_name }}<br>
  <strong>Periodo:</strong> {{ period }}<br>
  <strong>Imagens utilizadas:</strong> {{ images_used }}<br>
  <strong>Nivel de confianca:</strong> {{ confidence }}</p>

  <h2>Resultado</h2>
  <table>
    <tr><th>Categoria</th><th>Hectares</th></tr>
    <tr><td>Milho provavel</td><td class="metric">{{ values.area_provavel_milho_ha }}</td></tr>
    <tr><td>Milho possivel</td><td class="metric">{{ values.area_possivel_milho_ha }}</td></tr>
    <tr><td>Total estimado</td><td class="metric">{{ values.area_total_estimada_ha }}</td></tr>
  </table>

  {% if reference_rows %}
  <h2>Comparacao externa</h2>
  <table>
    <tr><th>Indicador</th><th>Valor</th></tr>
    {% for row in reference_rows %}
    <tr><td>{{ row.categoria }}</td><td>{{ row.valor }}</td></tr>
    {% endfor %}
  </table>
  {% endif %}

  <h2>Metodologia</h2>
  <p>O fluxo adapta a logica multitemporal de identificacao de milho: recorte da area, busca de imagens Sentinel-2 L2A, mascaramento de nuvens, calculo de NDVI/EVI/NDWI/SAVI, extracao de metricas fenologicas por pixel e classificacao fuzzy. Quando habilitado, pseudo-amostras de alta e baixa confianca treinam um Random Forest leve para compor um consenso.</p>

  <h2>Serie temporal</h2>
  <img src="{{ curve_png.name }}" alt="Grafico da serie temporal">

  <h2>Limitacoes</h2>
  <div class="note">
    <ul>{% for item in limitations %}<li>{{ item }}</li>{% endfor %}</ul>
  </div>

  <h2>Mapa interativo</h2>
  <p>Arquivo: <a href="{{ map_html.name }}">{{ map_html.name }}</a></p>
</body>
</html>
        """
    )
    html = template.render(
        area_name=area_name,
        period=period,
        images_used=images_used,
        summary=summary,
        values=values,
        confidence=confidence,
        limitations=limitations,
        curve_png=curve_png,
        map_html=map_html,
        reference_rows=[] if reference is None or reference.empty else reference.to_dict("records"),
    )
    output.write_text(html, encoding="utf-8")
    return output
