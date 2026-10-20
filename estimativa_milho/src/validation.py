from __future__ import annotations

import pandas as pd


def confidence_level(summary: pd.DataFrame, n_dates: int, cloud_note: str = "") -> str:
    if n_dates < 5:
        return "insuficiente"
    total = float(summary.loc[summary["categoria"] == "area_total_estimada_ha", "valor"].iloc[0])
    prov = float(summary.loc[summary["categoria"] == "area_provavel_milho_ha", "valor"].iloc[0])
    ratio = prov / total if total > 0 else 0
    if n_dates >= 8 and ratio >= 0.70:
        return "alta"
    if n_dates >= 5 and ratio >= 0.45:
        return "media"
    return "baixa"


def ensure_temporal_depth(n_dates: int, min_dates: int, allow_low_dates: bool) -> None:
    if n_dates >= min_dates or allow_low_dates:
        return
    raise RuntimeError(
        f"Serie temporal insuficiente: {n_dates} data(s) valida(s). "
        f"Para milho, use pelo menos {min_dates} datas cobrindo plantio, crescimento, pico e queda. "
        "Exemplo: --data-inicio 2023-09-01 --data-fim 2024-04-30 --max-cenas 12. "
        "Use --permitir-poucas-datas apenas para teste tecnico, nao para estimativa de area."
    )


def reference_comparison(summary: pd.DataFrame, reference_ha: float | None) -> pd.DataFrame:
    if reference_ha is None:
        return pd.DataFrame()
    total = float(summary.loc[summary["categoria"] == "area_total_estimada_ha", "valor"].iloc[0])
    diff = total - float(reference_ha)
    pct = (diff / float(reference_ha) * 100) if reference_ha else 0
    return pd.DataFrame(
        [
            {"categoria": "area_referencia_ha", "valor": round(float(reference_ha), 2)},
            {"categoria": "diferenca_estimativa_vs_referencia_ha", "valor": round(diff, 2)},
            {"categoria": "diferenca_estimativa_vs_referencia_pct", "valor": round(pct, 2)},
        ]
    )


def limitations_text() -> list[str]:
    return [
        "A classificacao nao usa amostras de campo; os resultados sao estimativas.",
        "Milho pode ser confundido com soja, feijao, arroz e pastagens temporarias quando a fenologia for parecida.",
        "Nuvens, sombras e lacunas temporais reduzem a confianca.",
        "Mapas oficiais exigem validacao local, inspeção visual e, idealmente, pontos de campo.",
        "A mascara de areas nao agricolas e aproximada quando nao houver MapBiomas ou outra camada auxiliar local.",
    ]
