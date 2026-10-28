# Build a native Windows tether-chat.exe using WebView2 (no Edge/Chrome app-window identity).
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Python venv missing. Create .venv and install tether-chat first." }
Push-Location $repo
try {
    & $python -m pip install -e . "pywebview>=5,<7" "pyinstaller>=6,<7"
    if ($LASTEXITCODE -ne 0) { throw "Native tether-chat build dependencies failed to install." }
    $icon = Join-Path $repo 'tether-horizon-circle.ico'
    & $python -m tether.windows_icon $icon
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $icon)) { throw "tether-chat icon generation failed." }

    & $python -m PyInstaller --noconfirm --clean --onefile --windowed --collect-all webview --hidden-import pystray._win32 --name tether-chat --icon $icon --distpath (Join-Path $repo 'dist') --workpath (Join-Path $repo 'build') --specpath $repo (Join-Path $repo 'tether\native.py')
    if ($LASTEXITCODE -ne 0) { throw "Native tether-chat.exe build failed." }

    $exe = Join-Path $repo 'dist\tether-chat.exe'
    if (-not (Test-Path $exe)) { throw "Missing native executable: $exe" }
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop 'tether-chat.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $exe
    $shortcut.Arguments = ''
    $shortcut.WorkingDirectory = $repo
    $shortcut.Description = 'tether-chat native desktop app'
    $shortcut.IconLocation = "$exe,0"
    $shortcut.WindowStyle = 1
    $shortcut.Save()
    Write-Host "Native tether-chat installed: $exe"
    Write-Host "Shortcut created: $shortcutPath"
    Write-Host "Pin dist\tether-chat.exe or the running native tether-chat app, not Edge."
} finally { Pop-Location }
