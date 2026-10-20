from __future__ import annotations

import numpy as np
import xarray as xr


def rising(x, low, high):
    return xr.where(x <= low, 0, xr.where(x >= high, 1, (x - low) / (high - low)))


def falling(x, low, high):
    return xr.where(x <= low, 1, xr.where(x >= high, 0, (high - x) / (high - low)))


def month_membership(month, start: int, end: int):
    if start <= end:
        inside = (month >= start) & (month <= end)
    else:
        inside = (month >= start) | (month <= end)
    near = xr.where(inside, 1.0, 0.35)
    return near


def calculate_fuzzy(features: xr.Dataset, phenology: dict, masks: dict) -> xr.DataArray:
    ndvi_low, ndvi_high = phenology.get("ndvi_max_bom", [0.50, 0.82])
    amp_low, amp_high = phenology.get("amplitude_boa", [0.20, 0.60])

    vigor = rising(features["ndvi_max"], ndvi_low, ndvi_high)
    amplitude = rising(features["ndvi_amp"], amp_low, amp_high)
    growth = rising(features["growth"], 0.15, 0.45)
    drop = rising(features["drop"], 0.12, 0.40)
    evi = rising(features["evi_max"], 0.30, 0.65)
    peak = month_membership(
        features["peak_month"],
        int(phenology.get("pico_inicio_mes", 1)),
        int(phenology.get("pico_fim_mes", 12)),
    )

    permanent_penalty = falling(
        features["high_fraction"],
        float(masks.get("fracao_alto_permanente", 0.75)) - 0.20,
        float(masks.get("fracao_alto_permanente", 0.75)),
    )
    water_penalty = falling(features["ndwi_max"], float(masks.get("ndwi_agua", 0.20)), 0.45)
    urban_penalty = rising(features["ndvi_max"], float(masks.get("ndvi_urbano_max", 0.20)), 0.45)

    score = (
        0.22 * vigor
        + 0.22 * amplitude
        + 0.16 * growth
        + 0.16 * drop
        + 0.10 * evi
        + 0.14 * peak
    )
    score = score * permanent_penalty * water_penalty * urban_penalty
    score = score.clip(0, 1).rename("milho_fuzzy")
    return score.where(np.isfinite(score), 0)


def classify_fuzzy(fuzzy: xr.DataArray, limiar_possivel: float, limiar_provavel: float) -> xr.DataArray:
    cls = xr.zeros_like(fuzzy, dtype="uint8")
    cls = xr.where(fuzzy >= limiar_possivel, 1, cls)
    cls = xr.where(fuzzy >= limiar_provavel, 2, cls)
    return cls.rename("classe_fuzzy")
