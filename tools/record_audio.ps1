param(
    [Parameter(Mandatory = $true)]
    [string]$Serial,
    [ValidateSet("output", "playback", "mic")]
    [string]$Source = "output",
    [ValidateRange(1, 120)]
    [int]$Duration = 10
)

$projectRoot = Split-Path $PSScriptRoot -Parent
$scrcpy = Get-ChildItem -Path (Join-Path $PSScriptRoot "scrcpy") -Filter scrcpy.exe -Recurse | Select-Object -First 1 -ExpandProperty FullName
if (-not $scrcpy) { throw "scrcpy não foi encontrado em tools\scrcpy." }

$ffmpegBundled = Join-Path $PSScriptRoot "ffmpeg\ffmpeg.exe"
if (Test-Path $ffmpegBundled) {
    $ffmpeg = $ffmpegBundled
} else {
    $ffmpeg = (Get-Command ffmpeg.exe -ErrorAction Stop).Source
}

$safeSerial = ($Serial -replace '[^A-Za-z0-9._-]', '_').Trim(' ', '.', '_')
if (-not $safeSerial) { $safeSerial = "unknown_device" }
$outputDir = Join-Path $projectRoot ("runtime\" + $safeSerial)
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$m4aFile = Join-Path $outputDir "audio.m4a"
$wavFile = Join-Path $outputDir "audio.wav"
Remove-Item -Force -ErrorAction SilentlyContinue $m4aFile, $wavFile

$arguments = @(
    "--serial", $Serial,
    "--no-video",
    "--audio-source=$Source",
    "--audio-codec=aac",
    "--record=$m4aFile",
    "--time-limit=$Duration"
)

& $scrcpy @arguments
if ($LASTEXITCODE -ne 0) { throw "scrcpy falhou com o código $LASTEXITCODE." }
if (-not (Test-Path $m4aFile)) { throw "O scrcpy não gerou audio.m4a." }

& $ffmpeg -y -hide_banner -loglevel error -i $m4aFile -ar 16000 -ac 1 -c:a pcm_s16le $wavFile
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $wavFile)) { throw "O FFmpeg não gerou audio.wav." }
Write-Host "WAV pronto: $wavFile"
