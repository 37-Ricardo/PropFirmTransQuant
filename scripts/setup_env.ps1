param(
    [string]$PythonVersion = "3.11.9"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $ProjectRoot "tools"
$PythonDir = Join-Path $ToolsDir "python311"
$Installer = Join-Path $ToolsDir "python-$PythonVersion-amd64.exe"
$DownloadUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
$VenvDir = Join-Path $ProjectRoot ".venv"

New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

function Test-ValidWindowsExe {
    param([string]$Path)

    if (!(Test-Path $Path)) {
        return $false
    }

    $File = Get-Item $Path
    if ($File.Length -lt 10485760) {
        return $false
    }

    $Stream = [System.IO.File]::OpenRead($Path)
    try {
        $Buffer = New-Object byte[] 2
        [void]$Stream.Read($Buffer, 0, 2)
        return ($Buffer[0] -eq 0x4D -and $Buffer[1] -eq 0x5A)
    }
    finally {
        $Stream.Dispose()
    }
}

if ((Test-Path $Installer) -and !(Test-ValidWindowsExe -Path $Installer)) {
    Write-Host "Existing installer is incomplete or corrupted. Removing it..."
    Remove-Item -LiteralPath $Installer -Force
}

if (!(Test-Path $Installer)) {
    Write-Host "Downloading Python $PythonVersion installer..."
    curl.exe -fL --retry 3 --retry-delay 2 -o $Installer $DownloadUrl
}

if (!(Test-ValidWindowsExe -Path $Installer)) {
    throw "Downloaded installer is not a valid Windows executable: $Installer"
}

if (!(Test-Path (Join-Path $PythonDir "python.exe"))) {
    Write-Host "Installing Python $PythonVersion into $PythonDir ..."
    Start-Process -FilePath $Installer -ArgumentList @(
        "/quiet",
        "InstallAllUsers=0",
        "TargetDir=$PythonDir",
        "Include_launcher=0",
        "Include_pip=1",
        "Include_test=0",
        "PrependPath=0",
        "Shortcuts=0"
    ) -Wait -NoNewWindow
}

$PythonExe = Join-Path $PythonDir "python.exe"
& $PythonExe --version

if (!(Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment..."
    & $PythonExe -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")

Write-Host ""
Write-Host "Environment is ready."
Write-Host "Activate with:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Validate with:"
Write-Host "  python main.py --csv examples\sample_nq_1min.csv --timeframe 5min"
