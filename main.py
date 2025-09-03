import os
import sys
import sqlite3
import tempfile
import webbrowser
import json
import customtkinter as ctk
from tkinter import filedialog, messagebox

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO

try:
    import PyPDF2
except ImportError:
    messagebox.showerror("Erro", "PyPDF2 não instalado. Instale com: pip install PyPDF2")
    exit()

# ------------------ CONFIGURAÇÃO ------------------
CONFIG_FILE = "config.json"
DB_DIR = "data"
DEFAULT_DB_FILE = os.path.join(DB_DIR, "songpdf.db")

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
        json.dump(config, f, indent=4)

config = load_config()
DB_FILE = config.get("db_file", DEFAULT_DB_FILE)

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
            pdf BLOB
        )
    """)
    
    # Tabela de grupos
    cur.execute("""
        CREATE TABLE IF NOT EXISTS grupos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
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
    
    conn.commit()
    conn.close()

def conectar_banco(path):
    try:
        init_db(path)
        # teste de conexão
        conn = sqlite3.connect(path)
        conn.execute("SELECT 1")
        conn.close()
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
    cur.execute("SELECT id, nome FROM grupos ORDER BY nome")
    rows = cur.fetchall()
    conn.close()
    return rows

def criar_grupo(nome):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO grupos (nome) VALUES (?)", (nome,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Grupo já existe
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
        return False  # Relação já existe
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
        SELECT m.id, m.titulo, m.artista, m.tonalidade 
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
        SELECT g.id, g.nome
        FROM grupos g
        JOIN musica_grupo mg ON g.id = mg.grupo_id
        WHERE mg.musica_id = ?
        ORDER BY g.nome
    """, (musica_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

# ------------------ PDF ------------------
def gerar_pdf(titulo, artista, tonalidade, letra):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 800, titulo)
    c.setFont("Helvetica", 12)
    
    # Formata a linha de artista e tonalidade
    info_line = ""
    if artista and tonalidade:
        info_line = f"{artista} • {tonalidade}"
    elif artista:
        info_line = artista
    elif tonalidade:
        info_line = tonalidade
    
    if info_line:
        c.drawString(100, 780, info_line)
    
    text = c.beginText(100, 750 if info_line else 780)
    text.setFont("Helvetica", 11)
    for linha in letra.splitlines():
        text.textLine(linha)
    c.drawText(text)
    c.save()
    buffer.seek(0)
    return buffer.read()

# ------------------ FUNÇÕES DE BANCO ------------------
def fetch_all_musicas():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, titulo, artista, tonalidade FROM musicas ORDER BY id DESC")
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

def insert_music(titulo, artista, tonalidade, pdf_bytes):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO musicas (titulo, artista, tonalidade, pdf) VALUES (?, ?, ?, ?)",
        (titulo, artista, tonalidade, pdf_bytes)
    )
    music_id = cur.lastrowid
    conn.commit()
    conn.close()
    return music_id

def update_music(music_id, titulo, artista, tonalidade, pdf_bytes=None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    if pdf_bytes:
        cur.execute(
            "UPDATE musicas SET titulo=?, artista=?, tonalidade=?, pdf=? WHERE id=?",
            (titulo, artista, tonalidade, pdf_bytes, music_id)
        )
    else:
        cur.execute(
            "UPDATE musicas SET titulo=?, artista=?, tonalidade=? WHERE id=?",
            (titulo, artista, tonalidade, music_id)
        )
    conn.commit()
    conn.close()

def delete_music(music_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM musicas WHERE id=?", (music_id,))
    conn.commit()
    conn.close()

def search_musicas(campo, termo):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    query = f"SELECT id, titulo, artista, tonalidade FROM musicas WHERE {campo} LIKE ? ORDER BY id DESC"
    cur.execute(query, (f"%{termo}%",))
    rows = cur.fetchall()
    conn.close()
    return rows

# ------------------ APP ------------------
class SongPDFApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SongPDF")
        self.geometry("1100x750")
        self.minsize(950, 650)

        if os.path.exists("./assets/icons/songpdf.ico"):
            self.iconbitmap("./assets/icons/songpdf.ico")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Variáveis de estado
        self.grupo_selecionado = None
        self.musicas_atuais = []

        # ---------- Top frame ----------
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=20, pady=(20, 5))

        # Botões principais
        btn_add = ctk.CTkButton(top_frame, text="➕ Nova Música", command=self.add_music_dialog)
        btn_add.pack(side="left", padx=5)
        btn_import = ctk.CTkButton(top_frame, text="⬇️ Importar PDF", command=self.import_pdf_dialog)
        btn_import.pack(side="left", padx=5)
        btn_grupos = ctk.CTkButton(top_frame, text="📁 Gerenciar Grupos", command=self.gerenciar_grupos_dialog)
        btn_grupos.pack(side="left", padx=5)

        # ---------- Botão ajuda / backup ----------
        self.popup_menu = None
        self.menu_hover = False

        def mostrar_ajuda():
            messagebox.showinfo(
                "Ajuda",
                "SongPDF é um gerenciador de músicas em PDF.\n\n"
                "- Adicione novas músicas ou importe PDFs existentes.\n"
                "- Edite, abra ou baixe os PDFs.\n"
                "- Use a busca para localizar músicas rapidamente.\n"
                "- Organize músicas em grupos/pastas.\n"
                "- Faça backup do banco de dados para segurança.\n"
                "- Troque o banco de dados se quiser trabalhar com outro arquivo SQLite."
            )

        def fazer_backup():
            aviso = (
                "ATENÇÃO: O backup será feito com os dados atuais.\n\n"
                "Quaisquer alterações feitas após este momento \n"
                "NÃO serão incluídas no backup.\n\n"
                "Deseja continuar com o backup?"
            )
            
            if not messagebox.askyesno("Aviso - Backup", aviso):
                return
            
            path = filedialog.asksaveasfilename(
                defaultextension=".db",
                filetypes=[("SQLite DB", "*.db")],
                initialfile="songpdf_backup.db"
            )
            if path:
                try:
                    conn = sqlite3.connect(DB_FILE)
                    bkp = sqlite3.connect(path)
                    conn.backup(bkp)
                    bkp.close()
                    conn.close()
                    messagebox.showinfo("Sucesso", f"Backup salvo em:\n{path}")
                except Exception as e:
                    messagebox.showerror("Erro", f"Falha ao salvar backup: {e}")

        def trocar_banco():
            path = filedialog.askopenfilename(
                filetypes=[("SQLite DB", "*.db")],
                title="Escolha o banco de dados"
            )
            if not path:
                return
            if conectar_banco(path):
                global DB_FILE
                DB_FILE = path
                config["db_file"] = path
                save_config(config)
                messagebox.showinfo("Sucesso", f"Conectado ao banco:\n{path}")
                self.apply_search()

        def close_popup():
            if not self.menu_hover:
                if self.popup_menu and self.popup_menu.winfo_exists():
                    self.popup_menu.destroy()
                    self.popup_menu = None

        def open_popup():
            if self.popup_menu and self.popup_menu.winfo_exists():
                return
            
            self.popup_menu = ctk.CTkToplevel(self)
            self.popup_menu.overrideredirect(True)
            self.popup_menu.attributes("-topmost", True)

            # Calcula a posição do botão na tela
            btn_x = btn_help.winfo_rootx()
            btn_y = btn_help.winfo_rooty()
            btn_width = btn_help.winfo_width()
            btn_height = btn_help.winfo_height()

            # Posiciona o modal ao lado direito do botão, alinhado pelo topo
            popup_x = btn_x + btn_width + 5
            popup_y = btn_y

            # Garante que o modal não saia da tela à direita
            screen_width = self.winfo_screenwidth()
            if popup_x + 240 > screen_width:
                popup_x = btn_x - 240 - 5

            self.popup_menu.geometry(f"240x200+{popup_x}+{popup_y}")
            
            frame = ctk.CTkFrame(self.popup_menu, corner_radius=12)
            frame.pack(fill="both", expand=True, padx=5, pady=5)

            frame.grid_rowconfigure((0, 1, 2, 3), weight=1)
            frame.grid_columnconfigure(0, weight=1)

            ctk.CTkButton(frame, text="Ajuda", height=32,
                        command=lambda: [self.popup_menu.destroy(), mostrar_ajuda()]).grid(row=0, column=0, sticky="ew", padx=20, pady=5)
            ctk.CTkButton(frame, text="Fazer Backup", height=32,
                        command=lambda: [self.popup_menu.destroy(), fazer_backup()]).grid(row=1, column=0, sticky="ew", padx=20, pady=5)
            ctk.CTkButton(frame, text="Trocar Banco", height=32,
                        command=lambda: [self.popup_menu.destroy(), trocar_banco()]).grid(row=2, column=0, sticky="ew", padx=20, pady=5)
            ctk.CTkButton(frame, text="Mostrar Caminho do Banco", height=32,
                        command=lambda: messagebox.showinfo("Banco Atual", f"Caminho: {DB_FILE}")).grid(row=3, column=0, sticky="ew", padx=20, pady=5)

            self.popup_menu.bind("<Enter>", lambda e: set_hover(True))
            self.popup_menu.bind("<Leave>", lambda e: set_hover(False))

        def set_hover(state: bool):
            self.menu_hover = state
            if not state:
                self.after(200, close_popup)

        btn_help = ctk.CTkButton(top_frame, text="❓", width=40)
        btn_help.pack(side="right", padx=5)
        btn_help.bind("<Enter>", lambda e: [set_hover(True), open_popup()])
        btn_help.bind("<Leave>", lambda e: set_hover(False))

        # ---------- Search frame ----------
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=20, pady=(0, 10))

        # Checkboxes de busca (linha superior)
        checkbox_frame = ctk.CTkFrame(search_frame, fg_color="transparent")
        checkbox_frame.pack(fill="x", pady=(0, 5))

        self.search_field_var = ctk.StringVar(value="titulo")
        self.chk_titulo = ctk.BooleanVar(value=True)
        self.chk_artista = ctk.BooleanVar(value=False)
        self.chk_tonalidade = ctk.BooleanVar(value=False)

        def uncheck_others(selected):
            if selected == "titulo":
                self.chk_artista.set(False)
                self.chk_tonalidade.set(False)
                self.search_field_var.set("titulo")
            elif selected == "artista":
                self.chk_titulo.set(False)
                self.chk_tonalidade.set(False)
                self.search_field_var.set("artista")
            else:
                self.chk_titulo.set(False)
                self.chk_artista.set(False)
                self.search_field_var.set("tonalidade")

        ctk.CTkCheckBox(checkbox_frame, text="Tonalidade", variable=self.chk_tonalidade,
                        command=lambda: uncheck_others("tonalidade"), width=20, height=20).pack(side="right", padx=2)
        ctk.CTkCheckBox(checkbox_frame, text="Artista", variable=self.chk_artista,
                        command=lambda: uncheck_others("artista"), width=20, height=20).pack(side="right", padx=2)
        ctk.CTkCheckBox(checkbox_frame, text="Título", variable=self.chk_titulo,
                        command=lambda: uncheck_others("titulo"), width=20, height=20).pack(side="right", padx=2)

        # Frame para busca e grupos (linha inferior)
        search_input_frame = ctk.CTkFrame(search_frame, fg_color="transparent")
        search_input_frame.pack(fill="x")

        # Botão de busca à direita
        btn_search = ctk.CTkButton(search_input_frame, text="🔍 Buscar", width=70, command=self.apply_search)
        btn_search.pack(side="right", padx=5)

        # Campo de busca
        self.entry_search = ctk.CTkEntry(search_input_frame, placeholder_text="Buscar...", width=300)
        self.entry_search.pack(side="right", padx=5)
        self.entry_search.bind("<Return>", lambda e: self.apply_search())

        # Combobox de grupos à esquerda
        ctk.CTkLabel(search_input_frame, text="Grupos:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))

        self.grupos_optionmenu = ctk.CTkOptionMenu(search_input_frame, 
                                                values=["Todas as Músicas"] + [grupo[1] for grupo in fetch_all_grupos()],
                                                command=self.selecionar_grupo, 
                                                width=200)
        self.grupos_optionmenu.pack(side="left", padx=(0, 20))
        self.grupos_optionmenu.set("Todas as Músicas")

        # ---------- Scroll frame ----------
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Minhas Músicas")
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.load_cards()

    # ---------- FUNÇÕES DE GRUPOS ----------
    def selecionar_grupo(self, escolha):
        if escolha == "Todas as Músicas":
            self.grupo_selecionado = None
            self.load_cards()
        else:
            grupos = fetch_all_grupos()
            for grupo_id, nome in grupos:
                if nome == escolha:
                    self.grupo_selecionado = grupo_id
                    musicas = fetch_musicas_do_grupo(grupo_id)
                    self.load_cards(musicas)
                    break

    def atualizar_combobox_grupos(self):
        grupos = ["Todas as Músicas"] + [grupo[1] for grupo in fetch_all_grupos()]
        self.grupos_optionmenu.configure(values=grupos)
        if self.grupo_selecionado:
            for grupo_id, nome in fetch_all_grupos():
                if grupo_id == self.grupo_selecionado:
                    self.grupos_optionmenu.set(nome)
                    break
        else:
            self.grupos_optionmenu.set("Todas as Músicas")

    def gerenciar_grupos_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Gerenciar Grupos")
        dialog.geometry("500x600")  # Aumentei o tamanho para caber a nova funcionalidade
        dialog.attributes("-topmost", True)
        
        # Adicionar ícone
        if os.path.exists("./assets/icons/songpdf.ico"):
            try:
                dialog.iconbitmap("./assets/icons/songpdf.ico")
            except:
                pass

        # Aba para adicionar múltiplas músicas a um grupo
        tabview = ctk.CTkTabview(dialog)
        tabview.pack(fill="both", expand=True, padx=20, pady=10)
        
        tab1 = tabview.add("Gerenciar Grupos")
        tab2 = tabview.add("Adicionar Múltiplas")

        # ABA 1: Gerenciar Grupos (já existente)
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
                messagebox.showwarning("Aviso", "Digite um nome para o grupo.")
                return
            if criar_grupo(nome):
                messagebox.showinfo("Sucesso", f"Grupo '{nome}' criado!")
                entry_grupo.delete(0, 'end')
                self.atualizar_combobox_grupos()
                carregar_grupos()
                carregar_grupos_multiplas()  # Atualiza a segunda aba também
            else:
                messagebox.showerror("Erro", f"Grupo '{nome}' já existe!")

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
            for grupo_id, nome in grupos:
                grupo_frame = ctk.CTkFrame(scroll_grupos)
                grupo_frame.pack(fill="x", pady=2)

                ctk.CTkLabel(grupo_frame, text=nome, width=250).pack(side="left", padx=5)
                
                def excluir(g_id=grupo_id, g_nome=nome):
                    if messagebox.askyesno("Confirmar", f"Excluir grupo '{g_nome}'?\n\nAs músicas não serão excluídas, apenas removidas do grupo."):
                        excluir_grupo(g_id)
                        carregar_grupos()
                        carregar_grupos_multiplas()  # Atualiza a segunda aba também
                        self.atualizar_combobox_grupos()
                        if self.grupo_selecionado == g_id:
                            self.grupo_selecionado = None
                            self.load_cards()

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
            for g_id, nome in fetch_all_grupos():
                if nome == grupo_nome:
                    grupo_id = g_id
                    break
            
            # Obter músicas que já estão no grupo
            musicas_no_grupo = []
            if grupo_id:
                musicas_no_grupo = [musica[0] for musica in fetch_musicas_do_grupo(grupo_id)]
            
            # Carregar todas as músicas e filtrar
            todas_musicas = fetch_all_musicas()
            for music_id, titulo, artista, tonalidade in todas_musicas:
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
                messagebox.showwarning("Aviso", "Crie um grupo primeiro!")
                return
                
            grupo_nome = grupos_multiplas_var.get()
            grupo_id = None
            for g_id, nome in fetch_all_grupos():
                if nome == grupo_nome:
                    grupo_id = g_id
                    break
            
            if not grupo_id:
                messagebox.showerror("Erro", "Grupo não encontrado!")
                return
            
            musicas_selecionadas = []
            for widget in scroll_multiplas.winfo_children():
                if hasattr(widget, 'winfo_children'):
                    for child in widget.winfo_children():
                        if isinstance(child, ctk.CTkCheckBox) and child._variable.get():
                            musicas_selecionadas.append(child.music_id)
            
            if not musicas_selecionadas:
                messagebox.showwarning("Aviso", "Selecione pelo menos uma música!")
                return
            
            # Adicionar cada música ao grupo
            adicionadas = 0
            for music_id in musicas_selecionadas:
                if adicionar_musica_ao_grupo(music_id, grupo_id):
                    adicionadas += 1
            
            messagebox.showinfo("Sucesso", f"{adicionadas} músicas adicionadas ao grupo '{grupo_nome}'!")
            carregar_musicas_multiplas()  # Recarregar a lista para remover as adicionadas
            self.apply_search()  # Atualiza a lista principal

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
        dialog.attributes("-topmost", True)

        grupos_musica = [grupo_id for grupo_id, _ in fetch_grupos_da_musica(music_id)]
        todos_grupos = fetch_all_grupos()

        scroll_frame = ctk.CTkScrollableFrame(dialog)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        for grupo_id, nome in todos_grupos:
            frame = ctk.CTkFrame(scroll_frame)
            frame.pack(fill="x", pady=2)

            var = ctk.BooleanVar(value=grupo_id in grupos_musica)
            chk = ctk.CTkCheckBox(frame, text=nome, variable=var)
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

    # ---------- UI ----------
    def load_cards(self, musicas=None):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        
        if musicas is None:
            musicas = fetch_all_musicas()
        
        self.musicas_atuais = musicas
        total = len(musicas)
        
        for idx, music in enumerate(musicas):
            self.add_card(music)
            if idx < total - 1:
                separator = ctk.CTkFrame(self.scroll_frame, height=2, fg_color="gray50")
                separator.pack(fill="x", padx=15, pady=5)

    def add_card(self, music):
        music_id, titulo, artista, tonalidade = music
        card = ctk.CTkFrame(self.scroll_frame, corner_radius=12)
        card.pack(fill="x", padx=10, pady=5)
        
        # Frame esquerdo com informações
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True, padx=10, pady=10)
        
        lbl = ctk.CTkLabel(
            info_frame,
            text=f"{titulo}\n{artista or ''} • {tonalidade or ''}".strip(),
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        lbl.pack(anchor="w")
        
        # Mostrar grupos da música
        grupos = fetch_grupos_da_musica(music_id)
        if grupos:
            grupos_text = ", ".join([nome for _, nome in grupos])
            grupos_label = ctk.CTkLabel(
                info_frame,
                text=f"📁 {grupos_text}",
                anchor="w",
                justify="left",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            )
            grupos_label.pack(anchor="w", pady=(5, 0))

        # Frame direito com botões (apenas Abrir e Menu)
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=10)
        
        # Botão Abrir
        ctk.CTkButton(btn_frame, text="⬆️ Abrir", width=70, 
                    command=lambda: self.open_pdf(music_id)).pack(side="left", padx=2)
        
        # Alternativa com Canvas para controle total
        menu_canvas = ctk.CTkCanvas(btn_frame, width=30, height=30, bg="#2b2b2b", highlightthickness=0)
        menu_canvas.pack(side="left", padx=4)

        # Desenhar três pontos
        menu_canvas.create_text(15, 10, text="•", fill="#ffffff", font=("Arial", 13))
        menu_canvas.create_text(15, 15, text="•", fill="#ffffff", font=("Arial", 13))
        menu_canvas.create_text(15, 20, text="•", fill="#ffffff", font=("Arial", 13))

        # Tornar clicável
        menu_canvas.bind("<Button-1>", lambda e, m_id=music_id, t=titulo: self.show_music_menu(m_id, t, menu_canvas))
        menu_canvas.bind("<Enter>", lambda e: menu_canvas.configure(bg="#2F2F2F", cursor="hand2"))
        menu_canvas.bind("<Leave>", lambda e: menu_canvas.configure(bg="#2b2b2b"))

    # ---------- Menu de Opções da Música ----------
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
        
        menu_width = 140  # Largura reduzida
        menu_height = 128  # Altura reduzida (4 botões de 28px + espaçamento)
        
        # Ajustar posição se estiver saindo da tela à direita
        if x + menu_width > screen_width:
            x = screen_width - menu_width - 10  # 10px de margem
        
        # Ajustar posição se estiver saindo da tela em baixo
        if y + menu_height > screen_height:
            y = button.winfo_rooty() - menu_height  # Mostrar acima do botão
        
        menu.geometry(f"{menu_width}x{menu_height}+{x}+{y}")
        
        frame = ctk.CTkFrame(menu, corner_radius=8)
        frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Configurar o grid para centralizar verticalmente
        frame.grid_rowconfigure((0, 1, 2, 3), weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Função para fechar o menu
        def close_menu():
            if menu and menu.winfo_exists():
                if hasattr(menu, '_close_bind_id'):
                    self.unbind("<Button-1>", menu._close_bind_id)
                menu.destroy()
        
        # Botões menores (height reduzido)
        btn_style = {"height": 28, "font": ctk.CTkFont(size=12)}
        
        ctk.CTkButton(frame, text="Grupos", **btn_style,
                    command=lambda: [close_menu(), self.gerenciar_grupos_musica(music_id, titulo)]).grid(row=0, column=0, sticky="nsew", padx=3, pady=1)
        
        ctk.CTkButton(frame, text="Editar", **btn_style,
                    command=lambda: [close_menu(), self.edit_music_dialog(music_id)]).grid(row=1, column=0, sticky="nsew", padx=3, pady=1)
        
        ctk.CTkButton(frame, text="Baixar", **btn_style,
                    command=lambda: [close_menu(), self.download_pdf(music_id, titulo)]).grid(row=2, column=0, sticky="nsew", padx=3, pady=1)
        
        ctk.CTkButton(frame, text="Excluir", **btn_style, fg_color="red",
                    command=lambda: [close_menu(), self.confirm_delete(music_id)]).grid(row=3, column=0, sticky="nsew", padx=3, pady=1)
        
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
            messagebox.showwarning("Aviso", "Esta música não possui PDF anexado.")
            return
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            webbrowser.open_new(tmp.name)

    def download_pdf(self, music_id, titulo):
        pdf_bytes = fetch_pdf(music_id)
        if not pdf_bytes:
            messagebox.showerror("Erro", "PDF não encontrado.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")],
            initialfile=f"{titulo}.pdf"
        )
        if path:
            with open(path, "wb") as f:
                f.write(pdf_bytes)
            messagebox.showinfo("Sucesso", f"PDF salvo em:\n{path}")

    def confirm_delete(self, music_id):
        if messagebox.askyesno("Confirmação", "Deseja realmente excluir esta música?"):
            delete_music(music_id)
            self.apply_search()

    # ---------- Busca ----------
    def apply_search(self):
        termo = self.entry_search.get().strip()
        campo = self.search_field_var.get()
        
        if self.grupo_selecionado:
            # Busca dentro do grupo selecionado
            musicas_grupo = fetch_musicas_do_grupo(self.grupo_selecionado)
            if termo:
                resultados = []
                for musica in musicas_grupo:
                    if campo == "titulo" and termo.lower() in musica[1].lower():
                        resultados.append(musica)
                    elif campo == "artista" and musica[2] and termo.lower() in musica[2].lower():
                        resultados.append(musica)
                    elif campo == "tonalidade" and musica[3] and termo.lower() in musica[3].lower():
                        resultados.append(musica)
                self.load_cards(resultados)
            else:
                self.load_cards(musicas_grupo)
        else:
            # Busca em todas as músicas
            if termo == "":
                self.load_cards()
            else:
                resultados = search_musicas(campo, termo)
                self.load_cards(resultados)

    # ---------- Nova Música ----------
    def add_music_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Nova Música")
        dialog.geometry("500x600")
        dialog.attributes("-topmost", True)

        titulo_var = ctk.StringVar()
        artista_var = ctk.StringVar()
        tonalidade_var = ctk.StringVar()

        ctk.CTkLabel(dialog, text="Título:").pack(pady=5)
        ctk.CTkEntry(dialog, textvariable=titulo_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dialog, text="Artista:").pack(pady=5)
        ctk.CTkEntry(dialog, textvariable=artista_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dialog, text="Tonalidade:").pack(pady=5)
        ctk.CTkEntry(dialog, textvariable=tonalidade_var).pack(fill="x", padx=20)

        ctk.CTkLabel(dialog, text="Letra / Conteúdo do PDF:").pack(pady=5)
        letra_text = ctk.CTkTextbox(dialog, height=200)
        letra_text.pack(fill="both", padx=20, pady=5, expand=True)

        def save():
            if not titulo_var.get():
                messagebox.showwarning("Aviso", "Preencha o título da música.")
                return
            pdf_bytes = gerar_pdf(titulo_var.get(), artista_var.get(), tonalidade_var.get(), letra_text.get("1.0", "end-1c"))
            music_id = insert_music(titulo_var.get(), artista_var.get(), tonalidade_var.get(), pdf_bytes)
            
            # Perguntar se quer adicionar a grupos
            if messagebox.askyesno("Grupos", "Deseja adicionar esta música a algum grupo?"):
                self.gerenciar_grupos_musica(music_id, titulo_var.get())
            
            dialog.destroy()
            self.apply_search()

        ctk.CTkButton(dialog, text="Salvar", command=save).pack(pady=20)

    # ---------- Editar Música ----------
    def edit_music_dialog(self, music_id):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Editar Música")
        dialog.geometry("500x600")
        dialog.attributes("-topmost", True)

        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT titulo, artista, tonalidade, pdf FROM musicas WHERE id=?", (music_id,))
        row = cur.fetchone()
        conn.close()

        if not row:
            messagebox.showerror("Erro", "Música não encontrada.")
            return

        titulo_var = ctk.StringVar(value=row[0])
        artista_var = ctk.StringVar(value=row[1])
        tonalidade_var = ctk.StringVar(value=row[2])
        pdf_bytes = row[3]

        letra = ""
        if pdf_bytes:
            try:
                reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
                texto = ""
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        texto += page_text + "\n"
                linhas = [l.strip() for l in texto.splitlines() if l.strip()]
                if len(linhas) >= 3:
                    letra = "\n".join(linhas[2:])
            except:
                letra = ""

        ctk.CTkLabel(dialog, text="Título:").pack(pady=5)
        ctk.CTkEntry(dialog, textvariable=titulo_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dialog, text="Artista:").pack(pady=5)
        ctk.CTkEntry(dialog, textvariable=artista_var).pack(fill="x", padx=20)
        ctk.CTkLabel(dialog, text="Tonalidade:").pack(pady=5)
        ctk.CTkEntry(dialog, textvariable=tonalidade_var).pack(fill="x", padx=20)

        ctk.CTkLabel(dialog, text="Letra / Conteúdo do PDF:").pack(pady=5)
        letra_text = ctk.CTkTextbox(dialog, height=200)
        letra_text.pack(fill="both", padx=20, pady=5, expand=True)
        letra_text.insert("1.0", letra)

        def save():
            pdf_bytes = gerar_pdf(titulo_var.get(), artista_var.get(), tonalidade_var.get(), letra_text.get("1.0", "end-1c"))
            update_music(music_id, titulo_var.get(), artista_var.get(), tonalidade_var.get(), pdf_bytes)
            dialog.destroy()
            self.apply_search()

        ctk.CTkButton(dialog, text="Salvar Alterações", command=save).pack(pady=20)

    # ---------- Importar PDF ----------
    def import_pdf_dialog(self):
        path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if not path:
            return

        try:
            reader = PyPDF2.PdfReader(path)
            texto = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    texto += page_text + "\n"

            # Função para limpar caracteres especiais
            def limpar_texto(texto):
                # Remove caracteres de controle (0x00-0x1F) exceto tab, newline, carriage return
                texto_limpo = ''.join(char for char in texto if ord(char) >= 32 or ord(char) in [9, 10, 13])
                # Remove espaços no início e fim
                texto_limpo = texto_limpo.strip()
                # Remove múltiplos espaços consecutivos
                texto_limpo = ' '.join(texto_limpo.split())
                return texto_limpo

            linhas = [limpar_texto(l) for l in texto.splitlines() if limpar_texto(l)]
            
            if len(linhas) < 2:
                messagebox.showerror("Erro", "PDF inválido: precisa ter pelo menos título e artista/tonalidade.")
                return

            titulo = limpar_texto(linhas[0])
            artista, tonalidade = "", ""
            
            # Analisa a segunda linha para separar artista e tonalidade
            linha2 = limpar_texto(linhas[1])
            
            # Lista de separadores em ordem de prioridade
            separadores = ["•", "-", "|", ":", ";", "–", "—"]
            
            encontrou_separador = False
            for sep in separadores:
                if sep in linha2:
                    partes = [limpar_texto(x) for x in linha2.split(sep)]
                    if len(partes) >= 2:
                        artista = partes[0]
                        tonalidade = partes[1]
                        # Se houver mais partes, junta as restantes na tonalidade
                        if len(partes) > 2:
                            tonalidade = sep.join(partes[1:])
                        encontrou_separador = True
                        break
            
            # Se não encontrou separador, tenta lógica alternativa
            if not encontrou_separador:
                # Verifica se a linha tem palavras que podem indicar tonalidade
                palavras_tonalidade = ["C", "D", "E", "F", "G", "A", "B", 
                                    "Cm", "Dm", "Em", "Fm", "Gm", "Am", "Bm",
                                    "C#", "D#", "F#", "G#", "A#",
                                    "Db", "Eb", "Gb", "Ab", "Bb",
                                    "Dó", "Ré", "Mi", "Fá", "Sol", "Lá", "Si",
                                    "Dóm", "Rém", "Mim", "Fám", "Solm", "Lám", "Sim"]
                
                palavras = linha2.split()
                if palavras and any(palavras[-1].upper() == p.upper() for p in palavras_tonalidade):
                    artista = " ".join(palavras[:-1])
                    tonalidade = palavras[-1]
                else:
                    artista = linha2  # Se não conseguir separar, coloca tudo no artista

            # Limpa novamente os campos individuais
            artista = limpar_texto(artista)
            tonalidade = limpar_texto(tonalidade)
            
            # Remove qualquer caractere especial restante que possa ser invisível
            def remover_caracteres_invisiveis(texto):
                # Caracteres comuns que podem aparecer invisíveis
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
            
            letra = "\n".join(limpar_texto(l) for l in linhas[2:]) if len(linhas) > 2 else ""
            
            # Mostra diálogo de confirmação com os dados extraídos
            confirm_dialog = ctk.CTkToplevel(self)
            confirm_dialog.title("Confirmar Importação")
            confirm_dialog.geometry("400x350")
            confirm_dialog.attributes("-topmost", True)
            
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
            
            def confirm_import():
                titulo_final = remover_caracteres_invisiveis(titulo_entry.get().strip())
                artista_final = remover_caracteres_invisiveis(artista_entry.get().strip())
                tonalidade_final = remover_caracteres_invisiveis(tonalidade_entry.get().strip())
                
                if not titulo_final:
                    messagebox.showwarning("Aviso", "O título é obrigatório.")
                    return
                
                pdf_bytes = gerar_pdf(titulo_final, artista_final, tonalidade_final, letra)
                music_id = insert_music(titulo_final, artista_final, tonalidade_final, pdf_bytes)
                
                # Perguntar se quer adicionar a grupos
                if messagebox.askyesno("Grupos", "Deseja adicionar esta música a algum grupo?"):
                    self.gerenciar_grupos_musica(music_id, titulo_final)
                
                confirm_dialog.destroy()
                self.apply_search()
                messagebox.showinfo("Sucesso", "PDF importado com sucesso!")
            
            ctk.CTkButton(confirm_dialog, text="Confirmar Importação", command=confirm_import).pack(pady=20)
            
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao importar PDF: {e}")


if __name__ == "__main__":
    app = SongPDFApp()
    app.mainloop()