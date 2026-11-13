# Integração Gmail — leitura e triagem agregada

## Contas autorizadas

A lista operacional é fixa e limitada a:
- `SG`
- `Drive1`

`Drive2` e `Drive5` não são monitoradas pelo Gmail. Drive5 permanece separado para a operação interna de arquivos no Google Drive.

## Escopos OAuth

- SG e Drive1: `https://www.googleapis.com/auth/gmail.readonly` somente.
- Drive5: `https://www.googleapis.com/auth/drive.readonly` somente.
- Nenhum escopo de Calendar, Gmail modify, Gmail send ou Drive write.
- A rota de início OAuth é `POST /google/login`, exige `X-Publish-Secret` e recebe `{"account":"SG"}` ou `{"account":"Drive1"}`. O state OAuth é armazenado no servidor e vinculado ao browser ID.
- O callback consome state de uso único e valida que o Google concedeu o escopo esperado. Tokens são criptografados antes de persistir.
- O operador ainda precisa realizar a autorização manual de cada conta. Nenhum login foi iniciado nesta etapa.

## Triagem interna

Endpoint: `POST /internal/gmail/triage/run`

Autenticação: `X-Gmail-Monitor-Secret`, comparado em tempo constante. Se `GMAIL_MONITOR_SECRET` não estiver configurado, retorna 503. O segredo não é retornado pelo readiness.

Política de minimização:
- Consulta fixa: `newer_than:7d -in:sent`.
- Limite: no máximo 2 mensagens por conta em cada execução.
- Somente chamadas Gmail API GET.
- O conteúdo é classificado em memória; a resposta contém apenas contagens agregadas por categoria e prioridade.
- IDs de mensagem, remetente, assunto, snippet e corpo nunca são retornados.
- Parâmetros de consulta do cliente não ampliam o escopo nem habilitam detalhes.
- O endpoint usa advisory lock para impedir execuções concorrentes.
- Logs contêm somente status, contas autorizadas e contagens agregadas.
- Não envia, responde, marca, arquiva, exclui nem modifica mensagens.

## Execução e custos

- Nenhuma execução Gmail real está habilitada automaticamente.
- Não há job de CI que acesse contas reais ou Render.
- O workflow de backend executa apenas testes unitários e PostgreSQL com mocks; nenhum token Gmail real é necessário.
- O monitor só poderá ser ativado após configuração segura do segredo, autorização OAuth manual e aprovação operacional específica. A consulta é somente leitura, mas ainda processa dados pessoais; a minimização e a base legal devem ser documentadas.

## Calendário

O calendário do produto permanece próprio/local-first. Não há Google Calendar OAuth scope, rota ou job de verificação.
