# Copies the built single-file app to the Desktop as Savetogrow.exe (and removes any old shortcut).
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$exe = Join-Path $root "dist\Savetogrow.exe"
if (-not (Test-Path $exe)) { Write-Error "Build the exe first: $exe not found"; exit 1 }
$desktop = [Environment]::GetFolderPath("Desktop")
$target = Join-Path $desktop "Savetogrow.exe"
Copy-Item -Path $exe -Destination $target -Force
$link = Join-Path $desktop "Savetogrow.lnk"
if (Test-Path $link) { Remove-Item $link -Force }
Write-Host "Installed: $target"
