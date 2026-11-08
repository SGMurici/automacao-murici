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
- Nome recomendado após pesquisa inicial: **Mila**. Apresentação sugerida: “Mila — assistente da Automação Murici”; em comunicação mais informal, “Mila, sua guia na Automação Murici”.
- A marca principal continua sendo **Camarada Murici**. Mila é a identidade feminina da experiência de ajuda/tutorial, não uma substituição do nome do serviço ou da IA principal.
- A recomendação é provisória até validação de disponibilidade de marca/domínio e eventual análise jurídica. O nome não deve ser tratado como marca registrada.

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
- Aprovação final do nome Mila e validação de marca/domínio.
- Aparência visual e personalidade da personagem.
- Fornecedor, tipo de voz, idioma(s), voz humana/sintética e custos.
- Política de reapresentação automática após atualizações e por período.
- Quais telas e funções entram no primeiro lote de tutoriais.
- Se o questionário será obrigatório ou dispensável; recomendação: opcional e ignorável.
- Armazenamento local temporário versus persistência central após autenticação.
- Métricas de eficácia e retenção, respeitando privacidade.

## Limites desta entrega
Esta atualização altera somente a especificação documental. Nenhum código, tela, áudio, personagem, serviço externo ou crédito Lovable foi alterado/consumido. Nenhuma publicação ou deploy foi realizado.
