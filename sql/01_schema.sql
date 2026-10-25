/* Eleições 2026 - histórico da apuração (dados abertos de divulgação do TSE)
   Executado automaticamente pelo coletor (banco.preparar). Idempotente.
   Grão: 1 snapshot = 1 versão (data/hora TSE) de 1 arquivo -u.json (cargo x abrangência). */
USE [Eleicoes2026];
GO
IF SCHEMA_ID(N'apuracao') IS NULL EXEC(N'CREATE SCHEMA apuracao');
GO
IF OBJECT_ID(N'apuracao.Snapshot') IS NULL
CREATE TABLE apuracao.Snapshot (
    SnapshotId        bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Snapshot PRIMARY KEY,
    Ambiente          varchar(40)   NOT NULL,          -- Oficial / Simulado / demo
    Eleicao           int           NOT NULL,          -- 6257 federal, 6259 estadual
    Cargo             tinyint       NOT NULL,          -- 1 Pres, 3 Gov, 5 Sen, 6 DF, 7 DE, 8 Distrital
    Nivel             char(1)       NOT NULL,          -- B Brasil, U UF, M Município
    UF                char(2)       NOT NULL,          -- 'BR' no nível Brasil
    CodMunTSE         char(5)       NOT NULL CONSTRAINT DF_Snapshot_Mun DEFAULT (''),
    CodIBGE           char(7)       NULL,
    NomeMunicipio     nvarchar(120) NULL,
    DataHoraTSE       datetime2(0)  NOT NULL,          -- dg + hg do arquivo
    ColetadoEm        datetime2(0)  NOT NULL CONSTRAINT DF_Snapshot_Col DEFAULT (SYSDATETIME()),
    SecoesTotal       int NULL, SecoesTotalizadas int NULL, PctSecoes decimal(6,2) NULL,
    Eleitorado        int NULL, Comparecimento int NULL, Abstencao int NULL,
    VotosTotal        int NULL, VotosValidos int NULL, Brancos int NULL, Nulos int NULL,
    TotalizacaoFinal  bit NOT NULL CONSTRAINT DF_Snapshot_TF DEFAULT (0),
    CONSTRAINT UQ_Snapshot UNIQUE (Ambiente, Cargo, Nivel, UF, CodMunTSE, DataHoraTSE)
);
GO
IF OBJECT_ID(N'apuracao.SnapshotCandidato') IS NULL
CREATE TABLE apuracao.SnapshotCandidato (
    SnapshotId  bigint       NOT NULL CONSTRAINT FK_SnapCand_Snap REFERENCES apuracao.Snapshot(SnapshotId),
    SqCand      varchar(20)  NOT NULL,
    Votos       int          NOT NULL,
    Pct         decimal(6,2) NULL,
    Eleito      bit          NOT NULL,
    Situacao    nvarchar(60) NULL,
    CONSTRAINT PK_SnapshotCandidato PRIMARY KEY (SnapshotId, SqCand)
);
GO
IF OBJECT_ID(N'apuracao.Candidato') IS NULL
CREATE TABLE apuracao.Candidato (
    SqCand        varchar(20)   NOT NULL CONSTRAINT PK_Candidato PRIMARY KEY,
    Cargo         tinyint       NOT NULL,
    UF            char(2)       NOT NULL,
    Numero        varchar(10)   NULL,
    NomeUrna      nvarchar(120) NULL,
    NomeCompleto  nvarchar(200) NULL,
    Partido       varchar(40)   NULL,
    Agremiacao    nvarchar(300) NULL,
    FotoUrl       varchar(400)  NULL,
    AtualizadoEm  datetime2(0)  NOT NULL CONSTRAINT DF_Candidato_At DEFAULT (SYSDATETIME())
);
GO
IF OBJECT_ID(N'apuracao.Municipio') IS NULL
CREATE TABLE apuracao.Municipio (
    UF         char(2)       NOT NULL,
    CodMunTSE  char(5)       NOT NULL,
    CodIBGE    char(7)       NULL,
    Nome       nvarchar(120) NOT NULL,
    CONSTRAINT PK_Municipio PRIMARY KEY (UF, CodMunTSE)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Snapshot_Ultimo')
CREATE INDEX IX_Snapshot_Ultimo ON apuracao.Snapshot (Ambiente, Cargo, Nivel, UF, CodMunTSE, DataHoraTSE DESC)
    INCLUDE (PctSecoes, VotosValidos);
GO
/* Último snapshot de cada arquivo */
CREATE OR ALTER VIEW apuracao.vw_UltimoSnapshot AS
SELECT s.*
FROM apuracao.Snapshot s
WHERE s.DataHoraTSE = (SELECT MAX(x.DataHoraTSE) FROM apuracao.Snapshot x
                       WHERE x.Ambiente = s.Ambiente AND x.Cargo = s.Cargo AND x.Nivel = s.Nivel
                         AND x.UF = s.UF AND x.CodMunTSE = s.CodMunTSE);
GO
/* Resultado atual por candidato (último snapshot) */
CREATE OR ALTER VIEW apuracao.vw_ResultadoAtual AS
SELECT s.Ambiente, s.Cargo, s.Nivel, s.UF, s.CodMunTSE, s.CodIBGE, s.NomeMunicipio, s.DataHoraTSE, s.PctSecoes,
       c.SqCand, k.NomeUrna, k.Partido, k.Numero, c.Votos, c.Pct, c.Eleito, c.Situacao
FROM apuracao.vw_UltimoSnapshot s
JOIN apuracao.SnapshotCandidato c ON c.SnapshotId = s.SnapshotId
LEFT JOIN apuracao.Candidato k ON k.SqCand = c.SqCand;
GO
/* Série temporal (evolução da apuração) por candidato */
CREATE OR ALTER VIEW apuracao.vw_Evolucao AS
SELECT s.Ambiente, s.Cargo, s.Nivel, s.UF, s.CodMunTSE, s.CodIBGE, s.NomeMunicipio, s.DataHoraTSE, s.PctSecoes,
       c.SqCand, k.NomeUrna, k.Partido, c.Votos, c.Pct
FROM apuracao.Snapshot s
JOIN apuracao.SnapshotCandidato c ON c.SnapshotId = s.SnapshotId
LEFT JOIN apuracao.Candidato k ON k.SqCand = c.SqCand;
GO
