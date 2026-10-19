; Per-user KŌRA installer for Windows x64 (Inno Setup 6). Saved as UTF-8 with BOM
; so Inno Setup reads the macron in the product name correctly.
; Built by scripts/build_windows_release.py, which passes the version and paths:
;   ISCC /DAppVersion=0.2.44 /DSourceDir=dist\windows\Kora /DOutputDir=... /DIconFile=...
; It installs the same files as the portable ZIP, without administrator rights.

#ifndef AppVersion
  #error AppVersion is required
#endif

[Setup]
AppId={{6E1F7B52-3C4D-4E0B-9A71-4B6D2C1F0A55}
AppName=KŌRA
AppVersion={#AppVersion}
AppVerName=KŌRA {#AppVersion}
AppPublisher=KŌRA
; Per-user mode: {autopf} is %LOCALAPPDATA%\Programs, matching the evaluation kit.
DefaultDirName={autopf}\Kora
DefaultGroupName=KŌRA
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19045
OutputDir={#OutputDir}
OutputBaseFilename=Kora-{#AppVersion}-Windows-x64-Setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\Kora.exe
UninstallDisplayName=KŌRA {#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
; Created by kora/desktop.py (WINDOWS_APP_MUTEX). Without it, uninstalling while
; KŌRA runs removes the shortcut and uninstall entry but leaves Kora.exe behind.
AppMutex=Kora-6E1F7B52-3C4D-4E0B-9A71-4B6D2C1F0A55

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Remove files of a previous version so no stale Python module stays loaded.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\tools"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\KŌRA"; Filename: "{app}\Kora.exe"
Name: "{autodesktop}\KŌRA"; Filename: "{app}\Kora.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Kora.exe"; Description: "{cm:LaunchProgram,KŌRA}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2Client = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2Installed(): Boolean;
var
  Version: String;
begin
  // Microsoft's documented detection keys for the Evergreen runtime.
  Result :=
    (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM, WebView2Client, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKCU, WebView2Client, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not WizardSilent()) and (not WebView2Installed()) then
    MsgBox('KŌRA needs the Microsoft Edge WebView2 Runtime, which was not found.' + #13#10 +
           'Install it from https://developer.microsoft.com/microsoft-edge/webview2/ before opening KŌRA.',
           mbInformation, MB_OK);
end;

function RemoveOwnedFolder(const Name: String): Boolean;
begin
  Result := True;
  if DirExists(Name) then
    Result := DelTree(Name, True, True, True);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Attempt: Integer;
  Internal, Tools: Boolean;
begin
  // AppMutex lets the uninstaller start as soon as KŌRA exits, but Windows can
  // keep the DLLs it loaded locked for a few seconds more (about 35 files on
  // Windows on Arm), and the uninstaller would skip them. Delete the folders
  // that [InstallDelete] already treats as ours, retrying while they are locked.
  if CurUninstallStep <> usUninstall then
    Exit;
  for Attempt := 1 to 60 do
  begin
    Internal := RemoveOwnedFolder(ExpandConstant('{app}\_internal'));
    Tools := RemoveOwnedFolder(ExpandConstant('{app}\tools'));
    if Internal and Tools then
      Exit;
    Sleep(500);
  end;
end;
