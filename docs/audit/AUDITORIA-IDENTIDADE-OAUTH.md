# Auditoria de identidade e OAuth

Data: 2026-11-08
Branch: integracao-base-2026-11-07
Método: leitura estática de app.py; nenhuma chamada externa ou consulta ao banco foi executada.

## Achados confirmados

- Flask usa cookie de sessão assinado, mas o código examinado não implementa identidade autenticada individual.
- require_publish_secret() compara um segredo compartilhado e protege rotas operacionais; não identifica o usuário que solicitou a operação.
- Fluxos OAuth LinkedIn e Google armazenam state em sessão, mas não definem expiração explícita nem removem state antes da troca do código. State é removido somente após persistência bem-sucedida.
- A validação de state é vinculada ao cookie de sessão atual, mas não há vínculo a um usuário autenticado porque essa camada não foi encontrada.
- Callback LinkedIn persiste uma conta global (LinkedIn Principal), sem user_id.
- Callback Google persiste uma conta fixa (Drive5) e o escopo drive.readonly; não representa uma conta pessoal Gmail.
- A tabela google_accounts não deve ser reaproveitada como cadastro de contas Gmail individuais.
- Mensagens de erro de callbacks incluem detalhes retornados pelo provedor; revisar sanitização antes de ampliar integrações.
- Não foi encontrada evidência de middleware de autenticação individual ou de autorização por recurso no arquivo examinado.

## Riscos

1. Habilitar leitura de Gmail antes de identidade e ownership permitiria associar uma conta externa sem isolamento confiável.
2. Usar a chave compartilhada para endpoints de usuário permitiria que qualquer cliente com a chave operasse recursos globais.
3. Reutilizar sessão OAuth sem expiração/uso único aumenta risco de replay e confusão de finalidade.
4. Backfill automático de registros globais para um usuário sem confirmação de titularidade criaria associação não comprovada.

## Ações desta etapa

- Adicionado identity_policy.py com verificações puras de principal, usuário, tenant e papel, todas fail-closed.
- Adicionados testes unitários para negação de ausência de identidade, owner ausente, acesso cruzado e privilégio familiar implícito.
- Criado contrato conceitual de identidade e migração; não foi criado SQL porque faltam inventário completo de schema e decisões sobre login/família/retenção.
- Nenhuma rota existente foi alterada. Nenhum OAuth, banco, serviço ou produção foi acessado.

## Próxima inspeção técnica

- Completar inventário do schema PostgreSQL a partir de migrations/schema versionados e consultas estáticas no código.
- Mapear todas as rotas e operações que leem/escrevem recursos pessoais.
- Revisar configuração de cookies, CSRF, CORS, proxy trust e rate limiting.
- Definir desenho OAuth state com TTL, consumo atômico e PKCE conforme o fluxo/provedor.


## Continuidade da auditoria — revisão das PRs de armazenamento, retenção e autenticação (08/11/2026)

### Escopo e método
Inspeção somente de leitura das PRs #1, #6 e #7, patches, metadados, arquivos alterados, workflow e código versionado. Nenhum workflow foi disparado manualmente; nenhuma branch, PR, migration, banco, Drive, OAuth ou serviço foi alterado.

### PR #6 — retenção de imagens após sete dias
- PR permanece aberta e em Draft; base `drive5-art-upload-test`, head `drive-image-retention-7d-test`, 17 commits e 8 arquivos alterados.
- O workflow `Image retention safety tests` teve execução confirmada no commit `01c10d99ce7b9eb1c87b74940bde2dc244487f6c`, run #42062070416. Job `unit-tests` e etapa `Run retention unit tests` concluíram com sucesso.
- O planejador exige ID único de Drive, MIME `image/*`, vínculo editorial, status `publicado`, timestamp com timezone e sete dias completos.
- A rota `GET /google-drive/image-retention/dry-run` é autenticada pelo segredo operacional e declara não chamar Drive nem modificar banco.
- O módulo `image_retention_executor.py` contém uma função de exclusão permanente com callbacks injetados, lock por ativo, validação de pasta de teste e auditoria de reconciliação. Não está conectada a rota HTTP nem habilitada em serviço. Os testes usam callbacks/mocks; não comprovam operação real.
- A migration adiciona estado `deleted` e `deleted_at` em `public.project_assets`. A rota também consulta `project_assets`.

**Bloqueio estrutural:** a inspeção anterior do Neon production não encontrou `public.project_assets`; a PR #1, por sua vez, cria um manifesto chamado `editorial_image_assets`, com colunas e modelo diferentes. Não há evidência suficiente nesta auditoria de que a branch-base `drive5-art-upload-test` contenha uma tabela `project_assets` compatível com a migration e a rota da PR #6. Não integrar nem aplicar migration até reconciliar nome, schema, ownership, FK editorial e origem dos dados. O sucesso do CI valida apenas os testes unitários do commit testado.

### PR #1 — armazenamento de imagens e ampliação Google Workspace
- Permanece aberta e em Draft, com base `main` e head `ai-code-executor-bootstrap`.
- O patch cria `editorial_image_assets` por SQL defensivo no código, com unicidade por `(post_number, version)`, hash e metadados; não cria `project_assets`.
- O código inclui upload Drive com flag de escrita desligada por padrão e reconciliação somente leitura. Não houve upload real nem autorização OAuth nesta auditoria.
- O conjunto de escopos documentado/codificado nessa proposta inclui Drive read/write limitado, Gmail read-only e Gmail send. O escopo `gmail.send` amplia capacidade de envio e não deve ser tratado como autorização operacional por si só.
- A proposta permite três nomes de conta Google e fluxo Gmail. Continua bloqueada pela ausência de identidade individual/ownership e isolamento multiusuário, conforme achados anteriores.
- A PR descreve recuperação/reconciliação limitada aos primeiros 1.000 arquivos e reconhece que órfãos após falhas parciais exigem hardening adicional.

### PR #7 — header X-Publish-Secret não ASCII
- Permanece aberta e em Draft, com base `main` e head `fix/publish-secret-ascii-header`.
- O patch codifica header e segredo em ASCII antes de chamar `secrets.compare_digest`; rejeita Unicode não ASCII com HTTP 403 e preserva 401 para ausência.
- Foram adicionados quatro testes unitários: ausente, incorreto, não ASCII e correto.
- Não foi encontrada execução CI associada ao head `f141e227945be2ad4c98c999be454b5a3084502c` nesta inspeção. A correção é plausível, mas permanece não validada por CI no estado observado.

### Estado da branch de integração
- O arquivo `app.py` em `main` e em `integracao-base-2026-11-07` retornou o mesmo blob SHA `85438c84f78a7ae719d99d80a5da9385e256ef83` durante esta inspeção. As alterações documentais recentes não equivalem à integração das PRs de código.
- A branch `integracao-base-2026-11-07` foi preservada; nenhuma PR foi mesclada e nenhuma alteração de produção foi feita.

### Próximas verificações prioritárias
1. Inspecionar a árvore e migrations da base `drive5-art-upload-test` e confirmar se `project_assets` existe, sua definição, constraints, FK e origem.
2. Reconciliar formalmente `editorial_image_assets` versus `project_assets`; escolher um manifesto canônico antes de integrar retenção.
3. Revisar o upload e a reconciliação da PR #1 para paginação completa, órfãos, idempotência, concorrência, limites de leitura e segurança dos metadados.
4. Executar/confirmar CI da PR #7 em seu head e revisar o comportamento de erro sem revelar segredo.
5. Manter o executor de exclusão permanente desconectado. A política de retenção precisa de decisão explícita sobre lixeira versus exclusão permanente e validação de ponta a ponta em pasta de teste.
6. Não habilitar Gmail send nem vincular contas a usuários antes de autenticação individual, ownership, consentimento OAuth e testes de isolamento.

### Resultado
A PR #6 tem CI unitário aprovado, mas não está pronta para integração devido à divergência de schema/manifesto e à existência de executor destrutivo não operacional. A PR #7 contém correção pontual, ainda sem CI observado. A PR #1 permanece uma proposta ampla com dependências de OAuth, ownership e hardening de recuperação. Nenhuma dessas PRs foi integrada nesta etapa.


### Verificação adicional da branch-base da PR #6 (08/11/2026)
- O `app.py` da base `drive5-art-upload-test` não contém referência a `project_assets`; o `app.py` do head da PR #6 passa a consultar essa tabela.
- O `app.py` da PR #1 cria/usa `editorial_image_assets`, não `project_assets`. A tabela proposta pela PR #1 guarda `post_number` e `version`, enquanto a rota da PR #6 espera `post_id`, `asset_status` e associação direta com `editorial_posts`.
- Portanto, a incompatibilidade não é apenas entre produção e branch: o código-base identificado da PR #6 também não demonstra a existência do manifesto que sua rota/migration pressupõem. A migration #6 não cria `project_assets`; apenas tenta alterar sua constraint e adicionar `deleted_at`.
- Classificação: bloqueio de integração confirmado por inspeção estática. É necessário escolher e migrar para um único contrato de manifesto, com FK editorial e estados coerentes, antes de reutilizar o planejador de retenção. Não aplicar migration nem conectar executor.

### Observação adicional — reconciliação de upload da PR #1
- A listagem da pasta Drive retorna no máximo 10 páginas e expõe indicador `truncated`; a reconciliação usa essa lista para identificar arquivos ausentes/não registrados.
- Quando `truncated=true`, a reconciliação não pode ser tratada como inventário completo: arquivos fora das páginas lidas podem ser classificados incorretamente como ausentes ou a lista de órfãos pode ficar incompleta. O consumidor deve interromper a conclusão de reconciliação e paginar até o fim ou marcar explicitamente o resultado como parcial.
- A PR reconhece limite de 1.000 arquivos; falta um fluxo de continuação/reconciliação incremental com checkpoint, deduplicação e recuperação de órfãos após upload parcial.
