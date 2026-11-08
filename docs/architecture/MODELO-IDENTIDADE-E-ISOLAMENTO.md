# Contrato de identidade, titularidade e isolamento

Status: desenho técnico para implementação isolada; ainda não integrado ao Flask nem ao PostgreSQL.

## Princípios obrigatórios

1. Cada pessoa possui identidade individual e autenticação própria.
2. Um usuário só acessa recursos cuja titularidade individual foi validada.
3. Plano familiar representa cobrança/benefício compartilhado, não compartilhamento de dados.
4. Pertencer à mesma família não concede acesso a e-mails, tokens OAuth, arquivos, histórico, posts, métricas ou preferências de outro membro.
5. Acesso administrativo, suporte e automações internas exigem papéis explícitos, auditáveis e de menor privilégio.
6. Ausência de identidade, titularidade ou tenant válido resulta em negação (fail closed).
7. IDs enviados pelo cliente nunca são prova de propriedade. O servidor resolve e valida titularidade no banco.
8. Jobs assíncronos carregam user_id e tenant_id verificados no momento da criação; não inferem identidade a partir de payload livre.
9. Tokens de provedores ficam associados a um usuário e conta conectada, criptografados no servidor. Segredos nunca retornam à interface nem aparecem em logs.
10. Exclusão/desconexão deve revogar credenciais quando suportado, interromper watch/sync, apagar ou anonimizar dados conforme política de retenção aprovada e registrar auditoria.

## Entidades conceituais

- users: identidade individual, status, timestamps; e-mail de login normalizado e único quando adotado como identificador.
- user_sessions: sessões revogáveis, hash do identificador de sessão, expiração, revogação e metadados mínimos.
- families: agrupamento para plano e cobrança, sem acesso implícito a dados.
- family_members: vínculo user-family, papel limitado ao contexto familiar e estado do convite/associação.
- connected_accounts: conta externa por usuário e provedor; identificador do provedor, endereço exibível, scopes concedidos, status, timestamps e referência segura ao segredo criptografado.
- oauth_transactions: state com hash, usuário iniciador, provedor, finalidade, redirect permitido, expiração, uso único e PKCE verifier protegido quando aplicável.
- audit_events: ator, ação, tipo/ID do recurso, resultado e instante; não armazenar corpo de e-mail, tokens ou segredos.
- email_sync_state: por connected_account, Gmail history cursor, watch expiration, último sucesso, erro sanitizado e estado.
- email_messages: por connected_account e identificador do provedor; metadados e conteúdo estritamente necessários, com política explícita de retenção.

## Regras de autorização

- Recurso pessoal: validar resource.user_id == principal.user_id.
- Recurso de integração: validar conta conectada pertence ao usuário autenticado antes de ler token ou chamar provedor.
- Recurso familiar: validar vínculo ativo ao grupo e papel requerido; isso só autoriza dados explicitamente familiares (ex.: plano), nunca dados pessoais de outros membros.
- Webhook Pub/Sub: autenticar origem/assinatura, validar envelope e mapear subscription/topic para conta previamente cadastrada; nunca aceitar user_id arbitrário no payload.
- Scheduler: resolver titularidade no servidor e carregar contexto verificado; credencial global de cron não substitui autorização de recurso.
- Rotas antigas com PUBLISH_SECRET: manter apenas para operações internas legadas durante migração; não usar como sessão de usuário nem expor ao frontend. Definir substituição e janela de remoção antes de ativar multiusuário.
- LinkedIn atual é uma conta global denominada LinkedIn Principal; não migrar automaticamente para modelo multiusuário sem decisão sobre titularidade e consentimento.

## Sequência segura de migração

1. Inventariar tabelas, chaves, constraints, rotas e chamadas de escrita existentes.
2. Criar migrations versionadas e reversíveis, sem executar em produção.
3. Introduzir identidade e autenticação em paralelo, mantendo rotas legadas isoladas.
4. Adicionar user_id/ownership às entidades pessoais com backfill explícito e auditável; registros sem titular conhecido permanecem em quarentena, nunca atribuídos por suposição.
5. Tornar obrigatória a autorização em cada endpoint, tarefa assíncrona e acesso a token.
6. Criar contas Gmail conectadas por usuário separadas de google_accounts/Drive5.
7. Executar testes de isolamento, migração em cópia sanitizada e revisão de segurança.
8. Planejar ativação, observabilidade e rollback. Só depois solicitar aprovação específica para produção.

## Bloqueios e decisões ainda necessárias

- Provedor e método de login (Google, e-mail/senha ou ambos), política de recuperação/MFA.
- Se família terá apenas titular pagador ou também papéis de gestão de assinatura.
- Política de retenção e exclusão de mensagens/metadados.
- Provedores de e-mail no MVP além do Gmail.
- Política de convite, remoção e transferência de titularidade familiar.

## Limites desta entrega

identity_policy.py contém apenas funções puras para testar decisões de autorização. Não autentica usuários, não protege rotas existentes e não deve ser tratado como barreira de segurança até sua integração com uma identidade validada e consultas SQL com ownership.
