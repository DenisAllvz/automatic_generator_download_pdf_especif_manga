import os
import shutil
import threading
import asyncio
import aiohttp
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from PIL import Image
import customtkinter as ctk
from playwright.async_api import async_playwright

# --- CORREÇÃO DE ROTA PARA O VENV NO WINDOWS ---
os.environ['TCL_LIBRARY'] = r"C:\Users\denil\AppData\Local\Programs\Python\Python313\tcl\tcl8.6"
os.environ['TK_LIBRARY'] = r"C:\Users\denil\AppData\Local\Programs\Python\Python313\tcl\tk8.6"
# -----------------------------------------------

class ExtratorMangaAssincrono:
    def __init__(self, app_ref):
        self.app = app_ref
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/117.0.0.0 Safari/537.36"
        }

    def extrair_nome_manga(self, url):
        partes = [p for p in url.strip('/').split('/') if p]
        return partes[-1] if partes else "Manga_Desconhecido"

    def obter_nome_pdf(self, url_capitulo):
        nome_cap = [p for p in url_capitulo.strip('/').split('/') if p][-1]
        return f"{nome_cap}.pdf"

    async def obter_links_capitulos(self, url_principal):
        self.app.escrever_log("[*] Acionando navegador fantasma (Playwright) para burlar bloqueios...")
        try:
            async with async_playwright() as p:
                # Inicia o navegador invisível
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Finge ser um navegador real para evitar bloqueios iniciais
                await page.set_extra_http_headers({"User-Agent": self.headers["User-Agent"]})
                
                self.app.escrever_log("[*] Carregando o site e processando JavaScript...")
                # Espera até a rede ficar ociosa (sinal de que o site terminou de carregar os scripts)
                await page.goto(url_principal, wait_until="networkidle", timeout=60000)
                
                # Rola até o final da página para forçar o carregamento de capítulos ocultos
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2) # Pausa dramática para os elementos renderizarem na tela
                
                html = await page.content()
                await browser.close()
                self.app.escrever_log("[+] HTML processado e extraído com sucesso.")

            soup = BeautifulSoup(html, 'html.parser')
            dominio = urlparse(url_principal).netloc
            links = []

            if "borutoexplorer" in dominio:
                itens = soup.find_all('li', class_='wp-manga-chapter')
                for item in itens:
                    tag_a = item.find('a')
                    if tag_a and 'href' in tag_a.attrs:
                        links.append(tag_a['href'])
                        
            elif "mangalivre" in dominio:
                tags_a = soup.find_all('a', href=True)
                for tag in tags_a:
                    href = tag['href']
                    if ('/capitulo-' in href or '/cap-' in href or 'capitulo' in href) and href not in links:
                        links.append(href)

            return links[::-1]
        except Exception as e:
            self.app.escrever_log(f"[!] Erro ao procurar capítulos com o navegador: {e}")
            return []

    async def baixar_imagem(self, session, img_url, caminho_img):
        if self.app.stop_event.is_set(): return False
        try:
            async with session.get(img_url, headers=self.headers, timeout=10) as img_res:
                tipo_conteudo = img_res.headers.get('Content-Type', '')
                if 'image' in tipo_conteudo:
                    conteudo = await img_res.read()
                    with open(caminho_img, 'wb') as f:
                        f.write(conteudo)
                    
                    self.imagens_baixadas += 1
                    self.app.atualizar_progresso(self.imagens_baixadas / self.total_imagens_capitulo)
                    return caminho_img
        except Exception:
            pass 
        return False

    async def _lidar_com_erro(self, nome_cap):
        self.app.pedir_decisao_erro(nome_cap)
        while not self.app.choice_event.is_set():
            await asyncio.sleep(0.5)

        if self.app.user_choice == "cancel":
            self.app.stop_event.set()
        return False 

    async def baixar_capitulo(self, session, url_capitulo, pasta_manga):
        nome_pdf = self.obter_nome_pdf(url_capitulo)
        nome_cap = nome_pdf.replace('.pdf', '')
        caminho_pdf = os.path.join(pasta_manga, nome_pdf)
        pasta_temp = os.path.join(pasta_manga, f"temp_{nome_cap}")

        if self.app.stop_event.is_set(): return False
        if os.path.exists(caminho_pdf):
            return True

        self.app.escrever_log(f"[*] Acessando: {nome_cap}...")
        
        try:
            async with session.get(url_capitulo, headers=self.headers, timeout=15) as res:
                html = await res.text()
            
            soup = BeautifulSoup(html, 'html.parser')
            dominio = urlparse(url_capitulo).netloc
            
            if "borutoexplorer" in dominio:
                imagens_tags = soup.find_all('img', class_='wp-manga-chapter-img')
            elif "mangalivre" in dominio:
                imagens_tags = soup.find_all('img', class_='chapter-image')
            else:
                imagens_tags = soup.find_all('img')

            if not imagens_tags:
                self.app.escrever_log(f"[!] Nenhuma imagem encontrada no {nome_cap}.")
                return await self._lidar_com_erro(nome_cap)

            os.makedirs(pasta_temp, exist_ok=True)
            self.total_imagens_capitulo = len(imagens_tags)
            self.imagens_baixadas = 0
            self.app.atualizar_progresso(0)

            tasks = []
            for i, tag in enumerate(imagens_tags):
                img_url = tag.get('src').strip()
                caminho_img = os.path.join(pasta_temp, f"{i:03d}.jpg")
                tasks.append(self.baixar_imagem(session, img_url, caminho_img))

            resultados = await asyncio.gather(*tasks)

            caminhos_imagens = [r for r in resultados if r is not False]
            caminhos_imagens.sort()

            if self.app.stop_event.is_set(): return False

            if len(caminhos_imagens) < (self.total_imagens_capitulo * 0.5):
                self.app.escrever_log(f"[!] Apenas {len(caminhos_imagens)}/{self.total_imagens_capitulo} imagens baixadas no {nome_cap}.")
                return await self._lidar_com_erro(nome_cap)
            
            await asyncio.to_thread(self._montar_pdf_em_memoria, caminhos_imagens, caminho_pdf)
            
            self.app.escrever_log(f"[+] Sucesso: {nome_pdf} criado!\n")
            self.app.atualizar_progresso(0)
            return True

        except Exception as e:
            self.app.escrever_log(f"[!] Erro crítico no {nome_cap}: {e}")
            return await self._lidar_com_erro(nome_cap)
            
        finally:
            if os.path.exists(pasta_temp):
                shutil.rmtree(pasta_temp, ignore_errors=True)

    def _montar_pdf_em_memoria(self, caminhos_imagens, caminho_pdf):
        if not caminhos_imagens: return
        imgs_abertas = []
        primeira = Image.open(caminhos_imagens[0]).convert('RGB')
        for caminho in caminhos_imagens[1:]:
            imgs_abertas.append(Image.open(caminho).convert('RGB'))
        primeira.save(caminho_pdf, save_all=True, append_images=imgs_abertas)


class AppManga(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Manga Downloader - Automação Total")
        self.geometry("750x650")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.stop_event = threading.Event()
        self.choice_event = threading.Event()
        self.user_choice = "continue"

        self.lbl_titulo = ctk.CTkLabel(self, text="Gerenciador de Downloads Assíncrono", font=("Arial", 20, "bold"))
        self.lbl_titulo.pack(pady=(20, 10))

        self.entry_url = ctk.CTkEntry(self, placeholder_text="Cole o link da página principal do mangá aqui...", width=600)
        self.entry_url.pack(pady=10)

        self.frame_botoes = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_botoes.pack(pady=10)

        self.btn_baixar = ctk.CTkButton(self.frame_botoes, text="Iniciar Varredura e Download", command=self.iniciar_download_thread)
        self.btn_baixar.pack(side="left", padx=10)

        self.btn_cancelar = ctk.CTkButton(self.frame_botoes, text="Cancelar", command=self.cancelar_processo, fg_color="#c0392b", hover_color="#922b21", state="disabled")
        self.btn_cancelar.pack(side="left", padx=10)

        self.progress_bar = ctk.CTkProgressBar(self, width=600)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=(15, 10))

        self.caixa_texto = ctk.CTkTextbox(self, width=600, height=350, state="disabled")
        self.caixa_texto.pack(pady=(5, 20))

    def escrever_log(self, texto):
        self.caixa_texto.configure(state="normal")
        self.caixa_texto.insert("end", texto + "\n")
        self.caixa_texto.see("end")
        self.caixa_texto.configure(state="disabled")

    def atualizar_progresso(self, valor):
        self.progress_bar.set(valor)

    def cancelar_processo(self):
        self.escrever_log("[!] Cancelando operação... Aguarde o encerramento da tarefa atual.")
        self.stop_event.set()
        self.btn_cancelar.configure(state="disabled")

    def pedir_decisao_erro(self, nome_capitulo):
        self.choice_event.clear()
        self.user_choice = "continue" 
        self.after(0, self._mostrar_popup_erro, nome_capitulo)

    def _mostrar_popup_erro(self, nome_capitulo):
        self.dialog = ctk.CTkToplevel(self)
        self.dialog.title("Falha no Capítulo")
        self.dialog.geometry("450x200")
        self.dialog.attributes("-topmost", True)
        self.dialog.grab_set() 

        lbl = ctk.CTkLabel(self.dialog, text=f"Não foi possível baixar/gerar: {nome_capitulo}\nDeseja continuar os próximos ou cancelar todo o processo?", wraplength=400)
        lbl.pack(pady=(20, 10))

        self.tempo_restante = 10
        self.lbl_timer = ctk.CTkLabel(self.dialog, text=f"Continuando automaticamente em {self.tempo_restante}s...", text_color="gray")
        self.lbl_timer.pack(pady=5)

        frame_btn = ctk.CTkFrame(self.dialog, fg_color="transparent")
        frame_btn.pack(pady=10)

        btn_cont = ctk.CTkButton(frame_btn, text="Ignorar e Continuar", command=lambda: self._resolver_popup("continue"))
        btn_cont.pack(side="left", padx=10)

        btn_canc = ctk.CTkButton(frame_btn, text="Cancelar Todo o Download", command=lambda: self._resolver_popup("cancel"), fg_color="#c0392b", hover_color="#922b21")
        btn_canc.pack(side="left", padx=10)

        self._atualizar_timer_popup()

    def _atualizar_timer_popup(self):
        if self.tempo_restante > 0 and self.dialog.winfo_exists():
            self.lbl_timer.configure(text=f"Continuando automaticamente em {self.tempo_restante}s...")
            self.tempo_restante -= 1
            self.timer_id = self.after(1000, self._atualizar_timer_popup)
        elif self.dialog.winfo_exists():
            self._resolver_popup("continue")

    def _resolver_popup(self, escolha):
        self.user_choice = escolha
        self.choice_event.set() 
        if hasattr(self, 'timer_id'):
            self.after_cancel(self.timer_id)
        if self.dialog.winfo_exists():
            self.dialog.destroy()

    def iniciar_download_thread(self):
        url = self.entry_url.get().strip()
        if not url: return

        self.stop_event.clear()
        self.btn_baixar.configure(state="disabled", text="A processar...")
        self.btn_cancelar.configure(state="normal")
        self.progress_bar.set(0)
        
        self.escrever_log("=========================================")
        self.escrever_log(f"[*] Iniciando análise e auditoria: {url}")
        
        thread = threading.Thread(target=self._configurar_loop_assincrono, args=(url,))
        thread.start()

    def _configurar_loop_assincrono(self, url):
        asyncio.run(self.processar_manga_async(url))

    async def processar_manga_async(self, url):
        extrator = ExtratorMangaAssincrono(app_ref=self)
        nome_manga = extrator.extrair_nome_manga(url)
        pasta_destino = os.path.join(os.getcwd(), "Downloads_Mangas", nome_manga)
        
        arquivos_locais = set()
        if os.path.exists(pasta_destino):
            self.escrever_log("[*] Pasta encontrada. Auditando integridade dos PDFs locais...")
            for arquivo in os.listdir(pasta_destino):
                if arquivo.endswith('.pdf'):
                    caminho_completo = os.path.join(pasta_destino, arquivo)
                    tamanho_kb = os.path.getsize(caminho_completo) / 1024
                    
                    if tamanho_kb > 500:
                        arquivos_locais.add(arquivo)
                    else:
                        self.escrever_log(f"[!] PDF Fantasma detectado e removido: {arquivo} ({tamanho_kb:.1f} KB)")
                        os.remove(caminho_completo)
                        
            self.escrever_log(f"[*] Você possui {len(arquivos_locais)} capítulos VÁLIDOS locais.")
        else:
            os.makedirs(pasta_destino)
            self.escrever_log("[*] Criando nova pasta para o mangá...")
        
        # O Playwright faz a extração inicial dos links pesados
        links_capitulos = await extrator.obter_links_capitulos(url)
        
        if not links_capitulos:
            self.escrever_log("[!] Erro: Nenhum link encontrado. O site pode estar bloqueando a automação.")
            self.after(0, self.finalizar_processo)
            return

        self.escrever_log(f"[*] O bot mapeou {len(links_capitulos)} links disponíveis no site.")

        links_para_baixar = []
        for link in links_capitulos:
            nome_pdf = extrator.obter_nome_pdf(link)
            if nome_pdf not in arquivos_locais:
                links_para_baixar.append(link)

        if not links_para_baixar:
            self.escrever_log("\n[+] VERIFICAÇÃO CONCLUÍDA: Você já possui todos os capítulos atualizados e íntegros!")
            self.after(0, self.finalizar_processo)
            return

        self.escrever_log(f"[*] Faltam {len(links_para_baixar)} capítulos reais. Iniciando downloads simultâneos...\n")
        capitulos_falhos = []

        # O aiohttp assume o trabalho bruto e simultâneo de baixar as imagens
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=20)) as session:
            for link in links_para_baixar:
                if self.stop_event.is_set(): break
                
                if link.startswith('/'):
                    dominio = urlparse(url).netloc
                    esquema = urlparse(url).scheme
                    link = f"{esquema}://{dominio}{link}"
                    
                sucesso = await extrator.baixar_capitulo(session, link, pasta_destino)
                
                if not sucesso and not self.stop_event.is_set():
                    capitulos_falhos.append(extrator.obter_nome_pdf(link))

        if self.stop_event.is_set():
            self.escrever_log("[-] Operação cancelada pelo usuário ou falha crítica.")
        else:
            self.escrever_log("\n[*] Processo de sincronização finalizado!")
            if capitulos_falhos:
                self.escrever_log("=========================================")
                self.escrever_log("           RELATÓRIO DE FALHAS           ")
                self.escrever_log("=========================================")
                self.escrever_log(f"Não foi possível baixar {len(capitulos_falhos)} capítulos:")
                for cap in capitulos_falhos:
                    self.escrever_log(f"  - {cap}")
                self.escrever_log("\nDica: Se a falha persistir, o site pode estar com instabilidade.")
                self.escrever_log("=========================================\n")
            else:
                self.escrever_log("[+] Arquivos 100% sincronizados e sem erros locais!")
            
        self.after(0, self.finalizar_processo)

    def finalizar_processo(self):
        self.btn_baixar.configure(state="normal", text="Iniciar Varredura e Download")
        self.btn_cancelar.configure(state="disabled")
        self.progress_bar.set(0)

if __name__ == "__main__":
    app = AppManga()
    app.mainloop()