# Dengue × Clima — Global Solution 2026.2 (CitizenTech · Data Science)

**Pergunta:** o clima (temperatura, chuva, umidade) antecipa a explosão de casos de dengue?
Base de dados para uma CitizenTech de **alerta precoce de dengue por município**.

Cruza as notificações de **dengue do SINAN/DATASUS** (2014–2026) com os dados das **estações
automáticas do INMET** e a **população SVS/IBGE**, em um ETL de 3 camadas que termina em um
modelo dimensional (fatos e dimensões) pronto para o **Power BI**.

## Estrutura

```
gs_fase7/
├── notebooks/
│   ├── 01_leitura/                       # CAMADA 1 — download + leitura (sem regra de negócio)
│   │   ├── 01_leitura_datasus.ipynb
│   │   └── 02_leitura_inmet.ipynb
│   ├── 02_tratamento/                    # CAMADA 2 — limpeza, padronização, integração
│   │   ├── 01_tratamento_datasus.ipynb
│   │   ├── 02_tratamento_inmet.ipynb
│   │   └── 03_integracao_dengue_clima.ipynb
│   └── 03_disponibilizacao/              # CAMADA 3 — camada semântica, análises, hipóteses, modelo, métricas
│       └── 01_camada_semantica_e_analises.ipynb   ← notebook principal
├── data/
│   ├── raw/                              # arquivos originais (TabNet CSV, INMET zip) + catálogo e manifesto
│   ├── 01_leitura/                       # Parquet com o conteúdo original, tipado e consolidado
│   ├── 02_tratamento/                    # Parquet limpo, formato longo, integrado (município × semana)
│   └── 03_disponibilizacao/              # CSVs finais para o Power BI (fatos, dimensões, métricas, dicionário)
├── reports/figures/                      # gráficos exportados (PNG) para slides e pitch
├── src/                                  # código reutilizado pelos notebooks
│   ├── config.py                         # caminhos das camadas e parâmetros globais
│   ├── tabnet.py                         # cliente do TabNet (formulário, POST, parsing)
│   ├── download_datasus.py               # catálogo + 29 consultas focadas
│   ├── download_inmet.py                 # zips anuais do INMET
│   ├── leitura_inmet.py                  # zip -> Parquet horário
│   ├── epi.py                            # calendário de semanas epidemiológicas
│   └── viz.py                            # estilo dos gráficos (paleta acessível, formato pt-BR)
├── docs/                                 # material de apoio da FIAP (local, não versionado)
└── requirements.txt
```

## Como executar

```bash
uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -r requirements.txt
# (ou: python -m venv .venv && .venv/bin/pip install -r requirements.txt)
```

Rode os notebooks **na ordem** (01 → 02 → 03). Tempo aproximado com os dados já baixados: ~6 min.
Na primeira execução, o download leva ~15 min (TabNet) + ~5 min (INMET, 1,3 GB).

```bash
cd notebooks/01_leitura && ../../.venv/bin/jupyter nbconvert --to notebook --execute --inplace *.ipynb
cd ../02_tratamento    && ../../.venv/bin/jupyter nbconvert --to notebook --execute --inplace 01_*.ipynb 02_*.ipynb 03_*.ipynb
cd ../03_disponibilizacao && ../../.venv/bin/jupyter nbconvert --to notebook --execute --inplace *.ipynb
```

Downloads são **idempotentes** (o que já existe é pulado). Se o TabNet estiver fora do ar, a leitura
segue com o catálogo salvo.

## As 3 camadas

| Camada | O que faz | Regras principais |
|---|---|---|
| **1. Leitura** | baixa as fontes e grava em Parquet sem alterar conteúdo | DATASUS lido como texto (preserva `-`, `Total`); INMET: metadados da estação → colunas, decimal com vírgula, `-9999` → ausente, layout pré/pós-2019 unificado. Totais conferidos com o manifesto. |
| **2. Tratamento** | limpa, tipa, padroniza e integra | `-` → 0; formato longo; semanas omitidas pelo TabNet → 0 (ou descartadas se futuras); categorias "ignorado" unificadas; QC de limites físicos no INMET; dia válido com ≥ 18 h; semana epidemiológica; estação → município pelo nome (96,5% casadas); incidência por 100 mil hab. |
| **3. Disponibilização** | camada semântica + análises | dimensões e fatos em CSV; 9 hipóteses testadas; modelo de alerta precoce (8 semanas); métricas e dicionário de dados |

## Fontes

| Fonte | Conteúdo | Link |
|---|---|---|
| SINAN/DATASUS (TabNet) | casos prováveis de dengue, 2014–2026 (2026 preliminar), por local de residência | [denguebbr.def](https://tabnet.datasus.gov.br/cgi/deftohtm.exe?sinannet/cnv/denguebbr.def) |
| SVS/IBGE (TabNet) | população residente por município, 2014–2025 | [popsvs2024br.def](https://tabnet.datasus.gov.br/cgi/deftohtm.exe?ibge/cnv/popsvs2024br.def) |
| INMET | dados horários das estações automáticas, 2014–2026 | [dadoshistoricos](https://portal.inmet.gov.br/dadoshistoricos) |

### Coleta do TabNet (29 consultas)
O formulário de dengue tem 47 linhas × 34 colunas × 13 anos × 57 filtros. Todas as opções ficam
registradas em `data/raw/datasus/catalogo/` (dicionário de dados), mas só são baixadas as tabulações
que respondem à pergunta:

| Conjunto | Linha × Coluna | Para quê |
|---|---|---|
| 1 `01_municipio_semana/` | município de residência × semana epidemiológica (1 arquivo/ano) | núcleo do cruzamento com o INMET |
| 2 `02_contexto_anual/` | região, UF, capital, município × ano; semana × ano | dimensionamento e conferências |
| 3 `03_perfil_gravidade/` | ano × faixa etária, sexo, raça, classificação, evolução, hospitalização, sorotipo; faixa etária × evolução e × hospitalização | persona e fatores não climáticos |
| 4 `04_desigualdade/` | municípios em extrema pobreza × ano | recorte de desigualdade (ODS 10) |
| 5 `05_populacao/` | população por município × ano | denominador da incidência |

## Saídas para o Power BI (`data/03_disponibilizacao/`)

CSV com separador `;`, decimal `,`, UTF-8 com BOM, datas `AAAA-MM-DD`. Ao importar, use a localidade
**Português (Brasil)**.

| Tipo | Tabela | Grão |
|---|---|---|
| Dimensão | `dim_tempo_semana` | semana epidemiológica (`id_semana` = AAAASS) |
| Dimensão | `dim_ano`, `dim_uf` | ano; UF |
| Dimensão | `dim_municipio` | município (código IBGE 6 dígitos) |
| Dimensão | `dim_estacao` | estação do INMET |
| Fato | `fato_dengue_semanal` | município × semana (só semanas com casos) |
| Fato | `fato_dengue_anual_municipio` | município × ano (casos, população, incidência, nível MS, pico) |
| Fato | `fato_clima_semanal_estacao` | estação × semana |
| Fato | `fato_dengue_clima_semanal` | município com estação × semana, com clima, faixas de risco e **nível de alerta** |
| Fato | `fato_perfil_anual` | ano × dimensão × categoria |
| Fato | `fato_gravidade_faixa_etaria` | faixa etária (letalidade, hospitalização) |
| Métrica | `metricas_kpis`, `resultados_hipoteses`, `metricas_defasagem_clima`, `metricas_risco_temperatura`, `metricas_risco_chuva`, `metricas_modelo_alerta`, `metricas_niveis_alerta` | indicadores e resultados das análises |
| Metadado | `dicionario_dados` | descrição de todas as colunas |

**Relacionamentos (1 → \*):** `dim_tempo_semana[id_semana]` → fatos semanais · `dim_municipio[cod_municipio]` →
fatos municipais · `dim_estacao[codigo_wmo]` → `fato_clima_semanal_estacao` · `dim_uf[sigla_uf]` → `dim_municipio` ·
`dim_ano[ano]` → `fato_dengue_anual_municipio`, `fato_perfil_anual`.

**Medida de incidência:** `DIVIDE(SUM(fato_dengue_anual_municipio[casos]), SUM(fato_dengue_anual_municipio[populacao])) * 100000`.

## Limitações
- Casos **notificados** (subnotificação varia por região); 2026 preliminar; as 4 últimas semanas são excluídas das análises (atraso de notificação).
- Estações do INMET cobrem 651 municípios (~43% da população); Norte sub-representado.
- Sorotipo (98%), hospitalização (34%) e raça/cor (22%) têm muitos campos em branco.
- Correlação não implica causalidade. Todos os dados são agregados e públicos (sem dados pessoais — LGPD).
