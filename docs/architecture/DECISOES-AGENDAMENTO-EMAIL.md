# Decisões de arquitetura — Automação Murici

Data: 2026-11-07  
Status: decisões aprovadas para implementação isolada; não autorizam alterações em produção.

## 1. Princípios de execução

- A nuvem é a fonte de verdade para tarefas agendadas e a executora primária das publicações.
- O aplicativo móvel é interface, acompanhamento, notificações e sincronização oportunista.
- Publicações não dependem de o telefone estar ligado, conectado ou com o aplicativo aberto.
- Manter o cronjob atual do Render até que a alternativa esteja implementada, testada e validada.
- Avaliar maior precisão que a cadência atual de 15 minutos somente após análise de custo, limites da plataforma e testes.
- Separar o dispatcher de publicações do watchdog de reconciliação.

## 2. Confiabilidade do dispatcher

Estados mínimos:
- `scheduled`: aguardando horário;
- `processing`: execução com lease e prazo de expiração;
- `published`: publicação confirmada externamente e persistida;
- `retryable_failed`: falha transitória segura para nova tentativa;
- `uncertain`: resultado externo não confirmado; exige reconciliação antes de retry;
- `overdue`: passou do horário sem conclusão.

Requisitos:
- Lease/expiração e recuperação de tarefas presas em `processing`.
- Idempotência por tarefa/publicação para evitar duplicidade.
- Retry com backoff e limite de tentativas.
- Em resultado incerto, consultar/reconciliar com LinkedIn antes de publicar novamente.
- Registrar eventos e transições para auditoria.
- Nunca interpretar fila vazia/idle como prova de publicação.

## 3. Integração de e-mail

- O usuário conecta a própria conta por OAuth e concede consentimento explícito.
- O escopo aprovado é leitura do conteúdo das mensagens da própria conta.
- Para Gmail, usar Gmail API `watch` + Google Cloud Pub/Sub para sinalizar alterações; após o aviso, o backend consulta histórico/mensagens na Gmail API.
- Notificação é um sinal de alteração, não necessariamente o conteúdo da mensagem.
- Renovar periodicamente o `watch`, persistir cursor de histórico e reconciliar para cobrir notificações perdidas/expiradas.
- Isolamento rigoroso por usuário e por conta; tokens OAuth protegidos no backend.
- Leitura não autoriza enviar, responder, redigir, excluir, arquivar, mover, rotular ou marcar mensagens.
- Não compartilhar mensagens entre membros de plano familiar.
- Provedores além do Gmail, escopos OAuth exatos, retenção, anexos e experiência de exibição permanecem decisões técnicas a validar.

## 4. Limites desta branch

Permitido nesta fase: documentação, contratos, código isolado e testes em ambiente não produtivo.

Não permitido sem autorização adicional:
- deploy ou alteração de serviços/variáveis no Render;
- alteração de cronjob ou execução manual do scheduler;
- migração ou escrita no Neon de produção;
- publicação real no LinkedIn;
- acesso ou alteração de contas externas do usuário;
- ativação de novos escopos OAuth em produção.

## 5. Critérios de aceite antes de produção

- Testes de concorrência, lease expirado, retry, idempotência e reconciliação de publicação incerta.
- Testes que provem que celular offline/desligado não interrompe execução na nuvem.
- Testes de notificação Gmail duplicada, atrasada, perdida, renovação de watch e recuperação via histórico.
- Testes de isolamento entre usuários/contas e revogação OAuth.
- Prova de que operações de escrita no e-mail não existem ou permanecem inacessíveis.
- Revisão de custo, quotas, escopos e política de retenção.
- Aprovação explícita antes de qualquer mudança em produção.
