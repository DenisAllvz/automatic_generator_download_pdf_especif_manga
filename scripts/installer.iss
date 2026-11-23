; Optional Inno Setup 6 template. Compiler not included/tested.
[Setup]
AppId=MangaManagerLocalLibrary
AppName=Manga Manager
AppVersion=2.5.0
DefaultDirName={localappdata}\Programs\MangaManager
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=MangaManager-Setup
UninstallDisplayIcon={app}\MangaManager.exe

[Files]
Source: "..\dist\MangaManager-2.5.0\*"; DestDir: "{app}"; Excludes: "data\*,portable.flag"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Manga Manager"; Filename: "{app}\MangaManager.exe"

; User data in LocalAppData\MangaManager is deliberately not removed.
