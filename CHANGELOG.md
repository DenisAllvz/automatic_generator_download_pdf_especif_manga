# 2.5.0 — 19/11/2026 — Google Drive integrado

- Conexão OAuth Desktop com PKCE e retorno local; credenciais protegidas com DPAPI.
- Seleção de pasta existente por link ou navegação nativa, por obra ou coleção.
- Prévia compacta e envio apenas dos PDFs ausentes, comparando tamanho e MD5.
- Preserva PDFs diferentes, pastas existentes e arquivos somente na nuvem.
- Upload em blocos, retomada após interrupção e envio automático opcional.
- Operações em segundo plano, cancelamento e mensagens sem poluir a lista de downloads.
- Requer credencial OAuth Desktop do usuário; conta real ainda não autorizada nesta entrega.

# 2.4.0 — 12/11/2026 — Biblioteca, leitura e downloads paralelos

- Dois capítulos simultâneos por padrão, de 1 a 3 configuráveis; PDF continua serializado.
- Agendador consulta apenas tarefas enfileiradas e reduz a espera entre capítulos.
- Biblioteca de capas, lista completa de capítulos, busca, importação e renomeação persistente.
- Marcação em massa, selo verde e progresso de leitura com retomada dentro da página.
- Leitor Qt PDF nativo com rolagem contínua, zoom, tela cheia, pesquisa e capítulos adjacentes.
- Reciclagem do cache de renderização e liberação do leitor ao fechar.
- Capas pequenas locais; primeira página do PDF como fallback de capa indisponível.
- Arquivos de páginas removidos após PDF validado; falhas preservam cache de retomada.
- Downloads sem concluídos, sem tentativas repetidas e com falhas antigas resumidas.
- Barras de rolagem mais largas e visíveis; leitura persistida em schema SQLite 2.

# 2.3.0 — 12/11/2026 — Memória, lotes e fila leve

- Gerador PDF incremental: uma imagem por vez, compressão em faixas, originais preservados.
- JPEG embutido sem recodificação; rotação EXIF, transparência e perfis ICC suportados.
- Integridade por leitura em blocos; deixa de carregar PDFs inteiros na RAM.
- Pular PDFs com recibo válido e estatísticas de arquivo inalteradas.
- Lotes de URLs deduplicados, preferência PT-BR, cancelamento e relatório de erros.
- Busca na fila; ações em lote respeitam as linhas filtradas.
- Uma instância por diretório de dados, evitando várias janelas do mesmo aplicativo.
- Inclui todas as correções de desempenho abaixo. Referências em REFERENCIAS.md.

# 2.2.1 — 12/11/2026 — Desempenho e travamentos

- Consultas periódicas da fila feitas em segundo plano, sem esperar o banco na interface.
- Eventos de progresso agrupados; no máximo uma leitura periódica pendente.
- Removida a recriação de controles por capítulo: porcentagens leves e itens reaproveitados.
- Telas inalteradas não são reconstruídas; seleção e posição de rolagem preservadas.
- Cadastro por link protegido contra cliques repetidos, com consulta de registros no worker.
- Comandos da fila em lote e fora da interface; uma notificação por operação.
- Correção de títulos na inicialização trabalha em segundo plano e grava apenas mudanças.
- Agendador evita consultar e ordenar a fila inteira enquanto um capítulo está ativo.
- Testes de fila com 1.000 capítulos e de interface durante bloqueio do banco/cadastro por link.

# 2.2.0 — Interface e pastas mais limpas

- Visual renovado com navegação lateral, cartões, barras de progresso e temas claro/escuro.
- Um catálogo SQLite oculto por obra substitui JSONs de capítulos e recibos dos PDFs.
- Migração verificada dos arquivos antigos; preserva arquivos inválidos ou desconhecidos.
- Execução de um capítulo por vez em ordem natural, ignorando prioridades antigas.
- Downloads com Pausar, Retomar e Tentar novamente; sem seleção, atua nos elegíveis.
- Cancelar/remover disponíveis no botão direito; opções técnicas recolhidas.
- Corrigida a montagem de botões utilitários; recuperação antecede início da fila.
- PDFs automáticos, relatórios finais e limpeza da fila preservados.

# 2.1.1 — Relatórios e fila limpa

- Ao finalizar os downloads de uma obra, grava TXT/JSON e mostra o resultado.
- Tarefas concluídas/canceladas saem da fila depois de salvar o relatório.
- Falhas ficam visíveis para repetir; tarefas pausadas impedem conclusão prematura.
- Histórico persistido separadamente, sem apagar PDFs, imagens ou capítulos.
- Botão Abrir relatórios de downloads; aviso não bloqueia o restante da fila.

# 2.1.0 — 10/10/2026

- PDF automático depois do download; conclusão depende do PDF validado.
- Biblioteca e Detalhes removidos; Downloads com quatro colunas essenciais.
- Correção de nomes MangaLivre e nome da obra editável antes de baixar.
- Recuperação de pastas movidas e conversão offline de imagens completas.
- Normalização sem perda para formatos incompatíveis; páginas longas com limites PDF.
- Recibos de integridade evitam reconversão e protegem PDFs existentes.
- Tentativas limitadas para bloqueio temporário de arquivos pelo Windows.

# Changelog

## 2.0.2 — 2026-10-10

* Adaptador FlorManga: título pelo caminho de navegação da obra e capítulo direto isolado.
* Lista da obra usa links/seletores Madara; nunca percorre o botão de próximo capítulo.
* robots.txt indisponível com 4xx segue RFC 9309; 429, erros de servidor/rede,
  regras Disallow e acesso negado às imagens continuam respeitados.
* Verificação real: obra com 158 capítulos e capítulo 1 com 8 imagens e PDF de 8 páginas.

## 2.0.1 — 2026-10-10

* Exportação PDF/CBZ de todos os selecionados em uma ação e pasta única.
* Botão PDF de todos os baixados da obra, progresso e relatório de falhas.
* Lotes continuam após falhas e preservam arquivos existentes.
* Remoção do leitor interno e da coluna de posição de leitura.
* Extração prioriza título da obra e corrige nomes de site já salvos sem mover downloads.
* MangaDex pela API pública, listagem paginada, filtro de idiomas e créditos de grupos.
* Cache por identidade de página MangaDex, preservado quando o servidor temporário muda.

## 2.0.0 — 2026-10-10
* Auditoria e snapshots preservados; wrappers para as entradas originais.
* Migração CustomTkinter para PySide6 com oito telas e workers/sinais.
* Biblioteca SQLite, preferências, recuperação de tarefas e histórico de erros.
* Extratores modulares, domínios exatos, paginação, lazy loading, srcset e JSON-LD.
* Transporte com DNS/redirect protegidos, robots.txt, limites, retries e Retry-After.
* Fila com prioridade, pausa, retomada, cancelamento e reparação por página.
* Imagens originais e manifestos com hash; sem apagar PDF por tamanho.
* Leitor local, posição salva, exportação CBZ e PDF explícita.
* Importação legada não destrutiva, favoritos, tags, pesquisa, filtros e backup.
* Testes isolados e scripts para gerar/verificar executável Windows portátil.
* Chromium opcional na instalação Python, com HTTP intermediado e bloqueio de rede
  privada inclusive em requisições iniciadas por JavaScript.

Limites e evidências efetivos estão em VALIDACAO.md e RELATORIO_FINAL.md.
