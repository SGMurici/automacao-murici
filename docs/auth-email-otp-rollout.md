# Rollout controlado de cadastro e login por e-mail — KAPPA

## Estado da implementação

As rotas de solicitação e verificação de OTP foram adicionadas ao backend, mas permanecem **desabilitadas por padrão**. O recurso só responde após configuração explícita de \`AUTH_ROUTES_ENABLED=true\` e de todos os segredos e parâmetros de proxy. Não há credenciais SMTP ou segredos de autenticação configurados no Render.

Rotas preparadas:

- \`POST /api/v1/auth/signup/request\`
- \`POST /api/v1/auth/signup/verify\`
- \`POST /api/v1/auth/login/request\`
- \`POST /api/v1/auth/login/verify\`

A solicitação retorna resposta genérica e identificador de desafio, sem confirmar se a conta existe. A solicitação de cadastro exige aceite explícito dos termos e confirmação de leitura do aviso de privacidade. As versões são registradas no evento de consentimento e na auditoria. A verificação bem-sucedida ativa o usuário, verifica o e-mail, cria tenant pessoal e associação owner na mesma transação e emite sessão opaca. Login só emite sessão para identidade previamente verificada e usuário ativo.

## Segredos e variáveis necessárias

Todos os valores são exclusivos do ambiente de backend. Nunca colocar no frontend, repositório, Notion público, logs ou mensagens de suporte.

- \`AUTH_ROUTES_ENABLED=false\` até a validação operacional e jurídica final.
- \`IDENTITY_LOOKUP_PEPPER\`: pelo menos 32 bytes aleatórios.
- \`OTP_PEPPER\`: pelo menos 32 bytes aleatórios, independente dos demais.
- \`OTP_RATE_LIMIT_PEPPER\`: pelo menos 32 bytes aleatórios, independente dos demais.
- \`IDENTITY_ENCRYPTION_KEY\`: chave Fernet independente de \`TOKEN_ENCRYPTION_KEY\`.
- \`TRUSTED_PROXY_HOPS\`: quantidade exata de proxies confiáveis da cadeia.
- \`TRUSTED_PROXY_CIDRS\`: redes CIDR dos proxies confiáveis; a aplicação valida o peer imediato e os proxies intermediários antes de aceitar \`X-Forwarded-For\`.
- \`SMTP_HOST=email-smtp.sa-east-1.amazonaws.com\`
- \`SMTP_PORT=587\`
- \`SMTP_USE_TLS=true\`
- \`SMTP_USE_SSL=false\`
- \`SMTP_USERNAME\`: usuário SMTP criado no Amazon SES para a região sa-east-1.
- \`SMTP_PASSWORD\`: senha SMTP criada no Amazon SES para a região sa-east-1; não usar a senha da conta AWS nem assumir que a access key IAM é a senha SMTP.
- \`SMTP_FROM\`: endereço em domínio verificado no SES.
- \`SMTP_TIMEOUT_SECONDS=10\`

As chaves de pepper devem ser geradas com gerador criptograficamente seguro, armazenadas no gerenciador de segredos do Render e compartilhadas entre instâncias. Rotação exige plano de compatibilidade para desafios ativos e hashes existentes.

## Configuração do Amazon SES

Região escolhida: \`sa-east-1\` (São Paulo).

Endpoint SMTP: \`email-smtp.sa-east-1.amazonaws.com\`.

Usar porta 587 com STARTTLS. O SES exige TLS. As credenciais SMTP são regionais e diferentes das credenciais normais de acesso à AWS.

**Plano de preço recomendado: à la carte.** A tabela oficial atual mostra USD 0,10 por 1.000 e-mails enviados, sem taxa mínima ou mensalidade fixa para o envio básico. O plano Essentials custa USD 0,16 por 1.000; Pro e Enterprise acrescentam taxas fixas por conta/região (USD 105 e USD 500/mês, respectivamente). Novas contas e regiões sem atividade tarifada desde 01/06/2025 passam a iniciar no Essentials a partir de 21/07/2026; portanto, durante a criação da conta, selecionar explicitamente à la carte se disponível/adequado, em vez de aceitar o plano padrão. Não contratar Pro/Enterprise para o volume inicial.

Estimativa do envio básico, sem anexos, impostos ou outros recursos: 10.000 mensagens/mês ≈ USD 1,00 no à la carte; 50.000 ≈ USD 5,00. No Essentials, seriam aproximadamente USD 1,60 e USD 8,00. A AWS também oferece créditos de nível gratuito para novas contas elegíveis, mas a decisão financeira não deve depender de créditos promocionais.

Sequência operacional, ainda não executada:

1. Acessar o console AWS com conta corporativa controlada pela empresa e MFA.
2. Abrir Amazon SES na região São Paulo (\`sa-east-1\`).
3. Criar/verificar identidade de domínio, preferencialmente um subdomínio dedicado para autenticação.
4. Publicar os registros de verificação e os três CNAMEs de Easy DKIM fornecidos pelo SES no DNS do domínio.
5. Configurar SPF e DMARC sem sobrescrever registros SPF existentes; validar alinhamento com a política do domínio.
6. Aguardar a verificação de domínio e DKIM.
7. Solicitar saída da sandbox na região São Paulo. Enquanto estiver na sandbox, o SES só envia para destinatários verificados e limita volume e taxa.
8. Criar credenciais SMTP específicas da região. Conceder somente permissões de envio necessárias; não usar credenciais root.
9. Inserir as variáveis SMTP no Render, sem imprimir os valores nos logs ou no GitHub.
10. Fazer teste de entrega para caixas de teste controladas, validar recebimento, SPF, DKIM, DMARC, bounce e complaint antes de habilitar usuários reais.

O domínio remetente ainda não foi identificado nem confirmado. Um registro histórico citava `muricisystem.com`, mas essa proposta antecede a consolidação da marca Sodalis Murici e não é domínio aprovado nem comprovadamente registrado; não configurar nem comprar com base nesse registro. Não inventar nem registrar domínio. O subdomínio proposto depende de domínio cujo controle a empresa possa comprovar.

## Proxy e rate limiting

A aplicação não confia cegamente no cabeçalho \`X-Forwarded-For\`. A rota só fica pronta quando \`TRUSTED_PROXY_HOPS\` e \`TRUSTED_PROXY_CIDRS\` estão configurados. O peer imediato e os proxies intermediários são validados contra a allowlist. Não preencher esses valores por estimativa: confirmar a cadeia efetiva do Render/Cloudflare em ambiente controlado e testar com requisições diretas e encaminhadas.

Até a confirmação, manter \`AUTH_ROUTES_ENABLED=false\`. Não usar \`0.0.0.0/0\`, redes excessivamente amplas ou o primeiro IP do cabeçalho sem validar a cadeia.

O limitador atual aplica quota por identidade e IP, com cooldown e janela compartilhados no PostgreSQL. A dimensão device não é obrigatória e não usa fingerprint de hardware. O identificador de dispositivo, se futuramente adotado, deve ser aleatório, rotativo e controlado pelo aplicativo.

## Segurança, privacidade e LGPD

- O código OTP nunca é devolvido ao cliente nem armazenado em texto claro.
- Identidade é normalizada, indexada por HMAC e armazenada cifrada.
- Respostas genéricas reduzem enumeração de contas.
- Falha de entrega consome o desafio; desafio enviado só pode ser usado uma vez.
- Cadastro ativa usuário, verifica identidade e cria tenant/owner em uma transação.
- Não enviar informações profissionais, currículos ou dados sensíveis no e-mail OTP.
- Definir retenção de logs e metadados de entrega, gestão de bounce/complaint e procedimento de exclusão. Contas pendentes sem e-mail verificado são removidas pelo scheduler após o TTL configurado (24 horas por padrão); confirmar formalmente esse prazo na matriz de retenção.
- Revisar aviso de privacidade, base legal, operador/suboperadores e transferência internacional antes da ativação pública.

## Origem do PWA e transporte de sessão

A origem final do PWA e a estratégia de sessão ainda precisam ser decididas. O preview Lovable e o backend Render estão em domínios diferentes; cookies cross-site podem ser bloqueados. A API atual devolve token opaco no corpo JSON e as rotas existentes usam `Authorization: Bearer`. Antes da ativação pública, decidir e testar armazenamento de sessão no cliente, CORS, CSRF, cookies Secure/HttpOnly/SameSite ou estratégia BFF same-site. Não guardar token de sessão em localStorage como atalho e não enfraquecer atributos de cookie para contornar o problema.

## Gate de ativação

Não habilitar produção até todos os itens estarem comprovados:

- [ ] domínio remetente aprovado e sob controle da empresa;
- [ ] SES verificado e fora da sandbox;
- [ ] SPF, DKIM e DMARC validados;
- [ ] credenciais SMTP de envio restrito criadas e guardadas no Render;
- [ ] quatro segredos de autenticação independentes criados e guardados;
- [ ] cadeia de proxy e CIDRs confirmados por evidência, não estimativa;
- [ ] domínio/origem final do PWA e transporte seguro de sessão, CORS e CSRF definidos e testados;
- [ ] testes de integração e segurança aprovados;
- [ ] aviso de privacidade e retenção revisados;
- [ ] prazo de retenção de cadastro pendente aprovado e limpeza do scheduler monitorada;
- [ ] plano de rollback testado mantendo o recurso desligado por padrão.

Nenhuma conta AWS, domínio, DNS, credencial, segredo Render, migration de produção, merge ou deploy foi criado/alterado por esta implementação.
