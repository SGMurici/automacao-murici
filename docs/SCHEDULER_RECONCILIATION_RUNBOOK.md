# Runbook — reconciliação de publicações LinkedIn incertas

Status: procedimento operacional provisório. Não substitui uma transição de estado auditada no backend.

## Objetivo

Investigar itens da fila com status `incerto` sem provocar publicação duplicada. Um item incerto significa que o sistema não consegue provar se o LinkedIn aceitou a publicação. A ausência de um identificador local não prova que a publicação não ocorreu.

## Regras de segurança

- Nunca reenfileirar ou republicar um item apenas porque o ID do LinkedIn está ausente.
- Nunca executar retry enquanto o resultado externo for inconclusivo.
- Não alterar a linha diretamente no banco de produção para “destravar” a fila.
- Não compartilhar `PUBLISH_SECRET`, tokens OAuth, corpo de publicação ou dados pessoais em tickets/logs.
- Preservar o `queue_id`, `post_number`, horário, tentativas e evidências consultadas.
- O número editorial continua reservado enquanto o item estiver `incerto`.

## 1. Consultar a fila de reconciliação

A rota exige o segredo operacional no cabeçalho. Execute de uma estação autorizada, com a variável já configurada no ambiente:

```bash
curl --fail --silent --show-error \
  --request GET "https://automacao-murici.onrender.com/scheduler/reconciliation" \
  --header "X-Publish-Secret: ${PUBLISH_SECRET}"
```

Não cole o valor do segredo no terminal compartilhado, no histórico de tickets ou nesta documentação. A resposta lista até 100 itens e não deve conter o corpo da publicação.

## 2. Reunir evidências no LinkedIn

Para cada item:

1. Registre o `queue_id`, `post_number`, título, horário agendado e `linkedin_post_id`, se houver.
2. Acesse a conta/página LinkedIn correta que deveria ter publicado o conteúdo.
3. Verifique a atividade/publicações da página e o intervalo de horário do agendamento, considerando atrasos de processamento e fuso horário.
4. Compare o conteúdo visível com o rascunho editorial armazenado no sistema, sem copiar o corpo para canais não autorizados.
5. Se houver `linkedin_post_id`, use-o como evidência de correlação, mas confirme que o post correspondente está acessível e pertence à conta esperada.
6. Registre a URL/permalink do post ou uma referência interna segura à evidência. Não registrar tokens ou credenciais.

## 3. Classificar o resultado

### A. Publicação confirmada

Critério: post correspondente encontrado e confirmado na página/conta correta.

Ação provisória: não reenviar. Manter o item fora de qualquer retry até que exista uma operação auditada para confirmar o estado `publicado`, gravar o ID/permalink e encerrar a reconciliação.

### B. Não publicação confirmada

Critério: investigação suficientemente abrangente confirma que o post não foi publicado na conta correta; ausência de resultado em uma busca superficial não é suficiente.

Ação provisória: não reenviar diretamente. Solicitar a operação de retry controlado que ainda precisa ser implementada. Essa operação deverá exigir evidência, confirmação humana, advisory lock, transição transacional e trilha de auditoria.

### C. Resultado inconclusivo

Critério: conta incorreta/indisponível, janela de busca incompleta, falha de acesso, evidência conflitante ou qualquer dúvida remanescente.

Ação: manter `incerto`; não reenviar. Escalar para revisão manual.

## 4. Evidência mínima a registrar

- ID da fila (`queue_id`) e número editorial.
- Responsável pela verificação e data/hora com timezone.
- Conta/página LinkedIn verificada.
- Resultado: `publicado`, `não publicado` ou `inconclusivo`.
- Evidência consultada (permalink ou referência interna segura).
- ID LinkedIn confirmado, quando existir.
- Justificativa objetiva e decisão/autorizações.

## 5. Limitação atual do sistema

A implementação atual oferece consulta dos itens incertos, mas ainda não oferece endpoint administrativo para resolver/reclassificar um item com evidência e auditoria. Portanto, este runbook orienta a investigação, não autoriza atualização manual no banco nem retry. A próxima entrega de código deve implementar uma ação de resolução protegida e testada para os três resultados, preservando a reserva do número editorial e impedindo publicação duplicada.
