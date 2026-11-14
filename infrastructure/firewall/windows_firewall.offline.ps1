# TITAN AI — block outbound for the app (run as Administrator).
# Blocks only TITAN's own executables, not the whole system.
$app = 'C:\TITAN-AI'
Get-ChildItem -Path $app -Recurse -Include *.exe | ForEach-Object {
  New-NetFirewallRule -DisplayName "TITAN-block-$($_.Name)" -Direction Outbound -Program $_.FullName -Action Block -Profile Any -ErrorAction SilentlyContinue | Out-Null
}
Write-Output 'TITAN outbound blocked. Remove with the download-mode script.'
