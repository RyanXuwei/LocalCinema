#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif
#define RepoRoot AddBackslash(SourcePath) + ".."
[Setup]
AppId={{42C66711-46C2-4A93-8348-10999483A817}
AppName=LocalCinema
AppVersion={#AppVersion}
AppPublisher=BitingBox Studio / Ryan Hsu
AppCopyright=Created by Ryan Hsu. 2026 Copyright
DefaultDirName={localappdata}\Programs\LocalCinema
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#RepoRoot}\dist
OutputBaseFilename=LocalCinema_Setup_v{#AppVersion}_x64
SetupIconFile={#RepoRoot}\assets\localcinema.ico
UninstallDisplayIcon={app}\LocalCinema.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "{#RepoRoot}\build\windows\dist\LocalCinema\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RepoRoot}\使用說明.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\安裝修復說明.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userprograms}\LocalCinema"; Filename: "{app}\LocalCinema.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\LocalCinema"; Filename: "{app}\LocalCinema.exe"; WorkingDir: "{app}"; Tasks: desktopicon
; No user-data deletion directives. Never add DATA to [UninstallDelete].
