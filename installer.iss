#ifndef AppVersion
  #error AppVersion must be supplied by the build script
#endif

[Setup]
AppId={{8CA4B520-085B-4AD0-B198-5DCCAD948A33}
AppName=handwrite-scanner
AppVersion={#AppVersion}
AppPublisher=Bun3
AppPublisherURL=https://github.com/Bun3/handwrite-scanner
DefaultDirName={localappdata}\Programs\handwrite-scanner
DefaultGroupName=handwrite-scanner
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=handwrite-scanner-setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
AppMutex=Local\HandwriteScannerRunning
CloseApplications=no
RestartApplications=no
UninstallDisplayIcon={app}\handwrite-scanner.exe
SetupLogging=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 실행 바로가기 만들기"; Flags: checkedonce

[Files]
Source: "dist\handwrite-scanner\handwrite-scanner.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\handwrite-scanner\handwrite-updater.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\handwrite-scanner\server-mode.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\handwrite-scanner\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\handwrite-scanner"; Filename: "{app}\handwrite-scanner.exe"; WorkingDir: "{app}"
Name: "{group}\handwrite-scanner 서버 모드"; Filename: "{app}\handwrite-scanner.exe"; Parameters: "--server"; WorkingDir: "{app}"
Name: "{autodesktop}\handwrite-scanner"; Filename: "{app}\handwrite-scanner.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\handwrite-scanner.exe"; Description: "handwrite-scanner 실행"; Flags: nowait postinstall skipifsilent

[Messages]
SelectDirDesc=프로그램을 설치할 폴더를 선택하세요.
SelectDirLabel3=기존 ZIP 버전의 모델·작업 기록을 계속 사용하려면 기존 handwrite-scanner.exe가 있는 폴더를 선택하세요. data와 engine 폴더는 유지됩니다.
SetupAppRunningError=handwrite-scanner가 실행 중입니다.%n%n진행 중인 작업을 마치고 프로그램 실행 창을 종료한 뒤 다시 시도하세요. 브라우저만 닫으면 서버는 계속 실행됩니다.

[Code]
function CreateFileW(lpFileName: String; dwDesiredAccess, dwShareMode,
  lpSecurityAttributes, dwCreationDisposition, dwFlagsAndAttributes,
  hTemplateFile: LongWord): LongWord;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseHandle(hObject: LongWord): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Handle: LongWord;
begin
  Result := '';
  { Older portable versions have no mutex. Never replace their running EXE. }
  if FileExists(ExpandConstant('{app}\handwrite-scanner.exe')) then
  begin
    Handle := CreateFileW(ExpandConstant('{app}\handwrite-scanner.exe'),
                          $40000000, 0, 0, 3, 0, 0);
    if Handle = $FFFFFFFF then
      Result := '기존 프로그램을 완전히 종료하고 설치 폴더의 쓰기 권한을 확인한 뒤 다시 진행하세요.'
    else
      CloseHandle(Handle);
  end;
end;
