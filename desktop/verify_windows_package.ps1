param(
    [Parameter(Mandatory)]
    [string] $Bundle,
    [string] $SmokeKit
)

$ErrorActionPreference = 'Stop'
$bundlePath = (Resolve-Path -LiteralPath $Bundle).ProviderPath
$SmokeKit = if ($SmokeKit) { $SmokeKit } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$kitPath = (Resolve-Path -LiteralPath $SmokeKit).ProviderPath
$tempRoot = [IO.DirectoryInfo]::new([IO.Path]::GetTempPath()).FullName.TrimEnd('\')
$scratch = Join-Path $tempRoot ("HEPLab standalone " + [guid]::NewGuid())
$appPath = Join-Path $scratch 'Workbench'
$workingDirectory = Join-Path $scratch 'Empty working directory'

function Start-IsolatedProcess($executable, $arguments, $capture = $false) {
    $info = [Diagnostics.ProcessStartInfo]::new($executable, $arguments)
    $info.UseShellExecute = $false
    $info.WorkingDirectory = $workingDirectory
    $info.RedirectStandardOutput = $capture
    $info.RedirectStandardError = $capture
    foreach ($key in @($info.EnvironmentVariables.Keys)) {
        if ($key -match '^(PYTHON|PYINSTALLER|_PYI_|HEPLAB_|QT_|QML|UV_|VIRTUAL_ENV$|CONDA)') {
            $info.EnvironmentVariables.Remove($key)
        }
    }
    $info.EnvironmentVariables['PATH'] = "$env:SystemRoot\System32;$env:SystemRoot"
    $info.EnvironmentVariables['TEMP'] = $scratch
    $info.EnvironmentVariables['TMP'] = $scratch
    $info.EnvironmentVariables['LOCALAPPDATA'] = $scratch
    [Diagnostics.Process]::Start($info)
}

New-Item -ItemType Directory -Path $workingDirectory -Force | Out-Null
try {
    for ($directory = [IO.DirectoryInfo]::new($scratch); $directory; $directory = $directory.Parent) {
        if ((Test-Path (Join-Path $directory.FullName 'pyproject.toml')) -and
            (Test-Path (Join-Path $directory.FullName 'CMakeLists.txt'))) {
            throw "Set TEMP to a directory outside the HEPLab checkout."
        }
    }
    Copy-Item -LiteralPath $bundlePath -Destination $appPath -Recurse
    foreach ($file in @('HEPLabWorkbench.exe', 'worker/heplab-worker.exe', 'worker/_internal/python312.dll')) {
        if (-not (Test-Path -LiteralPath (Join-Path $appPath $file) -PathType Leaf)) {
            throw "Missing bundled file: $file"
        }
    }

    $workerExe = Join-Path $appPath 'worker\heplab-worker.exe'
    $pythonDll = Join-Path $appPath 'worker\_internal\python312.dll'
    $app = Start-IsolatedProcess (Join-Path $appPath 'HEPLabWorkbench.exe') ''
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        do {
            Start-Sleep -Milliseconds 100
            $app.Refresh()
            if ($app.HasExited) { throw "Workbench exited during startup ($($app.ExitCode))." }
            $worker = Get-Process -Name heplab-worker -ErrorAction SilentlyContinue |
                Where-Object { $_.Path -eq $workerExe } | Select-Object -First 1
            $python = $worker.Modules | Where-Object ModuleName -EQ 'python312.dll'
        } until (($app.MainWindowHandle -ne [IntPtr]::Zero -and $python) -or
            [DateTime]::UtcNow -ge $deadline)
        if ($app.MainWindowHandle -eq [IntPtr]::Zero) { throw 'Workbench did not open a window.' }
        if ($python.FileName -ne $pythonDll) { throw 'Workbench did not load the bundled Python runtime.' }
        $qtCore = $app.Modules | Where-Object ModuleName -EQ 'Qt6Core.dll'
        if ($qtCore.FileName -ne (Join-Path $appPath 'Qt6Core.dll')) {
            throw 'Workbench did not load the bundled Qt runtime.'
        }
        Write-Output 'Workbench opened and loaded Qt and Python from the bundle.'
    } finally {
        if (-not $app.HasExited) {
            if (-not $app.CloseMainWindow() -or -not $app.WaitForExit(10000)) {
                $app.Kill()
                $app.WaitForExit()
            }
        }
        $app.Dispose()
    }

    foreach ($file in @('heplab_desktop_tests.exe', 'Qt6Test.dll')) {
        Copy-Item -LiteralPath (Join-Path $kitPath $file) -Destination $appPath
    }
    $resultLog = Join-Path $scratch 'simulation-test.txt'
    $tests = Start-IsolatedProcess (Join-Path $appPath 'heplab_desktop_tests.exe') `
        "packagedAnalyticSimulation -o `"$resultLog,txt`"" $true
    try {
        $stdout = $tests.StandardOutput.ReadToEndAsync()
        $stderr = $tests.StandardError.ReadToEndAsync()
        if (-not $tests.WaitForExit(120000)) {
            $tests.Kill()
            $tests.WaitForExit()
            throw 'Packaged simulation tests timed out.'
        }
        Write-Output $stdout.GetAwaiter().GetResult()
        Write-Output $stderr.GetAwaiter().GetResult()
        $log = if (Test-Path -LiteralPath $resultLog) { Get-Content -LiteralPath $resultLog -Raw }
        Write-Output $log
        if ($tests.ExitCode -ne 0) { throw "Packaged simulation failed ($($tests.ExitCode))." }
        if ($log -notmatch 'PASS\s+: MainWindowTests::packagedAnalyticSimulation\(\)') {
            throw 'Packaged simulation did not run.'
        }
    } finally {
        $tests.Dispose()
    }
} finally {
    $created = Get-Item -LiteralPath $scratch
    if ($created.Parent.FullName.TrimEnd('\') -eq $tempRoot -and
        $created.Name -match '^HEPLab standalone [0-9a-f-]{36}$' -and
        -not ($created.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Remove-Item -LiteralPath $created.FullName -Recurse -Force
    }
}
