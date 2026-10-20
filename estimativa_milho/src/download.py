from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd

from src.area import projected_crs_for_area

log = logging.getLogger(__name__)

S2_BANDS = ["B02", "B03", "B04", "B08"]
S2_FALLBACK_BANDS = ["B02", "B03", "B04", "B08"]


def load_sentinel2_stack(
    aoi: gpd.GeoDataFrame,
    data_inicio: str,
    data_fim: str,
    cloud_max: int,
    resolution: int,
    max_items: int,
):
    """Load a clipped Sentinel-2 L2A stack from Microsoft Planetary Computer.

    Returns an xarray.DataArray with dimensions time, band, y, x.
    Data is lazily opened and then clipped by the AOI bounds.
    """
    try:
        import planetary_computer
        import rioxarray  # noqa: F401
        import stackstac
        from pystac_client import Client
    except ImportError as exc:
        raise RuntimeError(
            "Instale pystac-client, planetary-computer e stackstac para baixar Sentinel-2."
        ) from exc

    aoi4326 = aoi.to_crs("EPSG:4326")
    geom = aoi4326.geometry.iloc[0].__geo_interface__
    bounds = tuple(aoi4326.total_bounds)
    log.info("Buscando Sentinel-2 L2A no Planetary Computer...")
    catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        intersects=geom,
        datetime=f"{data_inicio}/{data_fim}",
        query={"eo:cloud_cover": {"lt": cloud_max}},
        max_items=max_items,
    )
    items = list(search.items())
    if not items:
        raise RuntimeError("Nenhuma cena Sentinel-2 encontrada para a area e periodo.")

    items = sorted(items, key=lambda item: item.properties.get("eo:cloud_cover", 100))[:max_items]
    log.info("Cenas selecionadas: %s", len(items))
    signed = [planetary_computer.sign(item) for item in items]
    target_epsg = int(projected_crs_for_area(aoi).split(":")[-1])
    stack = stackstac.stack(
        signed,
        assets=S2_BANDS,
        bounds_latlon=bounds,
        epsg=target_epsg,
        resolution=resolution,
        chunksize=512,
        dtype="float64",
        rescale=False,
        errors_as_nodata=(Exception,),
    )
    stack = stack.rio.write_crs(f"EPSG:{target_epsg}")
    stack.attrs["reflectance_scale"] = 10000.0
    return stack


def search_sentinel2_items(
    aoi: gpd.GeoDataFrame,
    data_inicio: str,
    data_fim: str,
    cloud_max: int,
    max_items: int,
):
    import planetary_computer
    from pystac_client import Client

    aoi4326 = aoi.to_crs("EPSG:4326")
    geom = aoi4326.geometry.iloc[0].__geo_interface__
    catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        intersects=geom,
        datetime=f"{data_inicio}/{data_fim}",
        query={"eo:cloud_cover": {"lt": cloud_max}},
        max_items=max_items,
    )
    items = list(search.items())
    items = sorted(items, key=lambda item: item.properties.get("eo:cloud_cover", 100))[:max_items]
    return [planetary_computer.sign(item) for item in items]


def download_sentinel2_assets(
    aoi: gpd.GeoDataFrame,
    data_inicio: str,
    data_fim: str,
    cloud_max: int,
    max_items: int,
    cache_dir: str | Path,
) -> Path:
    """Download selected Sentinel-2 assets with requests for GDAL/Schannel fallback."""
    import requests

    items = search_sentinel2_items(aoi, data_inicio, data_fim, cloud_max, max_items)
    if not items:
        raise RuntimeError("Nenhuma cena Sentinel-2 encontrada para a area e periodo.")

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    log.info("Fallback local: baixando %s cenas Sentinel-2 para %s", len(items), cache_dir)

    for item in items:
        date = item.datetime.date().isoformat()
        scene_dir = cache_dir / item.id
        scene_dir.mkdir(parents=True, exist_ok=True)
        for band in S2_FALLBACK_BANDS:
            asset = item.assets.get(band)
            if asset is None:
                log.warning("Cena %s sem banda %s; ignorando.", item.id, band)
                continue
            out = scene_dir / f"{date}_{band}.tif"
            if out.exists() and out.stat().st_size > 0:
                continue
            log.info("Baixando %s %s", item.id, band)
            with requests.get(asset.href, stream=True, timeout=120) as response:
                response.raise_for_status()
                tmp = out.with_suffix(".tmp")
                with tmp.open("wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                tmp.replace(out)
    return cache_dir


def load_local_stack(folder: str | Path):
    """Load local GeoTIFFs named with band/date hints.

    Expected names can be like 2023-10-01_B04.tif or B04_20231001.tif.
    This is useful for manual downloads from Copernicus/INPE.
    """
    import re

    import rioxarray
    import xarray as xr

    folder = Path(folder)
    files = sorted(folder.rglob("*.tif")) + sorted(folder.rglob("*.tiff"))
    if not files:
        raise FileNotFoundError(f"Nenhum GeoTIFF encontrado em {folder}")

    arrays = []
    date_re = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")
    band_re = re.compile(r"(B0?2|B0?3|B0?4|B0?8|B11|SCL)", re.IGNORECASE)
    for path in files:
        date_match = date_re.search(path.stem)
        band_match = band_re.search(path.stem)
        if not date_match or not band_match:
            log.warning("Ignorando arquivo sem data/banda no nome: %s", path.name)
            continue
        date = "-".join(date_match.groups())
        band = band_match.group(1).upper().replace("B2", "B02").replace("B3", "B03").replace("B4", "B04").replace("B8", "B08")
        arr = rioxarray.open_rasterio(path, masked=True).squeeze("band", drop=True)
        arr = arr.assign_coords(time=date, band=band).expand_dims(["time", "band"])
        arrays.append(arr)

    if not arrays:
        raise RuntimeError("Arquivos locais encontrados, mas nenhum seguiu o padrao de nome esperado.")

    stack = xr.combine_by_coords(arrays, combine_attrs="override")
    return stack.astype("float32")
