import os
import sys

# --- CORREÇÃO DE ROTA PARA O VENV NO WINDOWS ---
os.environ['TCL_LIBRARY'] = r"C:\Users\denil\AppData\Local\Programs\Python\Python313\tcl\tcl8.6"
os.environ['TK_LIBRARY'] = r"C:\Users\denil\AppData\Local\Programs\Python\Python313\tcl\tk8.6"
# -----------------------------------------------

import re
import threading
import requests
from bs4 import BeautifulSoup
from PIL import Image
import customtkinter as ctk
# ==========================================
# LÓGICA DE EXTRAÇÃO E DOWNLOAD
# ==========================================
class ExtratorMangaGenerico:
    def __init__(self, log_callback):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
        }
        self.log = log_callback # Função para mandar mensagens para a interface

    def extrair_nome_manga(self, url):
        # Tenta extrair o nome do mangá pela URL (ex: naruto-versao-colorida-oficial)
        partes = [p for p in url.strip('/').split('/') if p]
        return partes[-1] if partes else "Manga_Desconhecido"

    def obter_links_capitulos(self, url_principal):
        self.log(f"[*] Analisando a página principal: {url_principal}")
        try:
            res = requests.get(url_principal, headers=self.headers, timeout=10)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Padrão para sites com tema Madara (como o Boruto Explorer)
            # Encontra todos os links dentro de itens de lista com a classe de capítulo
            links = []
            itens_capitulo = soup.find_all('li', class_='wp-manga-chapter')
            
            for item in itens_capitulo:
                tag_a = item.find('a')
                if tag_a and 'href' in tag_a.attrs:
                    links.append(tag_a['href'])
            
            # Inverte a lista para baixar do primeiro para o mais recente
            return links[::-1] 
        except Exception as e:
            self.log(f"[!] Erro ao buscar capítulos: {e}")
            return []

    def baixar_capitulo(self, url_capitulo, pasta_manga):
        try:
            # Extrai o nome do capítulo da URL (ex: capitulo-186)
            nome_cap = [p for p in url_capitulo.strip('/').split('/') if p][-1]
            nome_pdf = f"{nome_cap}.pdf"
            caminho_pdf = os.path.join(pasta_manga, nome_pdf)

            # VERIFICAÇÃO: Se o arquivo já existe, pula o download
            if os.path.exists(caminho_pdf):
                self.log(f"[-] O {nome_pdf} já existe. Pulando...")
                return True

            self.log(f"[*] Baixando: {nome_cap}...")
            res = requests.get(url_capitulo, headers=self.headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Padrão de imagens da página de leitura
            imagens_tags = soup.find_all('img', class_='wp-manga-chapter-img')
            
            if not imagens_tags:
                self.log(f"[!] Nenhuma imagem encontrada no {nome_cap}.")
                return False

            pasta_temp = os.path.join(pasta_manga, f"temp_{nome_cap}")
            os.makedirs(pasta_temp, exist_ok=True)
            caminhos_imagens = []

            for i, tag in enumerate(imagens_tags):
                img_url = tag.get('src').strip()
                img_res = requests.get(img_url, headers=self.headers)
                
                caminho_img = os.path.join(pasta_temp, f"{i:03d}.jpg")
                with open(caminho_img, 'wb') as f:
                    f.write(img_res.content)
                caminhos_imagens.append(caminho_img)

            # Montagem do PDF
            if caminhos_imagens:
                imgs_abertas = []
                primeira = Image.open(caminhos_imagens[0]).convert('RGB')
                for caminho in caminhos_imagens[1:]:
                    imgs_abertas.append(Image.open(caminho).convert('RGB'))
                
                primeira.save(caminho_pdf, save_all=True, append_images=imgs_abertas)
                
                # Limpeza
                for caminho in caminhos_imagens:
                    os.remove(caminho)
                os.rmdir(pasta_temp)
                self.log(f"[+] Sucesso: {nome_pdf} salvo!")
                return True

        except Exception as e:
            self.log(f"[!] Erro crítico no {url_capitulo}: {e}")
            return False

# ==========================================
# INTERFACE GRÁFICA (GUI)
# ==========================================
class AppManga(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Manga Downloader - Auto PDF")
        self.geometry("700x500")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Título
        self.lbl_titulo = ctk.CTkLabel(self, text="Gerenciador de Downloads de Mangá", font=("Arial", 20, "bold"))
        self.lbl_titulo.pack(pady=(20, 10))

        # Input de URL
        self.entry_url = ctk.CTkEntry(self, placeholder_text="Cole o link da página principal do mangá aqui...", width=600)
        self.entry_url.pack(pady=10)

        # Botão Iniciar
        self.btn_baixar = ctk.CTkButton(self, text="Iniciar Varredura e Download", command=self.iniciar_download_thread)
        self.btn_baixar.pack(pady=10)

        # Caixa de Log
        self.caixa_texto = ctk.CTkTextbox(self, width=600, height=250, state="disabled")
        self.caixa_texto.pack(pady=(10, 20))

    def escrever_log(self, texto):
        # Permite escrever na caixa de texto desabilitada
        self.caixa_texto.configure(state="normal")
        self.caixa_texto.insert("end", texto + "\n")
        self.caixa_texto.see("end") # Rola para baixo automaticamente
        self.caixa_texto.configure(state="disabled")

    def iniciar_download_thread(self):
        url = self.entry_url.get().strip()
        if not url:
            self.escrever_log("[!] Por favor, insira uma URL válida.")
            return

        # Desativa o botão para evitar múltiplos cliques
        self.btn_baixar.configure(state="disabled", text="Processando...")
        self.escrever_log("=========================================")
        self.escrever_log(f"[*] Iniciando processo para: {url}")
        
        # Inicia o processo em uma thread separada para não travar a UI
        thread = threading.Thread(target=self.processar_manga, args=(url,))
        thread.start()

    def processar_manga(self, url):
        extrator = ExtratorMangaGenerico(log_callback=self.escrever_log)
        
        # Cria a pasta baseada no nome do mangá
        nome_manga = extrator.extrair_nome_manga(url)
        pasta_destino = os.path.join(os.getcwd(), "Downloads_Mangas", nome_manga)
        os.makedirs(pasta_destino, exist_ok=True)
        self.escrever_log(f"[*] Pasta de destino: {pasta_destino}")

        # Busca os capítulos
        links_capitulos = extrator.obter_links_capitulos(url)
        
        if not links_capitulos:
            self.escrever_log("[!] Não foi possível encontrar os capítulos na página.")
            self.finalizar_processo()
            return

        self.escrever_log(f"[*] Encontrados {len(links_capitulos)} capítulos. Analisando...")

        # Inicia os downloads
        for link in links_capitulos:
            extrator.baixar_capitulo(link, pasta_destino)

        self.escrever_log("[*] Todos os capítulos foram processados com sucesso!")
        self.finalizar_processo()

    def finalizar_processo(self):
        # Restaura o botão na interface
        self.btn_baixar.configure(state="normal", text="Iniciar Varredura e Download")
        self.entry_url.delete(0, 'end')

if __name__ == "__main__":
    app = AppManga()
    app.mainloop()