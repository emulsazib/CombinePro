; Inno Setup script for the CombinePro Windows installer.
; Compile with:  iscc installer\CombinePro.iss
; (build_windows.ps1 runs PyInstaller first, then invokes this.)

#define AppName "CombinePro"
#define AppVersion "1.0.4"
#define AppPublisher "CombinePro"
#define AppExeName "CombinePro.exe"

[Setup]
AppId={{8E4C1F92-7A3D-4B65-9C2E-1D7F5A0B3E48}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install by default needs no admin rights; switch to "admin" for all-users.
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename={#AppName}-{#AppVersion}-Windows-Setup
SetupIconFile=build\{#AppName}.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; The whole PyInstaller onedir output.
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Leave the user's .env (API keys) in %APPDATA% alone on uninstall.
Type: filesandordirs; Name: "{app}"

[Code]
// Warn if Node.js is absent: the app still runs, but Delta Memory is disabled.
function NodeInstalled(): Boolean;
var
  Path: String;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\Node.js', 'InstallPath', Path)
         or RegQueryStringValue(HKCU, 'SOFTWARE\Node.js', 'InstallPath', Path)
         or FileExists(ExpandConstant('{pf}\nodejs\node.exe'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not NodeInstalled()) then
    MsgBox('CombinePro installed successfully.' + #13#10#13#10 +
           'Node.js was not detected. CombinePro runs fine without it, but the ' +
           'Delta Memory sidecar stays offline until Node.js 18+ is installed ' +
           '(nodejs.org). You can check this any time in Settings > Memory & MCP.',
           mbInformation, MB_OK);
end;
