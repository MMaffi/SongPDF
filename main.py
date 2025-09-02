import os
import sys
import sqlite3
import tempfile
import webbrowser
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

# ------------------ BANCO ------------------ 
DB_DIR = "data" 
DB_FILE = os.path.join(DB_DIR, "songpdf.db")

# ------------------ BANCO ------------------
def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
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

        # Icone da janela 
        if os.path.exists("./assets/icons/songpdf.ico"): self.iconbitmap("./assets/icons/songpdf.ico")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # ---------- Top frame ----------
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=20, pady=(20, 5))

        btn_add = ctk.CTkButton(top_frame, text="➕ Nova Música", command=self.add_music_dialog)
        btn_add.pack(side="left", padx=5)
        btn_import = ctk.CTkButton(top_frame, text="⬇️ Importar PDF", command=self.import_pdf_dialog)
        btn_import.pack(side="left", padx=5)

        # ---------- Search frame ----------
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=20, pady=(0, 10))

        # Linha 1: Checkboxes
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

        # Checkboxes menores
        ctk.CTkCheckBox(checkbox_frame, text="Tonalidade", variable=self.chk_tonalidade,
                        command=lambda: uncheck_others("tonalidade"), width=20, height=20).pack(side="right", padx=2)
        ctk.CTkCheckBox(checkbox_frame, text="Artista", variable=self.chk_artista,
                        command=lambda: uncheck_others("artista"), width=20, height=20).pack(side="right", padx=2)
        ctk.CTkCheckBox(checkbox_frame, text="Título", variable=self.chk_titulo,
                        command=lambda: uncheck_others("titulo"), width=20, height=20).pack(side="right", padx=2)

        # Linha 2: Entry e botão
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
            # linha de separação (não coloca depois do último)
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
    init_db()
    app = SongPDFApp()
    app.mainloop()
