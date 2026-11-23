# Auditoria do sistema original — 09/10/2026

## Arquitetura e comportamento
Dois scripts: `app_manga.py` (CustomTkinter, asyncio em thread, aiohttp, BeautifulSoup,
Playwright e Pillow) e `download_manga.py` (requests e Pillow). A interface recebe
a URL da obra, descobre links com Chromium, baixa imagens e produz PDFs.
O segundo script baixa um capítulo fixo. Não havia manifesto, banco, testes,
declaração de dependências ou procedimento de distribuição.

Os seletores originais mencionam Boruto Explorer (`wp-manga-chapter`,
`wp-manga-chapter-img`) e MangaLivre (`chapter-image`, links `capitulo`).
Isso é evidência de intenção de suporte, não de compatibilidade atual ou permissão.
Os PDFs de Downloads_Mangas e as imagens temporárias são dados do usuário.
O Git contém alterações anteriores em app_manga.py e exclusão de script.py;
essas alterações não serão revertidas.

## Problemas
* Crítico: exclusão automática de PDFs menores que 500 KB, sem validar conteúdo.
* Crítico: declara sucesso com apenas 50% das páginas; apaga as imagens depois.
* Alto: URLs e redirecionamentos sem proteção contra SSRF; nomes sem contenção.
* Alto: UI alterada por outra thread; exceções de imagens ocultadas.
* Alto: concorrência de imagens sem limite efetivo por domínio e sem backoff.
* Alto: ausência de persistência, retomada e comprovação de integridade.
* Médio: só uma página de capítulos, inversão cega, sem ordenação decimal.
* Médio: só src, todas as imagens no fallback, extensão JPEG imposta.
* Médio: caminhos Tcl/Tk absolutos de uma máquina; recursos Pillow não fechados.

## Preservação e decisões
Preservar PDFs, imagens e comportamento de adicionar URL e exportar PDF.
Guardar snapshot dos scripts originais em legacy/; encaminhar as entradas antigas
ao novo serviço. Importar PDFs como legado com integridade não verificável,
sem inferir que correspondem a uma fonte ou que contêm todas as páginas.
Escolha: PySide6 para UI e sinais entre threads, aiohttp para transporte,
BeautifulSoup para seletores existentes, Pillow para assinaturas/imagens, SQLite
para biblioteca e fila. CBZ mantém bytes originais; PDF é exportação explícita.

## Plano e riscos
1. Caracterização isolada, sem executar downloads originais.
2. Camadas de modelos, segurança, HTTP, extratores, armazenamento e serviços.
3. Paginação testada com fixtures, fila persistente e manifestos atômicos.
4. UI Qt, leitor offline, importação, diagnóstico e exportações.
5. Testes simulados, build Windows, smoke test e documentação.

Riscos: seletores mudam; listagens dinâmicas não garantem completude; PDFs antigos
não possuem proveniência; limites de servidor e permissões precisam ser avaliados.
Renderização JavaScript não será usada para contornar restrições. A versão inicial
prioriza HTML público: fontes somente JavaScript podem precisar de novo adaptador.
Cada etapa terá checkpoint documental em CHECKPOINTS.md e testes relevantes.
