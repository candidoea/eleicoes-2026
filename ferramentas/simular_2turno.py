"""Ensaio do 2º turno: gera, numa pasta local, arquivos no formato da API do TSE a partir da apuração real
de 2022 (Lula x Bolsonaro, na ordem real de totalização), rotulados como 2026. Serve para testar coletor,
painel e projeção antes de o TSE publicar os dados de verdade.

  python ferramentas/simular_2turno.py C:\\temp\\tse_fake 0.30      # 30% dos votos totalizados
  python -m http.server 8899 --directory C:\\temp\\tse_fake
  $env:APURACAO_TSE_BASE = "http://127.0.0.1:8899/oficial"; $env:APURACAO_DADOS = "C:\\temp\\dados_ensaio"
  python coletor.py --sem-banco      (e o painel em outro terminal, com as mesmas variáveis)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
FED, EST = "6258", "6260"


def fmtp(x):
    return f"{x:.2f}".replace(".", ",")


def arquivo(va, vb, pst, ts=100):
    vv = va + vb
    pa = 100 * va / vv if vv else 0
    st = round(ts * pst / 100)
    return {"ele": FED, "dg": "25/10/2026", "hg": "18:30:00", "tf": "s" if pst >= 100 else "n",
            "s": {"ts": str(ts), "st": str(st), "pst": fmtp(pst)},
            "e": {"te": str(int(vv * 1.3)), "c": str(int(vv * 1.06)), "pc": "80,00", "a": "0", "pa": "20,00"},
            "v": {"tv": str(int(vv * 1.06)), "vv": str(vv), "pvv": "94,00", "vb": "0", "pvb": "2,00", "tvn": "0", "ptvn": "4,00"},
            "carg": [{"cd": "1", "nmn": "Presidente", "nv": "1", "agr": [
                {"tp": "p", "nm": "", "par": [{"sg": "PT", "nm": "", "cand": [{"n": "13", "nmu": "LULA", "sqcand": "1",
                                                                             "e": "n", "st": "", "vap": str(va), "pvap": fmtp(pa)}]}]},
                {"tp": "p", "nm": "", "par": [{"sg": "PL", "nm": "", "cand": [{"n": "22", "nmu": "FLAVIO BOLSONARO", "sqcand": "2",
                                                                             "e": "n", "st": "", "vap": str(vb), "pvap": fmtp(100 - pa)}]}]}]}]}


def main(destino: str, fracao: float):
    out = Path(destino) / "oficial"
    r = pd.read_parquet(RAIZ / "modelo" / "replay_2022.parquet")
    t2 = r[r["turno"] == 2].pivot_table(index=["uf", "cd_tse", "hora_tot"], columns="partido", values="votos").reset_index()
    t2 = t2.sort_values("hora_tot")
    t2["acum"] = (t2["PT"] + t2["PL"]).cumsum() / (t2["PT"] + t2["PL"]).sum()
    t2["rep"] = t2["acum"] <= fracao
    base = out / "ele2026" / FED
    cfg_src = RAIZ / "modelo" / "mun-e006257-cm.json"  # lista de municípios do TSE (1º turno), versionada
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / f"mun-e00{FED}-cm.json").write_text(cfg_src.read_text(encoding="utf-8"), encoding="utf-8")
    (out / "comum" / "config").mkdir(parents=True, exist_ok=True)
    (out / "comum" / "config" / "ele-c.json").write_text(json.dumps(
        {"c": "ele2026", "pl": [{"e": [{"cd": "6257", "t": "1"}, {"cd": "6259", "t": "1"}, {"cd": FED, "t": "2"},
                                        {"cd": EST, "t": "2"}]}]}))
    for row in t2.itertuples():
        va, vb = (int(row.PT), int(row.PL)) if row.rep else (0, 0)
        d = base / "dados" / row.uf.lower()
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{row.uf.lower()}{row.cd_tse}-c0001-e00{FED}-u.json").write_text(json.dumps(arquivo(va, vb, 100.0 if row.rep else 0.0)))
    tot_va = tot_vb = 0
    for uf, g in t2.groupby("uf"):
        va, vb = int(g.loc[g.rep, "PT"].sum()), int(g.loc[g.rep, "PL"].sum())
        tot_va += va; tot_vb += vb
        pst = 100 * g.loc[g.rep, ["PT", "PL"]].sum().sum() / g[["PT", "PL"]].sum().sum()
        (base / "dados" / uf.lower() / f"{uf.lower()}-c0001-e00{FED}-u.json").write_text(json.dumps(arquivo(va, vb, pst, 1000)))
    (base / "dados" / "br").mkdir(parents=True, exist_ok=True)
    (base / "dados" / "br" / f"br-c0001-e00{FED}-u.json").write_text(json.dumps(arquivo(tot_va, tot_vb, 100 * fracao, 10000)))
    print(f"{int(t2.rep.sum())} municípios totalizados; Lula na parcial {100 * tot_va / (tot_va + tot_vb):.2f}%")


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.3)
