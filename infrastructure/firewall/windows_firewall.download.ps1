# TITAN AI — remove TITAN outbound block (run as Administrator).
Get-NetFirewallRule -DisplayName 'TITAN-block-*' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Output 'TITAN outbound block removed (download mode).'
