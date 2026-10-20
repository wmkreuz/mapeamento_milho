from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import xarray as xr

log = logging.getLogger(__name__)


FEATURE_NAMES = [
    "ndvi_min",
    "ndvi_max",
    "ndvi_mean",
    "ndvi_amp",
    "evi_max",
    "ndwi_max",
    "high_fraction",
    "growth",
    "drop",
    "ndvi_auc",
]


def _feature_matrix(features: xr.Dataset) -> tuple[np.ndarray, np.ndarray]:
    arrays = [features[name].values.ravel() for name in FEATURE_NAMES if name in features]
    x = np.vstack(arrays).T
    valid = np.isfinite(x).all(axis=1)
    return x, valid


def _rasterize_samples(features: xr.Dataset, milho_path: str | None, nao_milho_path: str | None) -> np.ndarray:
    labels = np.full(features[FEATURE_NAMES[0]].shape, -1, dtype=np.int8)
    if not milho_path and not nao_milho_path:
        return labels

    import geopandas as gpd
    from rasterio.features import rasterize

    transform = features.rio.transform()
    crs = features.rio.crs
    for path, label in [(nao_milho_path, 0), (milho_path, 1)]:
        if not path:
            continue
        sample_path = Path(path)
        if not sample_path.exists():
            raise FileNotFoundError(f"Arquivo de amostras nao encontrado: {sample_path}")
        gdf = gpd.read_file(sample_path)
        if gdf.empty:
            log.warning("Arquivo de amostras vazio: %s", sample_path)
            continue
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        gdf = gdf.to_crs(crs)
        mask = rasterize(
            [(geom, label) for geom in gdf.geometry if geom and not geom.is_empty],
            out_shape=labels.shape,
            transform=transform,
            fill=-1,
            all_touched=True,
            dtype="int8",
        )
        labels[mask == label] = label
        count = int((mask == label).sum())
        sample_name = "milho" if label == 1 else "nao milho"
        if count == 0:
            log.warning(
                "Amostras de %s nao cruzam o raster processado; elas nao serao usadas no RF: %s",
                sample_name,
                sample_path,
            )
        else:
            log.info("Amostras %s rasterizadas: %s pixels", sample_name, count)
    return labels


def feature_rows_from_samples(features: xr.Dataset, sample_path: str, label_name: str = "milho") -> np.ndarray:
    labels = _rasterize_samples(
        features,
        milho_path=sample_path if label_name == "milho" else None,
        nao_milho_path=sample_path if label_name != "milho" else None,
    )
    label_value = 1 if label_name == "milho" else 0
    x, valid_features = _feature_matrix(features)
    selected = (labels.ravel() == label_value) & valid_features
    rows = x[selected]
    log.info("Assinatura regional extraida (%s): %s pixels validos", label_name, rows.shape[0])
    return rows


def random_forest_from_pseudo_samples(
    features: xr.Dataset,
    fuzzy: xr.DataArray,
    milho_samples: str | None = None,
    nao_milho_samples: str | None = None,
    regional_milho_features: np.ndarray | None = None,
    regional_nao_milho_features: np.ndarray | None = None,
) -> xr.DataArray | None:
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError:
        log.warning("scikit-learn indisponivel; pulando Random Forest.")
        return None

    x, valid_features = _feature_matrix(features)
    f = fuzzy.values.ravel()
    valid = valid_features & np.isfinite(f)
    x_valid = x[valid]
    f_valid = f[valid]
    y = np.full(f_valid.shape, -1, dtype=np.int8)
    y[f_valid >= 0.78] = 1
    y[f_valid <= 0.25] = 0

    sample_labels = _rasterize_samples(features, milho_samples, nao_milho_samples).ravel()
    sample_valid = sample_labels[valid]
    real_mask = sample_valid >= 0
    if real_mask.any():
        y[real_mask] = sample_valid[real_mask]
        log.info(
            "Amostras reais usadas no RF: milho=%s, nao_milho=%s",
            int((sample_valid == 1).sum()),
            int((sample_valid == 0).sum()),
        )
    sample_mask = y >= 0

    if sample_mask.sum() < 100 or len(np.unique(y[sample_mask])) < 2:
        if regional_milho_features is None and regional_nao_milho_features is None:
            log.warning("Pseudo-amostras insuficientes; RF sera ignorado.")
            return None

    rng = np.random.default_rng(42)
    sample_idx = np.where(sample_mask)[0]
    x_train_parts = []
    y_train_parts = []
    for cls in [0, 1]:
        cls_idx = sample_idx[y[sample_idx] == cls]
        if cls_idx.size:
            max_per_class = min(cls_idx.size, 10000)
            chosen = rng.choice(cls_idx, max_per_class, replace=False)
            x_train_parts.append(x_valid[chosen])
            y_train_parts.append(np.full(chosen.shape[0], cls, dtype=np.int8))

    if regional_milho_features is not None and regional_milho_features.size:
        x_train_parts.append(regional_milho_features)
        y_train_parts.append(np.ones(regional_milho_features.shape[0], dtype=np.int8))
        log.info("RF recebeu assinatura regional de milho: %s pixels", regional_milho_features.shape[0])

    if regional_nao_milho_features is not None and regional_nao_milho_features.size:
        x_train_parts.append(regional_nao_milho_features)
        y_train_parts.append(np.zeros(regional_nao_milho_features.shape[0], dtype=np.int8))
        log.info("RF recebeu assinatura regional de nao milho: %s pixels", regional_nao_milho_features.shape[0])

    if not x_train_parts:
        log.warning("Sem amostras para treinar RF; RF sera ignorado.")
        return None

    x_train = np.vstack(x_train_parts)
    y_train = np.concatenate(y_train_parts)
    if len(np.unique(y_train)) < 2:
        log.warning("Treino RF tem apenas uma classe; RF sera ignorado.")
        return None

    if x_train.shape[0] > 30000:
        idx = rng.choice(np.arange(x_train.shape[0]), 30000, replace=False)
        x_train = x_train[idx]
        y_train = y_train[idx]

    clf = RandomForestClassifier(
        n_estimators=120,
        max_depth=14,
        min_samples_leaf=5,
        n_jobs=-1,
        random_state=42,
        class_weight="balanced",
    )
    clf.fit(x_train, y_train)
    classes = list(clf.classes_)
    if 1 not in classes:
        log.warning("RF treinou sem classe milho; RF sera ignorado.")
        return None
    pred = np.zeros(f.shape, dtype="uint8")
    prob = clf.predict_proba(x_valid)[:, classes.index(1)]
    pred_valid = (prob >= 0.50).astype("uint8")
    pred[valid] = pred_valid
    return xr.DataArray(pred.reshape(fuzzy.shape), coords=fuzzy.coords, dims=fuzzy.dims, name="rf_milho")


def consensus_class(fuzzy_class: xr.DataArray, rf_class: xr.DataArray | None) -> xr.DataArray:
    if rf_class is None:
        return fuzzy_class.rename("classe_consenso")
    consensus = xr.zeros_like(fuzzy_class, dtype="uint8")
    consensus = xr.where((fuzzy_class >= 1) | (rf_class == 1), 1, consensus)
    consensus = xr.where((fuzzy_class == 2) & (rf_class == 1), 2, consensus)
    consensus = xr.where((fuzzy_class == 2) & (rf_class == 0), 1, consensus)
    return consensus.rename("classe_consenso")
