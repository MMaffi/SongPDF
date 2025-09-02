; ------------------ CONFIGURAÇÃO BÁSICA ------------------
[Setup]
AppName=SongPDF
AppVersion=1.0
DefaultDirName=C:\SongPDF
DefaultGroupName=SongPDF
OutputBaseFilename=SongPDF_Installer
Compression=lzma
SolidCompression=yes
DisableProgramGroupPage=no
UninstallDisplayIcon={app}\SongPDF.exe
WizardStyle=modern

; ------------------ ARQUIVOS ------------------
[Files]
; Exe principal
Source: "dist\SongPDF.exe"; DestDir: "{app}"; Flags: ignoreversion
; Pasta data
Source: "data\*"; DestDir: "{app}\data"; Flags: recursesubdirs createallsubdirs ignoreversion
; Pasta assets
Source: "assets\*"; DestDir: "{app}\assets"; Flags: recursesubdirs createallsubdirs ignoreversion

; ------------------ TASKS ------------------
[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Tarefas adicionais"; Flags: unchecked

; ------------------ ATALHOS ------------------
[Icons]
Name: "{group}\SongPDF"; Filename: "{app}\SongPDF.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icons\songpdf.ico"
Name: "{group}\Desinstalar SongPDF"; Filename: "{uninstallexe}"
Name: "{userdesktop}\SongPDF"; Filename: "{app}\SongPDF.exe"; Tasks: desktopicon; IconFilename: "{app}\assets\icons\songpdf.ico"

; ------------------ REGISTRO OPCIONAL ------------------
; Você pode adicionar chaves de registro se quiser, mas não é obrigatório
; [Registry]
; Root: HKCU; Subkey: "Software\SongPDF"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey