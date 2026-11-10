# KAPPA — backup automático no Google Drive do cliente

## Decisão aprovada

O KAPPA terá armazenamento local Android como fonte primária e backup externo na conta Google do próprio cliente. O Drive será destino de cópia de segurança, nunca banco de dados operacional. O cliente poderá configurar backup automático e iniciar um backup manual.

## Arquitetura

1. O app cria um snapshot consistente dos dados locais.
2. O snapshot é compactado e criptografado no aparelho antes de qualquer upload.
3. O app envia o arquivo criptografado à conta Google autorizada pelo próprio cliente.
4. O app valida tamanho, checksum, versão do formato e confirmação do upload.
5. A restauração baixa o arquivo, verifica integridade e autentica a chave antes de importar os dados.

A indisponibilidade do Drive não pode bloquear o uso local/offline.

## Agendamento Android

Usar WorkManager com trabalho único periódico e restrições configuráveis. O sistema operacional pode adiar a execução; não prometer horário exato. Preferências previstas: diário/semanal/mensal, somente Wi-Fi, somente carregando e execução manual. Implementar retry com backoff, retomada idempotente de upload e limpeza de temporários.

## Criptografia e recuperação

- AES-256-GCM no aparelho, com nonce exclusivo por arquivo e autenticação do cabeçalho/metadados.
- A chave de restauração não pode depender exclusivamente do Android Keystore do aparelho antigo.
- Oferecer senha de backup forte ou chave de recuperação que o cliente guarde separadamente.
- Explicar claramente que perder a chave pode tornar os backups irrecuperáveis.
- Não incluir tokens OAuth, segredos de sessão ou credenciais no arquivo.
- Não registrar conteúdo, chave ou senha em logs.

O formato do arquivo deve ser versionado e conter apenas metadados mínimos: versão do formato, versão do app/schema, data de criação, salt/nonce, algoritmo, tamanho e checksum autenticado. Não colocar nome, e-mail ou outros identificadores pessoais em nomes de arquivos quando desnecessário.

## Google Drive e OAuth

A integração de backup é por cliente e deve ser isolada por usuário/tenant. Não reutilizar a conta operacional global Drive5 nem as tabelas/credenciais globais de integrações legadas. Solicitar somente escopos necessários, permitir desconexão e revogação e tratar refresh token como segredo.

A preferência de produto é uma pasta visível KAPPA/Backups, para o titular poder localizar e gerenciar suas cópias. Antes de implementar, comparar o escopo de API necessário com appDataFolder: este último é oculto na interface normal do Drive e pode frustrar a gestão manual. Confirmar a experiência de seleção da conta e os requisitos de verificação OAuth do Google.

A escolha final do fluxo OAuth ainda depende do app Android, do modelo de ameaça e da política de credenciais. Evitar guardar tokens duradouros no frontend ou em backups. Se houver backend intermediário, tokens devem ser segregados por usuário/tenant, criptografados em repouso e revogáveis.

## Histórico e restauração

Manter número limitado de versões e política clara de retenção. Um backup completo periódico pode ser combinado com incrementais apenas depois de garantir consistência, cadeia de dependências e recuperação após arquivo perdido/corrompido. Não implementar incrementais como requisito inicial se aumentarem risco de restauração.

A restauração deve ocorrer em staging: baixar, validar autenticidade, descriptografar, validar schema e mostrar resumo; só então substituir/importar dados após confirmação. Nunca sobrescrever a base atual com backup truncado, corrompido, adulterado ou incompatível. Preservar cópia de segurança local antes da substituição quando tecnicamente possível.

## Exclusão de conta e tombstones

O processo de exclusão deve apagar todas as cópias KAPPA na conta Drive autorizada e revogar a integração quando apropriado. Backups antigos não podem ressuscitar dados excluídos: manter tombstones de exclusão fora do snapshot restaurável e reaplicá-los após qualquer restauração. A exclusão só pode ser declarada concluída após evidência de remoção em cada destino aplicável, respeitando retenções legais justificadas.

## Política inicial de versões — proposta para validação

- Backup completo inicial.
- Backups incrementais apenas após testes de consistência e recuperação; caso contrário, snapshots completos.
- Reter até 7 versões recentes, com retenção por tempo configurável posteriormente.
- Não apagar a última cópia válida até a nova cópia ter upload e verificação confirmados.
- Informar espaço insuficiente e permitir gestão manual.

Os números acima são proposta técnica inicial, não compromisso comercial final.

## Critérios de aceite

- Arquivo no Drive sempre criptografado antes do upload.
- Restauração validada em outro aparelho/instalação.
- Integridade e compatibilidade verificadas antes de importar.
- Falhas de rede, quota, espaço, OAuth revogado e interrupção recuperáveis.
- Dados eliminados não reaparecem após restauração.
- Isolamento por usuário/tenant e testes de acesso cruzado.
- UX e política de privacidade explicam frequência, destino, criptografia, chave de recuperação, retenção e exclusão.

## Pendências antes da implementação Android

- Identificar repositório/framework e schema real do app Android.
- Inventariar dados locais incluídos e excluídos.
- Fechar UX de conta Google e escopos OAuth.
- Fechar formato e estratégia de chaves/recuperação.
- Definir política final de retenção e limites de versão.
- Testar em aparelhos reais, incluindo troca de aparelho, offline, bateria otimizada, pouco espaço, rede interrompida, revogação e exclusão.


## Refinamentos confirmados na documentação oficial do Android e Google Drive

- OAuth scope preferencial: `https://www.googleapis.com/auth/drive.file` (não sensível), porque o KAPPA cria e gerencia seus próprios arquivos/pasta; evitar `drive` e `drive.readonly` de acesso amplo. A pasta visível KAPPA/Backups deve ser criada pelo próprio app para permanecer dentro do escopo por arquivo. Se o produto exigir acesso a arquivos existentes escolhidos pelo usuário, avaliar Google Picker e consentimento explícito.
- Não usar `appDataFolder` como destino principal se a exigência é o cliente localizar e gerir os arquivos na interface normal do Drive: é uma área oculta da aplicação.
- Upload de backup móvel deve preferir `uploadType=resumable` quando o arquivo for grande ou houver risco de interrupção. A API permite consultar o estado e retomar o upload; o URI de sessão expira após uma semana e deve ser tratado como dado sensível/capacidade temporária.
- WorkManager periódico respeita restrições de rede, bateria e carregamento, mas não garante horário exato. A periodicidade mínima técnica é 15 minutos; a experiência do KAPPA oferecerá opções mais úteis (diária/semanal/mensal), não esse intervalo mínimo.
- Com Wi-Fi e carregamento configurados como restrições simultâneas, o trabalho só executa quando ambas forem atendidas; se não ocorrerem, o backup pode atrasar. A tela deve mostrar última execução e próxima tentativa estimada sem prometer horário fixo.


## Reuso da fundação de identidade já existente

A migration `migrations/0002_identity_core.sql` já cria `external_connections`, com `user_id`, `tenant_id`, `provider`, `external_account_id`, `granted_scopes`, campos de access/refresh token criptografados, expiração, estado e revogação. Portanto, não criar uma segunda tabela genérica de integrações para o Drive do cliente sem necessidade comprovada. Se o desenho final exigir tokens no backend, reutilizar essa estrutura após implementar e testar OAuth por usuário/tenant, criptografia, refresh, rotação, revogação e auditoria. A integração operacional legada (`google_accounts`/Drive5) permanece separada e nunca deve ser associada automaticamente a clientes.

A implementação de backup ainda depende de localizar o repositório Android correto. No GitHub conectado, o único repositório acessível atualmente é `SGMurici/automacao-murici`, que contém o backend Python; não foi encontrado um projeto Android/Kotlin/Flutter nesse acesso. Não criar um app paralelo nem presumir stack enquanto o repositório real não estiver identificado.


## Implementação backend — persistência isolada de conexão (lote 11/11/2026)

Foi criado `drive_backup_connections.py` para reutilizar `external_connections` sem duplicar tabela. A camada oferece salvar/atualizar, recuperar credenciais para o titular, atualizar tokens, revogar apagando ciphertext e listar apenas metadados. Toda leitura/escrita é restrita por user_id + tenant_id + provider. O upsert exige usuário ativo e membership ativa e não permite sobrescrever conexão do mesmo tenant pertencente a outro usuário.

- Provider interno: `google_drive_backup`, separado do Drive operacional.
- Exige o escopo `https://www.googleapis.com/auth/drive.file` e rejeita `drive`/`drive.readonly` amplos.
- Access/refresh tokens são criptografados por função injetada antes de persistir em BYTEA; não são retornados em listagens.
- A revogação marca estado `revoked` e remove os ciphertexts locais; a revogação remota no Google ainda precisa ser chamada pelo adaptador OAuth antes/de forma coordenada.
- Testes unitários cobrem escopos, associação a usuário/tenant, confidencialidade, atualização, revogação e listagem.

**Limite importante:** esta camada é persistência e controle de propriedade, não o fluxo OAuth completo. Só pode ser chamada depois de validar state + PKCE, trocar o código e validar o Google subject e os escopos. O fluxo mobile/Android ainda não foi implementado porque o repositório Android não foi localizado. O backend não deve aceitar tokens arbitrários enviados por um cliente sem prova verificável de origem.


## Preparação OAuth do cliente — state + PKCE (lote 11/11/2026)

- Migration `0004_customer_drive_oauth.sql` amplia `oauth_states` sem alterar a semântica das linhas legadas: adiciona purpose, user_id, tenant_id, ciphertext do PKCE verifier e redirect URI; fluxo de cliente exige vínculo tenant/user e verifier cifrado.
- `drive_backup_oauth.py` cria state aleatório com TTL de 10 minutos, calcula PKCE S256, guarda apenas SHA-256 do state e verifier criptografado, exige usuário e membership ativos e monta URL com escopo mínimo `drive.file`.
- O consumo usa `DELETE ... RETURNING`, validando provider/purpose/expiração e tornando o state de uso único. Retorna contexto do titular e verifier para a futura troca server-side.
- Testes unitários cobrem PKCE, escopo, membership, HTTPS redirect, state de uso único, expiração e falha de descriptografia.

**Ainda não é um OAuth funcional ponta a ponta:** faltam rota autenticada de início, callback server-side, troca do authorization code com PKCE, validação do Google subject/userinfo, persistência dos tokens com `drive_backup_connections.py`, renovação/revogação remota e deep-link/UX Android. A migration não foi aplicada em banco algum; PR continua Draft.


## Estado do lote de implementação — 11/11/2026

### Arquivos adicionados
- `migrations/0004_customer_drive_oauth.sql`: vincula estados OAuth temporários ao user/tenant e guarda PKCE verifier criptografado; mantém estados legados isolados com purpose `legacy`.
- `drive_backup_oauth.py`: cria fluxo state + PKCE S256 de 10 minutos, exige usuário e membership ativos, guarda hash do state e verifier cifrado e consome o state atomicamente uma única vez.
- `drive_backup_connections.py`: persistência de tokens e metadados por usuário/tenant, criptografia via função injetada, escopo mínimo `drive.file`, leitura restrita ao titular, listagem sem tokens e revogação local com apagamento de ciphertext.
- `tests/test_drive_backup_oauth.py` e `tests/test_drive_backup_connections.py`: testes unitários.
- `tests/test_identity_migrations_postgres.py`: migração 0004 incluída e novos testes de integração PostgreSQL para state/PKCE, conexão, isolamento de titular e revogação local.

### Decisões mantidas
- Não usar integração global Drive5 para clientes.
- Não criar tabela de conexão duplicada; reutilizar `external_connections`.
- Tokens são segredos: armazenar somente ciphertext e nunca retornar em listagens.
- State OAuth é armazenado como SHA-256 e consumido por DELETE RETURNING; PKCE verifier fica criptografado e expira em 10 minutos.
- Escopo `drive.file` é obrigatório; escopos globais `drive` e `drive.readonly` são rejeitados.

### Pendências antes de conectar uma conta real
- Implementar rotas autenticadas para iniciar o fluxo e callback server-side.
- Trocar authorization code usando o verifier PKCE e redirect URI exata.
- Consultar Google userinfo e validar `sub` como identificador externo estável e escopos efetivamente concedidos.
- Persistir tokens com Fernet/`TOKEN_ENCRYPTION_KEY`; implementar refresh, revogação remota e reconciliação de falhas.
- Criar UI Android e deep-link de retorno, testar app Android e fluxo de consentimento OAuth/verificação Google.
- Não aplicar migration 0004 nem habilitar cliente real até revisão do callback e testes de integração.
