# Apuração Eleições 2026

Painel em tempo (quase) real da apuração das eleições brasileiras de 2026, a partir dos dados abertos de
divulgação do TSE: Presidente, Governador, Senado e Câmaras no 1º turno; Presidente e Governador no 2º turno,
com **projeção do resultado por aprendizado de máquina** e um laboratório que compara a projeção com a
apuração real.

Painel não oficial, sem vínculo com a Justiça Eleitoral.

## Rodar em qualquer máquina (Windows, macOS ou Linux)

Requer Python 3.10 ou mais novo.

```bash
git clone https://github.com/candidoea/eleicoes-2026.git
cd eleicoes-2026
pip install -r requirements.txt

# terminal 1: coletor (baixa os arquivos do TSE para o cache local; 2º turno é o padrão)
python coletor.py --sem-banco

# terminal 2: painel  ->  http://localhost:8501
python -m streamlit run app.py
```

- Sem rede ou fora da noite de eleição: `python coletor.py --demo --uma-vez --sem-banco` e ative o
  "Modo demonstração" na barra lateral.
- Ensaio com a apuração de 2022: veja `ferramentas/simular_2turno.py`.
- Histórico no SQL Server (opcional, Windows): `pip install -r requirements-banco.txt` e rode o coletor sem
  `--sem-banco`. Sem SQL Server, o coletor segue só com o cache.
- Respeite o TSE: o coletor usa até 30 requisições por segundo (o limite tolerado é 100 por IP).


## 2º turno (25/10/2026)

```powershell
$py = "$env:USERPROFILE\anaconda3\python.exe"
& $py -m pip install -r requirements.txt -r requirements-banco.txt

# terminal 1: coletor do 2º turno (padrão). Confirma os códigos da eleição no TSE ao iniciar.
& $py coletor.py

# terminal 2: painel. Fonte "Oficial 2º turno": a projeção aparece ao lado da apuração em Brasil e Estado;
# a visão "Projeção e laboratório" traz a validação completa
& $py -m streamlit run app.py
```

- Códigos: 6258 (Presidente) e 6260 (Governador), confirmados em `comum/config/ele-c.json` pelo coletor.
- Só pede ao TSE o que existe no 2º turno: Presidente nas 27 UFs e Governador em AC, AM, DF, ES, RN e TO.
- Ciclo municipal a cada 300 s; ao fim de cada ciclo o coletor grava uma projeção em `dados/projecao/`.

### Projeção (`projecao.py`)
1. **Transferência:** em cada município totalizado, a fatia do finalista A no 2º turno é explicada pelas fatias do
   1º turno: `y = s_A + γ + Σ β_k s_k + u_UF`. β_k = fração dos eleitores do candidato eliminado k que foi para A.
2. **LightGBM:** com 400 municípios ou mais, aprende o resíduo pelo perfil do município; entra só se reduzir o
   erro em validação cruzada.
3. **Comparecimento:** válidos do 2º turno = válidos do 1º x razão por UF. **Incerteza:** bootstrap.
4. **Laboratório:** erro municipal fora da amostra (validação cruzada), projeção x resultado final e a
   reexecução da noite de 2022 na ordem real de totalização (`modelo/backtest_2022.parquet`).

Bases do modelo em `modelo/` (geradas por `ferramentas/gerar_base_projecao.py` a partir dos dados abertos do TSE).
Ensaio sem o TSE: `ferramentas/simular_2turno.py` gera arquivos no formato da API com a apuração de 2022.


## 1º turno (Windows, PowerShell, com SQL Server)

```powershell
$py = "$env:USERPROFILE\anaconda3\python.exe"
& $py -m pip install -r requirements.txt -r requirements-banco.txt

# 1) teste do banco e do pipeline com dados fictícios (cria o banco Eleicoes2026)
& $py coletor.py --demo --uma-vez

# 2) noite da eleição: terminal 1 = coletor (cache + SQL Server)
& $py coletor.py --ambiente oficial

# 3) terminal 2 = painel
& $py -m streamlit run app.py
```

## Arquitetura

```
TSE (resultados.tse.jus.br) ──► coletor.py ──► dados/cache/*.json ──► app.py (Streamlit)
                                    │
                                    └──► SQL Server [Eleicoes2026].apuracao.*
```

- `coletor.py`: microserviço com 2 laços em paralelo, limitados a 30 req/s (TSE tolera 100/s por IP):
  - rápido (60 s): Presidente BR + todos os cargos nas 27 UFs (~136 arquivos);
  - municipal (600 s): Presidente e Governador em todos os municípios (~11 mil arquivos).
  Usa requisição condicional (ETag) e cache negativo para 404 (o TSE bloqueia IP por excesso de 404).
  Opções: `--sem-banco`, `--ufs RN,PB`, `--cargos-mun 1,3`, `--rps 30`, `--intervalo 60`, `--intervalo-mun 600`.
- `app.py`: lê do cache local; se o arquivo estiver velho, busca direto no TSE. O mapa municipal do
  Brasil só usa o cache (precisa do coletor rodando).
- Banco: `sql/01_schema.sql` (criado automaticamente pelo coletor) e `sql/02_consultas.sql` (análises).
  Grão: 1 snapshot por versão (data/hora TSE) de cada arquivo; só grava quando o TSE atualiza.
  Conexão: Windows auth; instância tentada em ordem `localhost`, `localhost\SQLEXPRESS`,
  `(localdb)\MSSQLLocalDB`. Para outra: `$env:SQLSERVER_SERVER = "MINHAMAQUINA\INSTANCIA"`.

## Fonte e códigos
- `resultados.tse.jus.br/oficial/ele2026/{6257|6259}/dados/{uf}/{uf}[mun]-c{cargo}-e{ele}-u.json`
  (6257 federal/Presidente, 6259 estadual; cargos 1 Pres, 3 Gov, 5 Sen, 6 Dep. Fed., 7 Dep. Est., 8 Distrital)
- Municípios: `.../config/mun-e{ele}-cm.json` (código TSE ↔ IBGE pelo campo `cdi` ou, se faltar, por nome).
- Limitações: votos por partido = soma dos nominais (legenda não incluída); cadeiras proporcionais
  só contam quando o TSE marca o candidato como eleito.

## Mapas e identidade visual (`assets/`, `static/`)
- Malhas municipais e estaduais embarcadas em `assets/geo` (base IBGE via tbrugz/geodata-br), simplificadas
  e com orientação corrigida para o plotly. 5.564 municípios: os 6 criados depois da malha aparecem sem polígono.
- `static/topojson`: arquivos base do plotly servidos localmente (mapas não dependem do cdn.plot.ly).
- Bandeiras: bgeneto/bandeiras-br · Bandeira do Brasil: lipis/flag-icons (MIT)
- Logos dos partidos e Brasão: paulohpssantos/logoPartidos (marcas dos respectivos partidos; uso acadêmico).
- Fotos: servidas pelo TSE; se não carregarem, o cartão mostra as iniciais na cor do partido.

## Autoria

Eduardo Cândido, Cientista de Dados.
