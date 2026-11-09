; Inno Setup Script for KDM - Kevin Download Manager
; Compiles to: dist_installer\KDM_Setup_v1.2.exe

#define MyAppName "Kevin Download Manager"
#define MyAppShortName "KDM"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "Kevin Kieu"
#define MyAppExeName "KDM.exe"
#define MyAppIcon "kdm_icon.ico"

[Setup]
AppId={{8B32194D-93D2-4752-9B7C-A58F2E29112E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\KDM
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist_installer
OutputBaseFilename=KDM_Setup_v1.2
SetupIconFile={#MyAppIcon}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
SetupWindowTitle=Cài đặt - %1
WelcomeLabel1=Chào mừng bạn đến với trình cài đặt %1!
WelcomeLabel2=Phần mềm sẽ tự động cài đặt %1 lên máy tính của bạn.%n%nKDM là trình tăng tốc tải file đa luồng và bắt link video tự động (YouTube, TikTok, Phim lẻ, Phim bộ, Anime, HLS/M3U8) siêu tốc độ.%n%nNhấn "Next" để bắt đầu.
ReadyLabel1=Sẵn sàng cài đặt %1 lên máy tính.
ReadyLabel2a=Nhấn "Install" để bắt đầu quá trình cài đặt.
FinishedHeadingLabel=Cài đặt %1 hoàn tất!
FinishedLabel=%1 đã được cài đặt thành công vào máy tính của bạn.%n%nBạn có thể khởi động phần mềm và tích hợp Extension vào trình duyệt để bắt đầu tải file siêu tốc!
ClickFinish=Nhấn "Finish" để hoàn tất.

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng trên màn hình chính (Desktop Shortcut)"; GroupDescription: "Tùy chọn bổ sung:"
Name: "autostart"; Description: "Tự động khởi động cùng Windows khi mở máy"; GroupDescription: "Cấu hình hệ thống:"

[Files]
Source: "dist\KDM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "kdm_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "installer_assets\welcome.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "install_extension_helper.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcon}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcon}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KDM"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Khởi chạy {#MyAppName} ngay bây giờ"; Flags: nowait postinstall skipifsilent
Filename: "{app}\welcome.html"; Description: "Mở trang hướng dẫn tích hợp Extension (Cốc Cốc, Chrome, Edge, Firefox)"; Flags: shellexec nowait postinstall skipifsilent
