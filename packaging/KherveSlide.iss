; Inno Setup script for KherveSlide — per-user install, no admin rights.
;
; Not run by hand: packaging/build_installer.py freezes the app and then calls
;
;   ISCC.exe /DAPP_VERSION=0.158.N /DSRC_DIR=...\dist\KherveSlide /DOUT_DIR=...\dist
;            /DICON_FILE=...\build\KherveSlide.ico KherveSlide.iss
;
; Installs to %LOCALAPPDATA%\Programs\KherveSlide, so there is no elevation
; prompt; associates .kslide presentations, and lists KherveSlide under
; "Open with" for PowerPoint files (which it imports).
;
; Copyright (C) 2026 Gwilherm Kerherve.

#ifndef APP_VERSION
  #define APP_VERSION "0.0.0"
#endif
#ifndef SRC_DIR
  #define SRC_DIR "..\dist\KherveSlide"
#endif
#ifndef OUT_DIR
  #define OUT_DIR "..\dist"
#endif
#ifndef ICON_FILE
  #define ICON_FILE "..\build\KherveSlide.ico"
#endif

#define AppName "KherveSlide"
#define AppPublisher "Gwilherm Kerherve"
#define AppURL "https://khervetools.com/tools/kherveslide"
#define AppExe "KherveSlide.exe"

[Setup]
AppId={{643764D3-CC8F-45F9-9795-F7115B35E167}
AppName={#AppName}
AppVersion={#APP_VERSION}
AppVerName={#AppName} {#APP_VERSION}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
VersionInfoVersion={#APP_VERSION}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#ICON_FILE}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir={#OUT_DIR}
OutputBaseFilename={#AppName}-Setup-{#APP_VERSION}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[InstallDelete]
; Inno never removes a file a newer build dropped, and the Python packages
; (numpy, PySide6, matplotlib, PyMuPDF) are ABI-bound to each other: an upgrade must
; not leave the old _internal tree beside the new one. It is all build
; output; nothing the user made lives under {app}.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SRC_DIR}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Per-user (HKCU) to match the per-user install.
Root: HKCU; Subkey: "Software\Classes\.kslide"; ValueType: string; ValueName: ""; ValueData: "KherveSlide.Presentation"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\KherveSlide.Presentation"; ValueType: string; ValueName: ""; ValueData: "KherveSlide presentation"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\KherveSlide.Presentation\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"
Root: HKCU; Subkey: "Software\Classes\KherveSlide.Presentation\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""
; "Open with" for PowerPoint files: offered, not owned.
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".kslide"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pptx"; ValueData: ""

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
