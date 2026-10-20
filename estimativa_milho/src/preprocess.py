from __future__ import annotations

import geopandas as gpd
import numpy as np
import xarray as xr


VALID_SCL = {4, 5, 6, 7}
CLOUD_SCL = {0, 1, 2, 3, 8, 9, 10, 11}


def clip_stack(stack, aoi: gpd.GeoDataFrame):
    import rioxarray

    if not stack.rio.crs:
        stack = stack.rio.write_crs("EPSG:4326")
    geom = aoi.to_crs(stack.rio.crs).geometry
    return stack.rio.clip(geom, stack.rio.crs, drop=True)


def scale_reflectance(stack):
    bands = [str(b) for b in stack.band.values]
    scaled = stack.copy()
    scale = scaled.attrs.get("reflectance_scale")
    if scale:
        for band in ["B02", "B03", "B04", "B08", "B11"]:
            if band in bands:
                scaled.loc[dict(band=band)] = scaled.sel(band=band) / float(scale)
        scaled.attrs.pop("reflectance_scale", None)
        return scaled
    for band in ["B02", "B03", "B04", "B08", "B11"]:
        if band in bands:
            values = scaled.sel(band=band)
            if float(values.max(skipna=True)) > 2:
                scaled.loc[dict(band=band)] = values / 10000.0
    return scaled


def apply_scl_cloud_mask(stack):
    bands = [str(b) for b in stack.band.values]
    if "SCL" not in bands:
        return stack
    scl = stack.sel(band="SCL")
    valid = np.isin(scl, list(VALID_SCL))
    masked = stack.where(valid)
    return masked.drop_sel(band=["SCL"])


def reproject_stack(stack, target_crs: str, resolution: float):
    """Reproject 2D/3D/4D rasters, including time/band stacks."""
    if str(stack.rio.crs) == target_crs:
        return stack
    if "time" not in stack.dims or "band" not in stack.dims:
        return stack.rio.reproject(target_crs, resolution=resolution)

    time_slices = []
    for time_value in stack.time.values:
        band_slices = []
        for band_value in stack.band.values:
            arr = stack.sel(time=time_value, band=band_value)
            arr = arr.rio.write_crs(stack.rio.crs)
            reprojected = arr.rio.reproject(target_crs, resolution=resolution)
            reprojected = reprojected.assign_coords(band=band_value).expand_dims("band")
            band_slices.append(reprojected)
        by_band = xr.concat(band_slices, dim="band")
        by_band = by_band.assign_coords(time=time_value).expand_dims("time")
        time_slices.append(by_band)
    result = xr.concat(time_slices, dim="time")
    return result.rio.write_crs(target_crs)
