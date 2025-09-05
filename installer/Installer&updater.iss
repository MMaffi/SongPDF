; ------------------ CONFIGURAÇÃO BÁSICA ------------------
[Setup]
AppName=SongPDF
AppVersion=1.2.5.9.25
AppPublisher=MMaffi Software
DefaultDirName=C:\SongPDF
DefaultGroupName=SongPDF
OutputBaseFilename=SongPDF_Installer
Compression=lzma
SolidCompression=yes
DisableProgramGroupPage=no
WizardStyle=modern

; Ícone do instalador
SetupIconFile=..\assets\icons\songpdf.ico
; Ícone do desinstalador
UninstallDisplayIcon=..\assets\icons\songpdf.ico

; ------------------ ARQUIVOS ------------------
[Files]
; Exe principal
Source: "..\dist\SongPDF.exe"; DestDir: "{app}"; Flags: ignoreversion
; Pasta de dados (exceto o banco)
Source: "..\data\*"; DestDir: "{app}\data"; Flags: recursesubdirs createallsubdirs; Excludes: "songpdf.db"
; Banco de dados (copiar apenas se não existir)
Source: "..\data\songpdf.db"; DestDir: "{app}\data"; Flags: onlyifdoesntexist uninsneveruninstall
; Pasta assets
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: recursesubdirs createallsubdirs ignoreversion

; ------------------ TASKS ------------------
[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Tarefas adicionais"; Flags: unchecked

; ------------------ ATALHOS ------------------
[Icons]
; Atalho no menu iniciar
Name: "{group}\SongPDF"; Filename: "{app}\SongPDF.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icons\songpdf.ico"
Name: "{group}\Desinstalar SongPDF"; Filename: "{uninstallexe}"
; Atalho na área de trabalho
Name: "{userdesktop}\SongPDF"; Filename: "{app}\SongPDF.exe"; Tasks: desktopicon; IconFilename: "{app}\assets\icons\songpdf.ico"

; ------------------ REGISTRO OPCIONAL ------------------
; Você pode adicionar chaves de registro se quiser, mas não é obrigatório
; [Registry]
; Root: HKCU; Subkey: "Software\SongPDF"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey
