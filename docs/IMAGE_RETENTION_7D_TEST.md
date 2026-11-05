# Política de retenção de imagens — implementação de teste

## Estado
Implementação inicial isolada na branch `drive-image-retention-7d-test`. Apenas planejamento em modo dry-run. Não há exclusão, movimentação para lixeira, alteração de Drive, alteração de banco, publicação ou deploy.

## Regra
Uma imagem só pode ser considerada elegível quando:
- há referência única e explícita ao arquivo no Google Drive;
- o MIME type começa com `image/`;
- há vínculo com um registro editorial;
- o status editorial está confirmado como `publicado`;
- `published_at` contém timezone explícito;
- completaram-se sete dias integrais desde `published_at`.

O horário de referência é UTC, preservando o instante absoluto do timestamp publicado. A comparação é inclusiva no instante exato em que se completam sete dias.

## Proteções
- Registros sem timestamp, com timestamp sem timezone, sem vínculo, duplicados ou não publicados são excluídos do plano.
- O módulo não chama a API do Drive nem executa SQL.
- O plano declara explicitamente `destructive: false`.
- Histórico editorial/LinkedIn, texto, IDs, datas, métricas, status e fila não são modificados.
- Não há reenvio, requeue ou regeneração de arte.
- Período de retenção fixo em sete dias; não pode ser alterado por parâmetro.

## Pendências antes da integração operacional
1. Confirmar o esquema real da tabela/manifesto de imagens na branch de integração e sua relação com `editorial_posts`.
2. Garantir que cada upload registre `drive_file_id`, MIME type e `editorial_post_id` sem inferir associação por nome de arquivo.
3. Definir se a exclusão aprovada será mover para lixeira ou exclusão permanente.
4. Integrar relatório dry-run autenticado, paginação completa, auditoria e alertas.
5. Testar com arquivos fictícios em pasta de teste.
6. Exigir autorização separada antes de qualquer exclusão real ou mudança de produção.

## Testes
`python -m unittest tests/test_image_retention.py`

## Integração de leitura no backend de teste
Foi adicionada a rota autenticada `GET /google-drive/image-retention/dry-run`.
Ela consulta somente:
- `project_assets.drive_file_id`, `mime_type`, `post_id` e `asset_status`;
- `editorial_posts.status` e `published_at`, por meio de `project_assets.post_id = editorial_posts.id`.

A rota considera somente ativos com `asset_status = 'stored'` e referência de Drive presente. O planejador exclui itens sem publicação confirmada, vínculo editorial válido ou timestamp com timezone. A resposta informa `drive_api_called: false` e `database_modified: false`.

A existência das colunas e da FK foi verificada por leitura do esquema da branch de testes Neon `murici-controlled-tests-20261024`. Nenhuma consulta de dados de clientes foi feita e nenhuma alteração SQL foi executada.

## Validação pendente
A branch GitHub não está implantada no serviço Render de testes; portanto, a rota ainda não foi executada via HTTP. Os testes unitários foram adicionados, mas a execução CI ainda não foi observada. Não há operação de exclusão implementada.


## Executor de exclusão permanente — implementação isolada

Foi adicionado `image_retention_executor.py`, com dependências injetadas para leitura atual do registro, leitura de metadados do Drive, exclusão permanente e atualização do estado do ativo. O módulo:
- revalida o registro e exige `asset_status = 'stored'`;
- recalcula a elegibilidade com a regra fixa de sete dias;
- exige identidade do arquivo, MIME type de imagem e presença na pasta de testes configurada;
- só atualiza o estado do ativo após confirmação da exclusão pelo Drive;
- em caso de falha ao atualizar o banco depois da exclusão no Drive, informa necessidade de reconciliação;
- não recebe nem altera registros editoriais, fila ou métricas do LinkedIn.

Foram adicionados testes em `tests/test_image_retention_executor.py` cobrindo caminho válido e falhas de segurança. Os testes ainda precisam ser executados em CI ou ambiente Python controlado. O executor ainda não foi conectado a uma rota HTTP nem habilitado em serviço; não há execução operacional, exclusão real, deploy ou alteração de produção.

Antes de conectar a rota, ainda é necessário implementar bloqueio transacional/concorrência durante a operação, política explícita para HTTP 404 (arquivo já ausente), auditoria de reconciliação e um modo de simulação que nunca chame DELETE.


## Proteções adicionais do executor

O executor agora exige um gerenciador de lock por ativo, mantido durante releitura, validação, chamada ao Drive e atualização do estado. A integração deverá implementar esse callback com lock transacional/linha no banco de testes, impedindo execuções concorrentes para o mesmo ativo.

A resposta `already_deleted` só pode ser emitida pelo adaptador Drive após resposta HTTP 404 autoritativa para o mesmo ID; outros erros de rede/autorização não podem ser convertidos nesse estado. O executor registra auditoria de exclusão concluída e de reconciliação necessária quando o Drive exclui mas o banco não confirma a atualização.

Os testes agora cobrem lock, metadados ausentes, idempotência explícita e auditoria. Nenhum workflow GitHub Actions foi encontrado para o commit mais recente; portanto, os testes não estão declarados como executados ou aprovados.

A rota operacional continua deliberadamente não integrada. A integração real depende de confirmar que o serviço de testes está ligado à branch Neon `murici-controlled-tests-20261024`, validar a pasta de teste e garantir uma chave de habilitação destrutiva desativada por padrão. Até isso acontecer, não há chamada DELETE disponível pela rota de retenção.


## CI automatizada

Foi criado `.github/workflows/image-retention-tests.yml`. O workflow executa `python -m unittest discover -s tests -p "test_image_retention*.py" -v` em Python 3.12 quando arquivos do planejador, executor ou testes são alterados na branch de trabalho, e também em pull requests para `main`. A criação do workflow foi registrada; a execução e o resultado ainda precisam ser confirmados no GitHub Actions.

A rota de execução continua não integrada e não há deploy. A integração depende de confirmar o workspace Render e o ambiente de testes, além de configurar explicitamente o bloqueio por ambiente/branch e a pasta de teste. Nenhuma operação destrutiva foi executada.
