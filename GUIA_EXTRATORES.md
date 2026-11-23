# Guia de extratores

FlorManga está em `app/extractors/flormanga.py`: lê a obra no breadcrumb, isola links
diretos de capítulos e extrai listas pelos seletores Madara/option data-redirect.
Não trata próximo capítulo como próxima página da listagem.

Antes de integrar uma fonte, avalie termos, robots.txt, permissão do conteúdo e limites.
Não adicione mecanismos para contornar autenticação, CAPTCHA, paywall ou DRM.

O protocolo em `app/extractors/base.py` define can_handle, get_manga_info,
get_chapters e get_chapter_pages. Use o HttpClient recebido; não use uma sessão
paralela que contorne segurança, redirects, limites ou robots.txt.

Para HTML semelhante, derive de HtmlExtractor, declare nome, chapter_selector e
image_selector e implemente can_handle com igualdade de domínio ou sufixo com ponto.
Registre a classe antes de HtmlExtractor na Registry. Para API pública permitida,
implemente o protocolo completo com as mesmas proteções de transporte.

Retorne Chapter(title, URL absoluta) e PageList(urls, authoritative=False).
Somente marque authoritative=True quando um contrato real da fonte comprovar que
a contagem esperada corresponde ao capítulo inteiro. Não deduza isso da quantidade
de tags img. Paginação deve percorrer a listagem completa e manter versões distintas.

Inclua fixtures representativas de metadados, lazy loading, variantes, paginação,
mudança de layout e acesso negado. Teste seleção de domínio e rejeição de domínio
parecido. Uma fixture sintética não comprova que um site real funciona.

As classes BorutoExtractor e MangaLivreExtractor preservam os seletores originais;
foram verificadas apenas com fixtures. Fallback reconhece estruturas de leitor
conhecidas, títulos e JSON-LD hasPart. BrowserRenderer oferece fallback opcional na
instalação Python, com rotas mediadas pelo HttpClient, contexto isolado e sem cookies
pessoais. Chromium não faz parte do exe. A renderização tem limites e não substitui
adaptadores para paginação AJAX interativa ou APIs que exigem métodos não permitidos.

Integração real deve ficar separada: operador informa URL de fonte autorizada,
confere resultado manualmente e registra versão/data e limites. A suíte principal
não depende de sites externos.
