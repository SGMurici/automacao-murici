# Análise estática do dispatcher atual

Data: 2026-11-08  
Arquivo inspecionado: `app.py` na branch de integração.  
Tipo de verificação: leitura de código; sem execução, acesso ao banco ou publicação.

## Comportamento atual

1. `/scheduler/run` chama `scheduler_publish_one()`.
2. A função cria/verifica tabelas via `ensure_scheduler_tables()` durante a execução.
3. Usa advisory lock global no PostgreSQL para impedir dois schedulers simultâneos.
4. Seleciona uma única tarefa vencida em estado `agendado`, com `FOR UPDATE SKIP LOCKED`.
5. Marca a tarefa como `processando`, incrementa tentativas e registra `locked_at`.
6. Chama LinkedIn e depois grava `editorial_posts` e muda a fila para `publicado`.
7. Em exceção, muda a fila para `erro`; se houve ID retornado pelo LinkedIn, registra mensagem de reconciliação manual.

## Lacunas confirmadas pela leitura

- O lock é global, não por tarefa; limita o processamento a uma publicação por execução.
- Não há recuperação automática de registros antigos em `processando`/lease expirado.
- Não há chave de idempotência persistida para relacionar uma tentativa local a uma operação externa.
- Não há estado próprio `uncertain`; a situação fica representada por `erro` e mensagem textual.
- Não há reconciliação automática com LinkedIn antes de permitir nova tentativa.
- Se a chamada externa falhar sem devolver ID, o código não consegue provar se o LinkedIn recebeu a publicação; a mensagem conservadora evita retry automático.
- A tabela e índices são criados em tempo de requisição, o que mantém DDL no caminho operacional.
- O fluxo processa apenas um item por chamada; maior frequência do cron reduz atraso, mas não resolve por si só recuperação, incerteza ou capacidade.

## Direção de correção

- Separar migrações versionadas da execução normal de requisições.
- Projetar leases por item com expiração e mecanismo de recuperação.
- Adicionar estados explícitos, tentativas e trilha de eventos.
- Adotar idempotência interna e estratégia de reconciliação externa. Não presumir que LinkedIn aceite uma chave idempotente sem confirmar suporte oficial.
- Separar dispatcher (reivindica e executa) do watchdog (detecta vencidos, travados e incertos).
- Manter cadência de produção inalterada até testes concorrentes e reconciliação simulada passarem.

## Testes necessários antes de alterar o fluxo

- Duas execuções concorrentes não reivindicam o mesmo item.
- Worker encerrado após marcar `processando` é recuperado após expiração do lease.
- Resposta externa confirmada seguida de falha de banco não gera republicação automática.
- Timeout externo com resultado desconhecido entra em reconciliação, não em retry cego.
- Falha comprovadamente anterior à aceitação externa pode seguir retry com backoff.
- Itens publicados não voltam a ser reivindicados.
- Fila vazia continua distinguida de publicação concluída.
