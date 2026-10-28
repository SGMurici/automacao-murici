# Automação Murici — status operacional
Data da verificação: 2026-10-28

## Ambiente de testes confirmado
- Repositório: `SGMurici/automacao-murici`
- Branch: `drive5-art-upload-test`
- Serviço Render: `automacao-murici-testes-controlados`
- URL: https://automacao-murici-testes-controlados.onrender.com
- Serviço ID: `srv-dbedhu0n74is73ecnhg0`
- Workspace ID: `tea-daup2o142hec73fasv9g`
- Auto-deploy: desativado; alterações no branch não entram no ar até deploy manual.
- Produção: branch `main`, URL https://automacao-murici.onrender.com. Não alterar durante validação.

## Rotas relevantes já existentes no app.py de testes
Todas as rotas operacionais abaixo exigem o cabeçalho `X-Publish-Secret`; não registrar nem compartilhar o valor do segredo.
- `GET /google-drive/art-folder?account=Drive5`
- `GET /google-drive/files` (opcional: `?folder_id=<ID>`)
- `GET /google-drive/duplicates` (opcional: `?folder_id=<ID>`)
- `POST /google-drive/folders`
- `PATCH /google-drive/files/<file_id>` com exatamente um de `{"name":"..." }` ou `{"parent_id":"..." }`
- `POST /google-drive/files/<file_id>/trash` com confirmação literal `{"confirmation":"TRASH FILE <ID>"}`. A operação move para a lixeira; não exclui permanentemente.
- `POST /google-drive/upload` para upload genérico, limitado a 20 MiB.

## Auditoria de duplicatas registrada anteriormente
- Resultado informado: status `ok`, 298 itens analisados, 41 grupos de duplicatas.
- O endpoint agrupa arquivos por MD5 + tamanho e é somente leitura.
- A lista completa dos 41 grupos não está consolidada neste arquivo; exemplos vistos em mensagens anteriores não devem ser tratados como inventário completo.
- Não mover para a lixeira automaticamente arquivos que tenham nomes editoriais diferentes (por exemplo, `POST_051` e `POST_052`) sem verificar a relação com a planilha. A igualdade binária comprova conteúdo idêntico, mas não determina qual nome/associação editorial deve ser preservado.
- Priorizar cópias exatas redundantes com mesma identidade semântica/nome, mantendo pelo menos uma cópia e usando lixeira reversível.

## Pasta de teste previamente identificada
- `AUTOMACAO_MURICI_TESTES_UPLOAD`: `1kG1-6JjYlhwcPBpdTTWHAoHYC4RRqJ_Q`
- Subpasta `TESTE_AUTOMACAO_MURICI`: `1SNqfG8ffrYUZWp9Q9PkTnXf_5NeVdEfJ`
- Esses IDs identificam área de teste e não provam que toda a coleção editorial esteja dentro dela.

## Integridade editorial a preservar
- Posts/imagens 54–57: gerados no Recraft.
- Posts/imagens 58–60: gerados no Microsoft Designer.
- Não gerar imagens novas durante a etapa de auditoria/organização.
- Atualizar a planilha editorial somente com associações verificadas; não inferir mapeamentos por nome ou checksum isoladamente.

## Próximas ações seguras
1. Recuperar/consultar novamente o relatório completo de duplicatas através do endpoint autenticado do ambiente de testes.
2. Criar um plano de limpeza em modo somente leitura, agrupando cópias pelo checksum e distinguindo duplicatas de mesmo nome das colisões entre nomes editoriais diferentes.
3. Conferir a associação das imagens com a planilha editorial antes de qualquer movimentação.
4. Mover apenas cópias redundantes inequivocamente identificadas para a lixeira; registrar IDs e resultado por arquivo.
5. Verificar novamente inventário, pasta de destino e relatório de duplicatas.
6. Manter toda mudança de código em `drive5-art-upload-test` e validar antes de considerar qualquer promoção para `main`.

## Limitação operacional
O acesso ao repositório e ao estado do serviço Render está disponível; não há, neste contexto, um conector de Google Drive com acesso direto para executar mutações arbitrárias. A API do próprio app é o caminho autenticado existente. Nunca alegar que arquivos foram alterados sem resposta de sucesso da API e verificação posterior.
