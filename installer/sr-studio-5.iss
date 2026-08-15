#define MyAppName "SR Studio 5 Professional"
#ifndef MyAppVersion
  #define MyAppVersion "development"
#endif
#define MyAppPublisher "SR"
#define MyAppExeName "SR Studio 5.exe"

[Setup]
AppId={{B9A8D88B-2950-4BB8-9E4A-5C811E9C5A50}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\SR Studio 5
DefaultGroupName=SR Studio 5
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=SR-Studio-5-Setup
Compression=lzma2
SolidCompression=no
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\SR Studio 5\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\SR Studio 5"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\SR Studio 5"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir SR Studio 5"; Flags: nowait postinstall skipifsilent
