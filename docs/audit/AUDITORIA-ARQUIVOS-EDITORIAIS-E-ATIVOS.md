# Auditoria de ativos editoriais, imagens e métricas

**Data da análise:** 08/11/2026  
**Escopo:** arquivos fornecidos nesta conversa: `metadados_imagens.csv` e `Planejamento_Editorial_LinkedIn_ATUALIZADO_METRICAS_02-11-2026.xlsx`.  
**Limite:** análise de metadados e planilha; os binários das imagens não foram inspecionados individualmente. Nenhum arquivo do Drive foi movido, renomeado ou excluído.

## 1. Inventário de imagens

O CSV contém 297 registros distribuídos em três pastas consultadas:

| Pasta | Registros |
|---|---:|
| `imagens` | 217 |
| `arquivos_importantes` | 59 |
| `imagens_Claude` | 21 |
| **Total** | **297** |

Formatos informados: 197 PNG e 100 JPEG. Todos os 297 registros têm ID, hash MD5, data de modificação e link do Drive preenchidos.

### 1.1 Duplicidade binária

- 130 hashes MD5 distintos para 297 registros.
- 41 grupos de hashes repetidos.
- 208 registros pertencem a grupos com conteúdo repetido.
- Há 167 cópias excedentes além de uma ocorrência por hash.
- Os grupos repetidos identificados estão dentro da mesma pasta consultada; não foi detectada duplicidade entre as três pastas.

A repetição de hash indica conteúdo binário idêntico, não apenas nomes semelhantes. Não excluir automaticamente: diferentes IDs podem estar referenciados em planejamentos, posts ou históricos. A limpeza exige primeiro um mapa de referências e a escolha de um registro canônico por grupo.

### 1.2 Lacunas de catalogação

O CSV contém metadados técnicos e localização, mas não oferece campos estruturados para:
- post ou campanha relacionada;
- tema/editoria;
- status (rascunho, aprovado, publicado, descartado);
- variante principal ou alternativa;
- origem da imagem (gerada, enviada, editada);
- motivo de rejeição ou divergência;
- relação entre imagem, texto aprovado e publicação.

Há 82 nomes iniciados por `file_`, o que dificulta identificar o conteúdo sem abrir o arquivo. O nome da pasta não substitui uma classificação editorial.

### 1.3 Requisitos recomendados para o produto

1. Catálogo de mídia com miniatura, nome, tipo, dimensões, tamanho, hash e origem.
2. Associação explícita entre ativo, post, variante e campanha.
3. Estados de aprovação e rejeição, com motivo e histórico.
4. Detecção de duplicidade por hash, com sugestão de consolidar referências — nunca exclusão automática.
5. Busca por tema, post, data, status e origem.
6. Registro de ativos sem associação e de posts sem imagem.
7. Preservação do arquivo original e rastreabilidade de versões.
8. Permissões por usuário/tenant; ativos privados não podem vazar entre clientes.

Esses itens são recomendações derivadas da auditoria, não funcionalidades confirmadas como existentes.

## 2. Planejamento editorial e analytics

A planilha contém snapshots de analytics com janelas sobrepostas e backlog editorial. A própria planilha registra que:
- o snapshot de 01–14/10 não deve ser somado ao de 06–19/10, pois há sobreposição;
- o export específico de 19/10 mencionado em uma aba não foi localizado;
- entre 19 e 26/10, seguidores totais passaram de 576 para 747 (+171), enquanto a soma da coluna diária de novos seguidores para 20–26/10 é 115; a coluna de seguidores ganhos foi mantida em branco até validação;
- o backlog futuro inclui dez pautas de OKRs e KPIs logísticos, ainda sem data definida e sem autorização para inserção automática no calendário.

### 2.1 Requisitos de integridade para analytics

- Preservar arquivo fonte, período, data de extração e escopo de cada métrica.
- Diferenciar snapshots de períodos sobrepostos de séries diárias.
- Não somar totais de janelas sobrepostas.
- Sinalizar divergências entre totais acumulados e soma diária, sem preencher valores por inferência.
- Registrar proveniência, fórmula e regra de cálculo de cada indicador.
- Permitir marcar um dado como pendente de validação, sem tratá-lo como zero.
- Separar dados observados, estimativas e exemplos ilustrativos.

### 2.2 Requisitos editoriais

- Backlog sem data definida não deve entrar automaticamente no calendário.
- Evitar duplicidade temática com publicações anteriores.
- Preservar objetivo editorial, abordagem de diferenciação e observações de validação.
- Exigir aprovação explícita antes de mover conteúdo para o agendador cloud, conforme decisão funcional já registrada.

## 3. Prioridade sugerida

**P0 — Integridade e segurança**
- Não apagar duplicatas automaticamente.
- Não inferir métricas ausentes nem reconciliar snapshots sobrepostos por soma.
- Garantir isolamento multiusuário de ativos, posts e métricas.

**P1 — Rastreabilidade editorial**
- Criar vínculo entre mídia, post, versão, aprovação e publicação.
- Registrar origem, estado e motivo de rejeição.
- Manter backlog separado do calendário aprovado.

**P2 — Usabilidade e governança**
- Miniaturas, filtros e busca.
- Painel de duplicatas com consolidação assistida.
- Relatório de ativos órfãos e posts sem mídia.

## 4. Pendências para a próxima etapa da auditoria

1. Inspecionar os binários e validar visualmente se arquivos com mesmo hash são cópias legítimas do mesmo ativo.
2. Cruzar os IDs do Drive com referências presentes em posts, planejamentos e pastas.
3. Identificar se o backend atual possui tabela ou endpoint de biblioteca de mídia; o inventário Neon anterior identificou `drive_storage_locations`, mas não comprova catálogo editorial completo.
4. Definir política de retenção e recuperação antes de qualquer limpeza.
5. Validar a divergência de seguidores com os exports originais do LinkedIn.

## 5. Conclusão

O inventário disponível já evidencia um problema concreto de governança de ativos: 297 registros representam apenas 130 conteúdos binariamente distintos, e o CSV não contém relações editoriais suficientes para uma limpeza segura ou para reconstruir automaticamente qual imagem pertence a qual publicação. A prioridade deve ser construir rastreabilidade e revisão assistida, não apagar arquivos.

A planilha também contém divergências e sobreposições que exigem preservar proveniência e validação explícita. Nenhuma dessas inconsistências deve ser convertida automaticamente em dado definitivo.
