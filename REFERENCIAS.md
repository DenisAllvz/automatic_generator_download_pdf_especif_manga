# Referências da atualização 2.4.0

O leitor usa o módulo nativo Qt PDF, com apresentação de leitura contínua, ajuste à
largura, página selecionada e barra de rolagem. A inspiração de uso é a familiaridade
dos visualizadores comuns de PDF, incluindo o Google Drive citado pelo usuário;
não depende de conta, serviço ou código do Google Drive.

- [QPdfView e modos de leitura](https://doc.qt.io/qtforpython-6/PySide6/QtPdfWidgets/QPdfView.html)
- [Exemplo oficial de visualizador Qt](https://doc.qt.io/qtforpython-6/examples/example_pdfwidgets_pdfviewer.html)
- [Navegação de páginas](https://doc.qt.io/qtforpython-6/PySide6/QtPdf/QPdfPageNavigator.html)
- [Implementação Qt de cache e layout](https://github.com/qt/qtwebengine/blob/6.12/src/pdfwidgets/qpdfview.cpp)

A implementação deste aplicativo persiste posição, proporção de rolagem e leitura no
SQLite local. Reaproveita a renderização nativa e recicla seu cache para evitar retenção
de muitas páginas longas. Não foram incorporados componentes de interface do Google.

As referências abaixo documentam a atualização anterior.

# Referências da atualização 2.3.0

Consultadas em 12/11/2026. As melhorias foram implementadas no código deste projeto;
as referências serviram para comparar soluções e fluxos, sem incorporar código externo.

| Referência | Arquivo ou página | Ideia aproveitada |
|---|---|---|
| HakuNeko | [DownloadJob.mjs](https://github.com/manga-download/hakuneko/blob/master/src/web/mjs/engine/DownloadJob.mjs) | Separar estados da tarefa e publicar progresso apenas quando muda. |
| MangaDex Downloader | [downloader.py](https://github.com/mansuf/mangadex-downloader/blob/master/mangadex_downloader/downloader.py) | Trabalho com arquivos temporários e dados em blocos. |
| FMD2 | [README](https://github.com/dazedcat19/FMD2) | Entrada de múltiplos links e conversão dos capítulos. |
| Mihon | [CHANGELOG](https://github.com/mihonapp/mihon/blob/main/CHANGELOG.md) | Evitar atualizações redundantes em listas grandes e downloads duplicados. |

Aplicações nesta versão: fila incremental, atualizações agrupadas em segundo plano,
lotes de URLs com cancelamento, pular PDFs com recibo válido e verificações em blocos.
O gerador PDF foi refeito para gravar uma página por vez, sem acumular o capítulo.
Os adaptadores do aplicativo continuam próprios; isto não importa os catálogos de
sites, extensões, mecanismos de acesso ou todo o código dos projetos consultados.

## Medições locais

- Fila com 1.000 capítulos: 101,32 MB no início e 103,85 MB após 50 atualizações.
- Conversão local de Vagabond capítulo 1: 41 páginas, PDF de 48,16 MB,
  pico de 159,81 MB no processo inteiro e 117,01 MB ao terminar.
- As imagens e os PDFs do usuário permaneceram intactos. O teste gerou saída temporária.
- Evidência: `tmp/memory-profile-real.json`. Os números descrevem este cenário;
  não representam um teto de memória para qualquer imagem ou computador.

Verificação adicional no executável congelado, oculto, com dados isolados: 1.000
tarefas e conversão offline das 41 páginas concluída; pico de 127,25 MB. O
controlador encerrou o processo de teste ao terminar a amostragem. Evidência:
`tmp/memory-frozen.json`. O smoke separado validou encerramento normal.

## Google Drive — 2.5.0

- OAuth Desktop, PKCE e loopback: https://developers.google.com/identity/protocols/oauth2/native-app
- Escopos para acesso a pastas existentes: https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- Listagem e paginação: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list
- Upload retomável e consulta de posição: https://developers.google.com/workspace/drive/api/guides/manage-uploads

A implementação usa a API oficial via HTTPS. Os testes de autorização e transferência
simulam as respostas do Google; não demonstram conexão com uma conta real.
