from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    if not verbose:
        for logger_name in ["rasterio", "rasterio._env", "fiona", "pyogrio"]:
            logging.getLogger(logger_name).setLevel(logging.ERROR)


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").lower()
    return normalized or "area"


def load_yaml(path: str | Path) -> dict[str, Any]:
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_config(result[key], value)
        elif value is not None:
            result[key] = value
    return result


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def add_common_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--config", default="config.yaml", help="Arquivo YAML de configuracao.")
    parser.add_argument("--municipio", help="Nome do municipio.")
    parser.add_argument("--uf", help="Sigla da UF.")
    parser.add_argument("--poligono", help="GeoJSON/Shapefile/KML com a area de interesse.")
    parser.add_argument("--data-inicio", dest="data_inicio", help="Data inicial AAAA-MM-DD.")
    parser.add_argument("--data-fim", dest="data_fim", help="Data final AAAA-MM-DD.")
    parser.add_argument("--safra", choices=["verao", "safrinha", "manual"], help="Tipo de safra.")
    parser.add_argument("--limiar-provavel", type=float, help="Limiar fuzzy para milho provavel.")
    parser.add_argument("--limiar-possivel", type=float, help="Limiar fuzzy para milho possivel.")
    parser.add_argument("--area-minima-ha", type=float, help="Remove manchas menores que este valor.")
    parser.add_argument("--max-cenas", type=int, help="Numero maximo de cenas Sentinel-2.")
    parser.add_argument("--min-datas", type=int, help="Numero minimo de datas para classificar por fenologia.")
    parser.add_argument("--permitir-poucas-datas", action="store_true", help="Permite rodar mesmo com serie temporal insuficiente.")
    parser.add_argument("--area-referencia-ha", type=float, help="Area externa de referencia para comparacao, em hectares.")
    parser.add_argument("--amostras-milho", help="GeoJSON/Shapefile com poligonos conhecidos de milho.")
    parser.add_argument("--amostras-nao-milho", help="GeoJSON/Shapefile com poligonos conhecidos de nao milho.")
    parser.add_argument("--treino-regional", action="store_true", help="Processa tambem as amostras fora da area-alvo para treinar assinatura regional.")
    parser.add_argument("--pasta-saida", help="Pasta base de saida.")
    parser.add_argument("--stack-local", help="Pasta com GeoTIFFs multitemporais ja baixados.")
    parser.add_argument("--sem-rf", action="store_true", help="Desativa Random Forest com pseudo-amostras.")
    parser.add_argument("--verbose", action="store_true")
    return parser
