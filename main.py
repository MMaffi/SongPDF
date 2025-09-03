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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS musicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            artista TEXT,
            tonalidade TEXT,
            pdf BLOB
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

# ------------------ PDF ------------------
def gerar_pdf(titulo, artista, tonalidade, letra):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 800, titulo)
    c.setFont("Helvetica", 12)
    c.drawString(100, 780, f"{artista} • {tonalidade}".strip(" •"))
    text = c.beginText(100, 750)
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
    conn.commit()
    conn.close()

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

        # ---------- Top frame ----------
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=20, pady=(20, 5))

        # Botões principais
        btn_add = ctk.CTkButton(top_frame, text="➕ Nova Música", command=self.add_music_dialog)
        btn_add.pack(side="left", padx=5)
        btn_import = ctk.CTkButton(top_frame, text="⬇️ Importar PDF", command=self.import_pdf_dialog)
        btn_import.pack(side="left", padx=5)

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
                "- Faça backup do banco de dados para segurança.\n"
                "- Troque o banco de dados se quiser trabalhar com outro arquivo SQLite."
            )

        def fazer_backup():
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
            x = btn_help.winfo_rootx()
            y = btn_help.winfo_rooty() + btn_help.winfo_height()
            self.popup_menu.geometry(f"240x200+{x}+{y}")
            self.popup_menu.overrideredirect(True)
            self.popup_menu.attributes("-topmost", True)

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

        checkbox_frame = ctk.CTkFrame(search_frame, fg_color="transparent")
        checkbox_frame.pack(fill="x", pady=(0,5))

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

        search_input_frame = ctk.CTkFrame(search_frame, fg_color="transparent")
        search_input_frame.pack(fill="x")
        btn_search = ctk.CTkButton(search_input_frame, text="🔍 Buscar", width=70, command=self.apply_search)
        btn_search.pack(side="right", padx=5)
        self.entry_search = ctk.CTkEntry(search_input_frame, placeholder_text="Buscar...", width=300)
        self.entry_search.pack(side="right", padx=5)
        self.entry_search.bind("<Return>", lambda e: self.apply_search())

        # ---------- Scroll frame ----------
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Minhas Músicas")
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.load_cards()

    # ---------- UI ----------
    def load_cards(self, musicas=None):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        if musicas is None:
            musicas = fetch_all_musicas()
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
        lbl = ctk.CTkLabel(
            card,
            text=f"{titulo}\n{artista or ''} • {tonalidade or ''}".strip(),
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        lbl.pack(side="left", padx=10, pady=10, expand=True, fill="x")

        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=10)
        ctk.CTkButton(btn_frame, text="⬆️ Abrir", width=70, command=lambda: self.open_pdf(music_id)).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="✏️ Editar", width=70, command=lambda: self.edit_music_dialog(music_id)).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="⬇️ Baixar", width=80, command=lambda: self.download_pdf(music_id, titulo)).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="❌ Excluir", fg_color="red", width=70, command=lambda: self.confirm_delete(music_id)).pack(side="left", padx=5)

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
            insert_music(titulo_var.get(), artista_var.get(), tonalidade_var.get(), pdf_bytes)
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

            linhas = [l.strip() for l in texto.splitlines() if l.strip()]
            if len(linhas) < 2:
                messagebox.showerror("Erro", "PDF inválido: precisa ter pelo menos título e artista/tonalidade.")
                return

            titulo = linhas[0]
            artista, tonalidade = "", ""
            separadores = ["•", "-", "|", ":", ";"]
            linha2 = linhas[1]
            for sep in separadores:
                if sep in linha2:
                    artista, tonalidade = [x.strip() for x in linha2.split(sep, 1)]
                    break
            else:
                artista = linha2

            letra = "\n".join(linhas[2:]) if len(linhas) > 2 else ""
            pdf_bytes = gerar_pdf(titulo, artista, tonalidade, letra)
            insert_music(titulo, artista, tonalidade, pdf_bytes)
            self.apply_search()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao importar PDF: {e}")


if __name__ == "__main__":
    app = SongPDFApp()
    app.mainloop()