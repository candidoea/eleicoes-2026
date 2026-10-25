"""Malhas embarcadas (assets/geo), já simplificadas e com o sentido dos anéis corrigido
para o plotly (anel externo horário). Origem: tbrugz/geodata-br (base IBGE).
br_mun.json: 5.564 municípios (propriedades codarea = código IBGE de 7 dígitos, nome, uf).
br_uf.json : 27 UFs (codarea = código IBGE de 2 dígitos, uf)."""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

GEO = Path(__file__).parent / "assets" / "geo"


@lru_cache(maxsize=1)
def _mun() -> dict:
    return json.loads((GEO / "br_mun.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def ufs() -> dict:
    return json.loads((GEO / "br_uf.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _mun_leve() -> dict:
    p = GEO / "br_mun_leve.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else _mun()


def municipios_brasil(leve: bool = False) -> dict:
    """leve=True: malha ~3x menor (tolerância ~1 km), usada no mapa nacional para renderizar rápido."""
    return _mun_leve() if leve else _mun()


@lru_cache(maxsize=32)
def municipios_uf(uf: str) -> dict:
    g = _mun()
    return {"type": "FeatureCollection",
            "features": [f for f in g["features"] if f["properties"]["uf"] == uf.upper()]}


@lru_cache(maxsize=1)
def municipios_df() -> pd.DataFrame:
    return pd.DataFrame([{"cd_ibge": f["properties"]["codarea"], "nome": f["properties"]["nome"],
                          "uf": f["properties"]["uf"]} for f in _mun()["features"]])


def uf_unica(uf: str) -> dict:
    g = ufs()
    return {"type": "FeatureCollection", "features": [copy.deepcopy(f) for f in g["features"]
                                                      if f["properties"]["uf"] == uf.upper()]}
