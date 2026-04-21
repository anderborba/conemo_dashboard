# Fase C1 — Minuta executiva para o Agente Executor (abertura formal registrada no clone oficial)

**Data de registro:** 2026-04-06  
**Última atualização:** 2026-04-07 — encerramento pós-merge registrado na `main`  
**Status:** ✅ Fase C1 encerrada — PR #1 revisado, aprovado e incorporado à `main`; P0/P1/P2 integrados à versão principal do repositório  
**Modo principal:** Tipo F — dashboard, relatórios e exportação  
**Sequência secundária:** Tipo G — auditoria e reconciliação; Tipo H — documentação e handoff  
**Branch da fase:** `feat/dashboard-fase-c1-mvp-operacional`  
**Clone oficial utilizado:** `/Users/ricardoceneviva/Library/CloudStorage/GoogleDrive-ceneviva@gmail.com/.shortcut-targets-by-id/15FNAS0mfcKcdeIjRa8PNbvlMpwoj1tu6/proj_conemo/_clone_oficial_conemo`  
**Remoto validado:** `https://github.com/conemo-project/conemo.git`

> Esta minuta deriva do plano operacional aprovado e deve ser executada com estrita aderência ao `RULES.md`, ao `Workflow-Projeto.md` e à base executiva canônica do dashboard. O projeto exige fluxo curto, auditável, reprodutível e sem avanço automático para nova fase. Toda entrega substancial deve deixar trilha inspecionável por outro revisor.

## Registro de abertura formal no clone oficial

- abertura executada no clone oficial após integração mínima do conteúdo local validado;
- integração restrita a `README.md`, documentos canônicos em `Docs/`, `Code/README.md` e `Code/PY/dashboard_conemo.py`;
- nenhuma implementação funcional do dashboard foi iniciada nesta etapa;
- `Code/PY/dashboard_conemo.py` foi apenas integrado ao clone oficial, sem edição.

## Registro de execução — Etapa 2: P0

**Commit técnico:** `5ce299d`  
**Mensagem:** `feat: prioriza navegacao UBS-gestao, exibe timestamp cache e adiciona botao atualizar (P0)`  
**Arquivo editado:** `Code/PY/dashboard_conemo.py`  
**Validação:** `ast.parse()` confirmou sintaxe Python válida antes do commit

### P0.1 — Timestamp do cache

- adicionada a função `get_cache_timestamp()` que lê `os.path.getmtime(PARQUET_PATH)`;
- resultado exibido na sidebar com `st.sidebar.info()` e label `📅 Dados atualizados em:`;
- rótulo de modo `*Modo: cache local*` exibido abaixo para transparência operacional;
- tratamento de `FileNotFoundError` e exceção genérica incluído (sem propagação).

### P0.2 — Navegação reorientada para UBS/gestão

- `st.sidebar.radio` passou de `["📊 Estatísticas por UBS", "👤 Estatísticas por ID"]` para `["📊 Estatísticas por UBS"]`;
- visão individual por participante preservada integralmente no código;
- lógica individual migrada para `st.expander("👤 Consulta individual por participante (visão auxiliar)")` dentro da página de UBS;
- nenhuma análise ou dado da visão individual foi removido.

### P0.3 — Botão 🔄 Atualizar dados

- adicionado `st.sidebar.button("🔄 Atualizar dados")` na sidebar;
- ação: `st.cache_data.clear()` + `st.rerun()`;
- botão mantido visível conforme decisão vinculante da coordenação (2026-04-06);
- operação condicionada à credencial BigQuery em modo online (não bloqueadora no modo cache/local atual).

### Status após Etapa 2

| Item | Status |
|------|--------|
| P0.1 — Timestamp cache | ✅ Implementado |
| P0.2 — Nav. UBS/gestão | ✅ Implementado |
| P0.3 — Botão 🔄 | ✅ Implementado |
| P1 — Filtro cidade | ⬜ Pendente de autorização |
| P2 — Label versão MVP | ⬜ Pendente de autorização |
| Push para remoto | ⬜ Pendente |
| PR | ⬜ Pendente |

## Registro de execução — Etapa 3: P1

**Commit técnico:** `86fc1e2`  
**Mensagem:** `fix: corrige filtro de cidade e normaliza duplicidades`  
**Arquivo editado:** `Code/PY/dashboard_conemo.py`  
**Localização da mudança:** função `load_data()`, bloco de normalização e filtragem de `ubs_city`  
**Validação pré-commit:** `ast.parse()` confirmou sintaxe Python válida; `git diff` confirmou alteração cirúrgica (somente o bloco de normalização)

### P1.1 — Cidade vazia no filtro

**Problema identificado:** o código anterior filtrava apenas `"Fake City"` e `"N/A"`, mas não tratava:
- strings vazias `""` resultantes de `str.strip()` sobre valores whitespace-only na fonte;
- valores `NaN`/`None` (o `dropna()` no filtro UI era a única defesa, insuficiente para garantia na fonte).

**Correção implementada:** substituição do filtro simples por condição composta e explícita:
```python
_CIDADES_INVALIDAS = {"Fake City", "N/A", ""}
df = df[
    df["ubs_city"].notna()
    & (~df["ubs_city"].isin(_CIDADES_INVALIDAS))
]
```
Nenhuma cidade legítima é afetada: a condição é auditável e qualquer exclusão inesperada seria identificável na constante `_CIDADES_INVALIDAS`.

### P1.2 — Normalização de duplicidade por caixa

**Problema identificado:** `ubs_city` recebia apenas `str.strip()`, sem normalização de caixa. Variantes como `"são paulo"`, `"SÃO PAULO"` e `"São Paulo"` apareciam como três entradas distintas no multiselect.

**Regra adotada: strip → Title Case.**
```python
df["ubs_city"] = df["ubs_city"].str.strip().str.title()
```
- Simples, legível e consistente com nomes de cidades em português.
- `ubs_name` permanece em maiúsculas (padrão P0), preservando a coerência entre os dois filtros.

### P1.3 — UBS como pivô principal (verificação)

A arquitetura de filtro em cascata não foi alterada: cidade pré-filtra o conjunto de UBS, e UBS é o pivô operacional do dashboard. A correção de P1 não transformou cidade em eixo principal.

### Verificações realizadas

| Critério | Verificação |
|---|---|
| Cidade vazia no filtro | Removida via `notna()` + `isin(_CIDADES_INVALIDAS)` que inclui `""` |
| Duplicidades por caixa | Eliminadas via `.str.title()` aplicado em `load_data()` |
| Normalização legível | Regra `strip → Title Case` documentada no código com comentário |
| UBS como pivô | Cascata cidade → UBS preservada; `ubs_name` em maiúsculas intocado |
| P0 preservado — timestamp | `get_cache_timestamp()` e exibição na sidebar não foram alterados |
| P0 preservado — navegação | `st.sidebar.radio(["📊 Estatísticas por UBS"])` não foi alterado |
| P0 preservado — botão 🔄 | `st.sidebar.button("🔄 Atualizar dados")` não foi alterado |
| P2 não iniciado | Confirmado: nenhuma alteração fora do escopo de P1 |
| Sintaxe Python | `ast.parse()` retornou OK antes do commit |
| Diff cirúrgico | `git diff` confirmou: somente bloco de normalização modificado |

### Status após Etapa 3

| Item | Status |
|------|--------|
| P0.1 — Timestamp cache | ✅ Implementado (`5ce299d`) |
| P0.2 — Nav. UBS/gestão | ✅ Implementado (`5ce299d`) |
| P0.3 — Botão 🔄 | ✅ Implementado (`5ce299d`) |
| P1.1 — Filtro cidade vazia | ✅ Implementado (`86fc1e2`) |
| P1.2 — Normalização de caixa | ✅ Implementado (`86fc1e2`) |
| P1.3 — UBS como pivô | ✅ Verificado (arquitetura preservada) |
| P2 — Label versão MVP | ✅ Implementado (`1009fda`) |
| Push para remoto | ⬜ Pendente |
| PR | ⬜ Pendente |

## Registro de execução — Etapa 4: P2

**Commit técnico:** `1009fda`  
**Mensagem:** `feat: adiciona label discreto de versao MVP`  
**Arquivo editado:** `Code/PY/dashboard_conemo.py`  
**Localização da mudança:** bloco da sidebar, após `st.sidebar.radio` (navegação P0.2) e antes dos `Helpers`  
**Validação pré-commit:** `ast.parse()` confirmou sintaxe Python válida; `git diff` confirmou adição cirúrgica (10 linhas, 0 remoções)

### P2 — Label discreto de versão MVP

**Implementação adotada:**
```python
st.sidebar.markdown("---")
st.sidebar.caption("Dashboard CONEMO — Versão MVP")
```

**Justificativa da escolha:**
- `st.sidebar.caption()` renderiza texto em fonte pequena e cor muda (estilo Streamlit nativo de texto secundário) — o elemento menos intrusivo disponível;
- posicionado no rodapé da sidebar, após navegação e botão, em área secundária da interface;
- não altera nenhum elemento da área principal (página de UBS), nem da lógica de dados;
- nenhuma nova funcionalidade introduzida.

### Verificações realizadas

| Critério | Verificação |
|---|---|
| Label MVP visível | `st.sidebar.caption()` sempre visível na sidebar |
| Label discreto | `caption()` = menor tipografia disponível no Streamlit; área secundária |
| Não interfere na navegação | Inserido *após* o `radio`; `page` não foi alterado |
| P0 — timestamp | `get_cache_timestamp()` e exibição na sidebar não aparecem no diff |
| P0 — navegação UBS | `st.sidebar.radio(["📊 Estatísticas por UBS"])` não foi alterado |
| P0 — botão 🔄 | `st.sidebar.button("🔄 Atualizar dados")` não foi alterado |
| P1 — cidade vazia | `notna()` + `_CIDADES_INVALIDAS` em `load_data()` não foram alterados |
| P1 — normalização | `.str.title()` em `ubs_city` não foi alterado |
| P1 — UBS como pivô | Cascata de filtros não foi alterada |
| Sintaxe Python | `ast.parse()` retornou OK |
| Diff cirúrgico | `git diff`: 10 linhas adicionadas, 0 removidas, 1 bloco |
| Nenhuma ampliação de escopo | Somente label textual estático; sem nova lógica |

### Status após Etapa 4

| Item | Status |
|------|--------|
| P0.1 — Timestamp cache | ✅ Implementado (`5ce299d`) |
| P0.2 — Nav. UBS/gestão | ✅ Implementado (`5ce299d`) |
| P0.3 — Botão 🔄 | ✅ Implementado (`5ce299d`) |
| P1.1 — Filtro cidade vazia | ✅ Implementado (`86fc1e2`) |
| P1.2 — Normalização de caixa | ✅ Implementado (`86fc1e2`) |
| P1.3 — UBS como pivô | ✅ Verificado (arquitetura preservada) |
| P2 — Label versão MVP | ✅ Implementado (`1009fda`) |
| Push para remoto | ⬜ Pendente |
| PR | ⬜ Pendente |

---

## 1. Objetivo executivo da fase

Implementar a rodada inicial de melhoria do dashboard, já aprovada, como **início formal do ciclo contínuo de desenvolvimento** do dashboard, com **GitHub obrigatório**, preservando integralmente o escopo funcional P0/P1/P2 já validado:

* **P0**

  * exibir `timestamp` da última atualização do cache;
  * reorganizar a navegação principal para priorizar UBS/gestão;
  * manter o botão `🔄`;
* **P1**

  * corrigir cidade vazia no filtro;
  * normalizar duplicidade de cidade por caixa/variação;
* **P2**

  * incluir label discreto de versão MVP, apenas se não ampliar escopo.

## 2. Fontes canônicas obrigatórias

O executor deve trabalhar com esta hierarquia:

1. instruções explícitas do professor;
2. `Docs/Plano-implementacao-dashboard.md` final;
3. `Docs/RULES.md`;
4. `Docs/Workflow-Projeto.md`;
5. plano operacional aprovado desta fase.

## 3. Arquivos autorizados

**Arquivo técnico principal**

* `Code/PY/dashboard_conemo.py`

**Arquivos documentais complementares, se necessários**

* `Docs/fase-dashboard-executiva-1.md`
* `README.md`
* `Code/README.md`
* `Docs/README.md`

Nenhum outro arquivo deve ser alterado sem nova autorização. Isso é consistente com o workflow do projeto: executar apenas a fase aprovada, nos arquivos autorizados, sem abrir nova frente.

## 4. Escopo e fora de escopo

### Dentro do escopo

* ajustes locais no dashboard para P0/P1/P2;
* preservação das exportações CSV agregadas;
* criação de branch;
* commits pequenos e rastreáveis;
* abertura de PR;
* revisão antes do merge;
* registro documental mínimo da fase.

### Fora do escopo

* credenciais, segredos, BigQuery, integrações externas e deploy;
* refatoração ampla;
* reestruturação do repositório;
* mudança de regras clínicas ou motor de alertas;
* promoção da visão individual a eixo principal da navegação;
* CI/CD ou novas automações de governança.

---

# 5. Sequência exata de execução no GitHub

## Etapa 0 — Preparação local

Antes de editar qualquer arquivo:

1. atualizar `main` local com a versão corrente do repositório;
2. confirmar que a base a ser usada corresponde ao estado aprovado da Fase C;
3. confirmar que apenas `Code/PY/dashboard_conemo.py` será alterado tecnicamente, salvo documentação mínima autorizada.

## Etapa 1 — Criar branch da fase

Nome recomendado da branch:

```bash
git checkout main
git pull origin main
git checkout -b feat/dashboard-fase-c1-mvp-operacional
```

**Regra:** não trabalhar diretamente na `main`.

## Etapa 2 — Registrar abertura documental mínima

Se for necessário deixar rastro da abertura da fase, criar ou atualizar:

* `Docs/fase-dashboard-executiva-1.md`

Conteúdo mínimo:

* objetivo da fase;
* backlog P0/P1/P2;
* arquivo principal autorizado;
* branch utilizada;
* itens fora de escopo;
* critérios de validação.

**Commit recomendado**

```bash
git add Docs/fase-dashboard-executiva-1.md
git commit -m "docs: abre fase executiva C1 do dashboard"
```

Esse passo é desejável porque o projeto exige trilha documental e handoff revisável.

## Etapa 3 — Implementar P0

Editar `Code/PY/dashboard_conemo.py` para:

* exibir `timestamp` da última atualização do cache em posição visível;
* reorganizar navegação principal para priorizar UBS/gestão;
* remover a visão individual da navegação principal, sem apagar sua lógica subjacente;
* preservar o botão `🔄`.

**Commit recomendado**

```bash
git add Code/PY/dashboard_conemo.py
git commit -m "feat: prioriza navegacao UBS gestao e exibe timestamp do cache"
```

## Etapa 4 — Implementar P1

Ainda em `Code/PY/dashboard_conemo.py`:

* corrigir cidade vazia no filtro;
* normalizar duplicidade de cidade por caixa/variação;
* garantir UBS como pivô funcional do filtro.

**Commit recomendado**

```bash
git add Code/PY/dashboard_conemo.py
git commit -m "fix: corrige filtro de cidade e normaliza duplicidades"
```

## Etapa 5 — Implementar P2, se não ampliar escopo

Somente se não houver conflito com P0/P1:

* inserir label discreto de versão MVP.

**Commit recomendado**

```bash
git add Code/PY/dashboard_conemo.py
git commit -m "feat: adiciona label discreto de versao MVP"
```

Se P2 for adiado, registrar isso no documento da fase e não criar commit artificial.

## Etapa 6 — Atualizar documentação final da fase

Atualizar `Docs/fase-dashboard-executiva-1.md` com:

* arquivos modificados;
* conteúdo implementado;
* testes/verificações realizados;
* decisão sobre P2;
* pendências;
* pontos para decisão humana;
* branch e commits principais.

**Commit recomendado**

```bash
git add Docs/fase-dashboard-executiva-1.md README.md Docs/README.md Code/README.md
git commit -m "docs: registra validacao e handoff da fase C1 do dashboard"
```

Só incluir `README.md`, `Docs/README.md` e `Code/README.md` se houver mudança factual que justifique atualização.

## Etapa 7 — Push da branch

```bash
git push -u origin feat/dashboard-fase-c1-mvp-operacional
```

## Etapa 8 — Abrir Pull Request

Abrir PR da branch:

`feat/dashboard-fase-c1-mvp-operacional` → `main`

### Título recomendado do PR

`Fase C1 do dashboard: MVP operacional com navegacao UBS/gestao`

### Corpo recomendado do PR

```text
## Contexto
Implementa a Fase C1 do dashboard CONEMO conforme plano operacional aprovado.

## Escopo implementado
- P0: timestamp do cache, navegacao UBS/gestao, preservacao do botao 🔄
- P1: correcao de cidade vazia e normalizacao de duplicidades
- P2: [implementado ou adiado, informar]

## Arquivos alterados
- Code/PY/dashboard_conemo.py
- Docs/fase-dashboard-executiva-1.md
- [outros, se houver]

## Fora de escopo preservado
- sem alteracao de credenciais
- sem integracao externa
- sem deploy
- sem refatoracao ampla
- sem mudanca de regras clinicas

## Validacao realizada
- timestamp visivel
- navegacao principal orientada a UBS/gestao
- visao individual fora da navegacao principal
- botao 🔄 preservado
- filtro UBS mantido como pivo
- cidade vazia removida
- duplicidades de cidade normalizadas
- exportacoes CSV agregadas preservadas

## Pendencias
- [listar ou informar nenhuma]

## Pontos para revisao
- coerencia funcional da navegacao
- clareza do timestamp
- preservacao do escopo aprovado
```

---

# 6. Checklist de revisão do PR

O revisor deve verificar, no mínimo:

## Escopo

* a fase entregou exatamente P0/P1/P2, sem expansão indevida;
* nenhum item fora de escopo foi tocado.

## Funcionalidade do MVP

* a navegação principal está orientada a UBS/gestão;
* a visão individual saiu da navegação principal;
* o botão `🔄` permanece visível;
* o `timestamp` do cache está visível e compreensível;
* o filtro UBS continua sendo o pivô principal;
* a cidade vazia desapareceu;
* as duplicidades por caixa/variação foram normalizadas;
* as exportações CSV agregadas seguem preservadas.

## Segurança e governança

* não houve alteração em credencial, integração externa ou deploy;
* não houve mudança de regra clínica ou lógica de alertas;
* não houve exposição indevida de PII.

## Qualidade técnica

* os commits estão pequenos e semanticamente claros;
* o código ficou legível e auditável;
* a lógica implementada está explicada em documentação suficiente para revisão humana;
* o PR descreve corretamente o que foi feito e o que não foi feito.

## Handoff

* `Docs/fase-dashboard-executiva-1.md` registra:

  * o que foi feito;
  * por que foi feito;
  * quais fontes foram usadas;
  * o que foi validado;
  * o que ficou pendente;
  * o que depende de aprovação humana.

---

# 7. Critério para aprovação do PR

O PR só pode ser aprovado se houver evidência explícita de que:

1. a implementação respeitou o plano aprovado;
2. os critérios funcionais do Passo 4 foram cumpridos;
3. a trilha GitHub está completa:

   * branch própria;
   * commits rastreáveis;
   * PR com descrição adequada;
   * revisão anterior ao merge.

## 8. Regra de merge

Depois da revisão:

* corrigir eventuais comentários;
* registrar aprovação;
* só então fazer merge na `main`.

Como a proteção automática da `main` ainda pode não estar tecnicamente ativa, o executor e o mantenedor devem tratar essa revisão como **obrigatória por disciplina operacional**, não como mera formalidade. Isso é coerente com o plano aprovado e com a exigência de fluxos simples, auditáveis e reprodutíveis.

## 9. Relatório de conclusão esperado do executor

Ao final, o executor deve entregar um relatório curto com:

* branch usada;
* arquivos criados ou modificados;
* commits principais;
* link ou identificação do PR;
* conteúdo principal implementado;
* testes/verificações realizados;
* pendências;
* decisão sobre P2;
* confirmação explícita de que não avançou para nova fase.

---

## Registro operacional

- Minuta registrada em 2026-04-06.
- Etapa 1 solicitada em 2026-04-06 (abertura formal da fase) foi iniciada com leitura das fontes obrigatórias.
- Bloqueio técnico encontrado: pasta de trabalho atual sem diretório `.git` (erro: `fatal: not a git repository (or any of the parent directories): .git`), impedindo `git checkout main`, criação de branch e commit local.
- Nenhuma implementação funcional foi iniciada em `Code/PY/dashboard_conemo.py`.
- Próxima ação: assim que o repositório Git local estiver disponível nesta pasta, repetir apenas a Etapa 1 (`main` atualizado + branch `feat/dashboard-fase-c1-mvp-operacional` + commit `docs: abre fase executiva C1 do dashboard`).

---

## Consolidação final da Fase C1 — 2026-04-06

### Fechamento formal

A Fase C1 do dashboard CONEMO foi concluída integralmente. Todas as entregas de P0, P1 e P2 foram implementadas, validadas e commitadas na branch `feat/dashboard-fase-c1-mvp-operacional`. A branch foi publicada em `origin`, revisada por humano e mergeada na `main` por meio do PR #1.

### Arquivo técnico principal modificado

| Arquivo | Motivo |
|---|---|
| `Code/PY/dashboard_conemo.py` | P0 + P1 + P2 — único arquivo técnico autorizado na fase |
| `Docs/fase-dashboard-executiva-1.md` | Registro vivo de execução da fase |

### Commits da fase (em ordem cronológica)

| Hash | Tipo | Descrição |
|---|---|---|
| `eefcbf2` | `docs` | Abre fase executiva C1 do dashboard |
| `5ce299d` | `feat` | P0: timestamp, navegação UBS, botão 🔄 |
| `497a8e3` | `docs` | Registra execução de P0 |
| `86fc1e2` | `fix` | P1: corrige filtro de cidade e normaliza duplicidades |
| `19f6988` | `docs` | Registra execução de P1 |
| `1009fda` | `feat` | P2: adiciona label discreto de versão MVP |
| `cbd0ddf` | `docs` | Registra execução de P2 |
| `(este commit)` | `docs` | Consolida fechamento da Fase C1 |

### Verificações realizadas ao longo da fase

- `ast.parse()` executado antes de cada commit técnico — sintaxe Python válida em todos;
- `git diff` inspecionado antes de cada commit — diffs cirúrgicos confirmados;
- P0 verificado como intacto nos diffs de P1 e P2;
- P1 verificado como intacto no diff de P2;
- inspeção visual do dashboard aprovada pelo professor:
  - timestamp visível na sidebar;
  - label de versão MVP visível e discreto;
  - navegação orientada a UBS/gestão.

### Observações validadas

- pasta `Data/PARQUET` do workspace local copiada para dentro do clone oficial para execução local — necessária para rodar o dashboard em modo cache/local;
- inspeção visual realizada e aprovada;
- label `📅 Dados atualizados em:` aprovado;
- label `Dashboard CONEMO — Versão MVP` aprovado.

### Confirmações de escopo

| Item | Status |
|---|---|
| Alteração de credenciais | ❌ Não realizada |
| Integração externa nova | ❌ Não realizada |
| Deploy | ❌ Não realizado |
| Mudança de regra clínica | ❌ Não realizada |
| Refatoração ampla | ❌ Não realizada |
| Merge em `main` | ✅ Realizado via PR #1 |
| Push da branch | ✅ Realizado |
| Pull Request aberto | ✅ Realizado e mergeado |

### Pendências remanescentes

- **BigQuery**: o botão `🔄` opera em modo cache/local; a integração com credencial Google/BigQuery é pendência de fase futura, conforme decisão vinculante da coordenação;
- **Dados**: o arquivo Parquet local (`Data/PARQUET/`) não faz parte do repositório Git — cópia manual necessária para execução local do clone;
- **Priorização futura**: quaisquer próximas decisões dependem de priorização formal da coordenação para a fase seguinte.

### Registro pós-merge

- PR da Fase C1 revisado, aprovado e incorporado à `main`;
- número do PR mergeado: **#1**;
- data do merge registrada no GitHub: **2026-04-07T01:19:23Z**;
- as entregas P0, P1 e P2 passam a integrar formalmente a versão principal do repositório.

## Nota curta de encerramento

Fase C1 encerrada. O PR da fase foi revisado, aprovado e incorporado à `main`. Com isso, as entregas P0, P1 e P2 do dashboard CONEMO passam a integrar formalmente a versão principal do repositório. As próximas decisões ficam condicionadas à priorização da coordenação para a fase seguinte.
