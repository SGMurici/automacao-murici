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
