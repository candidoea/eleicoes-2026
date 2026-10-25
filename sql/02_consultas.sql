/* Consultas de exemplo para a análise pós-eleição. Ambiente: 'oficial' (ou 'demo' nos testes). */
USE [Eleicoes2026];
GO
-- 1) Resultado final de Presidente no Brasil
SELECT NomeUrna, Partido, Votos, Pct, Situacao
FROM apuracao.vw_ResultadoAtual
WHERE Ambiente = 'oficial' AND Cargo = 1 AND Nivel = 'B'
ORDER BY Votos DESC;

-- 2) Curva da apuração: % de cada candidato a Presidente conforme as seções foram totalizadas
SELECT DataHoraTSE, PctSecoes, NomeUrna, Partido, Pct
FROM apuracao.vw_Evolucao
WHERE Ambiente = 'oficial' AND Cargo = 1 AND Nivel = 'B'
ORDER BY DataHoraTSE, Pct DESC;

-- 3) Vencedor por município (Presidente)
WITH r AS (
    SELECT UF, CodIBGE, NomeMunicipio, NomeUrna, Partido, Votos, Pct,
           ROW_NUMBER() OVER (PARTITION BY UF, CodMunTSE ORDER BY Votos DESC) AS rk
    FROM apuracao.vw_ResultadoAtual
    WHERE Ambiente = 'oficial' AND Cargo = 1 AND Nivel = 'M'
)
SELECT UF, CodIBGE, NomeMunicipio, NomeUrna AS Vencedor, Partido, Pct
FROM r WHERE rk = 1;

-- 4) Municípios vencidos por candidato em cada UF
WITH r AS (
    SELECT UF, CodMunTSE, NomeUrna, Partido,
           ROW_NUMBER() OVER (PARTITION BY UF, CodMunTSE ORDER BY Votos DESC) AS rk
    FROM apuracao.vw_ResultadoAtual
    WHERE Ambiente = 'oficial' AND Cargo = 1 AND Nivel = 'M'
)
SELECT UF, NomeUrna, Partido, COUNT(*) AS Municipios
FROM r WHERE rk = 1
GROUP BY UF, NomeUrna, Partido
ORDER BY UF, Municipios DESC;

-- 5) Governadores: quem foi ao 2º turno ou se elegeu
SELECT UF, NomeUrna, Partido, Pct, Situacao
FROM apuracao.vw_ResultadoAtual
WHERE Ambiente = 'oficial' AND Cargo = 3 AND Nivel = 'U' AND (Eleito = 1 OR Situacao LIKE N'%2º turno%')
ORDER BY UF, Pct DESC;

-- 6) Bancada eleita na Câmara por partido
SELECT Partido, COUNT(*) AS Cadeiras
FROM apuracao.vw_ResultadoAtual
WHERE Ambiente = 'oficial' AND Cargo = 6 AND Nivel = 'U' AND Eleito = 1
GROUP BY Partido ORDER BY Cadeiras DESC;

-- 7) Volume coletado
SELECT Ambiente, Cargo, Nivel, COUNT(*) AS Snapshots, MIN(DataHoraTSE) AS Primeiro, MAX(DataHoraTSE) AS Ultimo
FROM apuracao.Snapshot GROUP BY Ambiente, Cargo, Nivel ORDER BY Ambiente, Cargo, Nivel;
