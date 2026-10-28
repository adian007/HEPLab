param([string]$Distro = 'Ubuntu', [int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$linuxUserDirectory = (& wsl.exe -d $Distro -- printenv HOME).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot read WSL user directory' }
$linuxProject = (& wsl.exe -d $Distro -- wslpath -a ($projectRoot.Replace('\', '/'))).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve project directory in WSL' }
$physicsBinary = "$linuxProject/kernels/physics-core/target/release/heplab-physics"
& wsl.exe -d $Distro -- test -x $physicsBinary
if ($LASTEXITCODE -eq 0) {
    $env:HEPLAB_RUST_EXECUTABLE = $physicsBinary
    $env:HEPLAB_RUST_WSL_DISTRO = $Distro
}
$simulationPrefix = "$linuxUserDirectory/.cache/heplab/sim-runtime"
& wsl.exe -d $Distro -- test -f "$simulationPrefix/heplab-runtime.json"
if ($LASTEXITCODE -eq 0) {
    $env:HEPLAB_SIM_PREFIX = $simulationPrefix
    $env:HEPLAB_SIM_WSL_DISTRO = $Distro
}
Push-Location -LiteralPath $projectRoot
try { python -m heplab.cli gui --port $Port --open-browser }
finally { Pop-Location }
