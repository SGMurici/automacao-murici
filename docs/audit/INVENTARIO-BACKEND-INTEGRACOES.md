# Inventário técnico inicial — backend e integrações

Data: 2026-11-08  
Branch: `integracao-base-2026-11-07`  
Escopo: inspeção estática de `app.py`; nenhuma chamada a serviços externos, banco ou produção foi executada.

## 1. Estrutura atual observada

- Backend Flask concentrado em um único arquivo `app.py`.
- PostgreSQL acessado por `psycopg`; tokens Google/LinkedIn são criptografados com Fernet.
- Configuração global usa variáveis de ambiente e uma sessão Flask.
- Rotas operacionais são protegidas por um segredo compartilhado (`PUBLISH_SECRET`); isso não equivale a identidade/autorização individual por usuário.
- Não foi identificado no trecho inspecionado um modelo de usuário, tenant ou autorização por recurso.

## 2. Google atual

- OAuth Google existente usa escopo `https://www.googleapis.com/auth/drive.readonly`.
- Callback grava credenciais em `google_accounts` usando `account_name`.
- `normalize_google_account_name` restringe explicitamente a conta a `Drive5`.
- As funções existentes são orientadas ao Google Drive; não há no trecho inspecionado cliente Gmail, endpoint Gmail, Gmail `watch`, Pub/Sub ou processamento de histórico.
- Portanto, a integração de e-mail aprovada é uma funcionalidade nova e não pode ser ativada reutilizando o escopo Drive atual.
- O callback OAuth mantém state na sessão e remove o state após sucesso; é necessário revisar consumo único, expiração e associação a usuário antes de ampliar o fluxo.

## 3. Agendador atual

- `ensure_scheduler_tables()` cria a tabela da fila em tempo de execução, incluindo índice parcial de unicidade para números de post em estados ativos.
- Campos atuais incluem `status`, `attempts`, `locked_at`, `published_at`, `linkedin_post_id` e `editorial_post_id`.
- O endpoint `/scheduler/run` chama `scheduler_publish_one()`; o fluxo completo e os testes ainda precisam ser inspecionados.
- O schema atual não demonstra, por si só, lease com expiração, chave de idempotência, estados de resultado incerto ou reconciliação automática.
- Evitar alterações de schema até definir migração explícita, compatibilidade com produção e rollback.

## 4. Bloqueios arquiteturais antes de implementação funcional

1. Identidade: falta autenticação individual e autorização por usuário. Não criar contas de e-mail de usuários enquanto o backend ainda opera por segredo compartilhado.
2. Persistência: `google_accounts` e o fluxo atual são vinculados a Drive5; será necessário modelo separado para contas de e-mail conectadas por usuário.
3. OAuth: separar scopes Drive e Gmail; desenhar consentimento, state de uso único, PKCE quando aplicável, revogação e proteção de tokens.
4. Notificações: configurar projeto Google Cloud, Pub/Sub, tópico, assinatura push autenticada e renovação de Gmail watch fora do fluxo de requisição do usuário.
5. Dispatcher: revisar `scheduler_publish_one()` e implementar testes de concorrência/recuperação antes de qualquer mudança de cadência.
6. Operação: estabelecer ambiente de testes isolado e credenciais de teste; nenhuma credencial real deve ser copiada para a branch ou para logs.

## 5. Próxima sequência segura

- Concluir leitura estática do restante do agendador e rotas OAuth.
- Identificar dependências, testes existentes, estrutura de deploy e compatibilidade do runtime.
- Especificar contratos de usuário/conta de e-mail e dispatcher antes de editar código de aplicação.
- Implementar primeiro testes e módulos isolados; manter produção inalterada.
