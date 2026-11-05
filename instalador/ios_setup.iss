; Script de Inno Setup para IOS (docs/PLAN.md, etapa 10).
; Compilar con ISCC.exe (Inno Setup, solo hace falta en la PC de desarrollo)
; DESPUÉS de generar dist/IOS/ con PyInstaller (ver README.md).
;
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" instalador\ios_setup.iss
;
; Genera "Instalar IOS.exe" en instalador\Output\. Copia el programa, crea
; el acceso directo en el escritorio y en el menú Inicio, y la carpeta de
; datos compartida C:\ProgramData\IOS. No borra la base al reinstalar o
; actualizar: el instalador nunca toca esa carpeta después de crearla, y
; el desinstalador no la borra porque el archivo ios.db no es un archivo
; que haya copiado el instalador.

#define MyAppName "IOS - Insumos Oftalmológicos Santiago"
#define MyAppVersion "1.2.1"
#define MyAppExeName "IOS.exe"

[Setup]
AppId={{8F3B6D9B-6E7B-4C4B-9E0B-2B6E8B6B3C01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\IOS
DefaultGroupName=IOS
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=Output
OutputBaseFilename=Instalar IOS
SetupIconFile=..\assets\ios.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos adicionales:"

[Files]
Source: "..\dist\IOS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Carpeta de datos compartida: la crea el instalador con permisos de
; escritura para usuarios; la base la crea IOS la primera vez que abre.
Name: "C:\ProgramData\IOS"; Permissions: users-modify

[Icons]
Name: "{group}\IOS"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\IOS"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir IOS"; Flags: nowait postinstall skipifsilent
