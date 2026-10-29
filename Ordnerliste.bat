@echo off
rem Erstellt eine Ordnerliste von X:\ (nur Ordner + Dateianzahl, keine Dateinamen in 00_Office)
rem Ergebnis: Desktop\MEC_Ordnerliste.txt  -> diese Datei in den Claude-Chat ziehen
set OUT=%USERPROFILE%\Desktop\MEC_Ordnerliste.txt
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root='X:\'; if(!(Test-Path $root)){ 'X: nicht erreichbar' | Out-File '%OUT%'; exit }" ^
  "$o=@(); $o+='MEC_Database Ordnerliste  '+(Get-Date -Format 'yyyy-MM-dd HH:mm'); $o+='';" ^
  "function Line($p,$d){ try{ $n=(Get-ChildItem -LiteralPath $p -File -Force -EA SilentlyContinue).Count; $s=(Get-ChildItem -LiteralPath $p -Directory -Force -EA SilentlyContinue).Count }catch{ $n=0;$s=0 }; (' '*($d*2))+(Split-Path $p -Leaf)+'\  ['+$s+' Ordner, '+$n+' Dateien]' }" ^
  "function Walk($p,$d,$max){ $o2=@(Line $p $d); if($d -lt $max){ foreach($c in (Get-ChildItem -LiteralPath $p -Directory -Force -EA SilentlyContinue | Sort-Object Name)){ $o2+=Walk $c.FullName ($d+1) $max } }; $o2 }" ^
  "$o+='=== X:\ (2 Ebenen) ==='; foreach($c in (Get-ChildItem $root -Directory -Force -EA SilentlyContinue | Sort-Object Name)){ $o+=Walk $c.FullName 0 1 }; $o+='';" ^
  "if(Test-Path 'X:\00_Office'){ $o+='=== 00_Office (4 Ebenen, nur Ordner) ==='; $o+=Walk 'X:\00_Office' 0 3; $o+='' }" ^
  "if(Test-Path 'X:\01_Projekte'){ $o+='=== 01_Projekte (Projektordner) ==='; $o+=Walk 'X:\01_Projekte' 0 1; $o+='';" ^
  "  $p=Get-ChildItem 'X:\01_Projekte' -Directory -EA SilentlyContinue | Where-Object Name -match '^\d{4}_\d{2}' | Sort-Object Name -Descending | Select-Object -First 2;" ^
  "  foreach($x in $p){ $o+='=== Beispielprojekt: '+$x.Name+' (3 Ebenen) ==='; $o+=Walk $x.FullName 0 2; $o+='' } }" ^
  "$o+='=== Dateitypen in 01_Projekte (Top 15) ==='; $o+=(Get-ChildItem 'X:\01_Projekte' -File -Recurse -Force -EA SilentlyContinue | Group-Object Extension | Sort-Object Count -Descending | Select-Object -First 15 | ForEach-Object { '  '+$_.Name+'  '+$_.Count });" ^
  "$o | Out-File -Encoding UTF8 '%OUT%'"
echo Fertig: %OUT%
start notepad "%OUT%"
pause
