# automacao-murici
Automação de publicações e análise de desempenho no LinkedIn

Gmail triage: a rota interna retorna exclusivamente totais e classificações agregadas. Mensagens individuais, remetentes, assuntos, snippets e corpos nunca são incluídos na resposta HTTP, independentemente dos parâmetros enviados.

<!-- [run-gmail-triage] -->
<!-- Verificação agregada pós-ajuste de regras. -->

<!-- [run-gmail-triage] Validar classificação documental explícita após deploy de testes. -->

<!-- [run-gmail-triage] Revalidar classificação de contato de recrutador após deploy isolado de 02/11/2026. -->

<!-- Validar execução de triagem após refinamento documental. -->

<!-- Revalidar precedência de classificação em triagem agregada. -->



## Agenda Murici — calendário próprio

A arquitetura vigente utiliza calendário próprio/local-first. Este branch não solicita escopo Google Calendar, não consulta eventos externos e não oferece endpoint de validação de Calendar. O fluxo Google OAuth aqui permanece restrito ao Gmail read-only (e ao acesso Drive5 legado somente leitura quando solicitado).
