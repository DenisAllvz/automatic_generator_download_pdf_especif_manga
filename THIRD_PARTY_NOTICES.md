# Dependências e distribuição

Este pacote utiliza PySide6/Qt e Shiboken (LGPLv3/GPLv3/comercial, conforme componentes),
aiohttp (Apache 2.0/MIT), BeautifulSoup (MIT), Pillow (HPND), img2pdf (LGPLv3),
pikepdf (MPL 2.0), libqpdf e dependências transitivas. PyInstaller possui licença
GPL com exceção para distribuição dos executáveis. Consulte as licenças exatas
das versões instaladas antes de redistribuir uma versão modificada.

Qt é ligado dinamicamente: DLLs permanecem separadas em `_internal/PySide6`; o pacote
onedir permite substituir bibliotecas compatíveis. Código e licenças upstream:
[Qt for Python](https://code.qt.io/cgit/pyside/pyside-setup.git/),
[Qt](https://code.qt.io/), [LGPLv3](https://www.gnu.org/licenses/lgpl-3.0.html),
[Pillow](https://github.com/python-pillow/Pillow),
[aiohttp](https://github.com/aio-libs/aiohttp),
[img2pdf](https://gitlab.mister-muffin.de/josch/img2pdf),
[pikepdf](https://github.com/pikepdf/pikepdf).

O build também contém runtimes Microsoft Visual C++ redistribuídos junto ao wheel Qt.
Não confunda a licença do aplicativo com a de suas dependências. Esta entrega não
define nem altera a licença autoral do repositório original.

Fonte MangaDex: [MangaDex](https://mangadex.org),
[documentação da API](https://api.mangadex.org/docs/) e
[limites oficiais](https://api.mangadex.org/docs/2-limitations/).
Créditos dos grupos são exibidos nos títulos dos capítulos. O adaptador usa a API
pública para clientes; a listagem de imagens assinadas não é uma varredura HTML.
Limites: espaçamento global de 0,25 s e AtHome de 1,6 s, respeitando 429/reset.
