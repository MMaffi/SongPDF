import os
import sys
import sqlite3
import tempfile
import webbrowser
import json
import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import datetime
from PIL import Image, ImageTk
import threading
import time

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO

try:
    import PyPDF2
    from docx import Document
except ImportError:
    messagebox.showerror("Erro", "Bibliotecas necessárias não instaladas. Instale com: pip install PyPDF2 python-docx")
    exit()

# ------------------ CONFIGURAÇÃO ------------------
CONFIG_FILE = "config.json"
DB_DIR = "data"
DEFAULT_DB_FILE = os.path.join(DB_DIR, "songpdf.db")
BACKUP_DIR = "backups"

# Registrar fontes Unicode para suporte a caracteres especiais
try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'assets/fonts/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'assets/fonts/DejaVuSans-Bold.ttf'))
    FONT_NAME = 'DejaVuSans'
    FONT_NAME_BOLD = 'DejaVuSans-Bold'
except:
    # Fallback para fontes padrão
    FONT_NAME = 'Helvetica'
    FONT_NAME_BOLD = 'Helvetica-Bold'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

config = load_config()
DB_FILE = config.get("db_file", DEFAULT_DB_FILE)
THEME = config.get("theme", "dark")
ACCENT_COLOR = config.get("accent_color", "#1f6aa5")

# ------------------ BACKUP AUTOMÁTICO ------------------
def criar_backup_automatico():
    """Cria backup automático do banco de dados"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"songpdf_backup_{timestamp}.db")
    
    try:
        conn = sqlite3.connect(DB_FILE)
        bkp = sqlite3.connect(backup_file)
        conn.backup(bkp)
        bkp.close()
        conn.close()
        
        # Manter apenas os 5 backups mais recentes
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("songpdf_backup_")], reverse=True)
        for old_backup in backups[5:]:
            os.remove(os.path.join(BACKUP_DIR, old_backup))
            
    except Exception as e:
        print(f"Erro no backup automático: {e}")

# ------------------ BANCO ------------------
def init_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    
    # Tabela de músicas
    cur.execute("""
        CREATE TABLE IF NOT EXISTS musicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            artista TEXT,
            tonalidade TEXT,
            pdf BLOB,
            texto_original TEXT,
            data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
            data_modificacao DATETIME DEFAULT CURRENT_TIMESTAMP,
            favorito BOOLEAN DEFAULT 0
        )
    """)
    
    # Tabela de grupos
    cur.execute("""
        CREATE TABLE IF NOT EXISTS grupos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            cor TEXT DEFAULT '#1f6aa5',
            descricao TEXT
        )
    """)
    
    # Tabela de relação música-grupo
    cur.execute("""
        CREATE TABLE IF NOT EXISTS musica_grupo (
            musica_id INTEGER,
            grupo_id INTEGER,
            PRIMARY KEY (musica_id, grupo_id),
            FOREIGN KEY (musica_id) REFERENCES musicas (id) ON DELETE CASCADE,
            FOREIGN KEY (grupo_id) REFERENCES grupos (id) ON DELETE CASCADE
        )
    """)
    
    # Tabela de histórico
    cur.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            musica_id INTEGER,
            acao TEXT,
            data DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (musica_id) REFERENCES musicas (id) ON DELETE SET NULL
        )
    """)
    
    # Índices para melhor performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_musicas_titulo ON musicas(titulo)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_musicas_artista ON musicas(artista)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_musicas_data ON musicas(data_criacao)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_musicas_favorito ON musicas(favorito)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_historico_data ON historico(data)")
    
    conn.commit()
    conn.close()

def conectar_banco(path):
    try:
        init_db(path)
        # teste de conexão
        conn = sqlite3.connect(path)
        conn.execute("SELECT 1")
        conn.close()
        
        # Criar backup após conexão bem-sucedida
        threading.Thread(target=criar_backup_automatico, daemon=True).start()
        
        return True
    except Exception as e:
        messagebox.showerror("Erro", f"Falha ao conectar ao banco:\n{e}")
        return False

# inicializa banco padrão se ainda não existir
init_db(DB_FILE)

# ------------------ FUNÇÕES DE GRUPOS ------------------
def fetch_all_grupos():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, nome, cor FROM grupos ORDER BY nome")
    rows = cur.fetchall()
    conn.close()
    return rows

def criar_grupo(nome, cor="#1f6aa5", descricao=""):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO grupos (nome, cor, descricao) VALUES (?, ?, ?)", (nome, cor, descricao))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def atualizar_grupo(grupo_id, nome, cor, descricao):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    try:
        cur.execute("UPDATE grupos SET nome=?, cor=?, descricao=? WHERE id=?", (nome, cor, descricao, grupo_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def excluir_grupo(grupo_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM grupos WHERE id = ?", (grupo_id,))
    conn.commit()
    conn.close()

def adicionar_musica_ao_grupo(musica_id, grupo_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO musica_grupo (musica_id, grupo_id) VALUES (?, ?)", (musica_id, grupo_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remover_musica_do_grupo(musica_id, grupo_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM musica_grupo WHERE musica_id = ? AND grupo_id = ?", (musica_id, grupo_id))
    conn.commit()
    conn.close()

def fetch_musicas_do_grupo(grupo_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        SELECT m.id, m.titulo, m.artista, m.tonalidade, m.favorito
        FROM musicas m
        JOIN musica_grupo mg ON m.id = mg.musica_id
        WHERE mg.grupo_id = ?
        ORDER BY m.titulo
    """, (grupo_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def fetch_grupos_da_musica(musica_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        SELECT g.id, g.nome, g.cor
        FROM grupos g
        JOIN musica_grupo mg ON g.id = mg.grupo_id
        WHERE mg.musica_id = ?
        ORDER BY g.nome
    """, (musica_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

# ------------------ HISTÓRICO ------------------
def registrar_historico(musica_id, acao):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT INTO historico (musica_id, acao) VALUES (?, ?)", (musica_id, acao))
    conn.commit()
    conn.close()

def fetch_historico_recente(limite=10):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        SELECT h.id, m.titulo, h.acao, h.data 
        FROM historico h
        LEFT JOIN musicas m ON h.musica_id = m.id
        ORDER BY h.data DESC
        LIMIT ?
    """, (limite,))
    rows = cur.fetchall()
    conn.close()
    return rows

# ------------------ FAVORITOS ------------------
def toggle_favorito(musica_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE musicas SET favorito = NOT favorito WHERE id = ?", (musica_id,))
    conn.commit()
    conn.close()

# ------------------ PDF ------------------
def gerar_pdf(titulo, artista, tonalidade, letra, tamanho_fonte=11, incluir_cabecalho=True, incluir_numero_pagina=True):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Configurações de fonte
    c.setFont(FONT_NAME_BOLD, 16)
    
    # Calcular posição do título
    titulo_width = c.stringWidth(titulo, FONT_NAME_BOLD, 16)
    titulo_x = (width - titulo_width) / 2
    
    if incluir_cabecalho:
        c.drawString(titulo_x, height - 50, titulo)
        c.setFont(FONT_NAME, 12)
        
        # Formata a linha de artista e tonalidade
        info_line = ""
        if artista and tonalidade:
            info_line = f"{artista} • {tonalidade}"
        elif artista:
            info_line = artista
        elif tonalidade:
            info_line = tonalidade
        
        if info_line:
            info_width = c.stringWidth(info_line, FONT_NAME, 12)
            info_x = (width - info_width) / 2
            c.drawString(info_x, height - 70, info_line)
        
        y_position = height - 100
    else:
        y_position = height - 50
    
    # Preparar o texto da letra com o tamanho de fonte especificado
    c.setFont(FONT_NAME, tamanho_fonte)
    line_height = tamanho_fonte + 3
    margin = 50
    
    # Manter as quebras de linha originais
    lines = letra.splitlines()
    
    # Desenhar as linhas com quebra de página
    page_number = 1
    
    for line in lines:
        if y_position < 50:
            c.showPage()
            c.setFont(FONT_NAME, tamanho_fonte)
            y_position = height - 50
            page_number += 1
            
            # Adicionar número da página
            if incluir_numero_pagina:
                c.setFont(FONT_NAME, 9)
                c.drawString(width - 50, 30, f"Página {page_number}")
                c.setFont(FONT_NAME, tamanho_fonte)
        
        if line.strip():  
            # Quebra de linha automática se a linha for muito longa
            max_width = width - (2 * margin)
            words = line.split()
            current_line = ""
            
            for word in words:
                test_line = current_line + word + " "
                test_width = c.stringWidth(test_line, FONT_NAME, tamanho_fonte)
                
                if test_width > max_width and current_line != "":
                    c.drawString(margin, y_position, current_line)
                    y_position -= line_height
                    current_line = word + " "
                    
                    if y_position < 50:
                        c.showPage()
                        c.setFont(FONT_NAME, tamanho_fonte)
                        y_position = height - 50
                        page_number += 1
                        if incluir_numero_pagina:
                            c.setFont(FONT_NAME, 9)
                            c.drawString(width - 50, 30, f"Página {page_number}")
                            c.setFont(FONT_NAME, tamanho_fonte)
                else:
                    current_line = test_line
            
            if current_line:
                c.drawString(margin, y_position, current_line)
            
        y_position -= line_height
    
    c.save()
    buffer.seek(0)
    return buffer.read()

# ------------------ FUNÇÕES DE BANCO ------------------
def fetch_all_musicas(ordenar_por="data", ordem="DESC", apenas_favoritos=False):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    order_field = {
        "data": "data_criacao",
        "titulo": "titulo",
        "artista": "artista",
        "tonalidade": "tonalidade"
    }.get(ordenar_por, "data_criacao")
    
    where_clause = "WHERE favorito = 1" if apenas_favoritos else ""
    
    query = f"SELECT id, titulo, artista, tonalidade, favorito FROM musicas {where_clause} ORDER BY {order_field} {ordem}"
    cur.execute(query)
    rows = cur.fetchall()
    conn.close()
    return rows

def fetch_pdf(music_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT pdf FROM musicas WHERE id=?", (music_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def insert_music(titulo, artista, tonalidade, pdf_bytes, texto_original=""):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO musicas (titulo, artista, tonalidade, pdf, texto_original) VALUES (?, ?, ?, ?, ?)",
        (titulo, artista, tonalidade, pdf_bytes, texto_original)
    )
    music_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    # Registrar no histórico
    registrar_historico(music_id, "Criação")
    
    return music_id

def update_music(music_id, titulo, artista, tonalidade, pdf_bytes=None, texto_original=""):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    if pdf_bytes:
        cur.execute(
            "UPDATE musicas SET titulo=?, artista=?, tonalidade=?, pdf=?, texto_original=?, data_modificacao=CURRENT_TIMESTAMP WHERE id=?",
            (titulo, artista, tonalidade, pdf_bytes, texto_original, music_id)
        )
    else:
        cur.execute(
            "UPDATE musicas SET titulo=?, artista=?, tonalidade=?, texto_original=?, data_modificacao=CURRENT_TIMESTAMP WHERE id=?",
            (titulo, artista, tonalidade, texto_original, music_id)
        )
    conn.commit()
    conn.close()
    
    # Registrar no histórico
    registrar_historico(music_id, "Edição")

def delete_music(music_id):
    # Registrar no histórico antes de excluir
    registrar_historico(music_id, "Exclusão")
    
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM musicas WHERE id=?", (music_id,))
    conn.commit()
    conn.close()

def search_musicas(campo, termo, apenas_favoritos=False):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    where_favorito = "AND favorito = 1" if apenas_favoritos else ""
    query = f"SELECT id, titulo, artista, tonalidade, favorito FROM musicas WHERE {campo} LIKE ? {where_favorito} ORDER BY data_criacao DESC"
    cur.execute(query, (f"%{termo}%",))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_music_stats():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    stats = {}
    
    # Total de músicas
    cur.execute("SELECT COUNT(*) FROM musicas")
    stats['total'] = cur.fetchone()[0]
    
    # Total de favoritos
    cur.execute("SELECT COUNT(*) FROM musicas WHERE favorito = 1")
    stats['favoritos'] = cur.fetchone()[0]
    
    # Total de grupos
    cur.execute("SELECT COUNT(*) FROM grupos")
    stats['grupos'] = cur.fetchone()[0]
    
    # Música mais recente
    cur.execute("SELECT titulo, artista FROM musicas ORDER BY data_criacao DESC LIMIT 1")
    stats['recente'] = cur.fetchone()
    
    conn.close()
    return stats

# ------------------ FUNÇÃO PARA MENSAGENS NO TOPO ------------------
def mostrar_mensagem_topo(titulo, mensagem, tipo="info"):
    # Criar uma janela temporária para ser pai da messagebox
    root = ctk.CTk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    if tipo == "info":
        result = messagebox.showinfo(titulo, mensagem, parent=root)
    elif tipo == "warning":
        result = messagebox.showwarning(titulo, mensagem, parent=root)
    elif tipo == "error":
        result = messagebox.showerror(titulo, mensagem, parent=root)
    elif tipo == "yesno":
        result = messagebox.askyesno(titulo, mensagem, parent=root)
    elif tipo == "yesnocancel":
        result = messagebox.askyesnocancel(titulo, mensagem, parent=root)
    
    root.destroy()
    return result

# ------------------ CARREGAR IMAGENS ------------------
def carregar_imagem(caminho, tamanho=(20, 20)):
    try:
        img = Image.open(caminho)
        img = img.resize(tamanho, Image.Resampling.LANCZOS)
        return ctk.CTkImage(light_image=img, dark_image=img, size=tamanho)
    except:
        # Fallback para ícones de texto se a imagem não for encontrada
        return None

# ------------------ APP ------------------
class SongPDFApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SongPDF")
        self.geometry("1200x800")
        self.minsize(1000, 700)
        self.iconbitmap("assets/icons/logo.ico")

        # Configurar tema
        ctk.set_appearance_mode(THEME)
        ctk.set_default_color_theme("dark-blue")
        
        # Carregar ícones
        self.icones = {
            "add": carregar_imagem("./assets/icons/add.png"),
            "import": carregar_imagem("./assets/icons/import.png"),
            "groups": carregar_imagem("./assets/icons/groups.png"),
            "search": carregar_imagem("./assets/icons/search.png"),
            "help": carregar_imagem("./assets/icons/help.png"),
            "favorite": carregar_imagem("./assets/icons/favorite.png"),
            "favorite_outline": carregar_imagem("./assets/icons/favorite_outline.png"),
            "open": carregar_imagem("./assets/icons/open.png"),
            "edit": carregar_imagem("./assets/icons/edit.png"),
            "download": carregar_imagem("./assets/icons/download.png"),
            "delete": carregar_imagem("./assets/icons/delete.png"),
            "stats": carregar_imagem("./assets/icons/stats.png"),
            "history": carregar_imagem("./assets/icons/history.png"),
            "settings": carregar_imagem("./assets/icons/settings.png"),
        }

        # Variáveis de estado
        self.grupo_selecionado = None
        self.musicas_atuais = []
        self.filtro_favoritos = False
        self.ordenacao = {"campo": "data_criacao", "ordem": "DESC"}
        self.pesquisa_atual = ""
        self.campo_pesquisa = "titulo"

        # Configurar layout principal
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ---------- Main container ----------
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.main_container.grid_columnconfigure(1, weight=1)
        self.main_container.grid_rowconfigure(1, weight=1)

        # ---------- Sidebar ----------
        self.sidebar = ctk.CTkFrame(self.main_container, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 10))
        self.sidebar.grid_rowconfigure(6, weight=1)

        # Logo
        logo = carregar_imagem("./assets/icons/logo.ico", (40, 40))
        if logo:
            ctk.CTkLabel(self.sidebar, image=logo, text="").pack(pady=(20, 10))
        ctk.CTkLabel(self.sidebar, text="SongPDF Pro", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(0, 20))

        # Navegação
        ctk.CTkButton(self.sidebar, text="Todas as Músicas", command=self.mostrar_todas_musicas,
                     image=self.icones.get("search"), anchor="w").pack(fill="x", padx=10, pady=5)
        
        ctk.CTkButton(self.sidebar, text="Favoritos", command=self.mostrar_favoritos,
                     image=self.icones.get("favorite"), anchor="w").pack(fill="x", padx=10, pady=5)
        
        ctk.CTkButton(self.sidebar, text="Histórico", command=self.mostrar_historico,
                     image=self.icones.get("history"), anchor="w").pack(fill="x", padx=10, pady=5)
        
        ctk.CTkButton(self.sidebar, text="Estatísticas", command=self.mostrar_estatisticas,
                     image=self.icones.get("stats"), anchor="w").pack(fill="x", padx=10, pady=5)

        # Separador
        ctk.CTkFrame(self.sidebar, height=2, fg_color="gray30").pack(fill="x", padx=10, pady=20)

        # Grupos
        ctk.CTkLabel(self.sidebar, text="GRUPOS", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(0, 10))
        self.grupos_container = ctk.CTkScrollableFrame(self.sidebar, height=200)
        self.grupos_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        ctk.CTkButton(self.sidebar, text="Gerenciar Grupos", command=self.gerenciar_grupos_dialog,
                     image=self.icones.get("groups"), anchor="w").pack(fill="x", padx=10, pady=5)

        # Separador
        ctk.CTkFrame(self.sidebar, height=2, fg_color="gray30").pack(fill="x", padx=10, pady=20)

        # Configurações
        ctk.CTkButton(self.sidebar, text="Configurações", command=self.mostrar_configuracoes,
                     image=self.icones.get("settings"), anchor="w").pack(fill="x", padx=10, pady=5)

        # ---------- Top frame ----------
        self.top_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.top_frame.grid(row=0, column=1, sticky="ew", pady=(0, 10))
        self.top_frame.grid_columnconfigure(1, weight=1)

        # Título da página
        self.titulo_pagina = ctk.CTkLabel(self.top_frame, text="Todas as Músicas", font=ctk.CTkFont(size=24, weight="bold"))
        self.titulo_pagina.grid(row=0, column=0, sticky="w", padx=(0, 20))

        # Botões de ação
        action_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        action_frame.grid(row=0, column=2, sticky="e")

        self.btn_nova = ctk.CTkButton(action_frame, text="Nova", width=80, 
                                     image=self.icones.get("add"), command=self.add_music_dialog)
        self.btn_nova.pack(side="left", padx=5)

        self.btn_importar = ctk.CTkButton(action_frame, text="Importar", width=80, 
                                         image=self.icones.get("import"), command=self.import_pdf_dialog)
        self.btn_importar.pack(side="left", padx=5)

        # ---------- Search frame ----------
        self.search_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.search_frame.grid(row=1, column=1, sticky="nsew")
        self.search_frame.grid_columnconfigure(0, weight=1)
        self.search_frame.grid_rowconfigure(1, weight=1)

        # Filtros e busca
        filter_frame = ctk.CTkFrame(self.search_frame, fg_color="transparent")
        filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        filter_frame.grid_columnconfigure(1, weight=1)

        # Ordenação
        ctk.CTkLabel(filter_frame, text="Ordenar por:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.ordenacao_combo = ctk.CTkOptionMenu(filter_frame, values=["Data", "Título", "Artista", "Tonalidade"],
                                                command=self.alterar_ordenacao)
        self.ordenacao_combo.grid(row=0, column=1, sticky="w", padx=(0, 20))
        self.ordenacao_combo.set("Data")

        ctk.CTkLabel(filter_frame, text="Ordem:").grid(row=0, column=2, sticky="w", padx=(0, 5))
        self.ordem_combo = ctk.CTkOptionMenu(filter_frame, values=["Crescente", "Decrescente"],
                                            command=self.alterar_ordem)
        self.ordem_combo.grid(row=0, column=3, sticky="w", padx=(0, 20))
        self.ordem_combo.set("Decrescente")

        # Busca
        search_input_frame = ctk.CTkFrame(filter_frame, fg_color="transparent")
        search_input_frame.grid(row=0, column=4, sticky="e")

        self.campo_pesquisa_combo = ctk.CTkOptionMenu(search_input_frame, values=["Título", "Artista", "Tonalidade"],
                                                     width=80, command=self.alterar_campo_pesquisa)
        self.campo_pesquisa_combo.pack(side="left", padx=(0, 5))
        self.campo_pesquisa_combo.set("Título")

        self.entry_search = ctk.CTkEntry(search_input_frame, placeholder_text="Buscar...", width=200)
        self.entry_search.pack(side="left", padx=(0, 5))
        self.entry_search.bind("<Return>", lambda e: self.apply_search())

        self.btn_search = ctk.CTkButton(search_input_frame, text="", width=40, 
                                       image=self.icones.get("search"), command=self.apply_search)
        self.btn_search.pack(side="left")

        # ---------- Content frame ----------
        self.content_frame = ctk.CTkScrollableFrame(self.search_frame, label_text="")
        self.content_frame.grid(row=1, column=0, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=1)

        # Status bar
        self.status_bar = ctk.CTkLabel(self.main_container, text="Pronto", anchor="w", 
                                      font=ctk.CTkFont(size=12))
        self.status_bar.grid(row=2, column=1, sticky="ew", pady=(10, 0))

        # Carregar dados iniciais
        self.carregar_grupos_sidebar()
        self.mostrar_todas_musicas()

        # Atualizar status bar periodicamente
        self.atualizar_status_bar()

    def atualizar_status_bar(self):
        stats = get_music_stats()
        self.status_bar.configure(text=f"Total: {stats['total']} músicas | Favoritos: {stats['favoritos']} | Grupos: {stats['grupos']}")
        self.after(30000, self.atualizar_status_bar)  # Atualizar a cada 30 segundos

    def carregar_grupos_sidebar(self):
        for widget in self.grupos_container.winfo_children():
            widget.destroy()
        
        grupos = fetch_all_grupos()
        for grupo_id, nome, cor in grupos:
            btn = ctk.CTkButton(self.grupos_container, text=nome, fg_color=cor, hover_color=cor,
                               anchor="w", command=lambda gid=grupo_id, gnome=nome: self.selecionar_grupo(gid, gnome))
            btn.pack(fill="x", pady=2)

    def selecionar_grupo(self, grupo_id, grupo_nome):
        self.grupo_selecionado = grupo_id
        self.titulo_pagina.configure(text=grupo_nome)
        self.filtro_favoritos = False
        self.apply_search()

    def mostrar_todas_musicas(self):
        self.grupo_selecionado = None
        self.filtro_favoritos = False
        self.titulo_pagina.configure(text="Todas as Músicas")
        self.apply_search()

    def mostrar_favoritos(self):
        self.grupo_selecionado = None
        self.filtro_favoritos = True
        self.titulo_pagina.configure(text="Favoritos")
        self.apply_search()

    def mostrar_historico(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Histórico Recente")
        dialog.geometry("600x400")
        dialog.transient(self)
        dialog.grab_set()

        historico = fetch_historico_recente(20)

        frame = ctk.CTkScrollableFrame(dialog)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        if not historico:
            ctk.CTkLabel(frame, text="Nenhuma atividade recente").pack(pady=20)
        else:
            for id, titulo, acao, data in historico:
                item_frame = ctk.CTkFrame(frame)
                item_frame.pack(fill="x", pady=5)

                acao_icone = "📝" if acao == "Criação" else "✏️" if acao == "Edição" else "🗑️"
                texto = f"{acao_icone} {acao}: {titulo or 'Música excluída'}"
                ctk.CTkLabel(item_frame, text=texto, anchor="w").pack(side="left", fill="x", expand=True)
                ctk.CTkLabel(item_frame, text=data, text_color="gray").pack(side="right")

        ctk.CTkButton(dialog, text="Fechar", command=dialog.destroy).pack(pady=10)

    def mostrar_estatisticas(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Estatísticas")
        dialog.geometry("400x300")
        dialog.transient(self)
        dialog.grab_set()

        stats = get_music_stats()

        ctk.CTkLabel(dialog, text="Estatísticas do SongPDF", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=20)

        info_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        info_frame.pack(fill="both", expand=True, padx=20, pady=10)

        ctk.CTkLabel(info_frame, text=f"Total de músicas: {stats['total']}", anchor="w").pack(fill="x", pady=5)
        ctk.CTkLabel(info_frame, text=f"Músicas favoritadas: {stats['favoritos']}", anchor="w").pack(fill="x", pady=5)
        ctk.CTkLabel(info_frame, text=f"Grupos criados: {stats['grupos']}", anchor="w").pack(fill="x", pady=5)
        
        if stats['recente']:
            titulo, artista = stats['recente']
            ctk.CTkLabel(info_frame, text=f"Última música adicionada: {titulo} - {artista}", anchor="w").pack(fill="x", pady=5)

        ctk.CTkButton(dialog, text="Fechar", command=dialog.destroy).pack(pady=20)

    def mostrar_configuracoes(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Configurações")
        dialog.geometry("500x400")
        dialog.transient(self)
        dialog.grab_set()

        tabview = ctk.CTkTabview(dialog)
        tabview.pack(fill="both", expand=True, padx=20, pady=20)

        # Aparência
        tab_aparencia = tabview.add("Aparência")
        tab_geral = tabview.add("Geral")
        tab_banco = tabview.add("Banco de Dados")

        # Aparência
        ctk.CTkLabel(tab_aparencia, text="Tema:", anchor="w").pack(fill="x", pady=(10, 5))
        tema_var = ctk.StringVar(value=THEME)
        tema_combo = ctk.CTkOptionMenu(tab_aparencia, values=["dark", "light", "system"], variable=tema_var)
        tema_combo.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(tab_aparencia, text="Cor de destaque:", anchor="w").pack(fill="x", pady=(10, 5))
        cor_var = ctk.StringVar(value=ACCENT_COLOR)
        cor_entry = ctk.CTkEntry(tab_aparencia, textvariable=cor_var)
        cor_entry.pack(fill="x", pady=(0, 20))

        # Geral
        ctk.CTkLabel(tab_geral, text="Backup automático:", anchor="w").pack(fill="x", pady=(10, 5))
        backup_var = ctk.BooleanVar(value=config.get("backup_auto", True))
        ctk.CTkSwitch(tab_geral, text="Ativar backup automático", variable=backup_var).pack(anchor="w", pady=(0, 20))

        # Banco de Dados
        ctk.CTkLabel(tab_banco, text="Localização do banco:", anchor="w").pack(fill="x", pady=(10, 5))
        ctk.CTkLabel(tab_banco, text=DB_FILE, text_color="gray", anchor="w").pack(fill="x", pady=(0, 5))

        def trocar_banco():
            path = filedialog.askopenfilename(
                filetypes=[("SQLite DB", "*.db")],
                title="Escolha o banco de dados"
            )
            if path and conectar_banco(path):
                global DB_FILE
                DB_FILE = path
                config["db_file"] = path
                save_config(config)
                mostrar_mensagem_topo("Sucesso", f"Conectado ao banco:\n{path}", "info")
                self.carregar_grupos_sidebar()
                self.apply_search()

        ctk.CTkButton(tab_banco, text="Trocar Banco", command=trocar_banco).pack(pady=5)

        def fazer_backup():
            path = filedialog.asksaveasfilename(
                defaultextension=".db",
                filetypes=[("SQLite DB", "*.db")],
                initialfile=f"songpdf_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            )
            if path:
                try:
                    conn = sqlite3.connect(DB_FILE)
                    bkp = sqlite3.connect(path)
                    conn.backup(bkp)
                    bkp.close()
                    conn.close()
                    mostrar_mensagem_topo("Sucesso", f"Backup salvo em:\n{path}", "info")
                except Exception as e:
                    mostrar_mensagem_topo("Erro", f"Falha ao salvar backup: {e}", "error")

        ctk.CTkButton(tab_banco, text="Fazer Backup Agora", command=fazer_backup).pack(pady=5)

        def salvar_config():
            config["theme"] = tema_var.get()
            config["accent_color"] = cor_var.get()
            config["backup_auto"] = backup_var.get()
            save_config(config)
            
            # Aplicar novo tema
            ctk.set_appearance_mode(config["theme"])
            mostrar_mensagem_topo("Sucesso", "Configurações salvas. Reinicie o aplicativo para aplicar todas as mudanças.", "info")
            dialog.destroy()

        ctk.CTkButton(dialog, text="Salvar Configurações", command=salvar_config).pack(pady=20)

    def alterar_ordenacao(self, escolha):
        mapeamento = {
            "Data": "data_criacao",
            "Título": "titulo",
            "Artista": "artista",
            "Tonalidade": "tonalidade"
        }
        self.ordenacao["campo"] = mapeamento.get(escolha, "data_criacao")
        self.apply_search()

    def alterar_ordem(self, escolha):
        self.ordenacao["ordem"] = "ASC" if escolha == "Crescente" else "DESC"
        self.apply_search()

    def alterar_campo_pesquisa(self, escolha):
        mapeamento = {
            "Título": "titulo",
            "Artista": "artista",
            "Tonalidade": "tonalidade"
        }
        self.campo_pesquisa = mapeamento.get(escolha, "titulo")

    def apply_search(self):
        termo = self.entry_search.get().strip()
        self.pesquisa_atual = termo
        
        if self.grupo_selecionado:
            musicas = fetch_musicas_do_grupo(self.grupo_selecionado)
            if termo:
                resultados = []
                for musica in musicas:
                    if self.campo_pesquisa == "titulo" and termo.lower() in musica[1].lower():
                        resultados.append(musica)
                    elif self.campo_pesquisa == "artista" and musica[2] and termo.lower() in musica[2].lower():
                        resultados.append(musica)
                    elif self.campo_pesquisa == "tonalidade" and musica[3] and termo.lower() in musica[3].lower():
                        resultados.append(musica)
                self.carregar_musicas(resultados)
            else:
                self.carregar_musicas(musicas)
        elif self.filtro_favoritos:
            if termo:
                resultados = search_musicas(self.campo_pesquisa, termo, True)
                self.carregar_musicas(resultados)
            else:
                musicas = fetch_all_musicas(apenas_favoritos=True)
                self.carregar_musicas(musicas)
        else:
            if termo:
                resultados = search_musicas(self.campo_pesquisa, termo)
                self.carregar_musicas(resultados)
            else:
                musicas = fetch_all_musicas(self.ordenacao["campo"], self.ordenacao["ordem"])
                self.carregar_musicas(musicas)

    def carregar_musicas(self, musicas):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        
        self.musicas_atuais = musicas
        total = len(musicas)
        
        if total == 0:
            ctk.CTkLabel(self.content_frame, text="Nenhuma música encontrada", 
                         font=ctk.CTkFont(size=16), text_color="gray").pack(pady=50)
            return
        
        # Header com contador
        header_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(header_frame, text=f"{total} música(s) encontrada(s)", 
                    font=ctk.CTkFont(weight="bold"), text_color="gray").pack(anchor="w")
        
        for idx, music in enumerate(musicas):
            self.add_card(music)
            if idx < total - 1:
                ctk.CTkFrame(self.content_frame, height=1, fg_color="gray70").pack(fill="x", pady=5)

    def add_card(self, music):
        music_id, titulo, artista, tonalidade, favorito = music
        card = ctk.CTkFrame(self.content_frame, corner_radius=10)
        card.pack(fill="x", pady=5)
        
        # Frame principal
        main_frame = ctk.CTkFrame(card, fg_color="transparent")
        main_frame.pack(fill="x", padx=10, pady=10)
        
        # Ícone de favorito
        fav_icon = self.icones.get("favorite" if favorito else "favorite_outline")
        fav_btn = ctk.CTkButton(main_frame, image=fav_icon, text="", width=30, height=30,
                               fg_color="transparent", hover_color="gray30",
                               command=lambda: self.toggle_favorito(music_id))
        fav_btn.pack(side="left", padx=(0, 10))
        
        # Informações
        info_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True)
        
        titulo_label = ctk.CTkLabel(info_frame, text=titulo, font=ctk.CTkFont(size=16, weight="bold"),
                                   anchor="w", justify="left")
        titulo_label.pack(anchor="w")
        
        detalhes_text = []
        if artista:
            detalhes_text.append(artista)
        if tonalidade:
            detalhes_text.append(tonalidade)
        
        if detalhes_text:
            detalhes_label = ctk.CTkLabel(info_frame, text=" • ".join(detalhes_text),
                                         text_color="gray", anchor="w", justify="left")
            detalhes_label.pack(anchor="w", pady=(5, 0))
        
        # Mostrar grupos da música
        grupos = fetch_grupos_da_musica(music_id)
        if grupos:
            grupos_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
            grupos_frame.pack(anchor="w", pady=(5, 0))
            
            for grupo_id, nome, cor in grupos:
                grupo_label = ctk.CTkLabel(grupos_frame, text=nome, font=ctk.CTkFont(size=12),
                                          text_color="#d0d0d0", fg_color=f"{cor}", corner_radius=8)
                grupo_label.pack(side="left", padx=(0, 5))
        
        # Botões de ação
        action_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        action_frame.pack(side="right")
        
        ctk.CTkButton(action_frame, text="", image=self.icones.get("open"), width=40,
                     command=lambda: self.open_pdf(music_id)).pack(side="left", padx=2)
        
        menu_btn = ctk.CTkButton(action_frame, text="•••", width=40,
                                command=lambda: self.show_music_menu(music_id, titulo, menu_btn))
        menu_btn.pack(side="left", padx=2)

    def toggle_favorito(self, music_id):
        toggle_favorito(music_id)
        self.apply_search()

    def show_music_menu(self, music_id, titulo, button):
        # Criar menu popup
        menu = ctk.CTkToplevel(self)
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        
        # Posicionar menu abaixo do botão
        x = button.winfo_rootx()
        y = button.winfo_rooty() + button.winfo_height()
        
        # Calcular posição para não sair da tela
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        menu_width = 140
        menu_height = 160
        
        # Ajustar posição se estiver saindo da tela à direita
        if x + menu_width > screen_width:
            x = screen_width - menu_width - 10
        
        # Ajustar posição se estiver saindo da tela em baixo
        if y + menu_height > screen_height:
            y = button.winfo_rooty() - menu_height
        
        menu.geometry(f"{menu_width}x{menu_height}+{x}+{y}")
        
        frame = ctk.CTkFrame(menu, corner_radius=8)
        frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Configurar o grid para centralizar verticalmente
        frame.grid_rowconfigure((0, 1, 2, 3, 4), weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Função para fechar o menu
        def close_menu():
            if menu and menu.winfo_exists():
                if hasattr(menu, '_close_bind_id'):
                    self.unbind("<Button-1>", menu._close_bind_id)
                menu.destroy()
        
        # Botões menores (height reduzido)
        btn_style = {"height": 28, "font": ctk.CTkFont(size=12)}
        
        ctk.CTkButton(frame, text="Grupos", **btn_style, image=self.icones.get("groups"),
                    command=lambda: [close_menu(), self.gerenciar_grupos_musica(music_id, titulo)]).grid(row=0, column=0, sticky="nsew", padx=3, pady=1)
        
        ctk.CTkButton(frame, text="Editar", **btn_style, image=self.icones.get("edit"),
                    command=lambda: [close_menu(), self.edit_music_dialog(music_id)]).grid(row=1, column=0, sticky="nsew", padx=3, pady=1)
        
        ctk.CTkButton(frame, text="Abrir", **btn_style, image=self.icones.get("open"),
                    command=lambda: [close_menu(), self.open_pdf(music_id)]).grid(row=2, column=0, sticky="nsew", padx=3, pady=1)
        
        ctk.CTkButton(frame, text="Download", **btn_style, image=self.icones.get("download"),
                    command=lambda: [close_menu(), self.download_pdf(music_id, titulo)]).grid(row=3, column=0, sticky="nsew", padx=3, pady=1)
        
        ctk.CTkButton(frame, text="Excluir", **btn_style, fg_color="red", image=self.icones.get("delete"),
                    command=lambda: [close_menu(), self.confirm_delete(music_id)]).grid(row=4, column=0, sticky="nsew", padx=3, pady=1)
        
        # Bind global para fechar ao clicar fora
        def close_on_click_outside(event):
            if menu and menu.winfo_exists():
                menu_x = menu.winfo_x()
                menu_y = menu.winfo_y()
                menu_width = menu.winfo_width()
                menu_height = menu.winfo_height()
                
                if (event.x_root < menu_x or event.x_root > menu_x + menu_width or
                    event.y_root < menu_y or event.y_root > menu_y + menu_height):
                    close_menu()
        
        # Bind global no root window
        menu._close_bind_id = self.bind("<Button-1>", close_on_click_outside)
        
        # Fechar com ESC
        def close_on_escape(event):
            close_menu()
        
        menu.bind("<Escape>", close_on_escape)
        menu.focus_set()

    # ---------- Ações ----------
    def open_pdf(self, music_id):
        pdf_bytes = fetch_pdf(music_id)
        if not pdf_bytes:
            mostrar_mensagem_topo("Aviso", "Esta música não possui PDF anexado.", "warning")
            return
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            webbrowser.open_new(tmp.name)

    def download_pdf(self, music_id, titulo):
        pdf_bytes = fetch_pdf(music_id)
        if not pdf_bytes:
            mostrar_mensagem_topo("Erro", "PDF não encontrado.", "error")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")],
            initialfile=f"{titulo}.pdf"
        )
        if path:
            with open(path, "wb") as f:
                f.write(pdf_bytes)
            mostrar_mensagem_topo("Sucesso", f"PDF salvo em:\n{path}", "info")

    def confirm_delete(self, music_id):
        if mostrar_mensagem_topo("Confirmação", "Deseja realmente excluir esta música?", "yesno"):
            delete_music(music_id)
            self.apply_search()

    # ---------- Diálogos de Música ----------
    def add_music_dialog(self):
        dialog = EditarMusicaDialog(self, "Nova Música")
        if dialog.result:
            titulo, artista, tonalidade, letra, tamanho_fonte = dialog.result
            pdf_bytes = gerar_pdf(titulo, artista, tonalidade, letra, tamanho_fonte)
            music_id = insert_music(titulo, artista, tonalidade, pdf_bytes, letra)
            
            # Perguntar se quer adicionar a grupos
            if mostrar_mensagem_topo("Grupos", "Deseja adicionar esta música a algum grupo?", "yesno"):
                self.gerenciar_grupos_musica(music_id, titulo)
            
            self.apply_search()

    def edit_music_dialog(self, music_id):
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT titulo, artista, tonalidade, texto_original FROM musicas WHERE id=?", (music_id,))
        row = cur.fetchone()
        conn.close()

        if not row:
            mostrar_mensagem_topo("Erro", "Música não encontrada.", "error")
            return

        titulo, artista, tonalidade, texto_original = row
        dialog = EditarMusicaDialog(self, "Editar Música", titulo, artista, tonalidade, texto_original)
        
        if dialog.result:
            novoTitulo, novoArtista, novoTonalidade, novaLetra, novoTamanhoFonte = dialog.result
            pdf_bytes = gerar_pdf(novoTitulo, novoArtista, novoTonalidade, novaLetra, novoTamanhoFonte)
            update_music(music_id, novoTitulo, novoArtista, novoTonalidade, pdf_bytes, novaLetra)
            self.apply_search()

    # ---------- Funções de Grupos (mantidas do código original com pequenas adaptações) ----------
    def gerenciar_grupos_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Gerenciar Grupos")
        dialog.geometry("500x600")
        dialog.transient(self)
        dialog.grab_set()
        
        # Aba para adicionar múltiplas músicas a um grupo
        tabview = ctk.CTkTabview(dialog)
        tabview.pack(fill="both", expand=True, padx=20, pady=10)
        
        tab1 = tabview.add("Gerenciar Grupos")
        tab2 = tabview.add("Adicionar Múltiplas")

        # ABA 1
        # Frame para adicionar novo grupo
        add_frame = ctk.CTkFrame(tab1)
        add_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(add_frame, text="Novo Grupo:").pack(pady=5)
        novo_grupo_var = ctk.StringVar()
        entry_grupo = ctk.CTkEntry(add_frame, textvariable=novo_grupo_var)
        entry_grupo.pack(fill="x", padx=10, pady=5)

        def adicionar_grupo():
            nome = novo_grupo_var.get().strip()
            if not nome:
                mostrar_mensagem_topo("Aviso", "Digite um nome para o grupo.", "warning")
                return
            if criar_grupo(nome):
                mostrar_mensagem_topo("Sucesso", f"Grupo '{nome}' criado!", "info")
                entry_grupo.delete(0, 'end')
                self.carregar_grupos_sidebar()
                carregar_grupos()
                carregar_grupos_multiplas()
            else:
                mostrar_mensagem_topo("Erro", f"Grupo '{nome}' já existe!", "error")

        ctk.CTkButton(add_frame, text="Adicionar", command=adicionar_grupo).pack(pady=5)

        # Lista de grupos
        grupos_frame = ctk.CTkFrame(tab1)
        grupos_frame.pack(fill="both", expand=True, padx=20, pady=10)

        scroll_grupos = ctk.CTkScrollableFrame(grupos_frame)
        scroll_grupos.pack(fill="both", expand=True)

        def carregar_grupos():
            for widget in scroll_grupos.winfo_children():
                widget.destroy()
            
            grupos = fetch_all_grupos()
            for grupo_id, nome, cor in grupos:
                grupo_frame = ctk.CTkFrame(scroll_grupos)
                grupo_frame.pack(fill="x", pady=2)

                ctk.CTkLabel(grupo_frame, text=nome, width=250).pack(side="left", padx=5)
                
                def excluir(g_id=grupo_id, g_nome=nome):
                    if mostrar_mensagem_topo("Confirmar", f"Excluir grupo '{g_nome}'?\n\nAs músicas não serão excluídas, apenas removidas do grupo.", "yesno"):
                        excluir_grupo(g_id)
                        carregar_grupos()
                        carregar_grupos_multiplas()
                        self.carregar_grupos_sidebar()
                        if self.grupo_selecionado == g_id:
                            self.grupo_selecionado = None
                            self.mostrar_todas_musicas()

                ctk.CTkButton(grupo_frame, text="❌", width=30, command=excluir).pack(side="right", padx=2)

        # ABA 2: Adicionar Múltiplas Músicas
        multiplas_frame = ctk.CTkFrame(tab2)
        multiplas_frame.pack(fill="both", expand=True, padx=20, pady=10)

        ctk.CTkLabel(multiplas_frame, text="Selecionar Grupo:").pack(pady=5)

        grupos_multiplas_var = ctk.StringVar()
        grupos_multiplas_combo = ctk.CTkOptionMenu(multiplas_frame, 
                                         values=[grupo[1] for grupo in fetch_all_grupos()],
                                         variable=grupos_multiplas_var,
                                         dynamic_resizing=False)
        grupos_multiplas_combo.pack(fill="x", pady=5)

        if fetch_all_grupos():
            grupos_multiplas_combo.set(fetch_all_grupos()[0][1])

        ctk.CTkLabel(multiplas_frame, text="Selecionar Músicas (apenas músicas não adicionadas):").pack(pady=5)

        scroll_multiplas = ctk.CTkScrollableFrame(multiplas_frame, height=300)
        scroll_multiplas.pack(fill="both", expand=True, pady=5)

        def carregar_grupos_multiplas():
            grupos = [grupo[1] for grupo in fetch_all_grupos()]
            grupos_multiplas_combo.configure(values=grupos)
            if grupos:
                grupos_multiplas_combo.set(grupos[0])

        def carregar_musicas_multiplas():
            for widget in scroll_multiplas.winfo_children():
                widget.destroy()
            
            # Obter o grupo selecionado
            grupo_nome = grupos_multiplas_var.get()
            grupo_id = None
            for g_id, nome, _ in fetch_all_grupos():
                if nome == grupo_nome:
                    grupo_id = g_id
                    break
            
            # Obter músicas que já estão no grupo
            musicas_no_grupo = []
            if grupo_id:
                musicas_no_grupo = [musica[0] for musica in fetch_musicas_do_grupo(grupo_id)]
            
            # Carregar todas as músicas e filtrar
            todas_musicas = fetch_all_musicas()
            for music_id, titulo, artista, tonalidade, favorito in todas_musicas:
                # Pular músicas que já estão no grupo selecionado
                if music_id in musicas_no_grupo:
                    continue
                    
                frame = ctk.CTkFrame(scroll_multiplas)
                frame.pack(fill="x", pady=2)

                var = ctk.BooleanVar()
                chk = ctk.CTkCheckBox(frame, text=f"{titulo} - {artista or 'Sem artista'}", variable=var)
                chk.pack(side="left", padx=5, fill="x", expand=True)
                
                # Store the music_id with the checkbox
                chk.music_id = music_id

        # Função para atualizar quando o grupo mudar
        def atualizar_musicas_multiplas(*args):
            carregar_musicas_multiplas()

        # Vincular a função de atualização ao combobox
        grupos_multiplas_var.trace("w", atualizar_musicas_multiplas)

        def adicionar_multiplas():
            if not fetch_all_grupos():
                mostrar_mensagem_topo("Aviso", "Crie um grupo primeiro!", "warning")
                return
                
            grupo_nome = grupos_multiplas_var.get()
            grupo_id = None
            for g_id, nome, _ in fetch_all_grupos():
                if nome == grupo_nome:
                    grupo_id = g_id
                    break
            
            if not grupo_id:
                mostrar_mensagem_topo("Erro", "Grupo não encontrado!", "error")
                return
            
            musicas_selecionadas = []
            for widget in scroll_multiplas.winfo_children():
                if hasattr(widget, 'winfo_children'):
                    for child in widget.winfo_children():
                        if isinstance(child, ctk.CTkCheckBox) and child._variable.get():
                            musicas_selecionadas.append(child.music_id)
            
            if not musicas_selecionadas:
                mostrar_mensagem_topo("Aviso", "Selecione pelo menos uma música!", "warning")
                return
            
            # Adicionar cada música ao grupo
            adicionadas = 0
            for music_id in musicas_selecionadas:
                if adicionar_musica_ao_grupo(music_id, grupo_id):
                    adicionadas += 1
            
            mostrar_mensagem_topo("Sucesso", f"{adicionadas} músicas adicionadas ao grupo '{grupo_nome}'!", "info")
            carregar_musicas_multiplas() 
            self.apply_search() 

        ctk.CTkButton(multiplas_frame, text="Adicionar Selecionadas ao Grupo", 
                    command=adicionar_multiplas).pack(pady=10)

        # Carregar dados iniciais
        carregar_grupos()
        carregar_grupos_multiplas()
        carregar_musicas_multiplas()

    def gerenciar_grupos_musica(self, music_id, titulo):
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Grupos - {titulo}")
        dialog.geometry("300x400")
        dialog.transient(self)
        dialog.grab_set()

        grupos_musica = [grupo_id for grupo_id, _, _ in fetch_grupos_da_musica(music_id)]
        todos_grupos = fetch_all_grupos()

        scroll_frame = ctk.CTkScrollableFrame(dialog)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        for grupo_id, nome, cor in todos_grupos:
            frame = ctk.CTkFrame(scroll_frame)
            frame.pack(fill="x", pady=2)

            var = ctk.BooleanVar(value=grupo_id in grupos_musica)
            chk = ctk.CTkCheckBox(frame, text=nome, variable=var, 
                                 fg_color=cor, hover_color=cor)
            chk.pack(side="left", padx=5)

            def toggle_grupo(g_id=grupo_id, v=var):
                if v.get():
                    adicionar_musica_ao_grupo(music_id, g_id)
                else:
                    remover_musica_do_grupo(music_id, g_id)

            var.trace("w", lambda *args, g_id=grupo_id, v=var: toggle_grupo(g_id, v))

        def fechar_e_atualizar():
            dialog.destroy()
            self.apply_search()

        ctk.CTkButton(dialog, text="Fechar", command=fechar_e_atualizar).pack(pady=10)

    # ---------- Importar PDF ----------
    def import_pdf_dialog(self):
        path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf"), ("DOCX Files", "*.docx"), ("Tipos Suportados", "*.pdf *.docx")])
        if not path:
            return

        try:
            texto = ""
            
            if path.lower().endswith('.docx'):
                # Processar arquivo DOCX
                doc = Document(path)
                for paragraph in doc.paragraphs:
                    texto += paragraph.text + "\n"
            else:
                # Processar arquivo PDF
                reader = PyPDF2.PdfReader(path)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        texto += page_text + "\n"

            # Função para limpar caracteres especiais sem remover quebras de linha
            def limpar_texto(texto):
                return ''.join(
                    char for char in texto if ord(char) >= 32 or ord(char) in [9, 10, 13]
                )

            # Mantém linhas vazias do PDF
            linhas = [limpar_texto(l) for l in texto.splitlines()]

            if len([l for l in linhas if l.strip()]) < 2:
                mostrar_mensagem_topo("Erro", "Documento inválido: precisa ter pelo menos título e artista/tonalidade.", "error")
                return

            titulo = limpar_texto(linhas[0]).strip()
            artista, tonalidade = "", ""

            # Analisa a segunda linha para separar artista e tonalidade
            linha2 = limpar_texto(linhas[1]).strip()

            separadores = ["•", "-", "|", ":", ";", "–", "—"]
            encontrou_separador = False
            for sep in separadores:
                if sep in linha2:
                    partes = [limpar_texto(x).strip() for x in linha2.split(sep)]
                    if len(partes) >= 2:
                        artista = partes[0]
                        tonalidade = partes[1]
                        if len(partes) > 2:
                            tonalidade = sep.join(partes[1:])
                        encontrou_separador = True
                        break

            if not encontrou_separador:
                palavras_tonalidade = [
                    "C", "D", "E", "F", "G", "A", "B",
                    "Cm", "Dm", "Em", "Fm", "Gm", "Am", "Bm",
                    "C#", "D#", "F#", "G#", "A#",
                    "Db", "Eb", "Gb", "Ab", "Bb",
                    "Dó", "Ré", "Mi", "Fá", "Sol", "Lá", "Si",
                    "Dóm", "Rém", "Mim", "Fám", "Solm", "Lám", "Sim"
                ]
                palavras = linha2.split()
                if palavras and any(palavras[-1].upper() == p.upper() for p in palavras_tonalidade):
                    artista = " ".join(palavras[:-1])
                    tonalidade = palavras[-1]
                else:
                    artista = linha2

            def remover_caracteres_invisiveis(texto):
                caracteres_invisiveis = [
                    '\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',
                    '\x08', '\x0b', '\x0c', '\x0e', '\x0f', '\x10', '\x11', '\x12',
                    '\x13', '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a',
                    '\x1b', '\x1c', '\x1d', '\x1e', '\x1f', '\x7f', '\x80', '\x81',
                    '\x82', '\x83', '\x84', '\x85', '\x86', '\x87', '\x88', '\x89',
                    '\x8a', '\x8b', '\x8c', '\x8d', '\x8e', '\x8f', '\x90', '\x91',
                    '\x92', '\x93', '\x94', '\x95', '\x96', '\x97', '\x98', '\x99',
                    '\x9a', '\x9b', '\x9c', '\x9d', '\x9e', '\x9f', '\ad', '\ae'
                ]
                for char in caracteres_invisiveis:
                    texto = texto.replace(char, '')
                return texto.strip()

            artista = remover_caracteres_invisiveis(artista)
            tonalidade = remover_caracteres_invisiveis(tonalidade)

            # Mantém quebras de linha originais a partir da 3ª linha
            letra = "\n".join(linhas[2:]) if len(linhas) > 2 else ""

            # Diálogo de confirmação
            confirm_dialog = ctk.CTkToplevel(self)
            confirm_dialog.title("Confirmar Importação")
            confirm_dialog.geometry("400x500")
            confirm_dialog.transient(self)
            confirm_dialog.grab_set()

            ctk.CTkLabel(confirm_dialog, text="Título:").pack(pady=5)
            titulo_entry = ctk.CTkEntry(confirm_dialog, width=350)
            titulo_entry.insert(0, titulo)
            titulo_entry.pack(fill="x", padx=20)

            ctk.CTkLabel(confirm_dialog, text="Artista:").pack(pady=5)
            artista_entry = ctk.CTkEntry(confirm_dialog, width=350)
            artista_entry.insert(0, artista)
            artista_entry.pack(fill="x", padx=20)

            ctk.CTkLabel(confirm_dialog, text="Tonalidade:").pack(pady=5)
            tonalidade_entry = ctk.CTkEntry(confirm_dialog, width=350)
            tonalidade_entry.insert(0, tonalidade)
            tonalidade_entry.pack(fill="x", padx=20)

            ctk.CTkLabel(confirm_dialog, text="Letra (apenas leitura):").pack(pady=5)
            letra_text = ctk.CTkTextbox(confirm_dialog, height=180)
            letra_text.pack(fill="x", padx=20, pady=5)
            letra_text.insert("1.0", letra)
            letra_text.configure(state="normal")

            def confirm_import():
                titulo_final = remover_caracteres_invisiveis(titulo_entry.get().strip())
                artista_final = remover_caracteres_invisiveis(artista_entry.get().strip())
                tonalidade_final = remover_caracteres_invisiveis(tonalidade_entry.get().strip())

                if not titulo_final:
                    mostrar_mensagem_topo("Aviso", "O título é obrigatório.", "warning")
                    return

                pdf_bytes = gerar_pdf(titulo_final, artista_final, tonalidade_final, letra)
                music_id = insert_music(titulo_final, artista_final, tonalidade_final, pdf_bytes, letra)

                if mostrar_mensagem_topo("Grupos", "Deseja adicionar esta música a algum grupo?", "yesno"):
                    self.gerenciar_grupos_musica(music_id, titulo_final)

                confirm_dialog.destroy()
                self.apply_search()
                mostrar_mensagem_topo("Sucesso", "Documento importado com sucesso!", "info")

            ctk.CTkButton(confirm_dialog, text="Confirmar Importação", command=confirm_import).pack(pady=20)

        except Exception as e:
            mostrar_mensagem_topo("Erro", f"Falha ao importar documento: {e}", "error")


class EditarMusicaDialog:
    def __init__(self, parent, title, titulo="", artista="", tonalidade="", letra="", tamanho_fonte=11):
        self.parent = parent
        self.result = None
        
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("600x700")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Variáveis
        self.titulo_var = ctk.StringVar(value=titulo)
        self.artista_var = ctk.StringVar(value=artista)
        self.tonalidade_var = ctk.StringVar(value=tonalidade)
        self.tamanho_fonte_var = ctk.IntVar(value=tamanho_fonte)
        
        # Frame para os campos básicos
        campos_frame = ctk.CTkFrame(self.dialog)
        campos_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(campos_frame, text="Título:").grid(row=0, column=0, sticky="w", pady=5)
        ctk.CTkEntry(campos_frame, textvariable=self.titulo_var).grid(row=0, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        ctk.CTkLabel(campos_frame, text="Artista:").grid(row=1, column=0, sticky="w", pady=5)
        ctk.CTkEntry(campos_frame, textvariable=self.artista_var).grid(row=1, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        ctk.CTkLabel(campos_frame, text="Tonalidade:").grid(row=2, column=0, sticky="w", pady=5)
        ctk.CTkEntry(campos_frame, textvariable=self.tonalidade_var).grid(row=2, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        ctk.CTkLabel(campos_frame, text="Tamanho da Fonte:").grid(row=3, column=0, sticky="w", pady=5)
        fonte_frame = ctk.CTkFrame(campos_frame, fg_color="transparent")
        fonte_frame.grid(row=3, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        ctk.CTkSlider(fonte_frame, from_=8, to=16, variable=self.tamanho_fonte_var, 
                     number_of_steps=8, width=150).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(fonte_frame, textvariable=self.tamanho_fonte_var).pack(side="left")

        campos_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(self.dialog, text="Letra / Conteúdo do PDF:").pack(pady=(10, 5))
        self.letra_text = ctk.CTkTextbox(self.dialog, height=250)
        self.letra_text.pack(fill="both", padx=20, pady=5, expand=True)
        self.letra_text.insert("1.0", letra)

        # Botões
        btn_frame = ctk.CTkFrame(self.dialog, fg_color="transparent")
        btn_frame.pack(pady=10)
        
        ctk.CTkButton(btn_frame, text="Cancelar", command=self.cancelar).pack(side="right", padx=10)
        ctk.CTkButton(btn_frame, text="Salvar", command=self.salvar).pack(side="right")
        
        # Focar no título
        self.dialog.after(100, lambda: self.focus_titulo())
        
        self.dialog.wait_window()

    def focus_titulo(self):
        children = self.dialog.winfo_children()
        for child in children:
            if isinstance(child, ctk.CTkFrame) and child.winfo_children():
                for grandchild in child.winfo_children():
                    if isinstance(grandchild, ctk.CTkEntry) and grandchild._textvariable == self.titulo_var:
                        grandchild.focus()
                        return

    def salvar(self):
        titulo = self.titulo_var.get().strip()
        if not titulo:
            mostrar_mensagem_topo("Aviso", "Preencha o título da música.", "warning")
            return
        
        artista = self.artista_var.get().strip()
        tonalidade = self.tonalidade_var.get().strip()
        letra = self.letra_text.get("1.0", "end-1c")
        tamanho_fonte = self.tamanho_fonte_var.get()
        
        self.result = (titulo, artista, tonalidade, letra, tamanho_fonte)
        self.dialog.destroy()

    def cancelar(self):
        self.dialog.destroy()


if __name__ == "__main__":
    app = SongPDFApp()
    app.mainloop()