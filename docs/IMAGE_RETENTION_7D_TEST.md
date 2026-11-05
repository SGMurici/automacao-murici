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
