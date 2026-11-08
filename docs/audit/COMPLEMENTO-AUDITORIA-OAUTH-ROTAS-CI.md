# Complemento da auditoria estática — rotas, OAuth e CI

Data da verificação: 08/11/2026  
Branch: `integracao-base-2026-11-07`  
Escopo: leitura estática do `app.py` e metadados do GitHub Actions. Nenhuma chamada foi feita ao Neon, Render, Google OAuth, LinkedIn OAuth ou contas reais.

## Correção da contagem de rotas

A contagem anterior de 21 rotas estava incorreta. A inspeção direta dos decorators Flask encontrou **22 rotas**:

| Método | Rota |
|---|---|
| GET | / |
| GET | /health |
| GET | /db-test |
| GET | /crypto-test |
| GET | /google-drive/accounts |
| GET | /google-drive/check |
| GET | /google-drive/art-folder |
| POST | /google-drive/test |
| GET | /google-drive/health |
| GET | /google-drive/router |
| POST | /storage-test |
| GET | /linkedin/login |
| GET | /linkedin/callback |
| GET | /google/login |
| GET | /google/callback |
| POST | /linkedin/publish |
| POST | /scheduler/queue |
| GET | /scheduler/status |
| POST | /scheduler/run |
| GET | /analytics/prepare |
| POST | /analytics/record |
| POST | /analytics/collect |

A lista acima conta decorators de rota, não métodos HTTP adicionais implícitos.

## Achados OAuth confirmados no código

### Estado OAuth
- LinkedIn e Google geram estado aleatório com `secrets.token_urlsafe(32)` e comparam o retorno usando `secrets.compare_digest`.
- O estado é guardado na sessão Flask, mas não há expiração/TTL explícita.
- O estado permanece na sessão até a gravação do token no banco terminar; portanto, não é consumido antes da troca do authorization code.
- Não há associação do estado a um principal autenticado, usuário, finalidade ou conta individual.
- Não foi encontrado PKCE.
- O callback Google aceita o nome da conta vindo da sessão, mas a normalização força a conta fixa `Drive5`.
- O fluxo atual não implementa conexão de contas por usuário. Ele persiste uma conta global identificada por `account_name`.

### LinkedIn
- O callback obtém `sub` via UserInfo e persiste token e member ID em `linkedin_accounts`, com chave lógica global `LinkedIn Principal`.
- A consulta de token posterior também procura apenas esse nome global.
- Isso confirma que a conexão LinkedIn atual não está pronta para múltiplos usuários: falta ownership por usuário e conta conectada.

### Google Drive
- O OAuth pede `drive.readonly`, não Gmail.
- A conta é restrita a `Drive5`; consultas e renovações usam esse identificador global.
- A tabela `google_accounts` é usada para Drive e não deve ser reaproveitada como armazenamento multiusuário do Gmail.
- Erros HTTP de troca/renovação de token podem incluir detalhes do provedor na resposta ou exceção; revisar para não devolver payloads brutos ao cliente nem registrar segredos.

## Proteção das rotas

- `require_publish_secret()` exige o cabeçalho `X-Publish-Secret`, compara com `secrets.compare_digest` e responde 401/403 em caso de ausência/incompatibilidade.
- Essa chave compartilhada é uma barreira operacional, não autenticação individual, identidade de usuário ou autorização por propriedade do recurso.
- A presença dessa proteção em endpoints operacionais não resolve o isolamento multiusuário.
- Os fluxos `/linkedin/login` e `/google/login` verificam a configuração da chave da sessão e credenciais do provedor; não verificam um usuário autenticado.
- O inventário de decorators confirma 22 rotas. A classificação rota-a-rota de exigência de segredo deve continuar sendo mantida no inventário principal, mas não deve ser confundida com autorização de usuário.

## Banco e migrações

- No repositório não foi identificado diretório ou ferramenta de migração no nível raiz; a listagem da branch mostra `app.py`, `requirements.txt`, módulos de política, testes, `.github` e `docs`.
- O código cria tabelas de métricas, execuções de coleta e fila de publicação por funções `ensure_*` executadas pela aplicação.
- `editorial_posts`, `linkedin_accounts`, `google_accounts` e `security_test` são referenciadas, mas suas DDLs completas não foram localizadas no código examinado.
- Não existe evidência suficiente para escrever uma migração segura de identidade. Não inferir colunas, chaves primárias, constraints, triggers, índices ou dados existentes.
- Pré-requisito bloqueante: exportar snapshot do schema PostgreSQL do ambiente de desenvolvimento/cópia (sem valores sensíveis), incluindo tabelas, colunas, tipos, defaults, PK/FK, constraints, índices, triggers e contagens agregadas. Não executar migração em produção.

## CI — resultado verificado

A consulta aos workflows da branch encontrou a execução **#10**:
- Commit: `0e763c2ec4405d21e296315feec1ef9b02701f0b`
- Resultado: `completed / success`
- URL: https://github.com/SGMurici/automacao-murici/actions/runs/42440282132

O workflow compila `scheduler_policy.py`, `identity_policy.py` e `tests`, e executa `python -m unittest discover -s tests -v`.

**Limite do resultado:** isso comprova apenas a execução dos checks isolados. Não comprova que `app.py` inteiro, banco, OAuth, Gmail, LinkedIn, frontend ou ambiente Render estejam funcionais.

## Próximas etapas seguras

1. Obter snapshot do schema de desenvolvimento/cópia.
2. Mapear cada SQL de leitura/escrita e sua tabela, inclusive ownership atual e constraints.
3. Especificar autenticação de usuário e transações OAuth de uso único, com TTL, PKCE quando suportado, vínculo a principal e finalidade.
4. Definir estratégia de sessão, CSRF, logout/revogação e proteção de endpoints.
5. Somente depois do schema e da estratégia de autenticação aprovados, desenhar migrações reversíveis e testes de isolamento.
6. Manter a branch isolada. Não integrar em `main`, implantar ou alterar serviços externos sem autorização específica.

## Limites desta auditoria

Leitura estática de código e metadados GitHub. Nenhum acesso ao banco Neon, painel Render, variáveis secretas, tokens, caixas de e-mail ou contas externas foi realizado.
