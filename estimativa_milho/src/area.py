from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd

log = logging.getLogger(__name__)


def _normalize_text(value: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()


def load_aoi(
    municipio: str | None = None,
    uf: str | None = None,
    polygon_path: str | None = None,
    target_crs: str = "EPSG:4326",
) -> gpd.GeoDataFrame:
    if polygon_path:
        log.info("Carregando poligono informado: %s", polygon_path)
        gdf = gpd.read_file(polygon_path)
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        return gdf.to_crs(target_crs).dissolve().reset_index(drop=True)

    if not municipio or not uf:
        raise ValueError("Informe --municipio e --uf, ou --poligono.")

    try:
        import geobr
    except ImportError as exc:
        raise RuntimeError(
            "Para buscar municipio automaticamente instale geobr, ou informe --poligono."
        ) from exc

    log.info("Baixando/consultando malha municipal pelo geobr: %s/%s", municipio, uf)
    mun = geobr.read_municipality(code_muni="all", year=2022)
    mun = mun[mun["abbrev_state"].str.upper() == uf.upper()].copy()
    target = _normalize_text(municipio)
    names = mun["name_muni"].map(_normalize_text)
    selected = mun[names == target]
    if selected.empty:
        contains = mun[names.str.contains(target, regex=False)]
        options = ", ".join(contains["name_muni"].head(8).tolist())
        raise ValueError(f"Municipio nao encontrado em {uf}. Opcoes proximas: {options}")

    selected = selected.to_crs(target_crs).dissolve().reset_index(drop=True)
    selected["nome_area"] = f"{municipio}/{uf.upper()}"
    return selected


def save_aoi(gdf: gpd.GeoDataFrame, output_dir: str | Path) -> Path:
    output = Path(output_dir) / "area_interesse.geojson"
    gdf.to_file(output, driver="GeoJSON")
    return output


def projected_crs_for_area(aoi: gpd.GeoDataFrame) -> str:
    centroid = aoi.to_crs("EPSG:4326").geometry.iloc[0].centroid
    lon = centroid.x
    lat = centroid.y
    zone = int((lon + 180) // 6) + 1
    epsg = 32700 + zone if lat < 0 else 32600 + zone
    return f"EPSG:{epsg}"
