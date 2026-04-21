# Dashboard CONEMO

**Status:** Versão final canônica — Fase B formalmente encerrada, 2026-04-06  
**Base executiva:** este documento é a referência única para a próxima fase técnica do dashboard CONEMO.

> **Decisão vinculante de coordenação (2026-04-06):**
> 1. o botão `🔄` permanece no dashboard, sem desabilitação nem remoção;
> 2. no curto prazo, a operação do botão é temporariamente condicionada à credencial Google/BigQuery;
> 3. o botão convive com o modo cache/local no estado atual do dashboard;
> 4. no longo prazo, permanece componente formal da arquitetura de atualização via BigQuery;
> 5. a dependência temporária de credencial não deve ser tratada como exclusão funcional.

> **Encerramento da Fase B (auditoria final, 2026-04-06):** a revisão final documental foi aprovada e encerrada. Este plano permanece como base executiva vigente para a preparação da Fase C.

\vspace{0.5cm}

### Fluxo descritivo

O fluxo descrito é o seguinte. O paciente preenche um formulário web com dados pessoais e os instrumentos PHQ-9, GAD-7, IGI e SRAP. A elegibilidade é decidida a partir de pontos de corte em PHQ e ou GAD. Se elegível, o sistema exibe o link de download do aplicativo e o backend cria automaticamente a jornada de depressão, a de ansiedade, ou ambas. Após o login com a mesma conta, o paciente acessa as jornadas, recebe sessões liberadas em intervalos de 1 a 3 dias, registra progresso no backend e passa por novas coletas via formulário web e baseline no aplicativo. O documento também pede integração entre participante, UBS, dados sociodemográficos, formulários, sessões, atividades e chatbot, além de funil, exportação em CSV, páginas por UBS e visões distintas para clínica, pesquisa e gestão. A documentação não informa os pontos de corte numéricos. Por isso, o plano abaixo trata elegibilidade e piora clínica como regras parametrizáveis. 

Do ponto de vista clínico, faz sentido modelar PHQ-9, GAD-7 e IGI como séries temporais de escores por participante, porque são instrumentos breves e repetíveis. Para o IGI, adoto a convenção usual do Índice de Gravidade de Insônia, equivalente ao ISI, inclusive com uso validado em ambiente web. Para risco de suicídio, recomendo que o dashboard use o SRAP como protocolo primário de alerta, porque o item suicidário isolado do PHQ-9 não substitui avaliação estruturada de risco, e diretrizes clínicas recomendam avaliação específica e formulação de risco.

\vspace{0.25cm}


## Plano de Implementação do Dashboard CONEMO (V.2.0.0 — versão final canônica, Fase B, 2026-04-06)

A seguir está a versão revisada do Plano de Implementação do Dashboard CONEMO. 

### 1. Objetivo funcional

O dashboard deve operar em três planos funcionais: nível do usuário, nível da UBS e nível de gestão do projeto. Na sua primeira versão visual (MVP), o eixo central é o plano **agregado e operacional**.

No nível da UBS, o dashboard consolida casuística, funil operacional, adesão, progresso das jornadas, atraso, abandono e indicadores clínicos agregados por unidade e território. No nível de gestão do projeto, monitora cobertura, funil completo, qualidade dos dados, desempenho operacional e heterogeneidade entre UBS.

O plano individual do usuário — acompanhamento de adesão, progresso terapêutico, reavaliações clínicas e alertas por participante — permanece estruturalmente obrigatório no banco analítico e no backend. No entanto, a visão individual não constitui o eixo principal da primeira versão visual do dashboard. A decisão de não priorizar o nível individual como eixo do MVP visual foi validada pela coordenação e não elimina a importância analítica desse plano no banco de dados.

Essa organização decorre diretamente das perguntas científicas, das perguntas de uso e das funcionalidades descritas no documento de especificação.

### 2. Arquitetura de processamento de dados para CSV

Proponho uma arquitetura em três camadas.

Na camada bruta, cada CSV recebido entra sem transformação estrutural. Cada arquivo recebe `load_id`, `file_name`, `source_system`, `import_timestamp`, `hash_checksum` e `schema_version`. Isso preserva rastreabilidade e permite reprocessamento.

Na camada curada, os CSVs são padronizados. Nessa etapa entram validação de tipos, normalização de datas e horas, deduplicação, reconciliação de identificadores e padronização de chaves. Também ocorre a separação entre evento clínico, evento operacional e metadado. O identificador mestre deve ser `participant_id`, vinculado à conta usada no formulário web e no aplicativo. Essa camada precisa gerar tabelas consolidadas para participante, UBS, submissões de formulário, respostas por item, escores por instrumento, jornadas, sessões, atividades, notificações, chatbot e eventos operacionais transversais de monitoramento. O documento do dashboard pede integração entre participante, UBS, sociodemográficos, formulário web, atividade, sessão e chatbot, e os templates mostram regras de navegação, perguntas baseadas em respostas anteriores, tarefas diárias e feedbacks.    

Na camada analítica, o sistema publica data marts para consumo do dashboard. Sugiro cinco marts principais. `mart_user_timeline`, `mart_user_clinical`, `mart_ubs_monitoring`, `mart_project_management` e `mart_alerts`. Essa camada deve ser incremental, com atualização por lote curto, por exemplo a cada 15 minutos, e recálculo completo diário para auditoria.

### 3. Estrutura proposta do banco de dados

A modelagem deve ser relacional, orientada a eventos, com dimensões estáveis, fatos versionados e metadados explícitos de coleta.

As dimensões centrais continuam sendo `dim_participant`, `dim_ubs`, `dim_user_role`, `dim_instrument`, `dim_journey`, `dim_session`, `dim_alert_rule` e `dim_calendar`.

Os fatos centrais passam a ser organizados em quatro blocos analíticos, para refletir a coleta real do CONEMO.

O primeiro bloco é de rastreio web. Inclui `fact_screening_web`, `fact_item_response`, `fact_instrument_score` e `fact_eligibility_decision`.

O segundo bloco é de baseline no aplicativo. Inclui `fact_baseline_submission`, `fact_baseline_item_response`, `fact_medication_report` e `fact_participant_context`.

O terceiro bloco é de jornada terapêutica. Inclui `fact_journey_enrollment`, `fact_session_release`, `fact_session_start`, `fact_session_completion`, `fact_daily_task_assignment`, `fact_daily_task_response`, `fact_activity_plan`, `fact_activity_feedback`, `fact_chatbot_event` e `fact_notification_event`.

O quarto bloco é de eventos transversais de monitoramento operacional e suporte de engajamento. Inclui `fact_chatbot_event`, `fact_help_request`, `fact_operational_monitoring_event`, `fact_dropout_event`, `fact_adverse_event` e `fact_alert`.

Os quatro blocos permanecem separáveis para auditoria e governança, mas devem ser integráveis para análise transversal por participante, UBS, coorte e período.

Além disso, o banco precisa de tabelas de parametrização. Sugiro `cfg_eligibility_rules`, `cfg_worsening_rules`, `cfg_alert_routes`, `cfg_access_policies` e `cfg_instrument_versions`.

A principal correção estrutural desta versão é a inclusão de um subsistema de metadados de coleta. Ele deve registrar o desenho lógico dos formulários e das jornadas. Recomendo as seguintes tabelas. `meta_form_template`, `meta_form_question`, `meta_form_option`, `meta_form_branch_rule`, `meta_journey_template`, `meta_session_template`, `meta_step_template`, `meta_daily_task_template` e `meta_feedback_template`. Essa inclusão é obrigatória porque os JSONs usam `rules`, `goTo`, `basedSession`, `basedStep`, `daily`, `shift`, `dayStart`, `dayEnd`, `reorder`, `feedbacks` e múltiplos tipos de item. Sem essas tabelas, o sistema não conseguirá reconstruir o fluxo real de coleta nem medir abandono por pergunta, por passo ou por tarefa.   

### 4. Regras de negócio que devem entrar no núcleo do sistema

A primeira regra é a de elegibilidade. O sistema deve avaliar a submissão inicial do formulário web e gravar três campos separados. `eligibility_status`, `eligibility_reason` e `rule_version`. Isso evita perda de histórico quando o protocolo mudar.

A segunda regra é a de alocação terapêutica. Se o participante atingir critério em GAD-7, entra na jornada de ansiedade. Se atingir critério em PHQ-9, entra na jornada de depressão. Se atingir ambos, entra nas duas. Se não atingir, permanece como não elegível, mas deve continuar aparecendo no funil, porque o documento quer monitorar também quem iniciou e não avançou. 

A terceira regra é a de progressão da jornada. Cada sessão precisa de `release_at`, `due_at`, `started_at`, `completed_at` e `timeliness_status`. Contudo, nesta versão revisada, a progressão precisa diferenciar sessão, tarefa derivada da sessão e resposta à tarefa. Isso é indispensável porque a jornada GAD contém blocos diários com `dayStart`, `dayEnd`, `shift`, escalas de intensidade, itens binários de sintomas e exercícios semanais; e a jornada PHQ contém quizzes, escolhas de atividade, perguntas baseadas em sessão anterior e feedbacks posteriores.  

A quarta regra é a de reavaliação clínica. Cada nova coleta de PHQ, GAD e IGI deve gerar uma linha temporal por instrumento, com comparação contra baseline e contra a coleta imediatamente anterior. O sistema não deve sobrescrever escores. Deve versionar cada submissão com data e tipo, como o documento pede para `follow up` e `RA`. 

A quinta regra é a de manejo do S-RAP. O protocolo deve ser armazenado item a item, com estágio final calculado. Não deve ser tratado como um simples score contínuo. O banco deve guardar respostas sobre ideação, método, plano, meios, disponibilidade dos meios, decisão temporal e tentativa recente, além do estágio resultante. O alerta decorrente desse protocolo deve acionar trilha assistencial própria. Quando houver ideação atual, plano factível, acesso a meios ou tentativa recente, o sistema deve marcar o caso como prioritário para avaliação clínica estruturada. Guias do NIMH recomendam avaliação adicional, definição de disposição clínica e discussão de restrição de meios após rastreio positivo para risco de suicídio.  ([Instituto Nacional de Saúde Mental][1])

### 5. Motor de alertas imediatos

O motor de alertas permanece requisito obrigatório de backend e governança operacional, com três saídas: risco suicidário, piora clínica e engajamento operacional.

Para evitar ambiguidade de escopo, a implementação deve distinguir três níveis:

1. **Alerta existente no sistema/banco**: regras ativas, versão de regra, status e trilha de tratamento registrados em fatos e tabelas de configuração.
2. **Alerta disponível para consumo analítico**: dados consolidados para monitoramento por participante, UBS, coorte e período, com auditabilidade de disparo e evolução.
3. **Alerta exibido visualmente no dashboard**: decisão de camada de visualização. No MVP visual atual, a exibição detalhada de alertas não é requisito obrigatório.

No risco suicidário, o disparo continua condicionado às regras canônicas (S-RAP, item crítico suicidário e combinações operacionais definidas), com registro em `fact_alert` e campos de prioridade, regra acionada, estágio e status.

Na piora clínica, as regras permanecem parametrizadas em `cfg_worsening_rules`, incluindo variação de escore, mudança de faixa de gravidade e padrões de não adesão associados.

No engajamento operacional, o motor deve capturar ausência de atividade, atraso prolongado, não preenchimento de follow-up, pedidos de ajuda pendentes e abandono de jornada, com foco em eventos operacionais e interações do chatbot.

### 6. Estrutura dos indicadores por nível funcional

Nesta fase, a prioridade visual do dashboard é agregada e operacional, com foco principal em **UBS** e **gestão do projeto**.

No nível da UBS, os indicadores devem cobrir volume de participantes, elegibilidade, downloads, baseline, ativos, atrasados, desistentes, concluídos, distribuição de escores e eventos de monitoramento operacional por unidade e período.

No nível de gestão do projeto, o foco é coorte e operação: funil completo, cobertura por cidade e UBS, tempos médios entre etapas, consistência de dados, comparabilidade entre unidades e desempenho operacional de notificações e chatbot em termos descritivos.

O nível do usuário permanece relevante no banco e na camada analítica, mas não constitui o eixo principal da interface visual nesta etapa. A dupla linha do tempo por participante deve existir como requisito de modelagem e backend:

1. linha clínica (PHQ, GAD, IGI, S-RAP);
2. linha terapêutica-operacional (sessões, tarefas, notificações, interações do chatbot, pedidos de ajuda, atraso e abandono).

Essa duplicação é obrigatória para auditabilidade e interpretação analítica, sem obrigatoriedade de aparecer como componente visual explícito no MVP.

### 7. Controle de acesso e segurança

O controle de acesso deve ser por perfil, mantendo como princípio que o dashboard visual não expõe PII e não depende de identificação nominal de participante.

As equipes de UBS devem visualizar prioritariamente agregados operacionais da unidade e filas analíticas de monitoramento sem exposição nominal. A equipe de pesquisa pode acessar dados analíticos com permissões ampliadas conforme governança. A equipe de gestão/administração deve acessar agregados do projeto em nível global.

Toda exportação CSV deve ser auditada em tabela própria, com usuário, data, filtro aplicado e conjunto exportado, em linha com os requisitos de exportação e rastreabilidade.

O domínio de PII permanece obrigatório na arquitetura de dados, segregado do domínio analítico. Recomendo manter `pii_participant_identity`, `pii_participant_contact`, `pii_alternate_contact`, `pii_locator_contact`, `pii_consent_contact_permission` e `pii_access_log`. Nesse domínio ficam CPF, telefones, e-mail, endereço e contatos alternativos. O consumo analítico e de dashboard deve ocorrer por chaves substitutas, sem exibição de identificadores pessoais.

### 8. Entrega mínima viável

A entrega mínima viável está organizada em três camadas. Essa distinção é obrigatória para evitar que requisitos de retaguarda sejam confundidos com requisitos visuais imediatos, e para deixar claro o que pertence ao backlog de fases futuras.

#### Camada 1 — MVP visual obrigatório

A primeira versão visual do dashboard deve conter os seguintes componentes:

1. **Funil operacional**: indicadores de quantos participantes iniciaram o formulário, concluíram o formulário, foram elegíveis, baixaram o app e preencheram o baseline.
2. **Progresso agregado das jornadas**: acompanhamento coletivo do andamento das jornadas de depressão e ansiedade, em nível de UBS.
3. **Atraso e desistência em nível agregado**: indicadores de sessões em atraso e abandono de jornada, apresentados por UBS, sem exposição de dados nominais individuais.
4. **Indicadores clínicos agregados por UBS**: distribuição de escores PHQ-9, GAD-7 e IGI por unidade de saúde. A exposição de escores individuais nominais não é exigida no MVP visual.
5. **Filtro por UBS**: toda a visão do dashboard deve ser filtrável por UBS.
6. **Páginas por UBS**: cada UBS deve ter uma seção ou visão dedicada, com indicadores específicos da unidade.
7. **Exportação CSV essencial**: exportação dos dados exibidos em gráficos e tabelas, com controle por perfil de acesso.
8. **Navegação principal orientada a UBS/gestão**: o eixo central de navegação do MVP visual é a visão agregada por UBS e gestão do projeto. A visão individual por participante não compõe a navegação principal do MVP visual desta etapa.
9. **Botão `🔄` mantido**: o botão de atualização permanece presente no MVP visual. A operação está temporariamente condicionada à credencial Google/BigQuery; no estado atual, o dashboard opera em modo cache/local. A presença do botão não é bloqueadora da execução.
10. **`timestamp` da última atualização do cache**: requisito obrigatório da próxima fase técnica. Deve ser exibido em destaque na interface (recomendado: sidebar). Garante transparência operacional sobre a atualidade dos dados exibidos.

#### Camada 2 — Requisitos obrigatórios de retaguarda (backend/banco), não necessariamente visíveis no MVP

Os componentes abaixo são obrigatórios na arquitetura de dados e no backend analítico, mas não precisam aparecer como componentes visíveis na interface do MVP:

1. **Subsistema de metadados de coleta**: templates de formulário, perguntas, alternativas, regras de salto, vínculos entre passos e estruturas `daily`. Necessário para reconstituir o fluxo real de coleta e calcular indicadores de abandono por pergunta, passo ou tarefa.
2. **Separação dos fatos em quatro blocos analíticos**: rastreio web, baseline no app, eventos de jornada e eventos transversais de monitoramento automatizado e chatbot. Obrigatório para auditabilidade e integridade do banco.
3. **Motor de alertas em três saídas**: risco suicidário, piora clínica e engajamento operacional. O motor deve estar implementado no backend e parametrizado conforme as regras canônicas; a exposição visual de alertas na interface é decisão de fase posterior.
4. **Dupla linha do tempo por participante**: linha clínica (PHQ-9, GAD-7, IGI, S-RAP) e linha terapêutico-operacional (sessões, tarefas, notificações, interações do chatbot e demais eventos operacionais de acompanhamento). Obrigatória no banco para auditabilidade e interpretação clínica; não é exigida como componente visual do MVP.
5. **Domínio segregado de PII**: tabelas dedicadas a dados pessoalmente identificáveis (`pii_participant_identity`, `pii_participant_contact` e similares), com chaves substitutas no domínio analítico. Obrigatório por segurança; não deve ser exposto na interface visual.

#### Camada 3 — Itens de fase posterior

Os componentes abaixo não são requisitos do MVP visual. Pertencem ao backlog de fases futuras:

1. Painel individual do usuário como eixo principal de navegação e visualização.
2. Visualização detalhada e intuitiva de alertas na interface do dashboard.
3. Timelines explícitas por participante na interface visual.
4. Análises causais do efeito do chatbot, notificações ou progressão de jornada. Nesta fase, basta registrar a exposição, a sequência temporal e a associação descritiva.
5. Indicadores parcialmente observáveis ou indisponíveis, como "quantas vezes o participante tentou mas não completou" — listado no documento de especificação como desejável, mas não coletado. Deve ser registrado como indicador indisponível ou parcialmente observável, e não como medida consolidada.

## Síntese final

A arquitetura geral permanece a mesma. O que muda é a reconciliação fina entre banco, backend analítico e dashboard visual. O sistema deve permanecer orientado a eventos, com regras parametrizadas, motor explícito de formulários e jornadas, quatro blocos analíticos integráveis, duas timelines por participante no backend/modelagem, domínio segregado de PII e prioridade visual agregada-operacional para UBS e gestão. Nesta versão, chatbot e eventos operacionais de monitoramento substituem suporte humano como eixo funcional principal do monitoramento descrito. Essa revisão preserva o restante do plano original e mantém aderência às decisões validadas.

Decisões vinculantes adicionais incorporadas nesta versão final (2026-04-06): (a) navegação principal do MVP visual orientada a UBS/gestão, com visão individual fora do eixo principal; (b) botão `🔄` mantido na interface, com operação temporariamente condicionada à credencial Google/BigQuery, sem remoção nem desabilitação; (c) `timestamp` da última atualização do cache é requisito obrigatório da próxima fase técnica.

