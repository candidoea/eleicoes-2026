"""Gera as bases do modelo de projeção do 2º turno a partir dos dados abertos do TSE (parquet do projeto
missao-2028). Rodar uma vez:  python ferramentas/gerar_base_projecao.py ..\\missao-2028\\dados\\parquet

Saídas em modelo/:
  base_2026.parquet     votos do 1º turno de 2026 por município e candidato (Presidente; Governador nas UFs com 2º turno)
  totais_2026.parquet   aptos, comparecimento e válidos do 1º turno por município
  replay_2022.parquet   1º e 2º turno de 2022 por município + hora de totalização (validação histórica)
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

P = Path(sys.argv[1] if len(sys.argv) > 1 else "../missao-2028/dados/parquet").resolve()
OUT = Path(__file__).resolve().parents[1] / "modelo"
OUT.mkdir(exist_ok=True)
UFS_GOV = "('AC','AM','DF','ES','RN','TO')"

duckdb.sql(f"""copy (
  select SG_UF uf, lpad(CD_MUNICIPIO, 5, '0') cd_tse, CD_CARGO::int cargo, SG_PARTIDO partido,
         any_value(NM_URNA_CANDIDATO) candidato, sum(QT_VOTOS_NOMINAIS_VALIDOS)::bigint votos
  from '{P}/votacao_candidato_munzona_2026/*.parquet'
  where NR_TURNO='1' and SG_UF<>'ZZ' and (CD_CARGO='1' or (CD_CARGO='3' and SG_UF in {UFS_GOV}))
  group by all) to '{OUT}/base_2026.parquet' (format parquet)""")
duckdb.sql(f"""copy (
  select SG_UF uf, lpad(CD_MUNICIPIO, 5, '0') cd_tse, CD_CARGO::int cargo, sum(QT_APTOS)::bigint aptos,
         sum(QT_COMPARECIMENTO)::bigint comparecimento, sum(QT_TOTAL_VOTOS_VALIDOS)::bigint validos
  from '{P}/detalhe_votacao_munzona_2026/*.parquet'
  where NR_TURNO='1' and SG_UF<>'ZZ' and (CD_CARGO='1' or (CD_CARGO='3' and SG_UF in {UFS_GOV}))
  group by all) to '{OUT}/totais_2026.parquet' (format parquet)""")
duckdb.sql(f"""copy (
  with v as (select NR_TURNO::int turno, SG_UF uf, lpad(CD_MUNICIPIO, 5, '0') cd_tse, SG_PARTIDO partido,
                    any_value(NM_URNA_CANDIDATO) candidato, sum(QT_VOTOS_NOMINAIS_VALIDOS)::bigint votos
             from '{P}/votacao_candidato_munzona_2022/*.parquet' where CD_CARGO='1' and SG_UF<>'ZZ' group by all),
       t as (select NR_TURNO::int turno, SG_UF uf, lpad(CD_MUNICIPIO, 5, '0') cd_tse,
                    sum(QT_APTOS)::bigint aptos, sum(QT_TOTAL_VOTOS_VALIDOS)::bigint validos,
                    max(strptime(DT_ULTIMA_TOTALIZACAO || ' ' || HH_ULTIMA_TOTALIZACAO, '%d/%m/%Y %H:%M:%S')) hora_tot
             from '{P}/detalhe_votacao_munzona_2022/*.parquet' where CD_CARGO='1' and SG_UF<>'ZZ' group by all)
  select v.*, t.aptos, t.validos, t.hora_tot from v join t using (turno, uf, cd_tse)
  ) to '{OUT}/replay_2022.parquet' (format parquet)""")
for f in ("base_2026", "totais_2026", "replay_2022"):
    print(f, duckdb.sql(f"select count(*) from '{OUT}/{f}.parquet'").fetchone()[0])
