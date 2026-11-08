# Plano de migração multiusuário — baseado no schema real do Neon

Status: desenho técnico preliminar; **não é uma migração executável**.  
Data: 08/11/2026  
Base observada: projeto Automação Murici / branch production / banco neondb / PostgreSQL 18.6.  
Regra: nenhuma alteração foi aplicada ao banco de produção.

## 1. Objetivo

Introduzir identidade individual, ownership explícito e isolamento de recursos sem interromper o funcionamento atual e sem atribuir registros legados a usuários por suposição.

A família é entidade de cobrança/benefícios. Pertencer à mesma família não concede acesso a e-mails, tokens, arquivos, publicações, métricas, histórico ou preferências de outro membro.

## 2. Estado de partida confirmado

12 tabelas em `public`. Nenhuma contém `user_id`, `owner_user_id` ou `tenant_id`.

Tabelas de credenciais:
- `google_accounts`: PK bigint; `account_name` UNIQUE; email/provider; access_token/refresh_token; token_expires_at; timestamps.
- `linkedin_accounts`: PK bigint; `account_name` UNIQUE; linkedin_member_id; access_token; token_expires_at; timestamps.

Tabelas de conteúdo/execução sem ownership:
- `editorial_posts`
- `linkedin_publish_queue`
- `linkedin_post_metrics`
- `linkedin_metrics_collection_runs`
- `engagement_post_observations`
- `engagement_hypotheses`
- `engagement_experiments`
- `engagement_evidence_sources`

Tabela dependente do Google:
- `drive_storage_locations.google_account_id` referencia `google_accounts.id`.

Tabela de teste:
- `security_test` contém encrypted_value; não é recurso de usuário e deve ser revisada para remoção/isolamento futuro, não promovida a dado de produto.

## 3. Modelo lógico recomendado

### users
Identidade principal da pessoa. O identificador interno deve ser UUID. A origem de autenticação (provedor/subject) deve ser única e vinculada a uma identidade interna; e-mail não deve ser usado sozinho como chave imutável.

### user_sessions
Sessões revogáveis, com hash de identificador/refresh token quando aplicável, timestamps, expiração, revogação e metadados mínimos de segurança. Não armazenar segredo em claro.

### families / family_members
Entidades de cobrança e associação. Papéis familiares não são papéis de acesso aos dados pessoais. A autorização para qualquer recurso continua exigindo ownership do usuário, salvo recurso explicitamente classificado como compartilhável e aprovado.

### connected_accounts
Vínculo individual do usuário com Google/LinkedIn e demais provedores: user_id, provider, provider_subject, account label, scopes concedidos, token cifrado, expiração, status, connected_at, revoked_at. Unique constraints devem refletir provider + provider_subject conforme regra do provedor; não presumir que e-mail identifica uma conta.

### oauth_transactions
Transação OAuth de curta duração: state hash, user_id, provider, purpose, redirect allowlist/identificador interno, PKCE verifier cifrado quando aplicável, created_at, expires_at, consumed_at. Consumo atômico e único; state de uso único. Nunca confiar em user_id enviado pelo browser.

### audit_events
Trilha append-only para eventos de autenticação, autorização, conexão/desconexão de provedor, acesso administrativo e alterações de ownership. Não registrar tokens, códigos OAuth, conteúdo de e-mails ou payloads sensíveis.

### Gmail
Separar estado de sincronização e mensagens por conta conectada:
- email_sync_state: connected_account_id, cursor/history_id, watch_expiration, last_success_at, last_error_at, recovery_required.
- email_messages: connected_account_id e identificador externo estável, metadados mínimos, timestamps e conteúdo protegido conforme política de retenção aprovada.
- MVP previamente definido sem anexos e sem escopo de escrita; conteúdo de e-mail nunca compartilhado automaticamente com membros da família.

## 4. Ownership das tabelas atuais

Após autenticação e antes de liberar leitura/escrita multiusuário, adicionar ownership às tabelas que realmente representam recursos de usuário. Candidatas:

| Tabela atual | Tratamento |
|---|---|
| editorial_posts | adicionar owner_user_id; preservar IDs e FKs; legado sem titularidade comprovada fica em quarentena. |
| linkedin_publish_queue | owner_user_id obrigatório para novos registros; validar owner do editorial_post_id e connected_account antes de processar. |
| linkedin_post_metrics | derivar ownership somente por relação confiável com publicação/conta; métricas sem relação comprovada ficam isoladas. |
| linkedin_metrics_collection_runs | owner_user_id ou connected_account_id para execuções por conta; não atribuir histórico global automaticamente. |
| engagement_post_observations | owner_user_id se observação for pessoal; se for dataset de pesquisa compartilhado, classificar explicitamente como dataset global aprovado. |
| engagement_hypotheses / engagement_experiments | decidir se são ativos privados do usuário ou biblioteca global curada; não inferir. |
| engagement_evidence_sources | provável biblioteca de evidências compartilhada e curada; exigir classificação explícita e governança editorial. |
| google_accounts / linkedin_accounts | migrar para connected_accounts após validação de titularidade e consentimento; não copiar token para usuário presumido. |
| drive_storage_locations | substituir referência global por connected_account_id; validar que pasta/arquivo pertence à conta Google conectada. |
| security_test | não migrar para dados do usuário; avaliar descarte controlado em plano separado. |

## 5. Migração em fases

### Fase 0 — preparar ambiente
- Criar branch Neon temporária a partir de production, sem alterar production.
- Confirmar que branch está pronta e apontada ao banco correto.
- Executar apenas inspeções e testes na branch temporária.
- Não copiar segredos para logs, documentos ou GitHub.

### Fase 1 — identidade paralela
- Definir provedor de autenticação e contrato de sessão.
- Criar tabelas novas sem exigir imediatamente ownership nas tabelas antigas.
- Adicionar índices/constraints com estratégia compatível com volume e bloqueios.
- Implementar login/logout/revogação e proteção CSRF em ambiente isolado.
- Garantir que endpoints legados continuem restritos a operação interna e não virem APIs públicas de usuário.

### Fase 2 — OAuth e contas conectadas
- Implementar transações OAuth vinculadas a principal autenticado, purpose e TTL.
- State aleatório de uso único, consumo atômico antes de finalizar callback, PKCE quando suportado e redirect allowlist.
- Tokens cifrados no servidor e nunca retornados ao frontend.
- Não associar contas globais antigas a usuários sem prova de titularidade/consentimento.

### Fase 3 — ownership gradual
- Adicionar colunas owner_user_id inicialmente nullable.
- Aplicar ownership obrigatório a novos registros.
- Ajustar consultas e jobs para exigir principal verificado e owner.
- Validar ownership em todas as relações: fila → publicação → conta conectada.
- Dados antigos sem owner ficam em quarentena, sem aparecer em consultas de usuário.
- Backfill somente com evidência auditável e decisão explícita.

### Fase 4 — enforcement
- Tornar ownership NOT NULL somente depois de relatório de cobertura sem órfãos.
- Adicionar FKs, índices e políticas de acesso necessárias.
- Testar tentativa de acesso cruzado entre usuários e entre famílias.
- Remover caminhos legados somente após telemetria e janela de rollback.

### Fase 5 — Gmail
- Gmail conectado individualmente via OAuth consentido.
- Gmail watch + Pub/Sub, recuperação por history cursor e reconciliação.
- Separação por connected_account_id em todos os jobs e dados.
- Sem anexos no MVP e sem ações de escrita.
- Definir retenção, exclusão e UX antes de armazenar corpo integral de mensagens.

## 6. Testes obrigatórios

- Usuário A não lê/atualiza/exclui recursos de B, mesmo conhecendo IDs.
- Membro de família não acessa e-mail, token, publicação ou histórico de outro membro.
- Usuário sem sessão e sessão revogada falham fechados.
- Callback OAuth com state expirado, reutilizado, alterado ou de outro usuário é rejeitado.
- Token de uma conta conectada não pode ser recuperado por outro usuário.
- Jobs sem owner/connected_account válidos não executam.
- Webhook Pub/Sub não pode selecionar tenant por user_id arbitrário do payload.
- FKs impedem vincular fila a publicação de outro owner.
- Rollback não perde dados preexistentes nem reativa acesso global inseguro.

## 7. Decisões pendentes antes de SQL definitivo

1. Provedor de autenticação da aplicação (Neon Auth ou identidade própria/terceiro) e formato do subject.
2. Se as tabelas de hipóteses/experimentos/observações/evidências são pessoais ou biblioteca global curada.
3. Titularidade comprovada das atuais contas Google e LinkedIn.
4. Se os dados atuais de conteúdo pertencem exclusivamente à conta operadora atual ou precisam ser segregados em workspace administrativo.
5. Política de retenção e exclusão de mensagens Gmail.
6. Estratégia de criptografia e rotação de chaves para tokens existentes e novos.

## 8. Critérios para aprovar execução

- Branch temporária testada e comparada com schema base.
- SQL revisado com rollback documentado.
- Testes de isolamento e migração aprovados.
- Backfill de legado documentado com evidência.
- Aprovação explícita antes de qualquer aplicação em production.

**Este documento é um desenho técnico. Não contém SQL executável e não autoriza alterações de schema.**
\n\n## 9. Decisões de produto incorporadas em 08/11/2026\n\n- O cliente decide individualmente entre “Concordo” e “Discordo” sobre o uso de estruturas analíticas desidentificadas/agregadas na inteligência coletiva. Não há compartilhamento de conteúdo bruto, identidade, dados pessoais ou dados estratégicos identificáveis. O texto explicativo deve aparecer antes da escolha; a decisão é revogável e independente de aprovação editorial ou sincronização.\n- A base coletiva deve manter proveniência, amostra, período, limitações e reavaliação temporal. Exemplos numéricos sem estudo real devem ser rotulados como ilustrativos.\n- Publicações não aprovadas e/ou aguardando data ficam no armazenamento local do aparelho do cliente. A publicação só entra no agendador cloud após aprovação explícita. Backup/sincronização futura exige escolha separada.\n