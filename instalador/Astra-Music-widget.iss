; Instalador de Astra-Music-widget (Inno Setup 6)
;
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" instalador\Astra-Music-widget.iss
;
; Deja instalador\Astra-Music-widget-1.0.0-setup.exe (~27 MB).
;
; Decisiones que importan:
; - Se instala en %LOCALAPPDATA%\Programs (por usuario, SIN pedir administrador). Ademas
;   de no molestar con el UAC, esa carpeta es escribible: el programa guarda su
;   config.json y su astra-widget.log al lado del .exe y sigue funcionando igual (en
;   C:\Program Files no se podria escribir y habria que mudarlos a %APPDATA%).
; - AppId es un GUID fijo: asi las versiones siguientes se instalan ENCIMA y no como una
;   segunda copia.
; - CloseApplications: si el widget esta corriendo, se cierra antes de reemplazar el .exe
;   (Windows no deja sobrescribir un ejecutable en uso).
; - En la desinstalacion se pregunta si conservar los ajustes antes de borrar config.json.

#define MiNombre "Astra-Music-widget"
#define MiVersion "1.0.0"
#define MiExe "Astra-Music-widget.exe"

[Setup]
AppId={{7F3A9C21-5E4B-4D18-9A62-3C7E51D08B44}
AppName={#MiNombre}
AppVersion={#MiVersion}
AppVerName={#MiNombre} {#MiVersion}
AppPublisher=Eduardo Fleitas
AppPublisherURL=https://github.com/eduardofleitass/Astra
AppSupportURL=https://github.com/eduardofleitass/Astra
DefaultDirName={localappdata}\Programs\{#MiNombre}
DefaultGroupName={#MiNombre}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=.
OutputBaseFilename={#MiNombre}-{#MiVersion}-setup
SetupIconFile=..\assets\icono.ico
UninstallDisplayIcon={app}\{#MiExe}
UninstallDisplayName={#MiNombre}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
AllowNoIcons=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "autostart"; Description: "Arrancar con Windows (recomendado: es un adorno de la barra)"; GroupDescription: "Inicio:"; Flags: checkedonce
Name: "desktopicon"; Description: "Crear un acceso en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\dist\{#MiExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\icono.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MiNombre}"; Filename: "{app}\{#MiExe}"; IconFilename: "{app}\icono.ico"; Comment: "Musica en la barra de tareas"
Name: "{group}\Desinstalar {#MiNombre}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MiNombre}"; Filename: "{app}\{#MiExe}"; IconFilename: "{app}\icono.ico"; Tasks: desktopicon
; el mismo nombre que usa el propio programa (tools/startup.py), asi no quedan dos
Name: "{userstartup}\{#MiNombre}"; Filename: "{app}\{#MiExe}"; IconFilename: "{app}\icono.ico"; Tasks: autostart

[Run]
Filename: "{app}\{#MiExe}"; Description: "Arrancar {#MiNombre} ahora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\astra-widget.log"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function InitializeUninstall(): Boolean;
var
  R: Integer;
begin
  Result := True;
  // Los ajustes son del usuario (color, ancho, fondo, posicion del panel): se pregunta
  // antes de borrarlos. En modo silencioso no se pregunta nada.
  if not UninstallSilent then
  begin
    R := MsgBox('¿Querés conservar tus ajustes?' + #13#10 + #13#10 +
                'Se guardan en config.json (color de la barra y las ondas, ancho, fondo, ' +
                'tamaño y posicion del panel).' + #13#10 +
                'Si elegis No, se borran tambien.',
                mbConfirmation, MB_YESNO);
    if R = IDNO then
      DeleteFile(ExpandConstant('{app}\config.json'));
  end;
end;
