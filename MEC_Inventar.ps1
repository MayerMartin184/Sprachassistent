# MEC_Inventar.ps1
# Liest X:\ komplett und schreibt eine Dateiliste mit Hash auf den Desktop.
# Aendert nichts. Dauer je nach Datenmenge 10 bis 60 Minuten.
# Ergebnis: Desktop\MEC_Inventar_<Datum>.csv  -> diese Datei in den Claude-Chat ziehen (oder liegen lassen, Claude liest den Desktop)

$ErrorActionPreference = 'SilentlyContinue'
$root  = 'X:\'
$stamp = Get-Date -Format 'yyyyMMdd_HHmm'
$desk  = [Environment]::GetFolderPath('Desktop')
$out   = Join-Path $desk "MEC_Inventar_$stamp.csv"
$log   = Join-Path $desk "MEC_Inventar_$stamp.log"
$skip  = @('#recycle','_NexusOffice_Trash','@eaDir','#snapshot','.git','__pycache__','node_modules','.venv','obj','bin')
$hashMax = 50MB

if (-not (Test-Path $root)) { "X: nicht erreichbar" | Out-File $log; Write-Host "X: nicht erreichbar"; pause; exit }

Write-Host "Lese Dateiliste von $root ..."
$all = Get-ChildItem -LiteralPath $root -Recurse -Force -File -ErrorVariable errs
$files = foreach ($f in $all) {
  $p = $f.FullName
  $hit = $false
  foreach ($s in $skip) { if ($p -like "*\$s\*") { $hit = $true; break } }
  if (-not $hit) { $f }
}
$n = $files.Count
Write-Host "$n Dateien gefunden. Berechne Hashes (nur Dateien bis 50 MB) ..."

$rows = New-Object System.Collections.Generic.List[object]
$i = 0
foreach ($f in $files) {
  $i++
  if ($i % 200 -eq 0) { Write-Progress -Activity "Inventar" -Status "$i von $n" -PercentComplete ([int](100*$i/$n)) }
  $h = ''
  if ($f.Length -gt 0 -and $f.Length -le $hashMax) {
    $h = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
  }
  $rel = $f.FullName.Substring($root.Length)
  $top = ($rel -split '\\')[0]
  $rows.Add([pscustomobject]@{
    Top        = $top
    Pfad       = $rel
    Name       = $f.Name
    Endung     = $f.Extension.ToLower()
    Bytes      = $f.Length
    Geaendert  = $f.LastWriteTime.ToString('yyyy-MM-dd HH:mm')
    SHA256     = $h
  })
}
Write-Progress -Activity "Inventar" -Completed

$rows | Export-Csv -LiteralPath $out -NoTypeInformation -Delimiter ';' -Encoding UTF8

# Leere Ordner
$empty = Get-ChildItem -LiteralPath $root -Recurse -Force -Directory | Where-Object {
  $p = $_.FullName; $hit = $false
  foreach ($s in $skip) { if ($p -like "*\$s\*" -or $p -like "*\$s") { $hit = $true; break } }
  (-not $hit) -and ((Get-ChildItem -LiteralPath $p -Force | Measure-Object).Count -eq 0)
} | ForEach-Object { $_.FullName.Substring($root.Length) }

@("MEC_Inventar $stamp", "Dateien: $n", "Leere Ordner: $($empty.Count)", "", "=== Leere Ordner ===") + $empty + @("", "=== Fehler beim Lesen ===") + ($errs | ForEach-Object { $_.TargetObject }) | Out-File -LiteralPath $log -Encoding UTF8

Write-Host ""
Write-Host "Fertig: $out"
Write-Host "Log:    $log"
Write-Host "Jetzt die CSV in den Claude-Chat ziehen."
pause
