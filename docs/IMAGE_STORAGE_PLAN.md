# Armazenamento persistente de imagens editoriais

**Prioridade:** P0 — não retomar geração em lote até a persistência estar implementada e validada.

## Problema confirmado na inspeção do código

O aplicativo já tem funções para obter/renovar o token do Google Drive e listar os metadados da pasta indicada por `GOOGLE_DRIVE_ART_FOLDER_ID`. A inspeção inicial não identificou upload de arquivos de imagem nem uma confirmação de integridade após gravação. A integração de leitura, por si só, não impede que imagens se percam.

## Desenho proposto

1. **Gerar uma imagem por vez.** Cada resultado recebe um identificador editorial estável (ex.: `post-041`) e uma versão.
2. **Persistir imediatamente.** Enviar o conteúdo binário ao Google Drive usando a integração existente, desde que a autorização atual tenha escopo de escrita. Não presumir que isso esteja autorizado.
3. **Confirmar o upload.** Exigir ID de arquivo retornado pela API; consultar os metadados do arquivo e confirmar nome, tamanho e tipo. Calcular SHA-256 do conteúdo local antes do envio e verificar o conteúdo recuperado quando possível.
4. **Registrar o manifesto.** Manter metadados persistentes em PostgreSQL, se a conexão e o esquema existentes permitirem: post, versão, nome, Drive file ID, MIME type, tamanho, SHA-256, prompt/referência, ferramenta, status e timestamps. Não armazenar bytes da imagem no banco.
5. **Idempotência e versões.** Usar chave idempotente baseada no identificador do post, versão e hash. Uma repetição do mesmo arquivo deve reconhecer o item existente; uma imagem diferente cria nova versão e nunca substitui silenciosamente a anterior.
6. **Falha segura.** Estados mínimos: `pending`, `uploading`, `stored`, `verification_failed`, `failed`. Somente `stored` após confirmação. Retry limitado com backoff; nenhuma confirmação fictícia.
7. **Reconciliação e recuperação.** Comparar o manifesto com a pasta real do Drive, apontando arquivos ausentes, duplicatas e arquivos sem registro. Permitir recuperar o arquivo original a partir do ID do Drive e validar o hash.
8. **Auditoria e privacidade.** Não registrar tokens, segredos ou bytes em logs; não usar Git, armazenamento efêmero do servidor ou histórico do chat como cópia principal.
9. **Backup.** Documentar como exportar o manifesto e como recuperar as imagens do Drive. O Drive é o armazenamento primário proposto; a necessidade de uma segunda cópia durável deve ser avaliada antes da operação em lote.

## Restrições de segurança

- Todo o desenvolvimento permanece na branch `ai-code-executor-bootstrap`.
- Nenhum deploy, merge, alteração de segredo, reautorização OAuth ou mudança em produção.
- Não executar escrita no Google Drive real nem criar pastas de teste sem autorização explícita.
- Não presumir que o escopo OAuth atual permita upload. Se não permitir, parar e pedir autorização antes de alterar permissões.
- Validar primeiro com testes simulados e arquivo sintético; o teste real só ocorre após autorização específica.

## Critérios de aceite

- Upload retorna sucesso somente após o arquivo existir no Drive.
- Arquivo pode ser recuperado e seu SHA-256 comparado ao original.
- O manifesto mantém vínculo exato com o post e versão.
- Repetições são idempotentes e não sobrescrevem conteúdo.
- Falhas simuladas não deixam um item marcado como armazenado.
- A reconciliação detecta registros sem arquivo e arquivos sem registro.
- Instruções de recuperação são claras para uso no celular.

## Bloqueios que exigem intervenção do usuário

A validação real depende de confirmar que a conta Google já autorizada tem permissão de escrita na pasta de artes e de aprovar um teste de upload de arquivo sintético. Não é necessário compartilhar tokens ou segredos na conversa.

## Bloqueio técnico confirmado no OAuth atual

A rota de autorização Google no código solicita explicitamente o escopo `https://www.googleapis.com/auth/drive.readonly`. Esse escopo permite leitura, não upload de novas imagens. Portanto, mesmo que a listagem funcione, o fluxo de persistência não poderá gravar arquivos com a autorização atual. O código também contém uma rota de teste que tenta criar uma pasta; ela não deve ser tratada como prova de que a permissão de escrita está concedida.

Para permitir uploads será necessário alterar o escopo solicitado para um escopo de escrita apropriado e reautorizar a conta Google. Isso amplia as permissões concedidas à aplicação e, por isso, **não será feito sem autorização explícita do usuário**. Até lá, o desenvolvimento pode avançar com implementação isolada e testes simulados, mas o armazenamento real continuará bloqueado.
