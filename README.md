# Manga Manager 2.5.0

Aplicativo desktop Windows para baixar, organizar, verificar e exportar capítulos de
fontes públicas compatíveis e autorizadas. Evolui os dois scripts existentes;
os originais estão preservados em `legacy/`. Não altera os PDFs existentes.

## Executar
Windows x64, Python 3.11+ (desenvolvimento validado com 3.13):

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe main.py
```

`app_manga.py` continua sendo uma entrada válida. A CLI aceita capítulo direto:

```powershell
.\venv\Scripts\python.exe download_manga.py https://fonte-autorizada.example/chapter-1 capitulo.pdf
```

O domínio acima é ilustrativo. Use apenas conteúdo que você pode acessar e baixar.
O executável fica em `dist/MangaManager-2.5.0/MangaManager.exe`; distribua a pasta inteira.
Consulte [GUIA_BUILD.md](GUIA_BUILD.md) para o pacote portátil e suas limitações.

## Fluxo
Adicionar obra → analisar URL → conferir metadados e capítulos → selecionar → baixar.
As páginas temporárias são removidas após o PDF validado. Um único catálogo oculto
`.manga-manager.sqlite3` por obra guarda metadados, retomada e integridade dos PDFs.
Os JSONs antigos reconhecidos são migrados e removidos após verificar a cópia salva.
A biblioteca e a fila ficam em SQLite. Capítulos interrompidos oferecem retomada
por página: arquivos completos válidos são reutilizados; o arquivo incompleto é
reiniciado, sem assumir que o servidor oferece Range confiável.

* Interface Qt com biblioteca de capas, leitor nativo e temas escuro/claro.
* Atualizações da fila em segundo plano, sem recriar controles por capítulo.
* Cliques repetidos durante o cadastro de uma obra não iniciam cadastros duplicados.
* Adaptadores HTML, paginação, lazy loading, srcset, metadados e JSON-LD hasPart.
* MangaDex pela API oficial: título da obra, traduções, filtro de idioma e páginas originais.
* FlorManga: obra ou capítulo direto, sem confundir navegação com paginação.
* Dois capítulos simultâneos por padrão (ajuste de 1 a 3), com limites por fonte.
* Pausa, retomada e nova tentativa com seleção opcional; cancelamento pelo botão direito.
* Imagens verificadas por assinatura, decodificação e hash; estados de certeza explícitos.
* PDF automático por capítulo, validado antes de marcar a tarefa como concluída.
* Downloads mostram obra/capítulo, status, porcentagem e erro.
* Organização em pasta por obra, com PDFs na subpasta `PDF`; com biblioteca de capas e leitor de PDF integrado.
* Recuperação automática de imagens já baixadas e de pastas movidas dentro do destino.
* Repetir uma conversão com falha reutiliza imagens locais, inclusive sem conexão.
* Nome da obra editável antes de baixar; MangaLivre remove títulos repetidos de capítulos.
* Conversão compatível com WebP, paleta, transparência e páginas longas.
* Consulta de novos capítulos, diagnóstico, backup e relatórios de falha.

## Atualização 2.5.0

- Nova aba Google Drive, com seleção de pasta e prévia compacta por obra.
- Reconhece PDFs já enviados manualmente pelo conteúdo, mesmo renomeados.
- Upload em blocos, cancelamento e retomada; credenciais protegidas pelo Windows.
- Preserva arquivos remotos diferentes e informa conflitos.

## Recursos anteriores — 2.4.0

- Dois capítulos em paralelo, com uma conversão PDF por vez; concorrência configurável.
- PDF é o arquivo final: páginas temporárias só são removidas após validação.
- Biblioteca com capas, todos os capítulos, seleção múltipla e marcação de leitura em massa.
- Renomeação persistente e selo verde quando todos os capítulos estiverem lidos.
- Leitor PDF nativo: rolagem contínua, zoom, tela cheia, páginas e capítulos adjacentes.
- Posição de leitura persistida dentro da página; conclusão automática ao chegar ao fim.
- Downloads sem histórico visual, com falhas antigas resumidas e scroll visível.
- Schema SQLite 2, migração preservando capítulos, tarefas e preferências anteriores.

Google Drive: conexão da conta pelo navegador, pasta existente, comparação por conteúdo e envio apenas dos PDFs faltantes. Envio automático opcional com o aplicativo aberto. A primeira conexão exige uma credencial OAuth Desktop própria no Google Cloud; veja o manual. Android e sincronização de progresso de leitura não fazem parte desta versão Windows.
Referências e medições históricas: [REFERENCIAS.md](REFERENCIAS.md).

## Compatibilidade e limites
Boruto Explorer e MangaLivre possuem seletores herdados, testados em HTML simulado.
Na atualização 2.0.1, MangaLivre.blog retornou Vagabond e 328 capítulos; MangaDex
foi validado com a obra solicitada, capítulo PT-BR completo e PDF de 14 páginas.
Na 2.0.2, FlorManga foi validado com a obra Raeliana (158 capítulos na listagem)
e o capítulo 1: 8 imagens baixadas e PDF com 8 páginas.
Isso não comprova compatibilidade com todos os títulos. O fallback só aceita estruturas de
leitor reconhecidas; não baixa todas as imagens de uma página arbitrária.
HTML público é o modo padrão. Na instalação Python há fallback Chromium opcional,
ativado em Configurações e usado somente quando o HTML não reconhece a obra/páginas.
Instale Playwright e execute `python -m playwright install chromium`.
O browser não está incluído no exe. Listas parcialmente visíveis, APIs interativas
e layouts diferentes podem exigir adaptador próprio. Não há bypass de
DRM, login, CAPTCHA ou paywall. Conteúdo escondido não permite afirmar completude.

O fallback Chromium foi validado apenas com DOM/JavaScript simulado e rede interceptada,
não com fontes reais. O programa consulta robots.txt, mas isso não substitui autorização do titular.
Ele bloqueia URLs locais/privadas, inclusive DNS e redirecionamentos. Não há flag
de produção para desativar essa proteção. Os testes isolam servidores locais.

Dados ficam em `%LOCALAPPDATA%/MangaManager`, ou ao lado do exe em modo portátil.
PDFs vão para a pasta escolhida; imagens de páginas são temporárias. Não apague a pasta de dados para atualizar.

## Verificar
```powershell
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe main.py --data-dir tmp/smoke-data --smoke-test tmp/smoke.json --screenshot tmp/ui.png
```

Evidências e cenários: [VALIDACAO.md](VALIDACAO.md). Guia de uso:
[MANUAL_USUARIO.md](MANUAL_USUARIO.md). Camadas e manutenção:
[ARQUITETURA.md](ARQUITETURA.md) e [GUIA_EXTRATORES.md](GUIA_EXTRATORES.md).
