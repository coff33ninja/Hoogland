[Setup]
AppName=Hoogland
AppVersion=1.0
DefaultDirName={autopf}\Hoogland
OutputDir=Output
OutputBaseFilename=HooglandInstaller
PrivilegesRequired=admin
Uninstallable=yes

[Files]
Source: "dist\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{userstartup}\Hoogland"; Filename: "{app}\app.exe"; WorkingDir: "{app}"; Comment: "Hoogland Alert System"

[Run]
Filename: "{app}\app.exe"; Description: "Launch Hoogland"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Leave %APPDATA%\Hoogland intact by not deleting it
Type: filesandordirs; Name: "{app}"