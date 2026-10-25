"""Cliente da API de divulgação de resultados do TSE (Eleições 2026, 1º e 2º turnos).

Fonte do layout: Informações técnicas sobre a divulgação de resultados 2026 (TSE).
Campos do JSON "-u.json" (abreviados pelo TSE):
  raiz : ele, cdabr, dg (data), hg (hora), tf (totalização final s/n)
  s    : ts (seções total), st (totalizadas), pst (% totalizadas)
  e    : te (eleitorado), c (comparecimento), pc, a (abstenção), pa
  v    : tv (total), vv (válidos), pvv, vb (brancos), pvb, tvn (nulos), ptvn
  carg : [{cd, nmn, nv (vagas), agr: [{tp, nm, par: [{sg, nm, cand: [{n, nmu, nm, e, st, vap, pvap}]}]}]}]
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

import fonte

# Códigos de eleição do TSE: 1º turno 6257 (federal) e 6259 (estadual). Seguindo o padrão de 2022
# (544/545 federal, 546/547 estadual), o 2º turno é 6258 e 6260; o coletor confirma no arquivo de
# configuração do TSE (comum/config/ele-c.json) ao iniciar e corrige se o TSE tiver usado outros códigos.
AMBIENTES = {
    "Oficial 2º turno (25/10/2026)": {
        "base": "https://resultados.tse.jus.br/oficial",
        "federal": os.getenv("APURACAO_ELE_FED_2T", "6258"),
        "estadual": os.getenv("APURACAO_ELE_EST_2T", "6260"),
        "turno": 2, "rotulo": "2º turno · 25 de outubro de 2026", "chave": "oficial2",
    },
    "Oficial 1º turno (04/10/2026)": {
        "base": "https://resultados.tse.jus.br/oficial",
        "federal": "6257",
        "estadual": "6259",
        "turno": 1, "rotulo": "1º turno · 4 de outubro de 2026", "chave": "oficial",
    },
    "Simulado (ensaio TSE)": {
        "base": "https://resultados-sim.tse.jus.br/simulado",
        "federal": "21270",
        "estadual": "21272",
        "turno": 1, "rotulo": "ambiente simulado do TSE", "chave": "simulado",
    },
}
CICLO = "ele2026"
if os.getenv("APURACAO_TSE_BASE"):  # testes com servidor falso local
    for _k in AMBIENTES:
        if _k.startswith("Oficial"):
            AMBIENTES[_k]["base"] = os.environ["APURACAO_TSE_BASE"]

# 2º turno: Presidente em todas as UFs; Governador só onde houve 2º turno
UFS_GOV_2T = ["AC", "AM", "DF", "ES", "RN", "TO"]


def turno(ambiente: str) -> int:
    return AMBIENTES[ambiente].get("turno", 1)


def chave(ambiente: str) -> str:
    return AMBIENTES[ambiente].get("chave", "oficial")


def ufs_do_cargo(ambiente: str, cargo: int) -> list[str]:
    """UFs em que o cargo tem eleição neste ambiente (evita pedir arquivos inexistentes ao TSE)."""
    if turno(ambiente) == 2:
        if cargo == 1:
            return list(UFS)
        return UFS_GOV_2T if cargo == 3 else []
    return list(UFS)


def cargos_do_ambiente(ambiente: str) -> list[int]:
    return [1, 3] if turno(ambiente) == 2 else list(CARGOS)


def descobrir_codigos_2t(log=print) -> None:
    """Lê comum/config/ele-c.json do TSE e ajusta os códigos do 2º turno, se o TSE tiver publicado outros.
    Silencioso em caso de falha: mantém o padrão 6258/6260."""
    amb = "Oficial 2º turno (25/10/2026)"
    try:
        raw = fonte.obter(f"{AMBIENTES[amb]['base']}/comum/config/ele-c.json", max_idade=1800)
    except Exception as exc:
        log(f"[config] não consegui ler ele-c.json ({exc}); mantendo {AMBIENTES[amb]['federal']}/"
            f"{AMBIENTES[amb]['estadual']}")
        return
    achados = []

    def walk(o):
        if isinstance(o, dict):
            cd = str(o.get("cd", ""))
            t = str(o.get("t", o.get("turno", o.get("trno", ""))))
            if cd.isdigit() and t == "2" and int(cd) > 6257:
                achados.append(int(cd))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(raw)
    achados = sorted(set(achados))
    if len(achados) >= 2:
        AMBIENTES[amb]["federal"], AMBIENTES[amb]["estadual"] = str(achados[0]), str(achados[1])
    log(f"[config] 2º turno: federal {AMBIENTES[amb]['federal']}, estadual {AMBIENTES[amb]['estadual']} "
        f"(códigos com turno 2 no TSE: {achados or 'nenhum'})")

# cargo -> (nome, eleição)
CARGOS = {
    1: ("Presidente", "federal"),
    3: ("Governador", "estadual"),
    5: ("Senador", "estadual"),
    6: ("Deputado Federal", "estadual"),
    7: ("Deputado Estadual", "estadual"),
    8: ("Deputado Distrital", "estadual"),
}

UFS = {
    "AC": ("Acre", 12), "AL": ("Alagoas", 27), "AM": ("Amazonas", 13), "AP": ("Amapá", 16),
    "BA": ("Bahia", 29), "CE": ("Ceará", 23), "DF": ("Distrito Federal", 53),
    "ES": ("Espírito Santo", 32), "GO": ("Goiás", 52), "MA": ("Maranhão", 21),
    "MG": ("Minas Gerais", 31), "MS": ("Mato Grosso do Sul", 50), "MT": ("Mato Grosso", 51),
    "PA": ("Pará", 15), "PB": ("Paraíba", 25), "PE": ("Pernambuco", 26), "PI": ("Piauí", 22),
    "PR": ("Paraná", 41), "RJ": ("Rio de Janeiro", 33), "RN": ("Rio Grande do Norte", 24),
    "RO": ("Rondônia", 11), "RR": ("Roraima", 14), "RS": ("Rio Grande do Sul", 43),
    "SC": ("Santa Catarina", 42), "SE": ("Sergipe", 28), "SP": ("São Paulo", 35),
    "TO": ("Tocantins", 17),
}

def cargo_legislativo_estadual(uf: str) -> int:
    """DF elege Deputado Distrital (8); demais UFs, Deputado Estadual (7)."""
    return 8 if uf.upper() == "DF" else 7


def codigo_eleicao(ambiente: str, cargo: int) -> str:
    return AMBIENTES[ambiente][CARGOS[cargo][1]]


def url_resultado(ambiente: str, cargo: int, abr: str) -> str:
    """abr: 'br', sigla da UF, ou UF + código TSE do município (ex.: 'rn17612')."""
    cfg = AMBIENTES[ambiente]
    ele = codigo_eleicao(ambiente, cargo)
    abr = abr.lower()
    uf = abr[:2]
    return f"{cfg['base']}/{CICLO}/{ele}/dados/{uf}/{abr}-c{cargo:04d}-e{int(ele):06d}-u.json"


def url_config_municipios(ambiente: str, cargo: int) -> str:
    cfg = AMBIENTES[ambiente]
    ele = codigo_eleicao(ambiente, cargo)
    return f"{cfg['base']}/{CICLO}/{ele}/config/mun-e{int(ele):06d}-cm.json"


NaoDisponivel = fonte.NaoDisponivel


# ---------------------------------------------------------------- normalização
def _n(x) -> int:
    try:
        return int(str(x).replace(".", "")) if x not in (None, "") else 0
    except ValueError:
        return 0


def _p(x) -> float:
    try:
        return float(str(x).replace(",", ".")) if x not in (None, "") else 0.0
    except ValueError:
        return 0.0


@dataclass
class Resultado:
    cargo: int
    abr: str
    cargo_nome: str = ""
    vagas: int = 0
    atualizado: str = ""
    final: bool = False
    secoes_total: int = 0
    secoes_tot: int = 0
    pct_secoes: float = 0.0
    eleitorado: int = 0
    comparecimento: int = 0
    pct_comparecimento: float = 0.0
    abstencao: int = 0
    pct_abstencao: float = 0.0
    votos_total: int = 0
    validos: int = 0
    brancos: int = 0
    pct_brancos: float = 0.0
    nulos: int = 0
    pct_nulos: float = 0.0
    candidatos: pd.DataFrame = field(default_factory=pd.DataFrame)


def normalizar(raw: dict, cargo: int, abr: str) -> Resultado:
    cargs = raw.get("carg") or []
    c = next((x for x in cargs if _n(x.get("cd")) == cargo), cargs[0] if cargs else {})
    linhas = []
    for agr in c.get("agr", []) or []:
        for par in agr.get("par", []) or []:
            for cand in par.get("cand", []) or []:
                linhas.append({
                    "sqcand": str(cand.get("sqcand", "")),
                    "numero": cand.get("n", ""),
                    "candidato": (cand.get("nmu") or cand.get("nm") or "").title(),
                    "partido": par.get("sg", ""),
                    "agremiacao": agr.get("nm", "") if agr.get("tp") in ("c", "f") else par.get("sg", ""),
                    "votos": _n(cand.get("vap")),
                    "pct": _p(cand.get("pvap")),
                    "eleito": cand.get("e") == "s",
                    "situacao": cand.get("st", "") or "",
                })
    df = pd.DataFrame(linhas, columns=["sqcand", "numero", "candidato", "partido", "agremiacao",
                                       "votos", "pct", "eleito", "situacao"])
    if not df.empty:
        df = df.sort_values(["votos", "candidato"], ascending=[False, True]).reset_index(drop=True)
        df.insert(0, "uf", abr[:2].upper())
    s, e, v = raw.get("s", {}) or {}, raw.get("e", {}) or {}, raw.get("v", {}) or {}
    return Resultado(
        cargo=cargo, abr=abr.upper(), cargo_nome=c.get("nmn", CARGOS[cargo][0]), vagas=_n(c.get("nv")),
        atualizado=f"{raw.get('dg', '')} {raw.get('hg', '')}".strip(), final=raw.get("tf") == "s",
        secoes_total=_n(s.get("ts")), secoes_tot=_n(s.get("st")), pct_secoes=_p(s.get("pst")),
        eleitorado=_n(e.get("te")), comparecimento=_n(e.get("c")), pct_comparecimento=_p(e.get("pc")),
        abstencao=_n(e.get("a")), pct_abstencao=_p(e.get("pa")),
        votos_total=_n(v.get("tv")), validos=_n(v.get("vv")), brancos=_n(v.get("vb")),
        pct_brancos=_p(v.get("pvb")), nulos=_n(v.get("tvn")), pct_nulos=_p(v.get("ptvn")),
        candidatos=df,
    )


# ---------------------------------------------------------------- coleta
def url_foto(ambiente: str, cargo: int, abr: str, sqcand: str) -> str:
    """Foto oficial do candidato (servida pelo TSE; carregada pelo navegador de quem vê o painel)."""
    cfg = AMBIENTES[ambiente]
    ele = codigo_eleicao(ambiente, cargo)
    return f"{cfg['base']}/{CICLO}/{ele}/fotos/{abr.lower()}/{sqcand}.jpeg"


def obter_raw(ambiente: str, cargo: int, abr: str, demo: bool = False, max_idade: float = 0,
              rede: bool = True) -> dict:
    if demo:
        import demo as _demo
        return _demo.gerar(cargo, abr)
    return fonte.obter(url_resultado(ambiente, cargo, abr), max_idade=max_idade, rede=rede)


def coletar(ambiente: str, cargo: int, abr: str, demo: bool = False, max_idade: float = 0,
            rede: bool = True) -> Resultado:
    raw = obter_raw(ambiente, cargo, abr, demo, max_idade, rede)
    res = normalizar(raw, cargo, abr)
    if not res.candidatos.empty:
        if demo:
            res.candidatos["foto"] = os.getenv("APURACAO_DEMO_FOTO", "")
        elif len(abr) == 2:
            res.candidatos["foto"] = [url_foto(ambiente, cargo, abr, s) for s in res.candidatos["sqcand"]]
        else:
            res.candidatos["foto"] = ""
    return res


def coletar_lote(ambiente: str, pedidos: list[tuple[int, str]], demo: bool = False, max_idade: float = 0,
                 rede: bool = True, workers: int = 8) -> tuple[dict, dict]:
    """Coleta paralela. Retorna ({(cargo, abr): Resultado}, {(cargo, abr): erro})."""
    ok, erros = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(coletar, ambiente, c, a, demo, max_idade, rede): (c, a) for c, a in pedidos}
        for f, p in futs.items():
            try:
                ok[p] = f.result()
            except Exception as exc:
                erros[p] = str(exc)
    return ok, erros


# ---------------------------------------------------------------- municípios
def _norm_nome(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", s.upper())
    return "".join(c for c in s if c.isalnum() and not unicodedata.combining(c))


def municipios(ambiente: str, cargo: int, demo: bool = False, rede: bool = True) -> pd.DataFrame:
    """Lista de municípios (uf, cd_tse, cd_ibge, nome). O TSE usa código próprio (5 dígitos);
    o código IBGE vem do campo 'cdi' do arquivo de configuração ou, se faltar, por nome."""
    import geo
    malha = geo.municipios_df()  # cd_ibge, nome, uf (da malha embarcada)
    if demo:
        m = malha.copy()
        m["cd_tse"] = m["cd_ibge"].str[2:]
        return m[["uf", "cd_tse", "cd_ibge", "nome"]]
    raw = fonte.obter(url_config_municipios(ambiente, cargo), max_idade=6 * 3600, rede=rede)
    linhas = []

    def walk(o, uf=None):
        if isinstance(o, dict):
            cd = str(o.get("cd", ""))
            if len(cd) == 2 and cd.isalpha():
                uf = cd.upper()
            if uf and len(cd) == 5 and cd.isdigit() and ("nm" in o or "ds" in o):
                cdi = str(o.get("cdi") or o.get("cdibge") or o.get("ibge") or "")
                linhas.append({"uf": uf, "cd_tse": cd, "cdi": cdi, "nome": o.get("nm") or o.get("ds")})
            for v in o.values():
                walk(v, uf)
        elif isinstance(o, list):
            for v in o:
                walk(v, uf)

    walk(raw)
    df = pd.DataFrame(linhas, columns=["uf", "cd_tse", "cdi", "nome"])
    df = df[df["uf"].isin(UFS.keys())].drop_duplicates(["uf", "cd_tse"])
    chave = malha.assign(k=malha["uf"] + malha["nome"].map(_norm_nome)).set_index("k")["cd_ibge"]
    por_nome = (df["uf"] + df["nome"].map(_norm_nome)).map(chave)
    df["cd_ibge"] = df["cdi"].where(df["cdi"].str.len() == 7, por_nome)
    return df[["uf", "cd_tse", "cd_ibge", "nome"]]


def coletar_municipal(ambiente: str, cargo: int, ufs: list[str], demo: bool = False, rede: bool = True,
                      max_idade: float = 600, workers: int = 8, ao_coletar=None) -> tuple[pd.DataFrame, int, int]:
    """Resultados por município (formato longo, 1 linha por candidato x município).
    ao_coletar(res, linha_municipio): callback opcional (usado pelo coletor para gravar no banco)."""
    mun = municipios(ambiente, cargo, demo, rede)
    mun = mun[mun["uf"].isin([u.upper() for u in ufs])]
    faltam = 0

    def job(m):
        if demo:
            import demo as _demo
            return m, _demo.gerar_municipio(cargo, m.uf, m.cd_ibge)
        return m, obter_raw(ambiente, cargo, m.uf.lower() + m.cd_tse, False, max_idade, rede)

    linhas = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in [ex.submit(job, m) for m in mun.itertuples()]:
            try:
                m, raw = f.result()
            except Exception:
                faltam += 1
                continue
            if ao_coletar:
                ao_coletar(raw, m)
            s_, v_ = raw.get("s") or {}, raw.get("v") or {}
            pst, vv = _p(s_.get("pst")), _n(v_.get("vv"))
            for c in raw.get("carg") or []:
                if _n(c.get("cd")) != cargo:
                    continue
                for agr in c.get("agr") or []:
                    for par in agr.get("par") or []:
                        for cand in par.get("cand") or []:
                            linhas.append((str(cand.get("sqcand", "")), (cand.get("nmu") or cand.get("nm") or "").title(),
                                           par.get("sg", ""), _n(cand.get("vap")), _p(cand.get("pvap")),
                                           m.uf, m.cd_tse, m.cd_ibge, m.nome, pst, vv))
    longo = pd.DataFrame(linhas, columns=["sqcand", "candidato", "partido", "votos", "pct", "uf", "cd_tse",
                                          "cd_ibge", "municipio", "pct_secoes", "validos"])
    return longo, len(mun) - faltam, faltam


# ---------------------------------------------------------------- histórico local (gráfico de evolução)
def salvar_snapshot(res: Resultado, chave: str, pasta: str = "dados/evolucao") -> None:
    Path(pasta).mkdir(parents=True, exist_ok=True)
    linha = {"coletado_em": pd.Timestamp.now().isoformat(timespec="seconds"), "pct_secoes": res.pct_secoes}
    if not res.candidatos.empty:
        for _, c in res.candidatos.head(5).iterrows():
            linha[f"{c['candidato']} ({c['partido']})"] = c["pct"]
    arq = Path(pasta) / f"{chave}_c{res.cargo}_{res.abr.lower()}.jsonl"
    with arq.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(linha, ensure_ascii=False) + "\n")


def ler_evolucao(cargo: int, abr: str, chave: str, pasta: str = "dados/evolucao") -> pd.DataFrame:
    arq = Path(pasta) / f"{chave}_c{cargo}_{abr.lower()}.jsonl"
    if not arq.exists():
        return pd.DataFrame()
    return pd.read_json(arq, lines=True)


def datahora_tse(res: Resultado):
    try:
        return pd.to_datetime(res.atualizado, format="%d/%m/%Y %H:%M:%S").to_pydatetime()
    except Exception:
        return None


# ---------------------------------------------------------------- camada consolidada (coletor -> app)
def _arq_consolidado(ambiente: str, cargo: int) -> Path:
    return fonte.RAIZ.parent / f"municipal_{chave(ambiente)}_c{cargo}.parquet"


def gravar_consolidado(ambiente: str, cargo: int, longo: pd.DataFrame) -> None:
    if longo.empty:
        return
    p = _arq_consolidado(ambiente, cargo)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    longo.to_parquet(tmp, index=False)
    for i in range(10):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.1 * (i + 1))


def ler_consolidado(ambiente: str, cargo: int, max_idade: float = 1500):
    p = _arq_consolidado(ambiente, cargo)
    if not p.exists() or time.time() - p.stat().st_mtime > max_idade:
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None
