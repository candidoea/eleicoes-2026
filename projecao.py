"""Projeção do 2º turno durante a apuração.

Ideia (modelo de "noite de eleição"): o TSE libera municípios em ordem não aleatória (estados, capitais e
interior chegam em horários diferentes), então a parcial contada é enviesada. Para corrigir, cada município
tem uma linha de base: o voto do 1º turno. O modelo aprende, nos municípios já totalizados, como o voto do
1º turno se converteu no 2º e aplica isso aos que faltam.

Etapa 1 (transferência, interpretável). Para cada município m, com fatias do 1º turno s_A, s_B e s_k
(demais candidatos):
    y_m = s_A,m + γ + Σ_k β_k s_k,m + u_UF + e_m
y = fatia do finalista A entre os votos válidos do 2º turno; β_k = fração dos eleitores do candidato k
que foram para A (entre os que escolheram um finalista); γ = deslocamento geral; u_UF = efeito do estado
(médias de resíduo encolhidas). β em [0, 1], com prior fraco (ridge) para os primeiros minutos.
Etapa 2 (aprendizado de máquina). Com 400 municípios ou mais, um LightGBM aprende o resíduo da etapa 1
a partir do perfil do município; só entra se reduzir o erro em validação cruzada.
Comparecimento: válidos do 2º turno = válidos do 1º turno x razão estimada por UF.
Incerteza: bootstrap dos municípios totalizados.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

MODELO = Path(__file__).parent / "modelo"
REGIAO = {"AC": 1, "AM": 1, "AP": 1, "PA": 1, "RO": 1, "RR": 1, "TO": 1, "AL": 2, "BA": 2, "CE": 2, "MA": 2,
          "PB": 2, "PE": 2, "PI": 2, "RN": 2, "SE": 2, "DF": 3, "GO": 3, "MS": 3, "MT": 3, "ES": 4, "MG": 4,
          "RJ": 4, "SP": 4, "PR": 5, "RS": 5, "SC": 5}
# Prior (hipótese fraca, só para antes dos primeiros municípios): fração dos eleitores de cada candidato
# eliminado que iria para o finalista A. Os dados substituem esses valores à medida que chegam.
PRIOR_PRESIDENTE = {"AVANTE": 0.45, "MISSÃO": 0.25, "PSD": 0.15, "NOVO": 0.15}
PRIOR_PADRAO = 0.5
FINALISTAS = {1: ("PT", "PL"), ("3", "AC"): ("PP", "REPUBLICANOS"), ("3", "AM"): ("PSD", "PL"),
              ("3", "DF"): ("PT", "PP"), ("3", "ES"): ("MDB", "REPUBLICANOS"), ("3", "RN"): ("PT", "UNIÃO"),
              ("3", "TO"): ("UNIÃO", "PSDB")}
UFS_GOV_2T = ["AC", "AM", "DF", "ES", "RN", "TO"]


def finalistas(cargo: int, uf: str | None = None) -> tuple[str, str]:
    return FINALISTAS[1] if cargo == 1 else FINALISTAS[("3", uf)]


@dataclass
class Projecao:
    partidos: tuple
    pct_a: float = np.nan              # projeção, % dos válidos
    p05: float = np.nan
    p95: float = np.nan
    prob_a: float = np.nan             # probabilidade de A vencer (bootstrap)
    contado_a: float = np.nan          # % de A no que já foi contado
    pct_contado: float = 0.0           # % dos válidos esperados já contados
    municipios: int = 0
    totalizados: int = 0
    parciais: int = 0
    betas: dict = field(default_factory=dict)
    gama: float = 0.0
    usa_ml: bool = False
    cv_mae: dict = field(default_factory=dict)   # erro municipal em validação cruzada (pontos percentuais)
    por_uf: pd.DataFrame = field(default_factory=pd.DataFrame)
    por_municipio: pd.DataFrame = field(default_factory=pd.DataFrame)


# ---------------------------------------------------------------- base do 1º turno
@lru_cache(maxsize=16)
def _base_cache(arq_base: str, arq_tot: str, cargo: int, ufs: tuple, a: str, b: str, k_outros: int):
    base = pd.read_parquet(arq_base)
    tot = pd.read_parquet(arq_tot)
    base = base[(base["cargo"] == cargo) & base["uf"].isin(ufs)]
    tot = tot[(tot["cargo"] == cargo) & tot["uf"].isin(ufs)]
    return montar_base(base, tot, a, b, k_outros)


def montar_base(base: pd.DataFrame, tot: pd.DataFrame, a: str, b: str, k_outros: int = 4):
    """base: uf, cd_tse, partido, votos (1º turno). tot: uf, cd_tse, aptos, validos."""
    outros = (base[~base["partido"].isin([a, b])].groupby("partido")["votos"].sum()
              .sort_values(ascending=False).index[:k_outros].tolist())
    base = base.assign(grupo=np.where(base["partido"].isin([a, b] + outros), base["partido"], "OUTROS"))
    larga = base.pivot_table(index=["uf", "cd_tse"], columns="grupo", values="votos", aggfunc="sum", fill_value=0)
    cols = [a, b] + outros + (["OUTROS"] if "OUTROS" in larga.columns else [])
    larga = larga.reindex(columns=cols, fill_value=0)
    tot1 = larga.sum(axis=1).replace(0, np.nan)
    s = larga.div(tot1, axis=0).add_prefix("s_")
    d = s.join(tot.set_index(["uf", "cd_tse"])[["aptos", "validos"]].rename(columns={"validos": "validos1"}))
    d["validos1"] = d["validos1"].fillna(tot1)
    d["comp1"] = d["validos1"] / d["aptos"].replace(0, np.nan)
    d["log_aptos"] = np.log1p(d["aptos"].fillna(0))
    d = d.reset_index()
    d["regiao"] = d["uf"].map(REGIAO).fillna(0)
    return d.dropna(subset=["s_" + a]), outros + (["OUTROS"] if "OUTROS" in larga.columns else [])


def base_2026(cargo: int, ufs: list[str], a: str, b: str):
    return _base_cache(str(MODELO / "base_2026.parquet"), str(MODELO / "totais_2026.parquet"), cargo,
                       tuple(sorted(ufs)), a, b, 4 if cargo == 1 else 2)


# ---------------------------------------------------------------- ajuste
def _ajuste_transferencia(X, z, w, prior, lam):
    """min Σ w (z - γ - Xβ)² + lam·|β - prior|² + lam·γ² com β em [0,1]."""
    from scipy.optimize import lsq_linear
    n, k = X.shape
    sw = np.sqrt(w)
    A = np.column_stack([np.ones(n), X]) * sw[:, None]
    y = z * sw
    reg = np.sqrt(lam) * np.eye(k + 1)
    A = np.vstack([A, reg])
    y = np.concatenate([y, np.sqrt(lam) * np.concatenate([[0.0], prior])])
    lo = np.concatenate([[-0.3], np.zeros(k)])
    hi = np.concatenate([[0.3], np.ones(k)])
    sol = lsq_linear(A, y, bounds=(lo, hi), method="bvls")
    return sol.x[0], sol.x[1:]


def _efeito_uf(res, uf, w, kappa):
    df = pd.DataFrame({"r": res * w, "w": w, "uf": uf})
    g = df.groupby("uf")[["r", "w"]].sum()
    return (g["r"] / (g["w"] + kappa)).to_dict()


class Modelo:
    def __init__(self, cols_outros, prior, lam_frac=0.0003, kappa_frac=0.002):
        self.cols = ["s_" + c for c in cols_outros]
        self.prior = np.asarray(prior, float)
        self.lam_frac, self.kappa_frac = lam_frac, kappa_frac
        self.ml = None

    def fit(self, d: pd.DataFrame, a: str, usar_ml: bool | None = None):
        X, z, w = d[self.cols].to_numpy(), (d["y"] - d["s_" + a]).to_numpy(), d["w"].to_numpy()
        lam = self.lam_frac * max(w.sum(), 1)
        self.gama, self.beta = _ajuste_transferencia(X, z, w, self.prior, lam)
        res = z - self.gama - X @ self.beta
        self.uf = _efeito_uf(res, d["uf"].to_numpy(), w, self.kappa_frac * max(w.sum(), 1))
        self.ml = None
        if usar_ml and len(d) >= 400:
            import lightgbm as lgb
            r2 = res - d["uf"].map(self.uf).fillna(0).to_numpy()
            self.ml = lgb.LGBMRegressor(n_estimators=150, learning_rate=0.05, num_leaves=15, min_child_samples=40,
                                        subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
            self.ml.fit(d[self._feats(a)], r2, sample_weight=w)
        return self

    def _feats(self, a):
        return ["s_" + a] + self.cols + ["comp1", "log_aptos", "regiao"]

    def predict(self, d: pd.DataFrame, a: str) -> np.ndarray:
        p = d["s_" + a].to_numpy() + self.gama + d[self.cols].to_numpy() @ self.beta
        p = p + d["uf"].map(self.uf).fillna(0).to_numpy()
        if self.ml is not None:
            p = p + self.ml.predict(d[self._feats(a)])
        return np.clip(p, 0.01, 0.99)


def _cv_mae(d, a, cols_outros, prior, usar_ml, k=5, seed=7):
    if len(d) < 50:
        return np.nan
    rng = np.random.default_rng(seed)
    dobra = rng.integers(0, k, len(d))
    erros, pesos = [], []
    for i in range(k):
        tr, te = d[dobra != i], d[dobra == i]
        m = Modelo(cols_outros, prior).fit(tr, a, usar_ml)
        erros.append(np.abs(m.predict(te, a) - te["y"].to_numpy()))
        pesos.append(te["w"].to_numpy())
    e, p = np.concatenate(erros), np.concatenate(pesos)
    return float(100 * (e * p).sum() / p.sum())


# ---------------------------------------------------------------- projeção
def projetar(base: pd.DataFrame, cols_outros: list[str], vivo: pd.DataFrame, a: str, b: str,
             prior: list[float] | None = None, n_boot: int = 40, limiar_tot: float = 99.99,
             calcular_cv: bool = True) -> Projecao:
    """vivo: 1 linha por município com uf, cd_tse, va, vb, pst (% seções totalizadas no município)."""
    if prior is None:
        prior = [PRIOR_PRESIDENTE.get(c, PRIOR_PADRAO) for c in cols_outros]
    d = base.merge(vivo[["uf", "cd_tse", "va", "vb", "pst"]], on=["uf", "cd_tse"], how="left")
    d[["va", "vb", "pst"]] = d[["va", "vb", "pst"]].fillna(0)
    d["contado"] = d["va"] + d["vb"]
    tot_mask = (d["pst"] >= limiar_tot) & (d["contado"] > 0)
    d["y"] = np.where(d["contado"] > 0, d["va"] / d["contado"].replace(0, np.nan), np.nan)
    d["w"] = d["contado"]
    treino = d[tot_mask]

    # comparecimento: válidos 2T / válidos 1T, por UF encolhido para a razão geral
    if len(treino) >= 5:
        r_geral = treino["contado"].sum() / treino["validos1"].sum()
        g = treino.groupby("uf")[["contado", "validos1"]].sum()
        k_ = 0.05 * treino["validos1"].sum() / max(len(g), 1)
        r_uf = ((g["contado"] + k_ * r_geral) / (g["validos1"] + k_)).to_dict()
    else:
        r_geral, r_uf = 0.97, {}
    razao = d["uf"].map(r_uf).fillna(r_geral)
    esperado = np.where(tot_mask, d["contado"],
                        np.where(d["pst"] >= 5, np.maximum(d["contado"] / (d["pst"] / 100).clip(lower=0.05),
                                                           d["contado"]), d["validos1"] * razao))
    falta = np.maximum(esperado - d["contado"], 0)
    peso_obs = (d["pst"] / 100).clip(0, 1).to_numpy()

    usar_ml = None
    cv = {}
    if calcular_cv and len(treino) >= 50:
        cv["transferência"] = _cv_mae(treino, a, cols_outros, prior, False)
        if len(treino) >= 400:
            cv["transferência + LightGBM"] = _cv_mae(treino, a, cols_outros, prior, True)
            usar_ml = cv["transferência + LightGBM"] < cv["transferência"] - 0.02
    elif len(treino) >= 400:
        usar_ml = True

    def total(modelo):
        pred = modelo.predict(d, a)
        obs = d["y"].fillna(0).to_numpy()
        share_falta = np.where(d["contado"] > 0, peso_obs * obs + (1 - peso_obs) * pred, pred)
        ta = d["va"].to_numpy() + falta * share_falta
        tb = d["vb"].to_numpy() + falta * (1 - share_falta)
        return ta, tb, pred

    if len(treino) == 0:  # antes do primeiro município: só a prior
        m0 = Modelo(cols_outros, prior)
        m0.gama, m0.beta, m0.uf, m0.ml = 0.0, np.asarray(prior, float), {}, None
        ta, tb, pred = total(m0)
        rng = np.random.default_rng(1)
        boots = []
        for _ in range(n_boot):
            mb = Modelo(cols_outros, prior)
            mb.gama, mb.uf, mb.ml = rng.normal(0, 0.02), {}, None
            mb.beta = np.clip(np.asarray(prior) + rng.normal(0, 0.15, len(prior)), 0, 1)
            xa, xb, _ = total(mb)
            boots.append(xa.sum() / (xa.sum() + xb.sum()))
        modelo = m0
    else:
        modelo = Modelo(cols_outros, prior).fit(treino, a, usar_ml)
        ta, tb, pred = total(modelo)
        rng = np.random.default_rng(2)
        boots = []
        idx = np.arange(len(treino))
        for _ in range(n_boot):
            amostra = treino.iloc[rng.choice(idx, len(idx), replace=True)]
            mb = Modelo(cols_outros, prior).fit(amostra, a, False)
            if modelo.ml is not None:
                mb.ml = modelo.ml
            xa, xb, _ = total(mb)
            boots.append(xa.sum() / (xa.sum() + xb.sum()))
    boots = np.asarray(boots)
    pa = ta.sum() / (ta.sum() + tb.sum())
    # o bootstrap só mede a incerteza dos coeficientes; somamos um piso de erro municipal agregado
    sd = np.sqrt(boots.var() + (0.004 * (1 - d["contado"].sum() / max(esperado.sum(), 1))) ** 2)
    from math import erf, sqrt
    prob = 0.5 * (1 + erf((pa - 0.5) / (sd * sqrt(2)))) if sd > 0 else float(pa > 0.5)

    d["pred_a"], d["proj_a_mun"] = pred, ta / np.maximum(ta + tb, 1)
    d["esperado"], d["totalizado"] = esperado, tot_mask
    uf = d.assign(ta=ta, tb=tb).groupby("uf").agg(ta=("ta", "sum"), tb=("tb", "sum"), va=("va", "sum"),
                                                   vb=("vb", "sum"), esperado=("esperado", "sum"),
                                                   contado=("contado", "sum"))
    uf["proj_a"] = 100 * uf["ta"] / (uf["ta"] + uf["tb"])
    uf["contado_a"] = 100 * uf["va"] / uf["contado"].replace(0, np.nan)
    uf["pct_contado"] = 100 * uf["contado"] / uf["esperado"].replace(0, np.nan)
    contado = d["contado"].sum()
    return Projecao(
        partidos=(a, b), pct_a=100 * pa, p05=100 * (pa - 1.645 * sd), p95=100 * (pa + 1.645 * sd), prob_a=prob,
        contado_a=100 * d["va"].sum() / contado if contado else np.nan,
        pct_contado=100 * contado / max(esperado.sum(), 1), municipios=len(d), totalizados=int(tot_mask.sum()),
        parciais=int(((d["pst"] > 0) & ~tot_mask).sum()),
        betas=dict(zip(cols_outros, np.round(modelo.beta, 3))), gama=float(modelo.gama),
        usa_ml=modelo.ml is not None, cv_mae=cv, por_uf=uf.reset_index(),
        por_municipio=d[["uf", "cd_tse", "pst", "va", "vb", "y", "pred_a", "proj_a_mun", "esperado", "totalizado",
                         "s_" + a, "s_" + b]],
    )


def vivo_de_longo(longo: pd.DataFrame, a: str, b: str) -> pd.DataFrame:
    """Converte o formato longo do painel (1 linha por candidato x município) em 1 linha por município."""
    if longo is None or longo.empty or "partido" not in longo:
        return pd.DataFrame({"uf": pd.Series(dtype=str), "cd_tse": pd.Series(dtype=str), "va": pd.Series(dtype=float),
                             "vb": pd.Series(dtype=float), "pst": pd.Series(dtype=float)})
    l = longo.copy()
    l["cd_tse"] = l["cd_tse"].astype(str).str.zfill(5)
    piv = l.pivot_table(index=["uf", "cd_tse"], columns="partido", values="votos", aggfunc="sum", fill_value=0)
    out = pd.DataFrame({"va": piv.get(a, 0), "vb": piv.get(b, 0)})
    out["pst"] = l.groupby(["uf", "cd_tse"])["pct_secoes"].max()
    return out.reset_index()


# ---------------------------------------------------------------- validação histórica (2022)
def backtest_2022(marcos=(0.02, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90)) -> pd.DataFrame:
    """Reexecuta a noite do 2º turno de 2022 na ordem real de totalização dos municípios e mede o erro
    da projeção contra o resultado final, comparado à parcial contada."""
    r = pd.read_parquet(MODELO / "replay_2022.parquet")
    t1, t2 = r[r["turno"] == 1], r[r["turno"] == 2]
    tot1 = t1.groupby(["uf", "cd_tse"]).agg(aptos=("aptos", "first"), validos=("validos", "first")).reset_index()
    base, outros = montar_base(t1[["uf", "cd_tse", "partido", "votos"]], tot1, "PT", "PL", 4)
    piv = t2.pivot_table(index=["uf", "cd_tse"], columns="partido", values="votos", aggfunc="sum").reset_index()
    hora = t2.groupby(["uf", "cd_tse"])["hora_tot"].max().reset_index()
    piv = piv.merge(hora, on=["uf", "cd_tse"]).sort_values("hora_tot")
    piv["acum"] = (piv["PT"] + piv["PL"]).cumsum() / (piv["PT"] + piv["PL"]).sum()
    final = 100 * piv["PT"].sum() / (piv["PT"] + piv["PL"]).sum()
    linhas = []
    for mk in marcos:
        parte = piv[piv["acum"] <= mk]
        vivo = pd.DataFrame({"uf": parte["uf"], "cd_tse": parte["cd_tse"], "va": parte["PT"], "vb": parte["PL"],
                             "pst": 100.0})
        pj = projetar(base, outros, vivo, "PT", "PL", prior=[PRIOR_PADRAO] * len(outros), n_boot=25,
                      calcular_cv=len(parte) >= 400)
        linhas.append({"marco": 100 * mk, "hora": parte["hora_tot"].max(), "municipios": len(parte),
                       "contado_lula": pj.contado_a, "projecao_lula": pj.pct_a, "p05": pj.p05, "p95": pj.p95,
                       "final_lula": final, "erro_contado": pj.contado_a - final, "erro_projecao": pj.pct_a - final,
                       "usa_ml": pj.usa_ml, **{f"beta_{k}": v for k, v in pj.betas.items()}})
    return pd.DataFrame(linhas)


if __name__ == "__main__":
    import time
    t = time.time()
    bt = backtest_2022()
    pd.set_option("display.width", 220)
    print(bt.round(2).to_string(index=False))
    bt.to_parquet(MODELO / "backtest_2022.parquet", index=False)
    print(f"{time.time() - t:.0f}s")


# ---------------------------------------------------------------- uso pelo coletor e pelo painel
import os as _os
HIST = Path(_os.getenv("APURACAO_DADOS", Path(__file__).parent / "dados")) / "projecao"


def projetar_de_longo(longo: pd.DataFrame, cargo: int, uf: str | None = None, n_boot: int = 40,
                      calcular_cv: bool = True) -> Projecao:
    a, b = finalistas(cargo, uf)
    ufs = [uf] if uf else list(REGIAO)
    base, outros = base_2026(cargo, ufs, a, b)
    if longo is not None and not longo.empty and uf and "uf" in longo:
        longo = longo[longo["uf"] == uf]
    return projetar(base, outros, vivo_de_longo(longo, a, b), a, b, n_boot=n_boot, calcular_cv=calcular_cv)


def registrar(chave: str, cargo: int, abr: str, pj: Projecao, pct_secoes: float | None = None) -> None:
    import json
    HIST.mkdir(parents=True, exist_ok=True)
    linha = {"coletado_em": pd.Timestamp.now().isoformat(timespec="seconds"), "pct_contado": pj.pct_contado,
             "pct_secoes": pct_secoes, "totalizados": pj.totalizados, "parciais": pj.parciais,
             "contado_a": pj.contado_a, "proj_a": pj.pct_a, "p05": pj.p05, "p95": pj.p95, "prob_a": pj.prob_a,
             "usa_ml": pj.usa_ml, "cv_mae": pj.cv_mae, "betas": pj.betas, "gama": pj.gama}
    with (HIST / f"{chave}_c{cargo}_{abr.lower()}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(linha, ensure_ascii=False, default=float) + "\n")


def ler_historico(chave: str, cargo: int, abr: str) -> pd.DataFrame:
    arq = HIST / f"{chave}_c{cargo}_{abr.lower()}.jsonl"
    if not arq.exists():
        return pd.DataFrame()
    return pd.read_json(arq, lines=True)


def fora_da_amostra(longo: pd.DataFrame, cargo: int, uf: str | None = None, k: int = 5) -> pd.DataFrame:
    """Previsão de cada município totalizado feita por um modelo que NÃO o viu (validação cruzada em k dobras).
    É a medida honesta da qualidade municipal do modelo durante a apuração."""
    a, b = finalistas(cargo, uf)
    base, outros = base_2026(cargo, [uf] if uf else list(REGIAO), a, b)
    if longo is not None and not longo.empty and uf and "uf" in longo:
        longo = longo[longo["uf"] == uf]
    vivo = vivo_de_longo(longo, a, b)
    d = base.merge(vivo, on=["uf", "cd_tse"], how="inner")
    d = d[(d["pst"] >= 99.99) & (d["va"] + d["vb"] > 0)].copy()
    if len(d) < 30:
        return pd.DataFrame()
    d["y"] = d["va"] / (d["va"] + d["vb"])
    d["w"] = d["va"] + d["vb"]
    prior = [PRIOR_PRESIDENTE.get(c, PRIOR_PADRAO) for c in outros]
    rng = np.random.default_rng(11)
    dobra = rng.integers(0, k, len(d))
    d["oof"] = np.nan
    for i in range(k):
        m = Modelo(outros, prior).fit(d[dobra != i], a, False)
        d.loc[dobra == i, "oof"] = m.predict(d[dobra == i], a)
    d["base_1t"] = d["s_" + a] / (d["s_" + a] + d["s_" + b])  # referência ingênua: só os dois finalistas do 1º turno
    return d[["uf", "cd_tse", "y", "oof", "base_1t", "w", "s_" + a]]
