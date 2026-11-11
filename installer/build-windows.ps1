param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = '0.1.0'
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

if (-not $IsWindows) { throw 'Run this script with PowerShell 7 on Windows x64.' }

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    python -c "import platform, struct, sys; sys.exit(0 if platform.machine() == 'AMD64' and struct.calcsize('P') == 8 else 'An x64 Python interpreter is required.')"
    $iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
    }
    if (-not (Test-Path $iscc -PathType Leaf)) {
        throw 'Inno Setup 6 was not found. Install it or add ISCC.exe to PATH.'
    }

    $thirdParty = (Resolve-Path 'third_party').Path
    $entryPoint = (Resolve-Path 'voltscope.py').Path
    $bundle = @(
        '--noconfirm', '--clean', '--noupx', '--onedir', '--windowed',
        '--name', 'VoltScope', '--distpath', 'work/windows/dist',
        '--workpath', 'work/windows/build', '--specpath', 'work/windows',
        '--add-data', "${thirdParty}:third_party"
    )
    foreach ($distribution in @('PySide6', 'PySide6-Essentials', 'PySide6-Addons', 'shiboken6', 'numpy', 'scipy', 'openpyxl', 'et_xmlfile', 'nrbf')) {
        $bundle += @('--copy-metadata', $distribution)
    }
    python -m PyInstaller @bundle $entryPoint
    & $iscc "/DAppVersion=$Version" 'installer/VoltScope.iss'

    $setup = Get-Item 'outputs/windows/VoltScope-Setup-x64.exe'
    $hash = (Get-FileHash $setup.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($setup.Name)" | Set-Content "$($setup.FullName).sha256" -Encoding ascii
} finally {
    Pop-Location
}
