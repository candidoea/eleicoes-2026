"""Persistência no SQL Server (histórico da apuração para análise pós-eleição).

Conexão (variáveis de ambiente, todas opcionais):
  SQLSERVER_SERVER   instância; padrão: tenta localhost, localhost\\SQLEXPRESS, (localdb)\\MSSQLLocalDB
  SQLSERVER_DATABASE banco; padrão Eleicoes2026 (criado se não existir)
  SQLSERVER_DRIVER   driver ODBC; padrão: o mais novo instalado
  SQLSERVER_CONN     string ODBC completa (sobrepõe as anteriores)
Autenticação: Windows (Trusted_Connection).
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

import pyodbc

DDL = (Path(__file__).parent / "sql" / "01_schema.sql")
_local = threading.local()


def _driver() -> str:
    if os.getenv("SQLSERVER_DRIVER"):
        return os.environ["SQLSERVER_DRIVER"]
    disponiveis = pyodbc.drivers()
    for d in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server",
              "SQL Server Native Client 11.0", "SQL Server"):
        if d in disponiveis:
            return d
    raise RuntimeError(f"Nenhum driver ODBC do SQL Server encontrado. Instalados: {disponiveis}")


def _conn_str(server: str, database: str) -> str:
    d = _driver()
    extra = "Encrypt=yes;TrustServerCertificate=yes;" if "18" in d else ""
    return f"DRIVER={{{d}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;{extra}"


def _servidores():
    if os.getenv("SQLSERVER_SERVER"):
        return [os.environ["SQLSERVER_SERVER"]]
    return ["localhost", r"localhost\SQLEXPRESS", r"(localdb)\MSSQLLocalDB"]


DATABASE = os.getenv("SQLSERVER_DATABASE", "Eleicoes2026")
_server_ok: str | None = None


def preparar() -> str:
    """Encontra a instância, cria o banco e o schema se necessário. Devolve a instância usada."""
    global _server_ok
    if os.getenv("SQLSERVER_CONN"):
        cn = pyodbc.connect(os.environ["SQLSERVER_CONN"], autocommit=True)
        _executar_ddl(cn)
        _server_ok = "SQLSERVER_CONN"
        return _server_ok
    erros = []
    for srv in _servidores():
        try:
            cn = pyodbc.connect(_conn_str(srv, "master"), autocommit=True, timeout=5)
        except pyodbc.Error as exc:
            erros.append(f"{srv}: {exc}")
            continue
        cn.execute(f"IF DB_ID(N'{DATABASE}') IS NULL CREATE DATABASE [{DATABASE}]")
        cn.close()
        _server_ok = srv
        cn = pyodbc.connect(_conn_str(srv, DATABASE), autocommit=True)
        _executar_ddl(cn)
        return srv
    raise RuntimeError("Não conectou em nenhuma instância:\n" + "\n".join(erros))


def _executar_ddl(cn):
    sql = DDL.read_text(encoding="utf-8")
    for bloco in [b.strip() for b in sql.split("\nGO") if b.strip()]:
        if re.search(r"^\s*USE\s", bloco, re.M | re.I):
            continue
        cn.execute(bloco)


def conexao():
    if not hasattr(_local, "cn"):
        if os.getenv("SQLSERVER_CONN"):
            _local.cn = pyodbc.connect(os.environ["SQLSERVER_CONN"])
        else:
            _local.cn = pyodbc.connect(_conn_str(_server_ok or preparar(), DATABASE))
    return _local.cn


def _n(x):
    try:
        return int(str(x).replace(".", "")) if x not in (None, "") else None
    except ValueError:
        return None


def _p(x):
    try:
        return float(str(x).replace(",", ".")) if x not in (None, "") else None
    except ValueError:
        return None


def _dt(raw):
    from datetime import datetime
    try:
        return datetime.strptime(f"{raw.get('dg')} {raw.get('hg')}", "%d/%m/%Y %H:%M:%S")
    except Exception:
        return None


def gravar(raw: dict, ambiente: str, eleicao: str, cargo: int, uf: str, cd_tse: str = "",
           cd_ibge: str | None = None, municipio: str | None = None, foto_base: str | None = None) -> bool:
    """Grava um arquivo -u.json como snapshot. Idempotente: se o TSE ainda não mudou a
    data/hora do arquivo, não grava nada. Devolve True se inseriu."""
    dt = _dt(raw)
    if dt is None:
        return False
    nivel = "B" if uf.upper() == "BR" else ("M" if cd_tse else "U")
    s, e, v = raw.get("s") or {}, raw.get("e") or {}, raw.get("v") or {}
    cn = conexao()
    cur = cn.cursor()
    try:
        cur.execute("""
            SET NOCOUNT ON;
            IF NOT EXISTS (SELECT 1 FROM apuracao.Snapshot WITH (UPDLOCK, HOLDLOCK)
                           WHERE Ambiente=? AND Cargo=? AND Nivel=? AND UF=? AND CodMunTSE=? AND DataHoraTSE=?)
            INSERT INTO apuracao.Snapshot (Ambiente, Eleicao, Cargo, Nivel, UF, CodMunTSE, CodIBGE, NomeMunicipio,
                DataHoraTSE, SecoesTotal, SecoesTotalizadas, PctSecoes, Eleitorado, Comparecimento, Abstencao,
                VotosTotal, VotosValidos, Brancos, Nulos, TotalizacaoFinal)
            OUTPUT inserted.SnapshotId
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);""",
                    ambiente, cargo, nivel, uf.upper(), cd_tse, dt,
                    ambiente, int(eleicao), cargo, nivel, uf.upper(), cd_tse, cd_ibge, municipio, dt,
                    _n(s.get("ts")), _n(s.get("st")), _p(s.get("pst")), _n(e.get("te")), _n(e.get("c")),
                    _n(e.get("a")), _n(v.get("tv")), _n(v.get("vv")), _n(v.get("vb")), _n(v.get("tvn")),
                    1 if raw.get("tf") == "s" else 0)
        row = cur.fetchone() if cur.description else None
        if not row:
            cn.commit()
            return False
        sid = row[0]
        cands, snap = [], []
        for c in raw.get("carg") or []:
            if _n(c.get("cd")) != cargo:
                continue
            for agr in c.get("agr") or []:
                for par in agr.get("par") or []:
                    for cand in par.get("cand") or []:
                        sq = str(cand.get("sqcand", ""))
                        snap.append((sid, sq, _n(cand.get("vap")) or 0, _p(cand.get("pvap")),
                                     1 if cand.get("e") == "s" else 0, (cand.get("st") or "")[:60]))
                        if nivel != "M":
                            foto = f"{foto_base}/{sq}.jpeg" if foto_base else None
                            cands.append((sq, cargo, uf.upper(), cand.get("n"), cand.get("nmu"), cand.get("nm"),
                                          par.get("sg"), agr.get("nm"), foto))
        cur.fast_executemany = True
        if snap:
            cur.executemany("INSERT INTO apuracao.SnapshotCandidato (SnapshotId, SqCand, Votos, Pct, Eleito, Situacao) "
                            "VALUES (?,?,?,?,?,?)", snap)
        if cands:
            cur.fast_executemany = False
            for c in cands:
                cur.execute("""
                    MERGE apuracao.Candidato AS t USING (SELECT ? AS SqCand) AS s ON t.SqCand = s.SqCand
                    WHEN MATCHED THEN UPDATE SET NomeUrna=?, Partido=?, Agremiacao=?, AtualizadoEm=SYSDATETIME()
                    WHEN NOT MATCHED THEN INSERT (SqCand, Cargo, UF, Numero, NomeUrna, NomeCompleto, Partido,
                         Agremiacao, FotoUrl) VALUES (?,?,?,?,?,?,?,?,?);""",
                            c[0], c[4], c[6], c[7], *c)
        cn.commit()
        return True
    except Exception:
        cn.rollback()
        raise


def gravar_municipios(df, ambiente: str):
    """Dimensão de municípios (TSE x IBGE)."""
    cn = conexao()
    cur = cn.cursor()
    for r in df.itertuples():
        cur.execute("""MERGE apuracao.Municipio AS t USING (SELECT ? AS UF, ? AS CodMunTSE) AS s
                       ON t.UF=s.UF AND t.CodMunTSE=s.CodMunTSE
                       WHEN NOT MATCHED THEN INSERT (UF, CodMunTSE, CodIBGE, Nome) VALUES (?,?,?,?);""",
                    r.uf, r.cd_tse, r.uf, r.cd_tse,
                    r.cd_ibge if isinstance(r.cd_ibge, str) and len(r.cd_ibge) == 7 else None, r.nome)
    cn.commit()
