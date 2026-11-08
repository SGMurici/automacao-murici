# Inventário de rotas, persistência e controles de segurança

Data: 2026-11-08
Branch: integracao-base-2026-11-07
Escopo: leitura estática de app.py, requirements.txt e workflow; nenhuma conexão ao banco, serviço ou ambiente de produção foi realizada.

## 1. Estrutura e configuração observada

- Backend concentrado em app.py (2.852 linhas no momento da inspeção).
- Dependências declaradas: Flask, gunicorn, psycopg[binary], cryptography. Não há biblioteca de autenticação, migração, CSRF, rate limiting ou CORS declarada em requirements.txt.
- DATABASE_URL é usado para conexão PostgreSQL via psycopg.
- FLASK_SECRET_KEY assina a sessão Flask.
- TOKEN_ENCRYPTION_KEY protege tokens de provedores com Fernet.
- PUBLISH_SECRET protege endpoints operacionais por segredo compartilhado.
- Cookies configurados com HttpOnly, SameSite=Lax e Secure em produção/Render.
- MAX_CONTENT_LENGTH = 1 MiB.
- Não foi localizada configuração explícita de SESSION_COOKIE_NAME, SESSION_COOKIE_DOMAIN, SESSION_COOKIE_PATH, SESSION_COOKIE_MAX_AGE, PERMANENT_SESSION_LIFETIME, CSRF, CORS, CSP, HSTS, X-Content-Type-Options, X-Frame-Options, trusted hosts/proxy ou rate limiting no arquivo examinado.
- Ausência no código inspecionado não prova ausência de controles na infraestrutura; isso exige verificação separada no Render/proxy.

## 2. Mapa das rotas observadas

| Rota | Método | Controle atual observado | Operação/risco |
|---|---|---|---|
| / | GET | Público | Identificação/status do serviço |
| /health | GET | Público | Health check |
| /db-test | GET | PUBLISH_SECRET | Consulta PostgreSQL |
| /crypto-test | GET | PUBLISH_SECRET | Teste criptográfico |
| /google-drive/accounts | GET | PUBLISH_SECRET | Lista contas Drive autorizadas |
| /google-drive/check | GET | PUBLISH_SECRET | Pode renovar token e acessar Google Drive |
| /google-drive/art-folder | GET | PUBLISH_SECRET | Lista metadados de arquivos |
| /google-drive/test | POST | PUBLISH_SECRET | Teste de integração Drive |
| /google-drive/health | GET | PUBLISH_SECRET | Diagnóstico Drive |
| /google-drive/router | GET | PUBLISH_SECRET | Seleção de conta Drive |
| /storage-test | POST | PUBLISH_SECRET | Grava valor criptografado em security_test |
| /linkedin/login | GET | Apenas exige FLASK_SECRET_KEY | Inicia OAuth LinkedIn e grava state na sessão |
| /linkedin/callback | GET | Valida state da sessão | Troca code, consulta userinfo e grava token em conta global |
| /google/login | GET | Apenas exige FLASK_SECRET_KEY | Inicia OAuth Drive readonly e grava state/conta na sessão |
| /google/callback | GET | Valida state da sessão | Troca code e grava token em conta fixa Drive5 |
| /linkedin/publish | POST | PUBLISH_SECRET | Publicação no LinkedIn e persistência editorial |
| /scheduler/queue | POST | PUBLISH_SECRET | Insere item na fila |
| /scheduler/status | GET | PUBLISH_SECRET | Consulta contagens e próximo item |
| /scheduler/run | POST | PUBLISH_SECRET | Executa publicação vencida |
| /analytics/prepare | GET | PUBLISH_SECRET | Cria tabelas/índices de analytics em runtime |
| /analytics/record | POST | PUBLISH_SECRET | Grava métricas recebidas |
| /analytics/collect | POST | PUBLISH_SECRET, além de feature flag | Coleta automática opcional do LinkedIn |

A proteção PUBLISH_SECRET autentica conhecimento de um segredo comum, não uma pessoa, sessão individual, titularidade ou permissão granular. Rotas OAuth não exigem autenticação individual e podem iniciar conexão global.

## 3. Inventário de tabelas e persistência observável

### DDL explícito localizado em app.py

| Tabela | Evidência de criação | Campos/uso observados | Observações |
|---|---|---|---|
| linkedin_post_metrics | ensure_analytics_tables() | editorial_post_id, linkedin_post_id, measured_at, métricas, source, created_at | UNIQUE (linkedin_post_id, measured_at); FK editorial_posts ON DELETE SET NULL |
| linkedin_metrics_collection_runs | ensure_analytics_tables() | started_at, finished_at, status, contadores, error_message | Índice por started_at |
| linkedin_publish_queue | ensure_scheduler_tables() | post_number, title, content, scheduled_for, status, attempts, locked_at, published_at, linkedin_post_id, editorial_post_id, error_message, timestamps | Índices por status/data, post_number e LinkedIn ID; índice único parcial para post_number ativo |

### Tabelas referenciadas por SQL, mas sem DDL de criação localizado no trecho auditado

- linkedin_accounts: account_name, linkedin_member_id, access_token criptografado, token_expires_at, updated_at. Upsert usa conflito por account_name. O valor configurado é LinkedIn Principal, portanto a conta é global.
- google_accounts: account_name, access_token, refresh_token, expires_at e updated_at conforme operações observadas; fluxo limita account_name a Drive5.
- editorial_posts: recebe dados da publicação e linkedin_post_id; é referenciada por queue e métricas. O DDL completo, constraints e titularidade não foram comprovados.
- security_test: recebe encrypted_value no endpoint /storage-test. DDL não foi localizado.

**Importante:** este é um inventário do SQL encontrado no arquivo, não um snapshot completo do schema real do PostgreSQL. Não foram executadas consultas de catálogo, migrations, introspecção ou acesso ao Neon. Antes de escrever migrations, obter o schema real e as constraints atuais em ambiente de desenvolvimento/cópia sanitizada.

## 4. Controles e lacunas

### Sessão e autenticação
- Flask usa sessão baseada em cookie assinado; não há identidade individual identificada no backend examinado.
- Cookie HttpOnly/SameSite=Lax e Secure condicional são bons controles parciais, mas não substituem autenticação, autorização, CSRF ou política de expiração/revogação.
- Não há SESSION_COOKIE_MAX_AGE nem PERMANENT_SESSION_LIFETIME explícitos no app.py.
- Não foi identificada rotação de sessão após autenticação, logout, revogação de sessão, MFA ou armazenamento de sessões server-side.
- PUBLISH_SECRET é compartilhado e não pode ser reaproveitado como identidade de usuário.

### CSRF e CORS
- Não há proteção CSRF explícita para rotas POST autenticadas por segredo/cookie.
- Não há configuração CORS explícita no backend examinado.
- Não adicionar CORS permissivo por conveniência. Definir origens exatas do frontend e credenciais antes de habilitar chamadas cross-origin.
- Definir token CSRF ou estratégia equivalente para operações autenticadas por cookie; avaliar proteção contra CSRF nos callbacks OAuth e operações mutáveis.

### OAuth
- State é armazenado na sessão Flask, mas não tem TTL independente.
- State não é consumido antes da troca do authorization code; é removido somente após persistência bem-sucedida.
- Não há vínculo do state a um user_id autenticado, provedor + finalidade, redirect URI permitido ou PKCE verifier.
- O Google atual solicita drive.readonly, access_type=offline e prompt=consent; não é Gmail.
- O LinkedIn salva uma conta global, sem user_id.
- Erros HTTP de token e userinfo podem retornar detalhes crus do provedor ao cliente.
- Redirect URIs são hardcoded para o serviço Render.
- Próximo desenho deve usar transação OAuth persistida com state hash, expiração curta, consumo atômico de uso único, provedor/finalidade/redirect vinculados, associação a usuário autenticado e PKCE quando suportado/recomendado pelo provedor. Nunca colocar tokens ou code em logs/respostas.

### Proteção operacional
- PUBLISH_SECRET deve ser comparado em tempo constante; confirmar implementação exata de require_publish_secret() e limitar segredo a operações internas.
- Aplicar rate limiting nos endpoints expostos e limites de tentativas em login/callback; não implementar bloqueios que possam interromper o cron atual sem plano de compatibilidade.
- Sanitizar mensagens de erro, registrar correlation IDs e não registrar credenciais, corpos de e-mail ou tokens.
- Rever endpoints de diagnóstico antes de exposição pública; /health deve permanecer mínimo.

## 5. Sequência recomendada antes de migrations

1. Obter schema real do PostgreSQL em ambiente de desenvolvimento/cópia sanitizada: tabelas, colunas, tipos, defaults, índices, constraints, FKs, triggers e volume de linhas.
2. Obter inventário de dados e decidir titularidade dos registros legados; dados sem titular conhecido ficam em quarentena.
3. Definir método de login, recuperação, MFA, política de sessão e papéis.
4. Definir origem exata do frontend e estratégia CSRF/CORS.
5. Definir OAuth transacional e armazenamento de credenciais por usuário.
6. Só então escrever migrations versionadas e reversíveis, testá-las em cópia e planejar backfill.
7. Integrar autorização em cada rota, consulta SQL, callback, tarefa assíncrona e acesso a token.
8. Fazer testes negativos de isolamento e testes de regressão das rotas legadas.
9. Solicitar autorização separada antes de qualquer alteração em Neon/Render/produção.

## 6. Bloqueios reais

Para implementar autenticação completa sem escolhas arbitrárias, será necessário definir:
- login por Google, e-mail/senha ou ambos;
- política de recuperação de conta e MFA;
- gestão familiar (titular pagador e permissões administrativas, se houver);
- origens oficiais do frontend;
- retenção e exclusão dos dados de e-mail.

Nenhuma dessas definições foi presumida nesta etapa. Nenhuma alteração foi feita em produção.
