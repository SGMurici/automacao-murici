# Bootstrap controlado do primeiro administrador global

## Objetivo

Conceder o primeiro privilégio de administrador da plataforma KAPPA sem confundir esse papel com `owner` ou `admin` de um tenant.

## Pré-condições obrigatórias

1. O usuário já concluiu cadastro e verificação de identidade no KAPPA.
2. Murici confirmou explicitamente qual conta verificada deve receber o privilégio.
3. O operador obteve o UUID do usuário por uma consulta autenticada e controlada ao banco de ambiente correto.
4. A migration `0012_global_administrators.sql` foi aplicada nesse ambiente.
5. O procedimento será executado por conexão administrativa controlada, com registro do operador, horário, ambiente e justificativa.

Não localizar usuário por e-mail presumido, não inferir UUID, não criar conta para contornar a ausência de identidade e não aceitar autoelevação por rota HTTP.

## Verificação prévia somente leitura

Substitua o UUID confirmado no comando abaixo. A consulta deve retornar exatamente um usuário com estado `active`.

```sql
SELECT id, status, created_at
FROM app_users
WHERE id = '<UUID_CONFIRMADO>'::uuid;
```

Se não retornar exatamente um usuário ativo, interrompa. Não tente corrigir o estado do usuário por este procedimento.

## Concessão transacional

Execute somente após a confirmação expressa da conta e em conexão administrativa do ambiente correto:

```sql
BEGIN;

SELECT id
FROM app_users
WHERE id = '<UUID_CONFIRMADO>'::uuid
  AND status = 'active'
FOR UPDATE;

INSERT INTO global_administrators
    (user_id, status, granted_at, granted_by, grant_reason)
SELECT id, 'active', NOW(), NULL,
       'Primeiro administrador global: bootstrap controlado aprovado por Murici'
FROM app_users
WHERE id = '<UUID_CONFIRMADO>'::uuid
  AND status = 'active'
ON CONFLICT (user_id) DO NOTHING;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM global_administrators
        WHERE user_id = '<UUID_CONFIRMADO>'::uuid
          AND status = 'active'
          AND revoked_at IS NULL
    ) THEN
        RAISE EXCEPTION 'Bootstrap não concedeu um administrador global ativo';
    END IF;
END
$$;

INSERT INTO audit_events
    (id, actor_user_id, action, resource_type, resource_id,
     result, occurred_at, metadata)
VALUES
    (gen_random_uuid(), '<UUID_CONFIRMADO>'::uuid,
     'global_admin.bootstrap', 'global_administrator',
     '<UUID_CONFIRMADO>',
     'success', NOW(),
     '{"method":"controlled_database_bootstrap","approved_by":"Murici"}'::jsonb);

COMMIT;
```

Se qualquer etapa falhar, a transação deve ser revertida. Se já existir registro revogado/suspenso, o `ON CONFLICT DO NOTHING` não o reativa; interrompa e faça revisão específica, sem atualizar estado automaticamente.

## Verificação posterior

```sql
SELECT g.user_id, g.status, g.granted_at, g.granted_by,
       g.grant_reason, g.revoked_at, u.status AS user_status
FROM global_administrators AS g
JOIN app_users AS u ON u.id = g.user_id
WHERE g.user_id = '<UUID_CONFIRMADO>'::uuid;
```

O resultado esperado é `g.status = 'active'`, `g.revoked_at IS NULL` e `user_status = 'active'`.

## Limites

- Não executar em produção até autorização de rollout específica.
- Não expor UUID, e-mail ou dados pessoais em logs, tickets ou frontend.
- Não criar endpoint público de concessão, bootstrap ou autoelevação.
- Revogar ou suspender a concessão global antes de permitir exclusão da conta que a possui.
- A existência desta tabela não significa que já exista console administrativo nem que as rotas administrativas estejam protegidas. Cada rota futura deve chamar `require_global_admin` após validar a sessão.
