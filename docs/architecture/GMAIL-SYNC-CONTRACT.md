# Contrato técnico — sincronização de Gmail

Status: desenho técnico para implementação em branch; não habilita OAuth nem acessa contas reais.

## Objetivo e limites

Sincronizar mensagens da conta que o próprio usuário conectou, com baixa latência após alterações notificadas pelo Gmail. A notificação Pub/Sub é um sinal de que a caixa mudou; o backend deve buscar o histórico e as mensagens na Gmail API.

O MVP de Gmail é somente leitura. Não incluir endpoints nem escopos para enviar, responder, redigir, arquivar, excluir, mover, rotular ou marcar mensagens.

## Componentes

1. **Conta conectada** — vínculo entre `user_id`, endereço verificado do Gmail, identificador interno da conta e estado de consentimento.
2. **Credencial** — access/refresh tokens criptografados no backend, nunca enviados ao browser ou gravados em logs.
3. **Watch manager** — cria/renova Gmail `users.watch` antes da expiração informada pelo Google.
4. **Pub/Sub** — tópico e assinatura push autenticada; payload deve ser validado antes de aceitar o evento.
5. **Notification inbox** — persiste `emailAddress`, `historyId`, instante recebido e ID da mensagem Pub/Sub para deduplicação.
6. **History synchronizer** — usa `users.history.list` a partir do cursor salvo; pagina até concluir e só então avança o cursor.
7. **Message reader** — busca mensagens novas/alteradas com escopo mínimo, normaliza cabeçalhos e conteúdo necessário ao produto.
8. **Reconciliation worker** — verifica periodicamente expiração de watch e recupera lacunas. Se Gmail responder 404 para cursor antigo, executar ressincronização controlada, sem apagar histórico válido sem política definida.
9. **App notifier** — publica atualização para o usuário certo; não inclui conteúdo sensível em push de lock-screen por padrão.

## Sequência de evento

- Receber POST da assinatura Pub/Sub.
- Validar autenticação da entrega, tópico esperado, formato e tamanho.
- Decodificar payload e validar que o endereço corresponde a uma conta conectada ativa.
- Registrar evento com chave de deduplicação; responder sucesso apenas depois de persistir o evento duravelmente.
- Worker consulta histórico do Gmail desde o cursor anterior.
- Para cada mudança, buscar apenas os dados necessários e associar à conta e ao usuário corretos.
- Persistir mensagens e novo cursor na mesma transação lógica de sincronização.
- Emitir evento interno para atualizar o app.
- Repetições do Pub/Sub não podem duplicar mensagens nem notificações do app.

## Modelo de dados proposto

- `connected_email_accounts`: id, user_id, provider, provider_subject, email_address, encrypted_access_token, encrypted_refresh_token, token_expires_at, granted_scopes, watch_expiration, history_cursor, consented_at, revoked_at, sync_status, created_at, updated_at.
- `email_sync_notifications`: id, connected_account_id, provider_message_id, history_id, received_at, processed_at, status, attempt_count, error_code. Unique por conta + provider_message_id.
- `email_messages`: id, connected_account_id, provider_message_id, thread_id, internal_date, from/subject/snippet conforme produto aprovado, payload normalizado protegido, labels somente para leitura, first_seen_at, last_synced_at. Unique por conta + provider_message_id.
- `email_sync_runs`: id, connected_account_id, started_at, finished_at, start_history_id, end_history_id, status, messages_seen, messages_updated, error_code.
- Todo acesso a estas tabelas deve derivar do `user_id` autenticado no servidor; nunca aceitar `user_id` arbitrário do cliente.

Schema definitivo depende de decisão de retenção, anexos e conteúdo visível na interface. Não criar tabelas de produção nesta fase.

## Segurança e privacidade

- OAuth consentimento por conta, com state de uso único e proteção contra CSRF; avaliar PKCE para o fluxo adotado.
- Solicitar apenas escopos de leitura Gmail estritamente necessários. Não pedir `gmail.modify`, `gmail.send` ou escopos de escrita.
- Tokens protegidos por criptografia gerenciada; não reutilizar a tabela/credenciais de Drive5.
- Separar tenant/usuário em queries, jobs, logs, caches e notificações.
- Não compartilhar mensagens em plano familiar.
- Push de sistema não deve mostrar remetente, assunto ou corpo na tela bloqueada sem escolha explícita do usuário.
- Revogação remove a capacidade de sincronizar; definir retenção/exclusão dos dados sincronizados antes do lançamento.
- Anexos ficam fora do MVP até avaliação de malware, limites, armazenamento, retenção e permissões.
- Logs registram IDs internos e códigos técnicos, não corpo, tokens, cabeçalhos sensíveis ou anexos.

## Operação e resiliência

- Watch é temporário: renovar com margem antes de `expiration`, monitorar falhas e reestabelecer após revogação/expiração.
- Tratar notificações duplicadas, fora de ordem, atrasadas e eventos agrupados.
- Usar cursor de histórico; nunca assumir que uma notificação representa uma única mensagem.
- Aplicar retry com backoff para 429/5xx; respeitar `Retry-After`.
- Em 401, tentar refresh uma vez; em refresh inválido, marcar conta como reautorização necessária.
- Em cursor expirado/inválido, executar recuperação documentada; não ignorar lacuna silenciosamente.
- Monitorar idade do último sync, watches próximos da expiração, backlog, taxa de erro e contas que precisam reautorizar.

## Critérios de aceite

- Usuário A não consegue ler conta/mensagem de usuário B, inclusive via IDs conhecidos.
- Pub/Sub forjado ou não autenticado é rejeitado.
- Evento duplicado/out-of-order não duplica mensagem nem push.
- Cursor só avança após persistência completa do lote.
- Notificação perdida é recuperada pelo reconciliador.
- Watch é renovado e a falha de renovação é visível ao usuário.
- Token revogado interrompe sincronização e solicita reconexão.
- API não oferece operações de escrita.
- Celular offline não impede recebimento e sincronização no backend; o app mostra os dados ao reconectar.
