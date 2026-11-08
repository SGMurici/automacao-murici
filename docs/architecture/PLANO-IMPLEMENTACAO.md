# Plano de implementação — branch integracao-base-2026-11-07

## Fase 0 — Segurança e inventário
- [x] Criar branch isolada a partir da main.
- [x] Registrar decisões aprovadas de agendamento e e-mail.
- [ ] Inventariar rotas, dependências, configuração e modelo atual de fila.
- [ ] Identificar contratos e limitações atuais de autenticação, sessão e persistência.
- [ ] Definir ambiente de teste isolado sem credenciais ou dados de produção.

## Fase 1 — Contratos e testes do agendador
- [ ] Especificar estados e transições da fila.
- [ ] Projetar lease, idempotência e recuperação de tarefas travadas.
- [ ] Projetar dispatcher e watchdog de reconciliação separados.
- [ ] Definir adaptador de publicação LinkedIn e comportamento de resultado incerto.
- [ ] Criar testes unitários e de integração com provedor simulado.
- [ ] Preservar a cadência atual em produção até validação completa.

## Fase 2 — Contrato de e-mail Gmail
- [ ] Definir modelo por usuário/conta conectada e armazenamento seguro de tokens.
- [ ] Mapear OAuth e escopos mínimos para leitura e notificações.
- [ ] Projetar endpoint Pub/Sub autenticado e validação de notificações.
- [ ] Implementar watch, renovação, cursor de histórico e reconciliação.
- [ ] Implementar consulta posterior à notificação e sincronização incremental.
- [ ] Testar duplicidade, atraso, perda, expiração, revogação e isolamento.
- [ ] Garantir ausência de operações de escrita na API de e-mail.

## Fase 3 — Identidade e isolamento
- [ ] Definir identidade individual e autorização por recurso.
- [ ] Cobrir isolamento entre usuários em todos os endpoints e tarefas assíncronas.
- [ ] Separar titularidade de dados de cobrança familiar.
- [ ] Testar revogação de sessão e consentimento OAuth.

## Fase 4 — Validação e entrega
- [ ] Rodar lint, testes, análise de dependências e revisão de segurança.
- [ ] Documentar migrações e rollback sem executar em produção.
- [ ] Apresentar evidências e abrir PR em modo Draft.
- [ ] Solicitar aprovação explícita antes de deploy, migração ou ativação de integrações reais.

## Restrições permanentes desta etapa
- Não alterar main diretamente.
- Não modificar Render, cronjob, Neon de produção ou contas externas.
- Não publicar posts reais nem criar posts de teste em produção.
- Não habilitar escopos OAuth adicionais em contas reais.
- Não expor conteúdo de e-mail entre usuários ou membros de plano familiar.
