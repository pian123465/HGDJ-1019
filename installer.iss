; Inno Setup 脚本 - 生成 Windows 安装包
;
; 流程:
;   1. pip install pyinstaller
;   2. pyinstaller shortdrama.spec --clean --noconfirm
;   3. 装 Inno Setup Compiler:https://jrsoftware.org/isdl.php
;   4. 双击本文件 / 用 Inno Setup Compiler 打开 → Build
;   5. 产出 installer_output\Setup-Shortdrama-0.3.exe
;
; 生成的安装包:
;   - 桌面图标
;   - 开始菜单快捷方式
;   - 卸载时清理 downloads / sqlite
;   - 提示装 aria2c / ffmpeg(可选)

[Setup]
AppId={{B5C7F6E3-0A1B-4D8E-9F2C-1A3B4C5D6E7F}
AppName=短剧下载器
AppVersion=0.3
AppVerName=短剧下载器 v0.3
AppPublisher=Mavis
AppPublisherURL=https://example.com
DefaultDirName={autopf}\Shortdrama-DL
DefaultGroupName=短剧下载器
AllowNoIcons=yes
LicenseFile=LICENSE
InfoBeforeShow=yes
OutputDir=installer_output
OutputBaseFilename=Setup-Shortdrama-0.3
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequirediaAdminAllowed=no
UninstallDisplayName=短剧下载器 v0.3
VersionInfoVersion=0.3.0
VersionInfoCompany=Mavis
VersionInfoDescription=短剧下载器 - 跨平台搜索下载工具
VersionInfoProductName=短剧下载器
MinVersion=10.0

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm,CreateDesktopIcon}"; GroupDescription: "{cm,AdditionalIcons}"; Flags: unchecked
Name: "quicklaunch"; Description: "{cm,CreateQuickLaunchIcon}"; GroupDescription: "{cm,AdditionalIcons}"; Flags: unchecked

[Files]
; 主程序(由 PyInstaller 生成)
Source: "dist\shortdrama-dl.exe"; DestDir: "{app}"; Flags: ignoreversion
; 图标(用于开始菜单和卸载)
Source: "assets\icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
; 文档
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\短剧下载器"; Filename: "{app}\shortdrama-dl.exe"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\{cm,UninstallProgram,短剧下载器}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\短剧下载器"; Filename: "{app}\shortdrama-dl.exe"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\短剧下载器"; Filename: "{app}\shortdrama-dl.exe"; IconFilename: "{app}\assets\icon.ico"; Tasks: quicklaunch

[Run]
; 安装完询问是否启动
Filename: "{app}\shortdrama-dl.exe"; Description: "{cm,LaunchProgram,短剧下载器}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\downloads"
Type: filesandordirs; Name: "{userappdata}\Shortdrama-DL"
Type: filesandordirs; Name: "{app}\shortdrama_tasks.db"
Type: filesandordirs; Name: "{app}\assets"

[Messages]
BeveledLabel=短剧下载器 v0.3
SetupWindowTitle=短剧下载器 - 安装向导