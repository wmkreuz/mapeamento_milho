from __future__ import annotations


def _safe_div(num, den):
    return num / den.where(abs(den) > 1e-6)


def calculate_indices(stack):
    import xarray as xr

    red = stack.sel(band="B04", drop=True)
    green = stack.sel(band="B03", drop=True) if "B03" in stack.band.values else red
    blue = stack.sel(band="B02", drop=True)
    nir = stack.sel(band="B08", drop=True)
    swir = stack.sel(band="B11", drop=True) if "B11" in stack.band.values else nir

    ndvi = _safe_div(nir - red, nir + red).rename("NDVI")
    evi = (2.5 * _safe_div(nir - red, nir + 6 * red - 7.5 * blue + 1)).rename("EVI")
    ndwi = _safe_div(nir - swir, nir + swir).rename("NDWI")
    savi = (((nir - red) / ((nir + red + 0.5).where(abs(nir + red + 0.5) > 1e-6))) * 1.5).rename("SAVI")
    gndvi = _safe_div(nir - green, nir + green).rename("GNDVI")
    return xr.Dataset({"NDVI": ndvi, "EVI": evi, "NDWI": ndwi, "SAVI": savi, "GNDVI": gndvi})
