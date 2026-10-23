# Automação Murici

Automação de publicações e análise de desempenho no LinkedIn.

## Diagnóstico operacional

- `GET /health`: confirma que o processo Flask responde. Não verifica banco de dados, credenciais ou integrações externas.
- `GET /readiness`: exige o cabeçalho `X-Publish-Secret` com o valor configurado em `PUBLISH_SECRET`. Informa quais variáveis obrigatórias estão ausentes e se as credenciais OAuth estão configuradas. Nunca retorna valores de segredos e não acessa nem altera o banco.
- `GET /db-test`: exige `X-Publish-Secret` e executa uma consulta simples ao PostgreSQL.

### Consultar /readiness

Use a URL base do ambiente que você já configurou, acrescentando `/readiness`, e envie o cabeçalho HTTP `X-Publish-Secret`. Não coloque a chave na URL, em capturas de tela ou em mensagens públicas.

Interpretação da resposta:
- HTTP `200` e `status: ready`: todas as variáveis obrigatórias avaliadas estão preenchidas; isso não prova que tokens, banco ou APIs externas estejam funcionando.
- HTTP `503` e `status: configuration_incomplete`: a lista `missing_settings` indica apenas os nomes das variáveis ausentes, nunca seus valores.
- HTTP `401` ou `403`: chave ausente ou inválida.

## Segurança e publicação

- Alterações de desenvolvimento devem ser feitas em uma branch separada e revisadas antes de integrar à `main`.
- Não ativar publicação automática, coleta automática de métricas, deploy ou migrações sem validação e autorização específicas.
- A coleta automática de analytics permanece desativada por padrão.
- Nunca registrar tokens OAuth, segredos de cliente ou a chave operacional em logs, URLs ou respostas HTTP.


## Armazenamento de imagens editoriais (em desenvolvimento)

A primeira implementação do endpoint `POST /google-drive/image-assets` está isolada na branch `ai-code-executor-bootstrap`. O endpoint exige `X-Publish-Secret`, aceita somente JPG/PNG/WEBP e limita imagens a 15 MiB. A gravação fica bloqueada por padrão por `GOOGLE_DRIVE_WRITE_ENABLED=false`; o escopo Google continua `drive.readonly` por padrão. A verificação de armazenamento inclui recuperação e comparação SHA-256, e a rota autenticada `GET /google-drive/image-assets/reconcile` faz uma reconciliação somente leitura. Não habilite a escrita nem faça deploy antes da revisão, reautorização OAuth e teste de recuperação descritos em [docs/IMAGE_STORAGE_PLAN.md](docs/IMAGE_STORAGE_PLAN.md).
