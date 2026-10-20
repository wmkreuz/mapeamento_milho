from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from src.utils import add_common_args, ensure_dir, load_yaml, merge_config, setup_logging, slugify

log = logging.getLogger(__name__)


def load_prepared_stack(aoi, aoi_projected, cfg, area_label, target_crs):
    from src.download import download_sentinel2_assets, load_local_stack, load_sentinel2_stack
    from src.preprocess import apply_scl_cloud_mask, clip_stack, reproject_stack, scale_reflectance

    used_remote_stack = False
    if cfg.get("stack_local"):
        stack = load_local_stack(cfg["stack_local"])
    else:
        stack = load_sentinel2_stack(
            aoi,
            cfg["data_inicio"],
            cfg["data_fim"],
            int(cfg.get("nuvem_maxima", 40)),
            int(cfg.get("resolucao_m", 10)),
            int(cfg.get("max_cenas", 18)),
        )
        used_remote_stack = True

    stack = clip_stack(stack, aoi_projected)
    try:
        stack = scale_reflectance(stack)
        stack = apply_scl_cloud_mask(stack)
        if used_remote_stack:
            log.info("Materializando recorte remoto para validar leitura GDAL...")
            stack = stack.compute()
    except Exception as exc:
        message = str(exc)
        remote_read_error = any(
            token in message
            for token in [
                "SEC_E_NO_CREDENTIALS",
                "AcquireCredentialsHandle",
                "Error reading",
                "Error opening",
                "TIFFReadEncodedTile",
                "IReadBlock",
                "Read failed",
                "UnicodeDecodeError",
            ]
        )
        if not used_remote_stack or not remote_read_error:
            raise
        log.warning("Leitura remota pelo GDAL falhou no Windows; usando fallback por download local.")
        cache_dir = Path(cfg.get("pasta_cache", "data/raw")) / "planetary_cache" / slugify(area_label)
        local_folder = download_sentinel2_assets(
            aoi,
            cfg["data_inicio"],
            cfg["data_fim"],
            int(cfg.get("nuvem_maxima", 40)),
            int(cfg.get("max_cenas", 18)),
            cache_dir,
        )
        stack = load_local_stack(local_folder)
        stack = clip_stack(stack, aoi_projected)
        stack = scale_reflectance(stack)
        stack = apply_scl_cloud_mask(stack)

    return reproject_stack(stack, target_crs, float(cfg.get("resolucao_m", 10)))


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimativa local de area plantada de milho.")
    add_common_args(parser)
    return parser.parse_args()


def main() -> None:
    args = build_args()
    setup_logging(args.verbose)

    from src.area import load_aoi, projected_crs_for_area, save_aoi
    from src.classification import consensus_class, feature_rows_from_samples, random_forest_from_pseudo_samples
    from src.fuzzy import calculate_fuzzy, classify_fuzzy
    from src.indices import calculate_indices
    from src.postprocess import clean_classification, raster_to_polygons, summarize_area, write_raster
    from src.report import make_interactive_map, plot_temporal_curve, write_html_report
    from src.timeseries import extract_features, mean_temporal_curve, smooth_indices
    from src.validation import confidence_level, ensure_temporal_depth, limitations_text, reference_comparison

    config_path = Path(args.config)
    config = load_yaml(config_path)
    defaults = config.get("defaults", {})
    cli = {k: v for k, v in vars(args).items() if v is not None and k not in {"config", "verbose"}}
    if args.sem_rf:
        cli["usar_random_forest"] = False
    cfg = merge_config(defaults, cli)

    safra = cfg.get("safra", "manual")
    phenology = config.get("fenologia", {}).get(safra, config.get("fenologia", {}).get("manual", {}))
    masks = config.get("mascaras", {})

    area_label = cfg.get("municipio") or Path(cfg.get("poligono", "area")).stem
    if cfg.get("uf"):
        area_label = f"{area_label}_{cfg['uf']}"
    output_dir = ensure_dir(Path(cfg.get("pasta_saida", "data/output")) / slugify(area_label))

    aoi = load_aoi(cfg.get("municipio"), cfg.get("uf"), cfg.get("poligono"))
    target_crs = projected_crs_for_area(aoi)
    aoi_projected = aoi.to_crs(target_crs)
    save_aoi(aoi_projected, output_dir)

    stack = load_prepared_stack(aoi, aoi_projected, cfg, area_label, target_crs)

    ds = calculate_indices(stack)
    ds = smooth_indices(ds)
    n_dates = int(ds.sizes.get("time", 0))
    ensure_temporal_depth(
        n_dates,
        int(cfg.get("min_datas", 5)),
        bool(cfg.get("permitir_poucas_datas", False)),
    )
    features = extract_features(ds).rio.write_crs(target_crs)
    fuzzy = calculate_fuzzy(features, phenology, masks).rio.write_crs(target_crs)
    fuzzy_class = classify_fuzzy(
        fuzzy,
        float(cfg.get("limiar_possivel", 0.50)),
        float(cfg.get("limiar_provavel", 0.70)),
    ).rio.write_crs(target_crs)

    rf = None
    regional_milho_features = None
    regional_nao_milho_features = None
    if cfg.get("treino_regional"):
        import geopandas as gpd

        for sample_key, label_name in [("amostras_milho", "milho"), ("amostras_nao_milho", "nao_milho")]:
            sample_path = cfg.get(sample_key)
            if not sample_path:
                continue
            log.info("Processando amostra regional (%s): %s", label_name, sample_path)
            sample_gdf = gpd.read_file(sample_path)
            if sample_gdf.crs is None:
                sample_gdf = sample_gdf.set_crs("EPSG:4326")
            sample_gdf = sample_gdf.to_crs("EPSG:4326").dissolve().reset_index(drop=True)
            sample_target_crs = projected_crs_for_area(sample_gdf)
            sample_projected = sample_gdf.to_crs(sample_target_crs)
            sample_stack = load_prepared_stack(
                sample_gdf,
                sample_projected,
                {**cfg, "stack_local": None},
                f"amostra_{label_name}_{Path(sample_path).stem}",
                sample_target_crs,
            )
            sample_ds = smooth_indices(calculate_indices(sample_stack))
            sample_features = extract_features(sample_ds).rio.write_crs(sample_target_crs)
            rows = feature_rows_from_samples(sample_features, sample_path, label_name=label_name)
            if label_name == "milho":
                regional_milho_features = rows
            else:
                regional_nao_milho_features = rows

    if cfg.get("usar_random_forest", True):
        rf = random_forest_from_pseudo_samples(
            features,
            fuzzy,
            milho_samples=cfg.get("amostras_milho"),
            nao_milho_samples=cfg.get("amostras_nao_milho"),
            regional_milho_features=regional_milho_features,
            regional_nao_milho_features=regional_nao_milho_features,
        )
        if rf is not None:
            rf = rf.rio.write_crs(target_crs)

    consensus = consensus_class(fuzzy_class, rf).rio.write_crs(target_crs)
    cleaned = clean_classification(
        consensus,
        float(cfg.get("resolucao_m", 10)),
        float(cfg.get("area_minima_ha", 0.50)),
    ).rio.write_crs(target_crs)

    write_raster(fuzzy, output_dir / "resultado_milho_probabilidade.tif", dtype="float32")
    write_raster(cleaned, output_dir / "resultado_milho_classificado.tif", dtype="uint8")
    polygons = raster_to_polygons(cleaned, float(cfg.get("area_minima_ha", 0.50)), output_dir)
    summary = summarize_area(cleaned, float(cfg.get("resolucao_m", 10)), polygons)
    summary.to_csv(output_dir / "resumo.csv", index=False, encoding="utf-8-sig")
    reference = reference_comparison(summary, cfg.get("area_referencia_ha"))
    if not reference.empty:
        reference.to_csv(output_dir / "comparacao_referencia.csv", index=False, encoding="utf-8-sig")

    curve = mean_temporal_curve(ds)
    curve.to_csv(output_dir / "serie_temporal_media.csv", index=False, encoding="utf-8-sig")
    curve_png = plot_temporal_curve(curve, output_dir)
    map_html = make_interactive_map(aoi_projected, polygons, output_dir)
    confidence = confidence_level(summary, n_dates)
    report = write_html_report(
        output_dir=output_dir,
        area_name=area_label.replace("_", "/") if cfg.get("uf") else area_label,
        period=f"{cfg['data_inicio']} a {cfg['data_fim']}",
        images_used=n_dates,
        summary=summary,
        confidence=confidence,
        limitations=limitations_text(),
        curve_png=curve_png,
        map_html=map_html,
        reference=reference,
    )

    values = {row["categoria"]: row["valor"] for _, row in summary.iterrows()}
    print(f"Area analisada: {area_label}")
    print(f"Periodo analisado: {cfg['data_inicio']} a {cfg['data_fim']}")
    print(f"Area provavel de milho: {values['area_provavel_milho_ha']:.2f} ha")
    print(f"Area possivel de milho: {values['area_possivel_milho_ha']:.2f} ha")
    print(f"Area total estimada: {values['area_total_estimada_ha']:.2f} ha")
    print(f"Confianca: {confidence}")
    print(f"Arquivos gerados em: {output_dir}")
    print(f"Relatorio: {report}")


if __name__ == "__main__":
    main()
