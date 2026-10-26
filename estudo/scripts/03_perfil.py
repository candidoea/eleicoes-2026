"""Mudança entre turnos por município: totais, UF, região, quintis de escolaridade, viradas e regressões de perfil."""
import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from comum import RES, pj, presidente

d = presidente()
d["dlula"] = d.lula2 / d.vv2 - d.lula1 / d.vv1
d["dcomp"] = d.comp2 / d.aptos2 - d.comp1 / d.aptos1
d["abst2r"] = 1 - d.comp2 / d.aptos2
d["w"] = d.lula2 + d.flavio2

# transferência final (equação 1 com todos os municípios) e intervalo por bootstrap
base, outros = pj.base_2026(1, list(pj.REGIAO), "PT", "PL")
dd = base.merge(d[["uf", "cd_tse", "lula2", "flavio2"]], on=["uf", "cd_tse"])
dd["y"], dd["w"] = dd.lula2 / (dd.lula2 + dd.flavio2), dd.lula2 + dd.flavio2
prior = [pj.PRIOR_PRESIDENTE.get(c, pj.PRIOR_PADRAO) for c in outros]
m = pj.Modelo(outros, prior).fit(dd, "PT", False)
rng = np.random.default_rng(3)
B = np.array([pj.Modelo(outros, prior).fit(dd.iloc[rng.integers(0, len(dd), len(dd))], "PT", False).beta for _ in range(200)])
json.dump({"outros": outros, "beta": m.beta.tolist(), "lo": np.percentile(B, 5, 0).tolist(),
           "hi": np.percentile(B, 95, 0).tolist(), "gama": m.gama, "uf": m.uf}, open(RES / "transferencia_final.json", "w"), indent=1)

# totais
A1, A2, C1, C2, V1, V2 = (d[c].sum() for c in ("aptos1", "aptos2", "comp1", "comp2", "vv1", "vv2"))
print(f"abstenção {A1 - C1:,} -> {A2 - C2:,} ({(A1 - C1) / A1:.2%} -> {(A2 - C2) / A2:.2%}); "
      f"brancos e nulos {C1 - V1:,} -> {C2 - V2:,}; válidos {V1:,} -> {V2:,}")

# UF, região e quintis
cols = ["aptos1", "comp1", "vv1", "aptos2", "comp2", "vv2", "lula1", "lula2", "flavio1", "flavio2"]
for chave, arq in (("uf", "uf.csv"), ("regiao", "regiao.csv")):
    g = d.groupby(chave)[cols].sum()
    g["abst1"], g["abst2"] = 1 - g.comp1 / g.aptos1, 1 - g.comp2 / g.aptos2
    g["dabst_mil"] = ((g.aptos2 - g.comp2) - (g.aptos1 - g.comp1)) / 1e3
    g["dl"] = g.lula2 / g.vv2 - g.lula1 / g.vv1
    g.to_csv(RES / arq)
x = d.dropna(subset=["p_esc_sup"]).copy()
x["q"] = pd.qcut(x.p_esc_sup.rank(method="first"), 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])
q = x.groupby("q", observed=True)[cols].sum()
q["abst1"], q["abst2"] = 1 - q.comp1 / q.aptos1, 1 - q.comp2 / q.aptos2
q["l1"], q["l2"] = q.lula1 / q.vv1, q.lula2 / q.vv2
q.to_csv(RES / "quintis_esc.csv")

# viradas
v1 = np.where(d.lula1 > d.flavio1, "Lula", "Flávio")
v2 = np.where(d.lula2 > d.flavio2, "Lula", "Flávio")
print(pd.crosstab(pd.Series(v1, name="vencedor 1º"), pd.Series(v2, name="vencedor 2º")))
print(f"Lula aumentou a fatia em {(d.dlula > 0).sum()} de {len(d)} municípios (mediana {d.dlula.median():+.2%})")

# regressões de perfil: efeito fixo de UF, erros agrupados por UF, variáveis padronizadas pelo eleitorado
X = ["p_esc_sup", "p_a18_24", "p_60m", "p_fem"]
for c in X:
    mu = np.average(x[c], weights=x.aptos2)
    x[c + "_z"] = (x[c] - mu) / np.sqrt(np.average((x[c] - mu) ** 2, weights=x.aptos2))
x["dlula"], x["dcomp"], x["abst2r"] = d.loc[x.index, "dlula"], d.loc[x.index, "dcomp"], d.loc[x.index, "abst2r"]
x["w"] = d.loc[x.index, "w"]
grupos = pd.factorize(x.uf)[0]
saida = []
for y, peso in (("dlula", "w"), ("dcomp", "aptos2"), ("abst2r", "aptos2")):
    r = smf.wls(f"{y} ~ " + " + ".join(c + "_z" for c in X) + " + C(uf)", data=x, weights=x[peso]).fit(
        cov_type="cluster", cov_kwds={"groups": grupos})
    for c in X:
        saida.append((y, c, 100 * r.params[c + "_z"], 100 * r.bse[c + "_z"], r.rsquared))
pd.DataFrame(saida, columns=["y", "x", "coef_pp", "se_pp", "r2"]).to_csv(RES / "perfil_reg.csv", index=False)
d.to_parquet(RES / "municipios.parquet")
print(pd.DataFrame(saida, columns=["y", "x", "coef_pp", "se_pp", "r2"]).round(3))
