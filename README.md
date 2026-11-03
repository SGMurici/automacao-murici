# automacao-murici
Automação de publicações e análise de desempenho no LinkedIn

Gmail triage: a rota interna retorna somente totais agregados por padrão. Detalhes individuais exigem `summary_only=false` explícito.

<!-- [run-gmail-triage] -->
<!-- Verificação agregada pós-ajuste de regras. -->

<!-- [run-gmail-triage] Validar classificação documental explícita após deploy de testes. -->

<!-- [run-gmail-triage] Revalidar classificação de contato de recrutador após deploy isolado de 02/11/2026. -->

<!-- Validar execução de triagem após refinamento documental. -->

<!-- Revalidar precedência de classificação em triagem agregada. -->



## Google Agenda — autorização somente leitura (conta SG)

A integração inicial da Agenda usa exclusivamente a conta SG e o escopo
`https://www.googleapis.com/auth/calendar.readonly`. A autorização também
mantém o escopo Gmail somente leitura já utilizado pelo monitoramento.

Para iniciar a autorização, acesse:

`/google/login?account=SG&purpose=calendar_readonly`

O callback OAuth é `/google/callback`. Em ambiente de testes, configure
`GOOGLE_REDIRECT_URI` para a URL de callback do serviço de testes e confirme
que essa URL exata está cadastrada como URI de redirecionamento autorizado no
cliente OAuth do Google Cloud. Não reutilize o callback de produção para testar.

Após concluir a autorização, valide o acesso por
`GET /google-calendar/check`, autenticando com o segredo interno já usado
pelas rotas administrativas. A validação consulta no máximo um identificador
de evento futuro e retorna somente uma contagem agregada; não expõe títulos,
horários, convidados ou descrições.

A integração permanece somente leitura. Criação, alteração, resposta a convite
e exclusão de eventos não fazem parte desta etapa.

<!-- run-gmail-triage -->

<!-- Controlled Calendar read-only verification trigger -->


## WhatsApp Cloud API — ambiente isolado de testes

A primeira integração usa exclusivamente o número de teste fornecido pela Meta.
O número pessoal do proprietário não deve ser conectado, migrado, registrado ou
usado como remetente ou destinatário de testes.

O módulo `whatsapp_cloud_api.py` está isolado: não cria rotas Flask, não é chamado
por tarefas agendadas e não envia mensagens automaticamente. O envio só pode
ser iniciado explicitamente por código de teste/operação, com as duas variáveis
abaixo habilitadas e com o destinatário presente na lista de números de teste
permitidos pela Meta:

- `WHATSAPP_TEST_MODE=true`
- `WHATSAPP_TEST_SEND_ENABLED=true`
- `WHATSAPP_TEST_RECIPIENTS` — números internacionais autorizados na Meta,
  separados por vírgula, sem compartilhar a lista em logs.
- `WHATSAPP_ACCESS_TOKEN` — token de teste, armazenado como segredo do ambiente.
- `WHATSAPP_PHONE_NUMBER_ID` — ID do número de teste da Meta.
- `WHATSAPP_GRAPH_API_VERSION` — versão Graph API confirmada no painel/documentação.
- `WHATSAPP_TEST_TEMPLATE=hello_world` e
  `WHATSAPP_TEST_TEMPLATE_LANGUAGE=en_US` — template padrão de teste.

O módulo envia somente templates, nunca texto livre. A primeira prova de ponta
a ponta deve usar o template `hello_world` da Meta e um destinatário de teste
não pessoal, autorizado e verificado. Não configure destinatários reais de
clientes nesta fase.

A função `build_email_summary_message` gera apenas uma prévia com contagens
agregadas. Ela não inclui remetentes, assuntos, trechos, corpos, identificadores
ou códigos extraídos dos e-mails. O envio do resumo ainda não está conectado ao
Gmail; para mensagens iniciadas pela empresa em produção, será necessário um
template aprovado adequado e os controles de consentimento aplicáveis.

### Configuração manual na Meta

1. Entre em [Meta for Developers](https://developers.facebook.com/) com a conta
   que administrará o ativo empresarial da Automação Murici.
2. Abra **My Apps / Meus aplicativos** e crie ou selecione um aplicativo do tipo
   **Business**. Não crie nem conecte um número pessoal.
3. No painel do aplicativo, adicione o produto **WhatsApp** e abra **API Setup**
   ou **Getting Started**.
4. Use o número de teste gerado pela Meta. Copie o **Phone Number ID** e o token
   temporário apenas para os campos de segredo do ambiente de testes; não os
   envie por chat, issue, commit ou log.
5. Em **To / Manage phone number list**, adicione somente um destinatário de
   teste que não seja o número pessoal do proprietário. A Meta exige a
   verificação desse destinatário.
6. Confirme a versão Graph API exibida na documentação/painel atual e configure
   os segredos acima no serviço Render de testes, nunca no serviço de produção.

Não prossiga se a Meta solicitar registrar, migrar ou verificar o número pessoal.
A integração não usa QR Code, WhatsApp Web, clientes não oficiais ou bibliotecas
que imitam o aplicativo.

### Estado e limites

- Nenhuma mensagem foi enviada por esta implementação.
- Não há webhook, agendamento ou envio automático.
- Não há integração com destinatários de clientes.
- A produção e a branch `main` permanecem intocadas.
- A Cloud API de produção exigirá um número empresarial dedicado e elegível,
  opt-in dos destinatários, templates aprovados quando aplicável, controles de
  privacidade e observância das políticas da Meta.
