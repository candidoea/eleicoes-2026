"""Reexecuta a noite do 2º turno na ordem real de chegada dos municípios.

Para cada instante (5 em 5 minutos), reconstrói o estado de cada município com o último registro anterior e roda
projecao.projetar em quatro variantes: transferência + LightGBM (padrão do código), só transferência (o que rodou
na noite), erro só de fatia e erro só de comparecimento (informação perfeita parcial, sobre a variante padrão).

uso:  python estudo/scripts/01_reexecucao.py              (Presidente e os 6 governadores; ~1 h)
      python estudo/scripts/01_reexecucao.py --cargo 1    (só Presidente)
      python estudo/scripts/01_reexecucao.py --cargo 1 --parte 0 --partes 2   (divide os instantes entre processos)
"""
import argparse
import sys

import numpy as np
import pandas as pd

from comum import RES, pj, snapshots

FIM = pd.Timestamp("2026-10-25 23:30")


def _municipios(s, cargo, uf, a, b, dtype):
    m = s[(s.Nivel == "M") & (s.Cargo == cargo)]
    if uf:
        m = m[m.UF == uf]
    m = m.pivot_table(index=["UF", "CodMunTSE", "ColetadoEm", "PctSecoes"], columns="Partido", values="Votos",
                      aggfunc="sum").reset_index()
    m = m.rename(columns={"UF": "uf", "CodMunTSE": "cd_tse", a: "va", b: "vb", "PctSecoes": "pst"})
    m["cd_tse"] = m.cd_tse.astype(dtype)
    return m.sort_values("ColetadoEm")


def _so_transferencia(base, outros, vivo, a, b, prior):
    orig = pj.Modelo.fit
    pj.Modelo.fit = lambda self, d, a_, usar_ml=None: orig(self, d, a_, False)
    try:
        return pj.projetar(base, outros, vivo, a, b, prior=prior, n_boot=30, calcular_cv=False)
    finally:
        pj.Modelo.fit = orig


def rodar(cargo, uf, parte=0, partes=1):
    a, b = pj.finalistas(cargo, uf)
    s = snapshots()
    base, outros = pj.base_2026(cargo, list(pj.REGIAO) if cargo == 1 else [uf], a, b)
    m = _municipios(s, cargo, uf, a, b, base.cd_tse.dtype)
    fin = m.groupby(["uf", "cd_tse"]).last().reset_index()
    real = 100 * fin.va.sum() / (fin.va.sum() + fin.vb.sum())
    prior = [pj.PRIOR_PRESIDENTE.get(c, pj.PRIOR_PADRAO) for c in outros] if cargo == 1 else None
    t0 = m[m.va + m.vb > 0].ColetadoEm.min()
    t1 = min(fin.ColetadoEm.max(), FIM)
    grade = pd.date_range(t0, t1, freq="5min").append(pd.DatetimeIndex([t1]))[parte::partes]
    linhas = []
    for t in grade:
        v = m[m.ColetadoEm <= t].groupby(["uf", "cd_tse"]).last().reset_index()
        if (v.va + v.vb).sum() == 0:
            continue
        p = pj.projetar(base, outros, v, a, b, prior=prior, n_boot=30, calcular_cv=True)
        r = {"t": t, "real": real, "pct": p.pct_contado, "tot": p.totalizados, "parc": p.parciais, "contado": p.contado_a,
             "proj": p.pct_a, "proj_lo": p.p05, "proj_hi": p.p95, "proj_p": p.prob_a, "usa_ml": p.usa_ml,
             **{"beta_" + k: float(x) for k, x in p.betas.items()}}
        q = _so_transferencia(base, outros, v, a, b, prior)
        r.update(transf=q.pct_a, transf_lo=q.p05, transf_hi=q.p95, transf_p=q.prob_a)
        pm = p.por_municipio.merge(fin[["uf", "cd_tse", "va", "vb"]].rename(columns={"va": "fa", "vb": "fb"}),
                                   on=["uf", "cd_tse"], how="left").fillna({"fa": 0, "fb": 0})
        ft = pm.fa + pm.fb
        r["so_fatia"] = 100 * (pm.proj_a_mun * ft).sum() / ft.sum()           # fatia projetada, total verdadeiro
        fatia_real = np.nan_to_num(pm.fa / ft.replace(0, np.nan))
        r["so_comparecimento"] = 100 * (fatia_real * pm.esperado).sum() / pm.esperado.sum()  # fatia verdadeira
        linhas.append(r)
        print(cargo, uf or "BR", t.strftime("%H:%M"), f"contado {r['pct']:5.1f}%  proj {r['proj']:.2f}  transf {r['transf']:.2f}",
              file=sys.stderr)
    sufixo = f"_{parte}" if partes > 1 else ""
    pd.DataFrame(linhas).to_csv(RES / f"reexecucao_{cargo}_{uf or 'BR'}{sufixo}.csv", index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cargo", type=int, choices=[1, 3])
    ap.add_argument("--uf")
    ap.add_argument("--parte", type=int, default=0)
    ap.add_argument("--partes", type=int, default=1)
    x = ap.parse_args()
    alvos = [(1, None)] + [(3, u) for u in ("AC", "AM", "DF", "ES", "RN", "TO")]
    if x.cargo:
        alvos = [(c, u) for c, u in alvos if c == x.cargo and (x.uf is None or u == x.uf)]
    for c, u in alvos:
        rodar(c, u, x.parte, x.partes)
