---
output:
  pdf_document: default
  html_document: default
---
# Contrato de Dados - Progresso de Formulario

## Onde mudou

- colecao: `users`
- campo atualizado: `forms`
- nivel do dado: documento do paciente

## O que mudou

Agora o formulario salva progresso parcial.

Campos novos:

- `submissionId`
- `status`: `in_progress` | `completed`
- `startedAt`
- `updatedAt`
- `completedAt`
- `currentStep`

## Significado rapido

- `submissionId` = 1 sessao do formulario
- `status = in_progress` = usuario ainda esta preenchendo
- `status = completed` = envio final
- `currentStep` = indice atual do stepper no momento do save
- registros antigos sem `status` devem ser lidos como `completed`

## Regra principal

- 1 `submissionId` = 1 snapshot da sessao
- saves seguintes sobrescrevem o mesmo `submissionId`
- se ja existir `completed`, qualquer `in_progress` com o mesmo `submissionId` deve ser ignorado
- abrir o link em outro dia gera um novo `submissionId`

## Ordenacao e selecao dentro de `forms[]`

- `forms[]` e ordenado por ordem de criacao (mais antigo primeiro)
- para leitura de scores clinicos (PHQ, GAD, IGI): usar o elemento mais recente com `status = "completed"` (ultimo completed do array)
- nao usar `forms[0]` para scores — pode ser uma triagem antiga
- registros sem `status` devem ser tratados como `completed` (retrocompatibilidade)

Em codigo:

```python
completed_forms = [
    f for f in forms
    if f.get("status", "completed") == "completed"
]
form_for_scores = completed_forms[-1] if completed_forms else None
```

## Escopo de unicidade do `submissionId`

- `submissionId` nao e garantido globalmente unico
- todas as metricas baseadas em `submissionId` devem ser calculadas dentro do escopo de um `user_id`
- nunca usar `count(distinct submissionId)` sem `GROUP BY user_id` ou filtro por usuario

## Definicao de abandono (nivel de paciente)

- abandono e definido no nivel do paciente, nao da submissao
- paciente concluinte = tem ao menos 1 `submissionId` com `status = "completed"`
- registros `in_progress` de um paciente concluinte nao contam como abandono
- paciente abandonante = nenhum `submissionId` com `status = "completed"`

Em SQL:

```sql
-- Pacientes que abandonaram = sem nenhum completed
SELECT user_id
FROM forms_expanded
GROUP BY user_id
HAVING COUNT(CASE WHEN status = 'completed' THEN 1 END) = 0
```

## Exemplos

### Save parcial

```json
{
  "submissionId": "a1b2",
  "status": "in_progress",
  "startedAt": "2026-04-23T10:00:00.000Z",
  "updatedAt": "2026-04-23T10:07:00.000Z",
  "currentStep": 6,
  "date": "2026-04-23T10:07:00.000Z",
  "answers": [
    { "question": "Nome completo", "answer": "Maria Silva" },
    { "question": "CPF", "answer": "529.982.247-25" }
  ],
  "scores": []
}
```

### Save final

```json
{
  "submissionId": "a1b2",
  "status": "completed",
  "startedAt": "2026-04-23T10:00:00.000Z",
  "updatedAt": "2026-04-23T10:24:00.000Z",
  "completedAt": "2026-04-23T10:24:00.000Z",
  "currentStep": 31,
  "date": "2026-04-23T10:24:00.000Z",
  "answers": [
    { "question": "Nome completo", "answer": "Maria Silva" },
    { "question": "CPF", "answer": "529.982.247-25" },
    { "question": "Ansiedade", "answer": "Mais da metade dos dias" }
  ],
  "scores": [
    { "type": "PHQ", "score": 12, "adverseEvent": false, "critical": true },
    { "type": "GAD", "score": 9, "adverseEvent": false, "critical": false }
  ]
}
```

## Regras para dashboard

### Formularios completos

Use:

```sql
status = "completed"
```

Example:

- `count(distinct submissionId)` quando `status = "completed"`
- `count(*)` nao e seguro se houver varios snapshots

### Formularios em progresso

Use:

```sql
status = "in_progress"
```

Example:

- sessoes em progresso
- abandono por step
- ultimo step antes do dropoff

### Dropoff por step

Use:

```sql
status = "in_progress"
```

Group by:

```sql
currentStep
```

Example:

- `currentStep = 0` -> usuario parou no primeiro step
- `currentStep = 6` -> usuario parou no step 6
- `currentStep = 31` -> usuario chegou no step final

## Metricas sugeridas

Todas as metricas abaixo devem ser calculadas com `GROUP BY user_id` ou dentro do escopo de um usuario.

- sessoes iniciadas = `count(distinct submissionId)`
- sessoes completas = `count(distinct submissionId where status = "completed")`
- sessoes abandonadas = pacientes sem nenhum `status = "completed"` (nivel de paciente, nao de submissao)
- taxa de conclusao = `completed / started`
- taxa de abandono = `in_progress / started`
- tempo para concluir = `completedAt - startedAt`
- tempo para abandonar = `updatedAt - startedAt`

## Observacoes

- `answers` e `scores` podem estar parciais em `in_progress`
- nao usar `answers.length` como sinal de conclusao
- nao usar `scores.length` como sinal de conclusao
- `currentStep` e o indice do stepper, nao um nome de etapa de negocio
