param(
    [Parameter(Mandatory=$true)][string]$InputPath
)
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
    $null = [Windows.Storage.FileAccessMode, Windows.Storage, ContentType=WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]

    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1
    } | Select-Object -First 1)

    function Await-Result($Operation, [Type]$ResultType) {
        $method = $asTaskGeneric.MakeGenericMethod($ResultType)
        $task = $method.Invoke($null, @($Operation))
        $task.Wait()
        return $task.Result
    }

    $full = [System.IO.Path]::GetFullPath($InputPath)
    $file = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($full)) ([Windows.Storage.StorageFile])
    $stream = Await-Result ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
    $decoder = Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $ocr = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $ocr) { exit 0 }
    $result = Await-Result ($ocr.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    if ($null -ne $result -and $result.Text) {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        Write-Output $result.Text
    }
} catch {
    # OCR is optional. Empty output means the Python ranker continues without it.
    exit 0
}
