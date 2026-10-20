from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr


def smooth_indices(ds: xr.Dataset, window: int = 3) -> xr.Dataset:
    if ds.sizes.get("time", 0) < window:
        return ds
    return ds.rolling(time=window, center=True, min_periods=1).median()


def extract_features(ds: xr.Dataset) -> xr.Dataset:
    ndvi = ds["NDVI"]
    evi = ds["EVI"]
    ndwi = ds["NDWI"]

    ndvi_min = ndvi.min("time", skipna=True)
    ndvi_max = ndvi.max("time", skipna=True)
    ndvi_mean = ndvi.mean("time", skipna=True)
    ndvi_amp = ndvi_max - ndvi_min
    evi_max = evi.max("time", skipna=True)
    ndwi_max = ndwi.max("time", skipna=True)
    high_fraction = (ndvi > 0.65).mean("time", skipna=True)

    valid_any = ndvi.notnull().any("time")
    peak_idx = ndvi.fillna(-9999).argmax("time")
    dates = pd.to_datetime(ndvi.time.values)
    month_numbers = np.array([d.month for d in dates], dtype="uint8")
    peak_month = xr.DataArray(
        month_numbers[peak_idx.values],
        coords=peak_idx.coords,
        dims=peak_idx.dims,
        name="peak_month",
    ).where(valid_any, 0)

    first = ndvi.isel(time=0, drop=True)
    last = ndvi.isel(time=-1, drop=True)
    growth = (ndvi_max - first).rename("growth")
    drop = (ndvi_max - last).rename("drop")
    auc = ndvi.fillna(0).mean("time").rename("ndvi_auc")

    features = xr.Dataset(
        {
            "ndvi_min": ndvi_min,
            "ndvi_max": ndvi_max,
            "ndvi_mean": ndvi_mean,
            "ndvi_amp": ndvi_amp,
            "evi_max": evi_max,
            "ndwi_max": ndwi_max,
            "high_fraction": high_fraction,
            "peak_month": peak_month,
            "growth": growth,
            "drop": drop,
            "ndvi_auc": auc,
        }
    )
    return features


def mean_temporal_curve(ds: xr.Dataset) -> pd.DataFrame:
    rows = []
    for name in ["NDVI", "EVI", "NDWI", "SAVI"]:
        if name in ds:
            series = ds[name].mean(("y", "x"), skipna=True).to_pandas()
            for date, value in series.items():
                rows.append({"data": pd.to_datetime(date).date().isoformat(), "indice": name, "valor": float(value)})
    return pd.DataFrame(rows)
