"""Exporta do SQL Server a evolução de cada município durante a apuração (1 linha por snapshot e candidato).
Serve para reexecutar a noite na ordem real em que os municípios chegaram.

  python ferramentas/exportar_snapshots.py              # 2º turno (oficial2)
  python ferramentas/exportar_snapshots.py oficial      # 1º turno
Saída: _analise/snapshots_<ambiente>.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import banco  # noqa: E402

amb = sys.argv[1] if len(sys.argv) > 1 else "oficial2"
cn = banco.conexao()
sql = """
SELECT s.Cargo, s.Nivel, s.UF, s.CodMunTSE, s.DataHoraTSE, s.ColetadoEm, s.SecoesTotal, s.SecoesTotalizadas,
       s.PctSecoes, s.Eleitorado, s.Comparecimento, s.Abstencao, s.VotosValidos, s.Brancos, s.Nulos,
       c.SqCand, c.Votos, k.Partido
FROM apuracao.Snapshot s
JOIN apuracao.SnapshotCandidato c ON c.SnapshotId = s.SnapshotId
LEFT JOIN apuracao.Candidato k ON k.SqCand = c.SqCand
WHERE s.Ambiente = ? AND s.Cargo IN (1, 3)
"""
df = pd.read_sql(sql, cn, params=[amb])
out = Path(__file__).resolve().parents[1] / "_analise"
out.mkdir(exist_ok=True)
df.to_parquet(out / f"snapshots_{amb}.parquet", index=False)
print(f"{len(df):,} linhas · {df[['UF', 'CodMunTSE']].drop_duplicates().shape[0]:,} áreas · "
      f"{df['ColetadoEm'].min()} a {df['ColetadoEm'].max()} -> {out / f'snapshots_{amb}.parquet'}")
