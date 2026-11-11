; Run the build script from the repository root before compiling this file.
#ifndef AppVersion
  #error AppVersion must be supplied by the build script
#endif

[Setup]
AppId={{4E06F18B-E448-4D49-8C89-EE4DA3890436}
AppName=VoltScope
AppVersion={#AppVersion}
AppPublisher=Aalto EMA
AppPublisherURL=https://github.com/aalto-ema/voltscope
DefaultDirName={localappdata}\Programs\VoltScope
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.17763
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\VoltScope.exe
LicenseFile=..\LICENSE
OutputDir=..\outputs\windows
OutputBaseFilename=VoltScope-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\work\windows\dist\VoltScope\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\third_party\*-LICENSE.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\VoltScope"; Filename: "{app}\VoltScope.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\VoltScope.exe"; Description: "Launch VoltScope"; Flags: nowait postinstall skipifsilent
