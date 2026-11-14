# ADWIN OS — block outbound for the app (run as Administrator).
# Blocks only ADWIN's own executables, not the whole system.
$app = 'C:\ADWIN-OS'
Get-ChildItem -Path $app -Recurse -Include *.exe | ForEach-Object {
  New-NetFirewallRule -DisplayName "ADWIN-block-$($_.Name)" -Direction Outbound -Program $_.FullName -Action Block -Profile Any -ErrorAction SilentlyContinue | Out-Null
}
Write-Output 'ADWIN outbound blocked. Remove with the download-mode script.'
