# Especificação funcional — onboarding guiado, ajuda contextual e acessibilidade

## Status
Requisito solicitado pelo usuário em 08/11/2026. Registrado como decisão de produto a detalhar; não implementado nem aprovado para execução no Lovable. Esta especificação preserva a intenção e separa comportamentos confirmados de decisões técnicas propostas.

## Objetivo
Tornar o aplicativo autoexplicativo para clientes novos e recorrentes, reduzindo a dependência de leitura de manuais e permitindo que pessoas com baixa alfabetização ou dificuldade de leitura compreendam e utilizem todas as funcionalidades.

A experiência deve lembrar os tutoriais interativos de jogos (ex.: Clash of Clans): uma personagem/assistente feminina conduz o usuário pela interface, explica controles e funcionalidades e demonstra onde agir. O tutorial deve ser contextual a cada tela, e não apenas um tour geral de boas-vindas.

## Jornada principal
1. Após cadastro e contratação/ativação do serviço, no primeiro acesso, apresentar o tutorial da tela inicial.
2. O tutorial explica os elementos e botões da tela atual, um por vez, com destaque visual no elemento correspondente e explicação simples.
3. Ao concluir ou sair, o usuário permanece na tela; a conclusão é registrada por usuário e versão do tutorial.
4. Quando o usuário abrir pela primeira vez outra área (por exemplo, Métricas), iniciar automaticamente o tutorial específico daquela área.
5. Ao navegar para outra área ainda não apresentada (por exemplo, Pontuações), iniciar automaticamente o tutorial contextual correspondente.
6. Um botão flutuante compacto com símbolo “?” permanece disponível nas telas. Ao acioná-lo, o usuário pode rever o tutorial da tela atual e acessar ajuda contextual.
7. Ao final de cada tutorial, apresentar uma pergunta curta de compreensão/necessidade: “Você encontrou o que queria?” e opções objetivas relacionadas à área.
8. Ao selecionar uma opção, abrir o tutorial ou passo exato que ensina aquela tarefa, direcionando o usuário ao controle correspondente (deep link/âncora guiada quando aplicável).

## Regras de apresentação
- Tutorial separado por tela, módulo e funcionalidade; não misturar explicações de áreas diferentes.
- Primeira visita a uma tela ainda não explicada: iniciar automaticamente, com possibilidade clara de pular/fechar.
- Visitas posteriores: não interromper repetidamente; manter o “?” para repetir o tutorial e oferecer ajuda específica. A frequência de reapresentação automática deve ser configurável e respeitar a preferência do usuário.
- Se houver atualização relevante de interface ou funcionalidade, oferecer tutorial de novidades ou reapresentar somente os passos alterados, sem reiniciar toda a aprendizagem.
- Persistir progresso por usuário e dispositivo/sessão de forma compatível com a futura arquitetura multiusuário. Não presumir que localStorage isolado represente conclusão sincronizada entre dispositivos.
- Permitir retomar, reiniciar, pausar e sair.
- Não bloquear o uso do aplicativo por quem já conhece a funcionalidade.

## Assistente e identidade
- A personagem/assistente será uma guia de uso da plataforma, com identidade própria e linguagem simples, respeitosa e adulta. Não deve ser apresentada como subordinada, secretária ou como alguém que exige interação social.
- Nome e identidade aprovados pelo usuário em 08/11/2026: **Mentora Lyla**.
- A marca principal continua sendo **Camarada Murici**. As identidades têm papéis complementares: Camarada Murici representa companheirismo, parceria e execução; Mentora Lyla representa seriedade, conhecimento, didática e orientação, ensinando, explicando, demonstrando e conduzindo o cliente pelas funcionalidades.
- **Decisão funcional confirmada pelo usuário:** o aplicativo terá duas assistentes distintas e complementares. **Mentora Lyla é a mentora do cliente:** orienta a pessoa a entender e utilizar as funcionalidades do aplicativo, ensina como navegar e explica os recursos. **Camarada Murici é quem trabalha pelo cliente:** atua como seu camarada/assistente de execução, ajudando a realizar tarefas, organizar, automatizar e resolver demandas em seu nome, sempre respeitando permissões, aprovações e limites de segurança. Síntese de posicionamento: **“Sua mentora e seu camarada.”**
- Não confundir as responsabilidades: Lyla ensina o cliente a usar o produto; Murici executa o trabalho solicitado pelo cliente. As duas podem encaminhar uma à outra quando a necessidade envolver orientação versus execução, sem duplicar papéis.
- “Mentora” foi escolhido por transmitir profissionalismo e remeter a uma professora/mentora que ensina algo, sem colocar a assistente em posição de subordinação. “Mila Descomplica” foi considerada alternativa, mas não escolhida.
- A aprovação do nome no produto não equivale a registro de marca. Disponibilidade no INPI e de domínios ainda precisa ser verificada antes de eventual proteção/uso jurídico exclusivo.

## Preferências de comunicação: áudio ou texto
- O cliente escolhe explicitamente como prefere receber as orientações: **somente texto**, **áudio sob solicitação** ou **áudio automático**.
- Padrão recomendado no primeiro acesso: **somente texto** ou áudio sob solicitação, sem iniciar fala automaticamente. Explicar a opção de áudio de forma neutra e deixar a escolha com o cliente.
- Disponibilizar a configuração em Preferências/Acessibilidade e também um controle discreto no próprio tutorial. A pessoa pode mudar a escolha a qualquer momento.
- Em “somente texto”, não reproduzir voz, sons de confirmação ou narração automática; manter texto, destaque visual, ícones e controles acessíveis.
- Em “áudio sob solicitação”, cada etapa terá botão de ouvir/repetir; a reprodução nunca começa sozinha.
- Em “áudio automático”, a fala acompanha os passos do tutorial, mas deve haver controles visíveis para pausar, parar, repetir e ajustar velocidade.
- A escolha deve ser persistida por usuário quando houver autenticação; antes disso, pode ser armazenada localmente no dispositivo, sem alegar sincronização entre aparelhos.
- Nenhuma opção pode reduzir a funcionalidade ou constranger o cliente. Não usar linguagem que sugira que a pessoa “precisa” conversar com a IA, falar em voz alta ou aceitar narração.
- Áudio sempre acompanhado de texto/legendas sincronizados. O tutorial deve funcionar integralmente sem áudio e sem microfone; não exigir fala do cliente.
- Não coletar gravação de voz do cliente para a experiência de tutorial. A narração de saída não implica autorização para captar áudio de entrada.

## Narração e controles de áudio
- Quando habilitada, narração em áudio para cada explicação, opção, botão e passo relevante.
- Controles visíveis: ouvir/reproduzir, pausar, parar, repetir e ajustar velocidade; indicar quando a fala está ativa.
- Legendas/texto sincronizados com a narração, para usuários surdos ou em ambientes sem áudio.
- Não depender exclusivamente de áudio: manter texto, ícones compreensíveis e demonstração visual.
- Planejar alternativa de síntese de voz e seleção de voz/idioma; custos, disponibilidade offline e privacidade devem ser avaliados antes de escolher fornecedor.
- Não enviar dados pessoais ou conteúdo privado a um serviço de voz sem base legal, transparência e consentimento apropriado.

## Acessibilidade
- Linguagem direta, frases curtas, uma instrução por vez e exemplos concretos.
- Áudio acompanhado de texto/legendas; não usar apenas cor para indicar o elemento destacado.
- Alvos de toque amplos, contraste adequado, foco/teclado e leitores de tela compatíveis.
- Não exigir leitura extensa, memorização ou rapidez para concluir o tutorial.
- Permitir repetir a fala quantas vezes quiser e controlar o ritmo.
- Evitar animações rápidas, flashes, movimento excessivo e sons inesperados.
- Respeitar preferências de acessibilidade e reduzir movimento quando solicitado.
- Testar com pessoas com diferentes níveis de alfabetização, deficiência visual/auditiva, limitações motoras e diferentes faixas etárias; não presumir que áudio sozinho resolve todas as barreiras.

## Questionário final e direcionamento
Pergunta inicial: “Você encontrou o que queria?”
Exibir opções concretas e específicas ao contexto da tela. Exemplos ilustrativos:
- Métricas: “Quero entender minhas impressões”; “Quero saber quem interagiu”; “Quero comparar períodos”; “Quero descobrir o que melhorar”.
- Pontuações: “O que significa minha pontuação?”; “Como ela é calculada?”; “Como posso melhorar?”.
- Tela inicial: “Quero entender os indicadores”; “Quero encontrar uma função”; “Quero configurar o aplicativo”.
Ao selecionar uma opção:
1. Abrir o passo a passo correspondente.
2. Destacar o botão/área exata.
3. Se o cliente tiver habilitado áudio, narrar a ação e exibir legenda; se escolheu texto, mostrar somente instrução escrita.
4. Ao concluir, retornar ao contexto de origem quando possível.
Registrar feedback mínimo para melhorar a ajuda, sem coletar conteúdo desnecessário. Opção “Não, preciso de outra ajuda” deve permitir escolher outra necessidade ou voltar ao tutorial completo.

## Conteúdo mínimo de cada tutorial
- Para que serve a tela.
- O que cada botão/indicador faz.
- Quando usar cada opção e o que acontece depois do clique.
- Exemplo simples e contextual.
- Alertas sobre ações irreversíveis, publicação, compartilhamento ou custos, quando existirem.
- Como voltar, cancelar ou pedir ajuda.
- Relação com outras áreas, sem induzir o usuário a executar ações externas sem confirmação.

## Requisitos técnicos propostos
- Catálogo versionado de tutoriais por rota/tela, componente e funcionalidade.
- Passos com alvo de interface, texto, áudio opcional, legenda, ação demonstrativa e fallback quando o alvo não estiver presente.
- Orquestrador de tours que detecta primeira entrada, navegação, versão do tutorial e preferência do usuário.
- Persistência de progresso, preferências de áudio e feedback com ownership por usuário após autenticação multiusuário.
- Deep links/âncoras internas para abrir o passo correspondente à opção escolhida no questionário.
- Eventos analíticos mínimos: tutorial iniciado/concluído/pulado, passo concluído e pedido de ajuda; sem registrar texto privado ou conteúdo de publicações.
- Compatibilidade com layouts responsivos e testes de regressão quando botões/rotas mudarem.
- Fallback acessível se o destaque do elemento falhar: explicação em painel/lista sem depender de posicionamento visual.
- Conteúdo de ajuda deve refletir a versão real do produto; não apresentar funcionalidades futuras como existentes.

## Critérios de aceite
- Um usuário novo recebe o tutorial da tela inicial após ativação e pode pular ou pausar.
- Primeira entrada em cada módulo ainda não apresentado inicia o tutorial daquele módulo.
- Tutoriais são independentes por tela e não repetem explicações de outros módulos sem necessidade.
- “?” está disponível de forma compacta e abre a ajuda contextual da tela atual.
- O usuário consegue repetir o tutorial completo ou ir diretamente a uma função.
- O questionário final direciona ao passo correto e destaca o controle correspondente.
- O cliente pode usar todos os tutoriais em modo somente texto, sem áudio e sem microfone.
- A preferência de áudio automático, sob solicitação ou somente texto é respeitada e pode ser alterada a qualquer momento.
- Cada passo pode ser ouvido, pausado e repetido quando o áudio estiver habilitado; texto/legendas acompanham a narração.
- Preferências e progresso são preservados conforme a política de conta/dispositivo, com isolamento por usuário.
- A navegação continua utilizável sem áudio e sem concluir o tutorial.
- Nenhum tutorial afirma que função não implementada já está disponível.

## Pesquisa inicial de nome
- **Mila**: nome curto, de pronúncia simples em português; fontes onomásticas consultadas associam a origem eslava a “querida/amável”. A forma curta soa independente, não como título hierárquico. Dados publicados com base no Censo 2022 indicam 4.718 pessoas com esse nome no Brasil.
- **Hanna**: alternativa válida e reconhecível; forma relacionada a Hannah/Ana, de origem hebraica, associada a “graça/favor”. O Censo 2022 contabiliza 15.652 pessoas chamadas Hanna no Brasil.
- Critério de escolha: legibilidade, pronúncia simples, neutralidade profissional, distinção em relação a “Camarada Murici” e ausência de conotação de subordinação. A pesquisa é preliminar e não substitui busca de marca no INPI.
- Fontes: [Mila — origem e dados do Censo 2022](https://nomesdobrasil.com/nomes/mila/); [Hanna — origem e dados do Censo 2022](https://nomesdobrasil.com/nomes/hanna/); [IBGE — divulgação do banco Nomes no Brasil](https://agenciabrasil.ebc.com.br/geral/noticia/2025-11/confira-nomes-e-sobrenomes-mais-comuns-no-pais-segundo-o-ibge).

## Dependências e riscos
- O frontend atual ainda tem telas placeholder e módulos sem integração real; os tutoriais devem ser construídos somente sobre funcionalidades efetivamente implementadas.
- A autenticação e o isolamento multiusuário ainda estão pendentes; progresso sincronizado entre dispositivos depende dessa base.
- Definir fornecedor/custo de voz, política de armazenamento de áudio, idiomas e disponibilidade offline.
- Produção de roteiros, gravações/voz sintética, ilustrações da personagem e manutenção após mudanças de interface exigem fluxo editorial.
- Testes de usabilidade com pessoas com baixa alfabetização são essenciais; não presumir que a solução de áudio seja suficiente por si só.

## Decisões ainda abertas
- Validação de disponibilidade de marca/domínio para Mentora Lyla antes de eventual registro ou alegação de exclusividade.
- Aparência visual e personalidade da personagem.
- Fornecedor, tipo de voz, idioma(s), voz humana/sintética e custos.
- Política de reapresentação automática após atualizações e por período.
- Quais telas e funções entram no primeiro lote de tutoriais.
- Se o questionário será obrigatório ou dispensável; recomendação: opcional e ignorável.
- Armazenamento local temporário versus persistência central após autenticação.
- Métricas de eficácia e retenção, respeitando privacidade.

## Limites desta entrega
Esta atualização altera somente a especificação documental. Nenhum código, tela, áudio, personagem, serviço externo ou crédito Lovable foi alterado/consumido. Nenhuma publicação ou deploy foi realizado.


## Reconhecimento de conquistas e marcos de score — requisito solicitado em 08/11/2026

A assistente de orientação (nome oficial: Mentora Lyla) poderá reconhecer e celebrar a evolução do cliente por meio de mensagens contextuais de parabéns.

### Eventos que podem gerar reconhecimento
- Atingir um marco de score pela primeira vez.
- Evoluir o score associado a uma atualização realizada.
- Desenvolver ou registrar uma habilidade ou competência, nova ou já existente, conforme as regras do sistema de pontuação.
- Alcançar uma nova faixa de pontuação ou superar um recorde pessoal, quando essa informação estiver disponível e validada.

### Marcos iniciais de pontuação
10, 20, 50, 100, 150, 200, 300, 500, 750, 950, 1000, 1200, 1300, 1500, 1800, 2000, 2500, 3000, 3500, 4000, 4500 e 5000 pontos. A lista é extensível: novos marcos podem ser acrescentados sem alteração estrutural do produto.

### Comportamento e linguagem
- Ao alcançar um marco, apresentar uma mensagem curta e positiva, informando o valor exato atingido.
- Variar os qualificativos para evitar repetição: “incrível”, “fabulosa”, “excelente”, “notável”, “impressionante”, “expressiva”, “extraordinária”, “consistente”, “admirável” e equivalentes.
- Exemplo de estrutura: “Parabéns! Seu score atingiu a marca de 100 pontos. Uma conquista notável! Continue assim!”
- O texto deve soar profissional, encorajador e adulto; evitar exagero, infantilização ou elogio automático sem fundamento.
- Não elogiar como conquista um valor que não tenha sido efetivamente calculado e confirmado pelo sistema.
- Não repetir a mesma comemoração a cada carregamento da tela. Registrar que o marco já foi celebrado para aquele usuário e ciclo/versão de pontuação.
- Se o usuário ultrapassar vários marcos de uma só vez, evitar uma sequência excessiva de notificações: priorizar o marco mais alto atingido e, quando útil, mencionar a evolução desde o marco anterior.
- As mensagens devem respeitar preferências de comunicação: texto sempre disponível; áudio somente conforme a escolha do cliente (somente texto, áudio sob solicitação ou áudio automático).

### Critérios de aceite
- Cada marco é celebrado uma única vez por usuário, conforme a regra de ciclo definida para o score.
- O valor apresentado corresponde ao score confirmado.
- Marcos e mensagens são configuráveis e extensíveis.
- Atualizações, habilidades e competências podem ser reconhecidas sem duplicar a comemoração do mesmo marco.
- A experiência não gera notificações intrusivas nem expõe score a outros usuários.
- A funcionalidade só é apresentada quando o cálculo e a origem do score estiverem implementados e auditáveis.

### Pendências
- Confirmar a regra de cálculo e a relação entre score geral, score por atualização e score por habilidade/competência.
- Definir se os marcos são globais, por categoria ou ambos.
- Definir se um marco pode ser celebrado novamente após perda e recuperação de pontos, mudança de ciclo ou revisão da fórmula.
- Definir canal de exibição (mensagem contextual, central de conquistas ou ambos) e controles de frequência.


## Atualização de decisão — nome oficial confirmado (08/11/2026)

O usuário confirmou a substituição definitiva de **Mentora Mila** por **Mentora Lyla**. A decisão anterior de Mentora Mila fica preservada apenas como histórico de aprovação inicial, posteriormente substituída. A justificativa final foi a sonoridade de “Mentora Lyla”, considerada melhor pelo usuário. A pronúncia poderá ser apresentada como “Lyla”; não presumir pronúncia alternativa sem validação. A marca principal permanece **Camarada Murici**. A alteração é documental; não houve implementação no Lovable, consumo de créditos, publicação ou deploy.


## Revisão de decisão — fronteiras definitivas entre Mentora Lyla e Camarada Murici (08/11/2026)

Esta revisão substitui qualquer formulação anterior que sugira encaminhamento rotineiro do cliente entre as duas assistentes. Encaminhamentos sem necessidade concreta devem ser evitados: geram atrito, repetição e cansaço. Cada assistente responde diretamente dentro de seu próprio escopo; não há transferência de conversa como etapa padrão.

### Mentora Lyla — mentora e auxiliar de carreira

A Lyla é responsável pela orientação do cliente e pela comunicação de informações relevantes de carreira e do próprio aplicativo. Seu escopo inclui:
- Ensinar o cliente a navegar e utilizar o aplicativo: telas, botões, indicadores, funcionalidades e tutoriais contextuais.
- Conduzir onboarding, ajuda contextual e explicações de novidades do produto.
- Atuar como auxiliar de carreira, comunicando e explicando informações relevantes como atualizações de processos seletivos, oportunidades e orientações de desenvolvimento profissional.
- Apresentar mensagens informativas no topo do aplicativo (banner/faixa de novidades), incluindo atualizações de processos seletivos, avisos sobre situações como publicação sem validação e mudanças relevantes nos processos do aplicativo.
- Reconhecer conquistas e parabenizar o cliente por evolução, habilidades, competências e marcos de score confirmados.

A Lyla comunica, contextualiza e orienta. Não é responsável por executar métricas, preparar/publicar conteúdo ou operar automações editoriais.

### Camarada Murici — automação

O Murici é responsável pela automação e execução operacional do aplicativo, incluindo:
- Métricas, coleta, organização e análises.
- Processos editoriais, preparação e automação de publicações.
- Agendamentos, filas, execuções e demais rotinas automatizadas.

Tudo que envolve métricas, publicações e automação pertence ao escopo do Camarada Murici. A comunicação de orientação e de novidades ao cliente pertence à Lyla, ainda que a informação comunicada tenha sido produzida por um processo automatizado do Murici.

### Regra de interação entre assistentes

- Não encaminhar o cliente de uma assistente para a outra por conveniência interna, divisão técnica ou simples continuidade de fluxo.
- Cada assistente deve resolver diretamente o que estiver dentro de seu escopo.
- Integração interna entre componentes pode ocorrer sem expor ao cliente uma transferência de conversa.
- Só considerar encaminhamento visível quando houver uma necessidade concreta que não possa ser resolvida no escopo atual; não é comportamento padrão.
- Não duplicar mensagens, perguntas ou tarefas entre as assistentes.

### Mensagens no topo do aplicativo

A faixa/banner de novidades é um canal de comunicação da Mentora Lyla. O conteúdo pode ser alimentado por eventos e dados gerados pelas automações do Murici, mas a apresentação, explicação e contextualização para o cliente ficam com a Lyla. Exemplos incluem atualizações de processos seletivos, avisos sobre publicações sem validação e novidades relevantes do aplicativo. Não apresentar como fato uma atualização que não tenha sido confirmada pela fonte correspondente.

### Estado da decisão

Decisão funcional confirmada pelo usuário em 08/11/2026. Esta revisão prevalece sobre trechos anteriores que atribuam métricas/publicações à Lyla ou proponham encaminhamento genérico entre assistentes. Registro documental apenas: não implementado no Lovable, sem consumo de créditos, deploy ou publicação.
