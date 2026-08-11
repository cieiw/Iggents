param(
    [Parameter(Mandatory = $true)]
    [string]$InputFile
)

$projectRoot = Split-Path $PSScriptRoot -Parent
$ffmpegBundled = Join-Path $PSScriptRoot "ffmpeg\ffmpeg.exe"
if (Test-Path $ffmpegBundled) {
    $ffmpeg = $ffmpegBundled
} else {
    $ffmpeg = (Get-Command ffmpeg.exe -ErrorAction Stop).Source
}
$input = (Resolve-Path -LiteralPath $InputFile).Path
$wav = [System.IO.Path]::ChangeExtension($input, ".wav")
& $ffmpeg -y -hide_banner -loglevel error -i $input -ar 16000 -ac 1 -c:a pcm_s16le $wav
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $wav)) { throw "O FFmpeg não gerou o WAV." }
Write-Host "WAV pronto: $wav"
