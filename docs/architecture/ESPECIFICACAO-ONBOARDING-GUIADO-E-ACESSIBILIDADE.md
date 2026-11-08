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

## Assistente narradora e áudio
- Personagem/assistente feminina, consistente visualmente e com linguagem simples, respeitosa e adulta (não infantilizar o usuário).
- Narração em áudio para cada explicação, opção, botão e passo relevante.
- Controles visíveis: ouvir/reproduzir, pausar, repetir e ajustar velocidade; indicar quando a fala está ativa.
- Legendas/texto sincronizados com a narração, para usuários surdos ou em ambientes sem áudio.
- Controle global para ativar/desativar narração automática e controle local para ouvir um trecho novamente.
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
3. Narrar a ação em áudio e exibir legenda.
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
- Passos com alvo de interface, texto, áudio, legenda, ação demonstrativa e fallback quando o alvo não estiver presente.
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
- Cada passo pode ser ouvido, pausado e repetido; texto/legendas acompanham a narração.
- Preferências e progresso são preservados conforme a política de conta/dispositivo, com isolamento por usuário.
- A navegação continua utilizável sem áudio e sem concluir o tutorial.
- Nenhum tutorial afirma que função não implementada já está disponível.

## Dependências e riscos
- O frontend atual ainda tem telas placeholder e módulos sem integração real; os tutoriais devem ser construídos somente sobre funcionalidades efetivamente implementadas.
- A autenticação e o isolamento multiusuário ainda estão pendentes; progresso sincronizado entre dispositivos depende dessa base.
- Definir fornecedor/custo de voz, política de armazenamento de áudio, idiomas e disponibilidade offline.
- Produção de roteiros, gravações/voz sintética, ilustrações da personagem e manutenção após mudanças de interface exigem fluxo editorial.
- Testes de usabilidade com pessoas com baixa alfabetização são essenciais; não presumir que a solução de áudio seja suficiente por si só.

## Decisões ainda abertas
- Nome, aparência e personalidade da personagem narradora.
- Se a narração automática começa sempre ou se o usuário escolhe no primeiro acesso; recomendação: explicar a opção no onboarding e permitir ativação/desativação.
- Política de repetição automática após atualizações e por período.
- Idiomas e voz.
- Uso de voz sintetizada versus gravações humanas.
- Quais telas e funções entram no primeiro lote de tutoriais.
- Se o questionário será obrigatório ou dispensável; recomendação: opcional e ignorável.
- Armazenamento local temporário versus persistência central após autenticação.
- Métricas de eficácia e retenção, respeitando privacidade.

## Limites desta entrega
Este documento formaliza o requisito e critérios de aceite. Nenhum código, tela, áudio, personagem, serviço externo ou crédito Lovable foi alterado/consumido. Nenhuma publicação ou deploy foi realizado.
