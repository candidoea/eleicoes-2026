"""Coletor (microserviço) da apuração: baixa os arquivos do TSE em ciclos, mantém o cache
local que o painel lê e grava o histórico no SQL Server.

Uso (num terminal separado do Streamlit):
  python coletor.py                       # 2º turno oficial, grava no banco
  python coletor.py --ambiente oficial    # 1º turno
  python coletor.py --demo --uma-vez      # testa o pipeline e o banco com dados fictícios
  python coletor.py --sem-banco           # só mantém o cache do painel
  python coletor.py --ufs RN,PB           # restringe a coleta municipal

Ciclos:
  rápido    (--intervalo, 60 s): Presidente BR + todos os cargos nas 27 UFs (~136 arquivos)
  municipal (--intervalo-mun, 600 s): Presidente e Governador em todos os municípios (~11 mil arquivos)
Limite global: --rps (padrão 30 req/s; o TSE tolera 100 req/s por IP).
"""
from __future__ import annotations

import argparse
import os
import threading
import time
from datetime import datetime

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--ambiente", choices=["oficial2", "oficial", "simulado"], default="oficial2",
                    help="oficial2 = 2º turno (padrão); oficial = 1º turno; simulado = ensaio do TSE")
parser.add_argument("--demo", action="store_true", help="dados fictícios (testa banco sem rede)")
parser.add_argument("--sem-banco", action="store_true")
parser.add_argument("--intervalo", type=int, default=60)
parser.add_argument("--intervalo-mun", type=int, default=0, help="padrão: 300 s no 2º turno, 600 s no 1º")
parser.add_argument("--rps", type=float, default=30)
parser.add_argument("--ufs", default="", help="UFs da coleta municipal (padrão: todas)")
parser.add_argument("--cargos-mun", default="1,3", help="cargos coletados por município (padrão 1,3)")
parser.add_argument("--uma-vez", action="store_true", help="executa um ciclo de cada e sai")
args = parser.parse_args()

os.environ["APURACAO_RPS"] = str(args.rps)  # antes de importar fonte
import fonte  # noqa: E402
import tse  # noqa: E402
from tse import CARGOS, UFS, cargo_legislativo_estadual  # noqa: E402

AMB = {"oficial2": "Oficial 2º turno (25/10/2026)", "oficial": "Oficial 1º turno (04/10/2026)",
       "simulado": "Simulado (ensaio TSE)"}[args.ambiente]
TURNO2 = tse.turno(AMB) == 2
if not args.intervalo_mun:
    args.intervalo_mun = 300 if TURNO2 else 600
if TURNO2 and not args.demo:
    tse.descobrir_codigos_2t(lambda m: print(m, flush=True))
NOME_AMB = "demo" if args.demo else args.ambiente
banco = None
if not args.sem_banco:
    try:
        import banco  # noqa: E402
        print(f"[banco] conectado em {banco.preparar()} / {banco.DATABASE}")
    except Exception as exc:  # sem SQL Server (ou sem pyodbc): segue só com o cache do painel
        banco = None
        print(f"[banco] indisponível ({exc}); seguindo sem banco. Use --sem-banco para não tentar.")

_ultimo: dict = {}  # (cargo, abr) -> (dg, hg): evita ida ao banco se o arquivo não mudou
_lock = threading.Lock()
_lock_banco = threading.Lock()
parar = threading.Event()


def log(msg):
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


def gravar(raw, cargo, uf, cd_tse="", cd_ibge=None, nome=None):
    if banco is None or not raw:
        return 0
    cd_ibge = cd_ibge if isinstance(cd_ibge, str) and len(cd_ibge) == 7 else None
    chave = (cargo, uf, cd_tse)
    marca = (raw.get("dg"), raw.get("hg"))
    with _lock:
        if _ultimo.get(chave) == marca:
            return 0
    ele = tse.codigo_eleicao(AMB, cargo) if not args.demo else "0"
    foto = None
    if not cd_tse and not args.demo:
        foto = tse.url_foto(AMB, cargo, uf, "x").rsplit("/", 1)[0]
    ok = False
    for tentativa in range(5):
        try:
            with _lock_banco:  # gravação serializada: evita deadlock entre as threads
                ok = banco.gravar(raw, NOME_AMB, ele, cargo, uf, cd_tse, cd_ibge, nome, foto)
            break
        except Exception as exc:
            if "1205" in str(exc) or "40001" in str(exc):  # deadlock: tenta de novo
                time.sleep(0.2 * (tentativa + 1))
                continue
            log(f"[banco] erro {cargo}/{uf}{cd_tse}: {exc}")
            return 0
    else:
        log(f"[banco] desisti após 5 deadlocks: {cargo}/{uf}{cd_tse}")
        return 0
    with _lock:
        _ultimo[chave] = marca
    return int(ok)


def ciclo_rapido():
    if TURNO2:
        pedidos = [(1, "br")] + [(1, uf) for uf in UFS] + [(3, uf) for uf in tse.ufs_do_cargo(AMB, 3)]
    else:
        pedidos = [(1, "br")] + [(c, uf) for uf in UFS for c in (1, 3, 5, 6, cargo_legislativo_estadual(uf))]
    t0, novos, erros = time.time(), 0, 0
    from concurrent.futures import ThreadPoolExecutor

    def job(p):
        cargo, abr = p
        raw = tse.obter_raw(AMB, cargo, abr, args.demo, max_idade=0)
        return gravar(raw, cargo, abr.upper())

    with ThreadPoolExecutor(max_workers=8) as ex:
        for f in [ex.submit(job, p) for p in pedidos]:
            try:
                novos += f.result()
            except Exception:
                erros += 1
    log(f"[rápido] {len(pedidos)} arquivos em {time.time() - t0:.1f}s · {novos} snapshots novos · {erros} indisponíveis")


def ciclo_municipal():
    ufs_pedidas = [u.strip().upper() for u in args.ufs.split(",") if u.strip()] or list(UFS)
    for cargo in [int(c) for c in args.cargos_mun.split(",")]:
        ufs = [u for u in ufs_pedidas if u in tse.ufs_do_cargo(AMB, cargo)]
        if not ufs:
            continue
        t0 = time.time()
        cont = {"n": 0}

        def cb(raw, m, cargo=cargo):
            cont["n"] += gravar(raw, cargo, m.uf, m.cd_tse, m.cd_ibge, m.nome)

        if banco is not None:
            try:
                banco.gravar_municipios(tse.municipios(AMB, cargo, args.demo), NOME_AMB)
            except Exception as exc:
                log(f"[banco] municípios: {exc}")
        df, ok, falta = tse.coletar_municipal(AMB, cargo, ufs, demo=args.demo, max_idade=0, workers=12,
                                              ao_coletar=cb)
        if not args.demo and not args.ufs:
            try:
                tse.gravar_consolidado(AMB, cargo, df)  # o painel lê este arquivo único
            except Exception as exc:
                log(f"[consolidado] {exc}")
        log(f"[municipal] {CARGOS[cargo][0]}: {ok} municípios em {time.time() - t0:.0f}s · "
            f"{cont['n']} snapshots novos · {falta} indisponíveis")
        if TURNO2 and not args.demo and not df.empty:
            projetar_e_registrar(cargo, df)


def projetar_e_registrar(cargo, longo):
    """2º turno: projeção do resultado com os municípios já totalizados (histórico para o laboratório)."""
    try:
        import projecao
        alvos = [None] if cargo == 1 else tse.ufs_do_cargo(AMB, 3)
        for uf in alvos:
            pj = projecao.projetar_de_longo(longo, cargo, uf, n_boot=30)
            projecao.registrar(tse.chave(AMB), cargo, uf or "br", pj)
            a, b = pj.partidos
            log(f"[projeção] {CARGOS[cargo][0]} {uf or 'BR'}: {a} {pj.pct_a:.2f}% (90%: {pj.p05:.2f} a {pj.p95:.2f}) "
                f"· P({a} vencer) {100 * pj.prob_a:.0f}% · {pj.totalizados} municípios totalizados · "
                f"{pj.pct_contado:.1f}% dos válidos esperados contados")
    except Exception as exc:
        log(f"[projeção] falhou: {exc}")


def laco(fn, intervalo):
    while not parar.is_set():
        t0 = time.time()
        try:
            fn()
        except Exception as exc:
            log(f"[{fn.__name__}] falhou: {exc}")
        if args.uma_vez:
            return
        parar.wait(max(1, intervalo - (time.time() - t0)))


if __name__ == "__main__":
    log(f"coletor · ambiente={NOME_AMB} · {args.rps} req/s · cache em {fonte.RAIZ}")
    ts = [threading.Thread(target=laco, args=(ciclo_rapido, args.intervalo), daemon=True),
          threading.Thread(target=laco, args=(ciclo_municipal, args.intervalo_mun), daemon=True)]
    for t in ts:
        t.start()
    try:
        while any(t.is_alive() for t in ts):
            time.sleep(0.5)
    except KeyboardInterrupt:
        parar.set()
        log("encerrando...")
    # os ThreadPoolExecutor internos não são daemon: sem isto o Python espera o ciclo municipal
    # inteiro terminar antes de sair. O que já foi gravado está commitado.
    os._exit(0)
