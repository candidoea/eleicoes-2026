"""Gerador de dados FICTÍCIOS no mesmo layout do JSON do TSE, para testar o app
antes da apuração ou sem rede. Apuração simulada completa em ~10 minutos."""
from __future__ import annotations

import copy
import json
import os
import random
import time

from tse import UFS

_INICIO = time.time()
DURACAO = int(os.getenv("APURACAO_DEMO_DURACAO", "600"))
PARTIDOS = ["PT", "PL", "UNIÃO", "PSD", "MDB", "PP", "REPUBLICANOS", "PSB", "PDT",
            "PSDB", "PSOL", "NOVO", "PODE", "AVANTE", "SOLIDARIEDADE", "CIDADANIA"]
ELEITORADO_UF = {"SP": 34_000_000, "MG": 16_000_000, "RJ": 12_800_000, "BA": 11_300_000,
                 "RS": 8_600_000, "PR": 8_200_000, "PE": 7_100_000, "CE": 6_900_000}
VAGAS_DF = {"SP": 70, "MG": 53, "RJ": 46, "BA": 39, "RS": 31, "PR": 30, "PE": 25, "CE": 22}


def _fmt_pct(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def gerar(cargo: int, abr: str) -> dict:
    abr = abr.lower()
    rnd = random.Random(f"{cargo}-{abr}")
    prog = min(1.0, (time.time() - _INICIO) / DURACAO * rnd.uniform(0.8, 1.25))
    if abr == "br":
        te = 158_000_000
    else:
        te = ELEITORADO_UF.get(abr.upper(), rnd.randint(500_000, 6_000_000))
    ts = te // 330
    st = int(ts * prog)
    comp = int(te * 0.79 * prog)
    vb, vn = int(comp * 0.025), int(comp * 0.04)
    vv = comp - vb - vn

    if cargo in (1, 3, 5):
        n_cand, vagas = (rnd.randint(4, 9), 1 if cargo != 5 else 2)
    else:
        vagas = VAGAS_DF.get(abr.upper(), rnd.choice([8, 10, 12, 18])) if cargo == 6 else 24
        n_cand = vagas * 6
    # pesos com cauda longa + deriva temporal (líder pode mudar)
    base = [rnd.random() ** 3 + 0.01 for _ in range(n_cand)]
    drift = [rnd.uniform(-0.3, 0.3) for _ in range(n_cand)]
    pesos = [max(0.001, b * (1 + d * prog)) for b, d in zip(base, drift)]
    soma = sum(pesos)
    votos = [int(vv * p / soma) for p in pesos]

    ordem = sorted(range(n_cand), key=lambda i: -votos[i])
    final = prog >= 1
    situ = {}
    for rank, i in enumerate(ordem):
        if not final:
            situ[i] = ("", "n")
        elif cargo in (1, 3) and votos[ordem[0]] / max(vv, 1) <= 0.5:
            situ[i] = ("2º turno", "n") if rank < 2 else ("Não eleito", "n")
        else:
            situ[i] = ("Eleito", "s") if rank < vagas else ("Não eleito", "n")

    por_partido: dict[str, list] = {}
    for i in range(n_cand):
        sg = PARTIDOS[rnd.randrange(len(PARTIDOS))] if cargo >= 5 else PARTIDOS[i % len(PARTIDOS)]
        num = f"{rnd.randint(10, 90)}{rnd.randint(0, 999):03d}" if cargo >= 6 else str(rnd.randint(10, 90))
        por_partido.setdefault(sg, []).append({
            "n": num, "sqcand": str(rnd.randint(10**11, 10**12)), "nm": f"Candidato fictício {i + 1}",
            "nmu": f"Candidato {chr(65 + i % 26)}{i // 26 or ''}", "e": situ[i][1], "st": situ[i][0],
            "vap": str(votos[i]), "pvap": _fmt_pct(100 * votos[i] / max(vv, 1)),
        })
    agr = [{"n": "1", "nm": sg, "tp": "i", "par": [{"sg": sg, "nm": sg, "cand": cs}]}
           for sg, cs in por_partido.items()]
    return {
        "ele": "demo", "cdabr": abr, "dg": time.strftime("%d/%m/%Y"), "hg": time.strftime("%H:%M:%S"),
        "tf": "s" if final else "n",
        "s": {"ts": str(ts), "st": str(st), "pst": _fmt_pct(100 * st / ts)},
        "e": {"te": str(te), "c": str(comp), "pc": _fmt_pct(100 * comp / te),
              "a": str(te - comp), "pa": _fmt_pct(100 * (te - comp) / te)},
        "v": {"tv": str(comp), "vv": str(vv), "pvv": _fmt_pct(100 * vv / max(comp, 1)),
              "vb": str(vb), "pvb": _fmt_pct(100 * vb / max(comp, 1)),
              "tvn": str(vn), "ptvn": _fmt_pct(100 * vn / max(comp, 1))},
        "carg": [{"cd": str(cargo), "nmn": "", "nv": str(vagas), "agr": agr}],
    }


assert set(ELEITORADO_UF) <= set(UFS)


_PAIS: dict = {}


def gerar_municipio(cargo: int, uf: str, cd_ibge: str) -> dict:
    """Município fictício coerente com o pai (BR p/ Presidente, UF p/ demais): mesmos candidatos,
    com força regional por UF + ruído local, para o mapa ter "regiões" e fronteiras de disputa."""
    chave = (cargo, "br" if cargo == 1 else uf.lower(), int(time.time() // 5))
    if chave not in _PAIS:
        _PAIS.clear() if len(_PAIS) > 200 else None
        _PAIS[chave] = gerar(cargo, chave[1])
    pai = _PAIS[chave]
    rnd = random.Random(f"m{cargo}-{cd_ibge}")
    cands = [c for a in pai["carg"][0]["agr"] for p in a["par"] for c in p["cand"]]
    prog = float(pai["s"]["pst"].replace(",", ".")) / 100
    prog = min(1.0, prog * rnd.uniform(0.6, 1.6))
    te = int(rnd.lognormvariate(9.5, 1.0)) + 1500
    comp = int(te * 0.8 * prog)
    vb, vn = int(comp * 0.025), int(comp * 0.04)
    vv = comp - vb - vn
    pesos = []
    for c in cands:
        base = max(int(c["vap"]), 1)
        regional = random.Random(f"r{c['sqcand']}{uf}{cd_ibge[:4]}").uniform(0.3, 2.2)
        pesos.append(base * regional * rnd.uniform(0.7, 1.3))
    soma = sum(pesos) or 1
    out = json.loads(json.dumps(pai))
    i = 0
    for a in out["carg"][0]["agr"]:
        for p in a["par"]:
            for c in p["cand"]:
                v = int(vv * pesos[i] / soma)
                c["vap"], c["pvap"], c["e"], c["st"] = str(v), _fmt_pct(100 * v / max(vv, 1)), "n", ""
                i += 1
    out.update({"cdabr": cd_ibge, "tf": "n",
                "s": {"ts": "20", "st": str(int(20 * prog)), "pst": _fmt_pct(100 * prog)},
                "e": {"te": str(te), "c": str(comp), "pc": _fmt_pct(100 * comp / te), "a": str(te - comp),
                      "pa": _fmt_pct(100 * (te - comp) / te)},
                "v": {"tv": str(comp), "vv": str(vv), "pvv": "0", "vb": str(vb), "pvb": "0", "tvn": str(vn),
                      "ptvn": "0"}})
    return out
