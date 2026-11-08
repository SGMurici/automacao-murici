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
