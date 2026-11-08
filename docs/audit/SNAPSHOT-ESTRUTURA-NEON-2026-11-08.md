# Snapshot estrutural do Neon — Automação Murici

Data da leitura: 08/11/2026  
Projeto Neon: `Automação Murici` (`sweet-dust-48417314`)  
Branch consultada: `production` (`br-young-field-b65u7hwg`), marcada como default/primary  
Banco: `neondb`  
PostgreSQL: `18.6`  
Escopo: consultas somente de leitura aos catálogos do PostgreSQL. Nenhum dado de conteúdo, token, e-mail ou publicação foi selecionado. Nenhuma escrita ou alteração de schema foi executada.

## Resultado geral

O banco possui um schema de aplicação `public` e 12 tabelas-base:

1. `drive_storage_locations`
2. `editorial_posts`
3. `engagement_evidence_sources`
4. `engagement_experiments`
5. `engagement_hypotheses`
6. `engagement_post_observations`
7. `google_accounts`
8. `linkedin_accounts`
9. `linkedin_metrics_collection_runs`
10. `linkedin_post_metrics`
11. `linkedin_publish_queue`
12. `security_test`

O inventário estrutural foi consultado diretamente no Neon. As definições de colunas, tipos, nulabilidade, defaults, índices, constraints e triggers foram obtidas dos catálogos; também foi obtida a árvore de objetos da branch.

## Tabelas e estrutura relevante

| Tabela | Estrutura / observações |
|---|---|
| drive_storage_locations | id bigint PK; google_account_id bigint NOT NULL FK para google_accounts(id); metadados de pasta/arquivo e timestamps. |
| editorial_posts | id bigint PK; post_number, title, content, status default 'rascunho', scheduled_at, published_at, linkedin_post_id e timestamps. Sem FK ou índice adicional além da PK. |
| engagement_evidence_sources | id bigint PK; evidence_key UNIQUE; área, citação, URL, tipo, claims suportadas/não suportadas, status de revisão e datas. |
| engagement_experiments | id bigint PK; experiment_key UNIQUE; hypothesis_id FK para engagement_hypotheses(id) ON DELETE SET NULL; plano, datas, status com CHECK e resultado. |
| engagement_hypotheses | id bigint PK; hypothesis_key UNIQUE; hipótese, mecanismo, status, confiança, arrays de IDs de observações/fontes, revisão ética, plano e resultado de teste, aprovação para orientar conteúdo e timestamps. |
| engagement_post_observations | id bigint PK; editorial_post_id, linkedin_post_id, post_number, measured_at, métricas, data_source NOT NULL, atributos JSONB de texto/visual/contexto e notas. CHECK exige data_source não vazio. Nenhuma FK foi declarada. |
| google_accounts | id bigint PK; account_name UNIQUE NOT NULL; email, provider default 'google', access_token, refresh_token, token_expires_at e timestamps. |
| linkedin_accounts | id bigint PK; account_name UNIQUE NOT NULL; linkedin_member_id, access_token, token_expires_at e timestamps. |
| linkedin_metrics_collection_runs | id bigint PK; início/fim, status, contadores, error_message e índice por started_at. |
| linkedin_post_metrics | id bigint PK; editorial_post_id FK para editorial_posts(id) ON DELETE SET NULL; linkedin_post_id NOT NULL; measured_at; métricas; UNIQUE(linkedin_post_id, measured_at); índices por post, editorial e data. |
| linkedin_publish_queue | id bigint PK; conteúdo e scheduled_for NOT NULL; status default 'agendado'; attempts default 0; lock/publicação/erro; vínculo opcional a editorial_posts com ON DELETE SET NULL; campos de mídia/Drive; índices de fila, post, LinkedIn e arquivo; índice único parcial uq_linkedin_publish_queue_active_post_number. |
| security_test | id bigint PK; encrypted_value text NOT NULL; created_at. |

## Ownership / multiusuário

**Nenhuma das 12 tabelas apresenta coluna explícita `user_id`, `owner_user_id` ou `tenant_id` no snapshot.**

Consequências:
- O schema atual não demonstra isolamento de dados por usuário.
- As tabelas de contas Google e LinkedIn são globais por `account_name` UNIQUE, sem vínculo relacional com usuário.
- `editorial_posts`, fila, métricas e observações não têm proprietário explícito.
- Não é seguro atribuir os registros existentes a um usuário por suposição.
- Antes de habilitar usuários múltiplos, é necessário definir titularidade legítima dos dados atuais, registrar decisão explícita e manter registros de titularidade desconhecida em quarentena até resolução.

## Integridade referencial identificada

Foreign keys encontradas:
- `drive_storage_locations.google_account_id → google_accounts.id`
- `engagement_experiments.hypothesis_id → engagement_hypotheses.id ON DELETE SET NULL`
- `linkedin_post_metrics.editorial_post_id → editorial_posts.id ON DELETE SET NULL`
- `linkedin_publish_queue.editorial_post_id → editorial_posts.id ON DELETE SET NULL`

Não foram encontradas outras FKs no schema public consultado. As relações lógicas em arrays de IDs na tabela `engagement_hypotheses` não são FKs declaradas.

## Índices e triggers

- Os índices foram extraídos via `pg_indexes`; as definições estão resumidas na tabela acima e no resultado de catálogo consultado.
- Não foram encontrados triggers de usuário nas 12 tabelas (`pg_trigger` filtrando triggers internos).
- A árvore da branch também apresenta funções da extensão pgcrypto no schema public (por exemplo encrypt/decrypt/digest e funções PGP). A presença dessas funções não comprova, por si só, que todos os tokens estejam criptografados em repouso pela aplicação.

## Estatísticas de linhas

A consulta ao catálogo retornou estimativas `pg_class.reltuples`, não contagens exatas. A maior parte está em zero e a fila retornou estimativa 2. Essas estimativas podem estar desatualizadas; não devem ser tratadas como contagem real nem usadas para decidir migração/backfill.

## Consequências para o desenho da migração

1. O bloqueio anterior sobre ausência de DDL foi resolvido: agora temos evidência estrutural real do banco.
2. Ainda não há base para fazer backfill automático de propriedade. Não existe ownership atual explícito.
3. O modelo multiusuário deve introduzir identidade e ownership sem presumir que registros globais pertencem ao primeiro usuário que conectar.
4. A conexão Gmail deve usar estrutura separada por usuário/conta conectada; não reutilizar `google_accounts` global do Drive.
5. As contas Google/LinkedIn atuais exigem decisão de titularidade e plano de transição antes de associá-las a qualquer usuário.
6. A próxima etapa segura é preparar uma migração em branch Neon isolada, validar constraints e caminhos de rollback, e só então avaliar aprovação. Nenhuma migração foi criada ou aplicada nesta etapa.

## Limites

Esta captura cobre tabelas-base no schema public, colunas, defaults, constraints, índices, triggers de usuário e árvore de objetos. Não foi feito dump de dados, leitura de tokens, inspeção de e-mails, nem contagem exata de linhas. Não foi alterada a branch production.
