# Arquitetura de agendamento local-first e revisão do Render Cronjob

**Status:** proposta técnica para revisão (Draft).  
**Data:** 11/11/2026.  
**Escopo:** separar agendamento do aplicativo Android de tarefas remotas do backend. Este documento não altera produção, Render, banco ou credenciais.

## 1. Decisão arquitetural proposta

O KAPPA deve funcionar localmente sem depender de polling contínuo na nuvem. O relógio do aparelho é a autoridade operacional para lembretes, agenda pessoal, contadores e tarefas que pertencem ao próprio usuário. A nuvem complementa o aplicativo quando uma operação exige disponibilidade remota, integração externa ou execução mesmo com o aparelho desligado.

Não usar Render Cronjob como relógio da experiência pessoal do cliente. Não enviar tarefas locais ao servidor apenas para descobrir se chegou a hora de notificar.

## 2. Matriz de responsabilidades

| Capacidade | Responsável primário | Rede necessária? | Observação |
| --- | --- | --- | --- |
| Contador regressivo visível enquanto o app está aberto | UI/app local | Não | Derivar do prazo persistido; não decrementar e salvar a cada segundo. |
| Lembretes pessoais e compromissos | Android local | Não, após cadastro | Persistir e agendar no sistema operacional. |
| Rotinas e recorrências pessoais | Android local | Não, após cadastro | Resolver recorrência no fuso IANA do usuário. |
| Notificação local | Android local | Não | Permissão de notificações deve ser explicada e solicitada no contexto correto. |
| Sincronização eventual do calendário | App + API | Sim, para sincronizar | A agenda continua utilizável offline; conflitos exigem política explícita. |
| Cadastro, login, verificação OTP e recuperação | Backend + provedor de e-mail | Sim | Não depender do relógio do cliente nem de o app estar aberto. |
| Publicação agendada no LinkedIn | Backend + LinkedIn | Sim | Precisa ocorrer mesmo com aparelho desligado. |
| Outbox OTP e retries | Backend/worker | Sim | Processamento assíncrono com leases e idempotência. |
| Limpeza de contas pendentes e manutenção | Backend agendado | Sim | Executar no servidor, com retenção aprovada juridicamente. |
| Backup local/exportação | Android local | Não para exportar | Sincronização opcional pode exigir rede; chave e recuperação ainda precisam de decisão. |

## 3. Modelo de tempo local

### 3.1 Não persistir contadores decrementais

- Persistir o prazo final como instante absoluto (UTC) e o contexto de fuso aplicável.
- Calcular o tempo restante como max(0, deadline - now) sempre que a tela for atualizada.
- Um contador em memória serve apenas para animação/atualização visual enquanto a tela está aberta; ele nunca é a fonte da verdade.
- Ao reabrir o app, restaurar o prazo e recalcular. Não tentar recuperar o valor de um contador que ficou parado.
- Usar relógio monotônico para medir intervalos dentro de uma sessão/processo; usar instante de parede persistido para compromissos reais e recuperação após encerramento/reboot.

### 3.2 Instantes, recorrência e fuso

- Evento único: armazenar instante UTC, fuso IANA original e a regra de exibição.
- Evento recorrente definido como “todos os dias às 08:00”: armazenar hora civil, regra de recorrência e fuso IANA; gerar a próxima ocorrência a partir dessas regras.
- Mudança de fuso do aparelho: preservar a intenção registrada. Para rotinas locais (“08:00 no horário onde estou”), recalcular usando o novo fuso; para eventos vinculados a um instante (“entrevista às 14:00 de Brasília”), preservar o instante e mostrar a conversão.
- Tratar explicitamente horário inexistente ou duplicado em transições de horário de verão, mesmo que o fuso atual do Brasil não use DST.
- Toda ocorrência deve ter chave idempotente para impedir notificações duplicadas.

## 4. Android: mecanismos de execução

Usar os mecanismos nativos em função da semântica, não um loop permanente:

1. **AlarmManager:** lembretes individuais solicitados pelo usuário. Preferir alarmes inexatos quando a precisão ao segundo não for essencial. Solicitar acesso a alarmes exatos somente para funções centrais que realmente dependam de horário preciso, explicando o motivo e oferecendo fallback.
2. **WorkManager:** sincronização, reconciliação local-remota, limpeza de cache e tarefas adiáveis. Trabalho periódico tem intervalo mínimo de 15 minutos e não oferece horário exato; não usar como despertador de minuto em minuto.
3. **Persistência local:** banco local transacional como fonte da verdade para eventos, recorrências, estado de entrega e preferências.
4. **Reinicialização:** reconstruir alarmes a partir do banco após boot e após atualização do pacote; não depender de alarmes voláteis previamente registrados.
5. **Permissões:** verificar estado de notificações e acesso especial a alarmes antes de prometer entrega exata. Se negados, manter o evento visível na agenda e informar a limitação.
6. **Limites do sistema:** modo Doze, economia de bateria, restrições do fabricante e encerramento forçado podem atrasar ou impedir execução em segundo plano. A interface deve distinguir “agendado”, “permissão pendente” e “entrega sujeita ao sistema”.

Referências oficiais Android:
- Alarmes: https://developer.android.com/develop/background-work/services/alarms
- WorkManager e trabalho persistente: https://developer.android.com/develop/background-work/background-tasks/persistent
- Intervalo mínimo de trabalho periódico: https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started/define-work
- Permissão de alarmes exatos no Android 14: https://developer.android.com/about/versions/14/changes/schedule-exact-alarms

## 5. Auditoria do Cronjob Render existente

Estado consultado em 11/11/2026:

- Serviço: automacao-murici-scheduler.
- ID: crn-db57q4qd0e5s73egg5bg.
- Branch executada: main.
- Região: Oregon.
- Plano: 0.5c-512mb.
- Frequência: */15 * * * *.
- Comando: POST autenticado para /scheduler/run.
- O endpoint chama scheduler_publish_one() e processa no máximo uma publicação editorial vencida por execução.
- A função usa advisory lock PostgreSQL para impedir duas execuções simultâneas e FOR UPDATE SKIP LOCKED para reivindicar uma publicação.
- O Cronjob não agenda lembretes pessoais do cliente e não processa a outbox OTP atual.

### 5.1 Utilidade que permanece

Manter o Cronjob para tarefas remotas que precisam ocorrer com o aparelho desligado: publicação LinkedIn, recuperação de filas remotas, expiração/limpeza de registros quando juridicamente aprovada e processamento de fallback da outbox.

Não manter um Cronjob para relógios, contadores, tarefas ou notificações que pertencem ao aparelho.

### 5.2 Problema de integração OTP

A PR #22 implementa uma outbox transacional e um worker one-shot, mas não instala nem conecta um scheduler. O worker chama expire_due() antes de reivindicar mensagens; os desafios OTP têm validade de 10 minutos. Assim, deixar a outbox dependendo exclusivamente do Cronjob atual, que roda a cada 15 minutos, é incompatível com a validade atual: um desafio pode expirar antes de ser processado.

Isso não justifica mover o OTP para o telefone. O envio precisa continuar no backend. A integração deve ser resolvida no backend com latência adequada, sem misturar locks ou falhas entre as filas.

## 6. Estratégia recomendada para processamento remoto

- Preservar o Cronjob único existente; não criar um segundo serviço agendado nesta etapa.
- Criar um orquestrador backend com funções isoladas: publicação editorial, processamento OTP em lote pequeno e manutenção de baixa prioridade.
- Cada fila mantém seu próprio mecanismo de concorrência, limites, timeout, retry e métricas. Falha de uma fila não impede a execução das demais.
- O endpoint atual /scheduler/run deve manter compatibilidade até que o novo orquestrador tenha testes e rollout aprovados.
- O worker OTP deve continuar enviando fora da transação, reivindicar jobs com lease, preservar o mesmo challenge/código nos retries e não registrar destinatário/código em logs.
- Avaliar duas estratégias de latência: (A) Cronjob combinado a cada minuto como fallback simples; (B) acionamento imediato do worker após commit mais Cronjob de recuperação. Não armazenar credenciais Render de alto privilégio na API apenas para disparar jobs sem avaliar risco.
- Não adotar worker contínuo pago sem comparar o custo mensal com a execução por segundo do Cronjob.
- Medir duração real e volume antes de decidir frequência definitiva.

## 7. Estimativa de custo do Cronjob

Render documenta cobrança proporcional aos segundos de execução ativa e mínimo de USD 1/mês por serviço Cronjob. O plano observado custa USD 0,00016 por minuto ativo.

Simulações para 30 dias, sem incluir workspace, banco, tráfego ou provedor de e-mail:

| Frequência | Duração média por execução | Minutos ativos/mês | Custo de compute estimado | Total mínimo aplicável |
| --- | ---: | ---: | ---: | ---: |
| 15 min | 5 s | 240 | USD 0,0384 | USD 1,00 |
| 1 min | 5 s | 3.600 | USD 0,576 | USD 1,00 |
| 1 min | 10 s | 7.200 | USD 1,152 | USD 1,152 |
| 1 min | 20 s | 14.400 | USD 2,304 | USD 2,304 |

Os números são cenários, não previsão de fatura. O custo real depende da duração de cada execução, volume, retries e tempo de inicialização contabilizado. O intervalo de um minuto não é automaticamente caro neste plano, mas só deve ser adotado se o SLA justificar.

Referências Render:
- Cron Jobs e cobrança por segundo: https://render.com/docs/cronjobs
- Planos de compute: https://render.com/docs/compute-plans
- Preços: https://render.com/pricing

## 8. Testes obrigatórios antes de rollout

### Aplicativo Android
- Lembrete continua agendado após fechar/reabrir o app.
- Lembrete é reconstruído após reboot e atualização do app.
- Permissão de notificações negada não apaga o evento nem cria falsa confirmação.
- Permissão de alarme exato negada ativa fallback e informa precisão reduzida.
- Mudança de fuso e transição DST não duplicam nem deslocam incorretamente recorrências.
- Edição/exclusão cancela o alarme antigo e cria/cancela a ocorrência correta.
- Reagendamento idempotente não duplica notificações.
- Contador reaberto após horas/dias calcula o restante pelo prazo persistido, sem drift acumulado.
- Modo offline não bloqueia criação, edição, consulta ou notificação local.

### Backend e Render
- Uma falha da fila OTP não bloqueia publicação editorial, e vice-versa.
- Execuções concorrentes não reivindicam a mesma mensagem ou publicação.
- OTP expirado não é enviado; retry reutiliza o mesmo challenge e código ainda válido.
- Timeout, falha SMTP e lease expirado são recuperáveis e auditáveis.
- Uma execução interrompida não causa publicação duplicada no LinkedIn.
- O endpoint legado mantém contrato até migração controlada.
- Logs e métricas não expõem destinatário, código OTP, conteúdo privado ou segredo.
- Testes de integração PostgreSQL cobrem transações, locks, leases e idempotência.

## 9. Limites e bloqueios de evidência

- O repositório GitHub acessível nesta auditoria (SGMurici/automacao-murici) contém o backend Flask; não contém código Android, manifesto, configuração WorkManager/AlarmManager ou projeto de cliente nativo.
- O código do aplicativo local não foi disponibilizado em um repositório acessível nesta sessão. Portanto, esta entrega define o contrato arquitetural e os testes, mas não afirma que a implementação Android já foi auditada ou alterada.
- A decisão anterior de produto em Notion ainda contém trechos históricos sobre PWA e deve ser harmonizada com a decisão mais recente de Android como cliente primário, sem ressuscitar o PWA como produto principal.
- Nenhuma alteração foi feita no Cronjob Render, secrets, banco de produção, provedor, DNS, deploy ou frequência.

## 10. Sequência de implementação

1. Revisar e integrar a cadeia de PRs de identidade/outbox antes de qualquer rollout.
2. Implementar orquestrador remoto combinado e testes de isolamento entre filas em branch Draft.
3. Medir custo/duração do Cronjob com execução controlada em ambiente não produtivo.
4. Definir e implementar a camada local de agendamento no repositório Android correto.
5. Executar matriz de testes offline, reboot, fuso, permissões, Doze e idempotência.
6. Só então propor mudança de frequência Render e rollout, preservando reversibilidade.

**Decisão proposta:** Android é o relógio da experiência pessoal; backend é o relógio das operações remotas; Render Cronjob é um executor periódico de contingência e tarefas remotas, não um mecanismo de funcionamento do aplicativo.
