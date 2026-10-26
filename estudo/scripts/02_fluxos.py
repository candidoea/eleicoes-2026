"""Matriz de transição ecológica 1º -> 2º turno (Presidente), com restrições e bootstrap.

Origens (fatias do eleitorado apto no 1º turno): Lula, Flávio, Cury, Renan, Caiado, Zema e demais, branco ou nulo,
abstenção. Destinos: Lula, Flávio, não votou válido. Linhas somam 1 e entradas são não negativas.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

from comum import RES, presidente

ORIG = ["lula1", "flavio1", "cury1", "renan1", "caiado1", "outros_z1", "bn1", "abst1"]


def preparar(d):
    d = d.copy()
    d["bn1"] = d.comp1 - d.vv1
    d["abst1"] = d.aptos1 - d.comp1
    d["outros_z1"] = d.zema1 + d.outros1
    d["nao2"] = d.aptos2 - d.lula2 - d.flavio2
    return d


def ajustar(d, x0=None):
    X = d[ORIG].div(d.aptos1, axis=0).to_numpy()
    w = d.aptos1.to_numpy() / d.aptos1.mean()
    Y = np.column_stack([d.lula2, d.flavio2, d.nao2]) / d.aptos1.to_numpy()[:, None]
    k = len(ORIG)

    def f(p):
        a, b = p[:k], p[k:]
        P = np.column_stack([X @ a, X @ b, X @ (1 - a - b)])
        return (w[:, None] * (P - Y) ** 2).sum()

    def g(p):
        a, b = p[:k], p[k:]
        P = np.column_stack([X @ a, X @ b, X @ (1 - a - b)])
        r = 2 * w[:, None] * (P - Y)
        return np.concatenate([X.T @ (r[:, 0] - r[:, 2]), X.T @ (r[:, 1] - r[:, 2])])

    x0 = np.full(2 * k, 0.4) if x0 is None else x0
    cons = [{"type": "ineq", "fun": lambda p, i=i: 1 - p[i] - p[k + i],
             "jac": lambda p, i=i: -np.eye(2 * k)[i] - np.eye(2 * k)[k + i]} for i in range(k)]
    s = minimize(f, x0, jac=g, bounds=[(0, 1)] * (2 * k), constraints=cons, method="SLSQP",
                 options={"maxiter": 500, "ftol": 1e-12})
    a, b = s.x[:k], s.x[k:]
    return pd.DataFrame({"lula": a, "flavio": b, "nao_votou_valido": 1 - a - b}, index=ORIG)


if __name__ == "__main__":
    d = preparar(presidente())
    T = ajustar(d)
    T.to_csv(RES / "fluxo_nacional.csv")
    x0 = np.concatenate([T.lula.to_numpy(), T.flavio.to_numpy()])
    rng = np.random.default_rng(11)
    boots = [ajustar(d.iloc[rng.integers(0, len(d), len(d))], x0) for _ in range(60)]
    arr = np.stack([100 * b.to_numpy() for b in boots])
    pd.DataFrame(np.percentile(arr, 5, 0), index=ORIG, columns=T.columns).to_csv(RES / "fluxo_lo.csv")
    pd.DataFrame(np.percentile(arr, 95, 0), index=ORIG, columns=T.columns).to_csv(RES / "fluxo_hi.csv")
    print((100 * T).round(1))
