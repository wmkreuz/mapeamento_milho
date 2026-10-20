from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio.features import shapes
from shapely.geometry import shape
from skimage.morphology import remove_small_objects


def clean_classification(classified: xr.DataArray, resolution_m: float, min_area_ha: float) -> xr.DataArray:
    min_pixels = max(1, int((min_area_ha * 10000) / (resolution_m * resolution_m)))
    arr = classified.values.astype("uint8")
    cleaned = np.zeros_like(arr, dtype="uint8")
    for cls in [1, 2]:
        mask = arr == cls
        cleaned[remove_small_objects(mask, min_size=min_pixels)] = cls
    return xr.DataArray(cleaned, coords=classified.coords, dims=classified.dims, name="classe_limpa")


def write_raster(data: xr.DataArray, path: str | Path, dtype: str = "float32") -> Path:
    path = Path(path)
    data = data.rio.write_nodata(0, encoded=True)
    data.rio.to_raster(path, dtype=dtype, compress="deflate")
    return path


def raster_to_polygons(classified: xr.DataArray, min_area_ha: float, output_dir: str | Path) -> gpd.GeoDataFrame:
    arr = classified.values.astype("uint8")
    transform = classified.rio.transform()
    crs = classified.rio.crs
    records = []
    for geom, value in shapes(arr, mask=arr > 0, transform=transform):
        cls = int(value)
        poly = shape(geom)
        records.append({"classe": cls, "descricao": "milho_provavel" if cls == 2 else "milho_possivel", "geometry": poly})
    if not records:
        gdf = gpd.GeoDataFrame(columns=["classe", "descricao", "area_ha", "geometry"], geometry="geometry", crs=crs)
    else:
        gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=crs)
        gdf["area_ha"] = gdf.geometry.area / 10000
        gdf = gdf[gdf["area_ha"] >= min_area_ha].copy()
    output_dir = Path(output_dir)
    gdf.to_file(output_dir / "areas_milho.geojson", driver="GeoJSON")
    if not gdf.empty:
        gdf.to_file(output_dir / "areas_milho.shp")
    return gdf


def summarize_area(classified: xr.DataArray, resolution_m: float, polygons: gpd.GeoDataFrame) -> pd.DataFrame:
    pixel_ha = (resolution_m * resolution_m) / 10000
    arr = classified.values
    provavel = float((arr == 2).sum() * pixel_ha)
    possivel = float((arr == 1).sum() * pixel_ha)
    if polygons is not None and not polygons.empty:
        provavel = float(polygons.loc[polygons["classe"] == 2, "area_ha"].sum())
        possivel = float(polygons.loc[polygons["classe"] == 1, "area_ha"].sum())
    total = provavel + possivel
    return pd.DataFrame(
        [
            {"categoria": "area_provavel_milho_ha", "valor": round(provavel, 2)},
            {"categoria": "area_possivel_milho_ha", "valor": round(possivel, 2)},
            {"categoria": "area_total_estimada_ha", "valor": round(total, 2)},
        ]
    )
