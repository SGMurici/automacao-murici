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
