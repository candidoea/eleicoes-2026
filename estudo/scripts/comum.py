"""Caminhos e cargas comuns aos scripts do estudo do 2º turno."""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
RAIZ = Path(__file__).resolve().parents[2]          # raiz do repositório
ESTUDO = RAIZ / "estudo"
DADOS = ESTUDO / "dados"                             # entradas do estudo (versionadas)
RES = ESTUDO / "resultados"                          # saídas intermediárias (csv)
FIG = ESTUDO / "fig"
RES.mkdir(exist_ok=True)
FIG.mkdir(exist_ok=True)
sys.path.insert(0, str(RAIZ))
import projecao as pj  # noqa: E402

REGIAO = {"AC": "Norte", "AM": "Norte", "AP": "Norte", "PA": "Norte", "RO": "Norte", "RR": "Norte", "TO": "Norte",
          "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "PB": "Nordeste", "PE": "Nordeste",
          "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste", "DF": "Centro-Oeste", "GO": "Centro-Oeste",
          "MS": "Centro-Oeste", "MT": "Centro-Oeste", "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
          "PR": "Sul", "RS": "Sul", "SC": "Sul"}


def presidente() -> pd.DataFrame:
    """Uma linha por município: 1º turno por grupo de candidato, totais dos dois turnos e perfil do eleitorado."""
    b = pd.read_parquet(pj.MODELO / "base_2026.parquet")
    b = b[b.cargo == 1]
    t = pd.read_parquet(pj.MODELO / "totais_2026.parquet")
    t = t[t.cargo == 1]
    grupos = {"PT": "lula1", "PL": "flavio1", "AVANTE": "cury1", "MISSÃO": "renan1", "PSD": "caiado1", "NOVO": "zema1"}
    b["g"] = b.partido.map(grupos).fillna("outros1")
    w = b.pivot_table(index=["uf", "cd_tse"], columns="g", values="votos", aggfunc="sum", fill_value=0).reset_index()
    w = w.merge(t[["uf", "cd_tse", "aptos", "comparecimento", "validos"]]
                .rename(columns={"aptos": "aptos1", "comparecimento": "comp1", "validos": "vv1"}), on=["uf", "cd_tse"])
    m = pd.read_parquet(DADOS / "mun_2t.parquet")
    m = m[m.cargo == 1].copy()
    m["lula2"] = np.where(m.p0 == "PT", m.v0, m.v1)
    m["flavio2"] = np.where(m.p0 == "PL", m.v0, m.v1)
    m = m.rename(columns={"aptos": "aptos2", "comp": "comp2", "abst": "abst2", "vv": "vv2", "vb": "vb2", "vn": "vn2"})
    d = w.merge(m[["uf", "cd_tse", "aptos2", "comp2", "abst2", "vv2", "vb2", "vn2", "lula2", "flavio2"]], on=["uf", "cd_tse"])
    d = d.merge(pd.read_parquet(DADOS / "perfil_mun.parquet"), on=["uf", "cd_tse"], how="left")
    d["regiao"] = d.uf.map(REGIAO)
    return d


def snapshots() -> pd.DataFrame:
    return pd.read_parquet(DADOS / "snapshots_oficial2.parquet")
