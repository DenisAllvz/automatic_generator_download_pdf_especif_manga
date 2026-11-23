import os
import requests
from bs4 import BeautifulSoup
from PIL import Image

def baixar_capitulo(url, nome_arquivo_pdf):
    # Simulando um navegador real para evitar bloqueios do site
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
    }

    print(f"[*] Acessando a URL: {url}")
    resposta = requests.get(url, headers=headers)
    
    if resposta.status_code != 200:
        print(f"[!] Erro ao acessar a página. Código de status: {resposta.status_code}")
        return

    # Passa o HTML para o BeautifulSoup analisar
    soup = BeautifulSoup(resposta.text, 'html.parser')

    # Encontra todas as tags de imagem que contêm a classe específica
    imagens_tags = soup.find_all('img', class_='wp-manga-chapter-img')

    if not imagens_tags:
        print("[!] Nenhuma imagem encontrada. A estrutura do site pode ter mudado.")
        return

    # Cria uma pasta temporária para armazenar as imagens baixadas
    pasta_temp = "temp_imagens_manga"
    os.makedirs(pasta_temp, exist_ok=True)
    caminhos_imagens = []

    print(f"[*] Encontradas {len(imagens_tags)} páginas. Iniciando download...")

    # Loop para baixar cada imagem
    for i, tag in enumerate(imagens_tags):
        # Pega a URL da imagem e usa .strip() para remover os espaços em branco indesejados
        img_url = tag.get('src').strip()
        
        try:
            img_resposta = requests.get(img_url, headers=headers)
            img_resposta.raise_for_status() # Verifica se o download falhou

            # Salva a imagem com números formatados (001.jpg, 002.jpg) para garantir a ordem no PDF
            caminho_arquivo = os.path.join(pasta_temp, f"pagina_{i:03d}.jpg")
            
            with open(caminho_arquivo, 'wb') as f:
                f.write(img_resposta.content)
            
            caminhos_imagens.append(caminho_arquivo)
            print(f"    - Baixada: página {i+1} de {len(imagens_tags)}")
            
        except Exception as e:
            print(f"[!] Erro ao baixar a imagem da página {i+1}: {e}")

    # Montando o PDF
    if caminhos_imagens:
        print("[*] Todas as imagens baixadas. Montando o PDF...")
        imagens_abertas = []

        # A primeira imagem precisa ser o "documento base" do PDF
        primeira_imagem = Image.open(caminhos_imagens[0]).convert('RGB')

        # As outras imagens são adicionadas a uma lista
        for caminho in caminhos_imagens[1:]:
            img = Image.open(caminho).convert('RGB')
            imagens_abertas.append(img)

        # Salva tudo em um único arquivo PDF
        primeira_imagem.save(nome_arquivo_pdf, save_all=True, append_images=imagens_abertas)
        print(f"[*] Sucesso! PDF salvo como: {nome_arquivo_pdf}")

        # Limpeza: apaga as imagens soltas e a pasta temporária
        print("[*] Limpando arquivos temporários...")
        for caminho in caminhos_imagens:
            os.remove(caminho)
        os.rmdir(pasta_temp)
        print("[*] Processo finalizado!")

# ==== EXECUÇÃO ====
if __name__ == "__main__":
    url_do_capitulo = "https://leitor.borutoexplorer.com.br/manga/naruto-versao-colorida-oficial/volume-21/capitulo-186/"
    nome_do_pdf = "Naruto_Colorido_Cap_186.pdf"
    
    baixar_capitulo(url_do_capitulo, nome_do_pdf)