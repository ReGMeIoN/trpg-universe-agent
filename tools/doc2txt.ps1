# Convert legacy .doc files to text via Word COM (read-only, no dialogs).
# English-only on purpose: PS 5.1 parses UTF-8 scripts as GBK and dies on CJK.
# Usage: powershell -File tools\doc2txt.ps1 -InDir <dir> -OutDir <dir>
#
# !! 2026-10-03: Word COM HANGS under a restricted sandbox (cross-process ALPC over
# !! named pipes is blocked). Prefer the pure-Python reader instead:
# !!     .venv\Scripts\python.exe tools\_doc_text.py --dir <dir> --out-dir <dir>
# !! Keep this script only for environments where COM is actually reachable.
param(
    [Parameter(Mandatory = $true)][string]$InDir,
    [Parameter(Mandatory = $true)][string]$OutDir
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $InDir)) { throw "missing input dir: $InDir" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$files = Get-ChildItem -LiteralPath $InDir -Filter '*.doc' -File
if (-not $files) { Write-Output 'no .doc files found'; exit 0 }

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$ok = 0
$failed = 0
try {
    foreach ($f in $files) {
        $out = Join-Path $OutDir ($f.BaseName + '.txt')
        try {
            $doc = $word.Documents.Open($f.FullName, $false, $true)
            # wdFormatUnicodeText = 7  -> UTF-16LE with BOM
            $doc.SaveAs([ref]$out, [ref]7)
            $doc.Close([ref]0)
            Write-Output "OK   $out"
            $ok++
        }
        catch {
            Write-Output "FAIL $($f.Name): $($_.Exception.Message)"
            $failed++
        }
    }
}
finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
Write-Output "done ok=$ok failed=$failed"
