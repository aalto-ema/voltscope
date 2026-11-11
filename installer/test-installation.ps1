# Use a fresh runner: the setup registers VoltScope for the current user.
$ErrorActionPreference = 'Stop'

function Invoke-CheckedProcess($File, $Arguments, $TimeoutSeconds) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru
    try {
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw "$File timed out after $TimeoutSeconds seconds."
        }
        if ($process.ExitCode -ne 0) { throw "$File returned exit code $($process.ExitCode)." }
    } finally {
        $process.Dispose()
    }
}

$setup = (Resolve-Path "$PSScriptRoot/../outputs/windows/VoltScope-Setup-x64.exe").Path
$temp = Join-Path $env:RUNNER_TEMP 'VoltScope installer check'
$install = Join-Path $temp 'VoltScope'
$report = Join-Path $temp 'smoke.txt'
$installLog = Join-Path $temp 'install.log'
New-Item -ItemType Directory -Path $temp -Force | Out-Null

try {
    Invoke-CheckedProcess $setup "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR=`"$install`" /LOG=`"$installLog`"" 180
    Invoke-CheckedProcess (Join-Path $install 'VoltScope.exe') "--packaging-smoke-test `"$report`"" 90
    if ((Get-Content $report -Raw).Trim() -ne 'VoltScope packaging smoke test passed.') {
        throw 'The installed app did not report success.'
    }
} catch {
    foreach ($log in @($installLog, $report)) {
        if (Test-Path $log) { Get-Content $log -Tail 40 }
    }
    throw
} finally {
    $uninstaller = Join-Path $install 'unins000.exe'
    if (Test-Path $uninstaller) {
        Invoke-CheckedProcess $uninstaller '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' 120
    }
}
if (Test-Path (Join-Path $install 'VoltScope.exe')) { throw 'Uninstall left VoltScope.exe in place.' }
