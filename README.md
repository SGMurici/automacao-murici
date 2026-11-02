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
