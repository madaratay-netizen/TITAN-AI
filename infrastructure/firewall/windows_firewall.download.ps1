# ADWIN OS — remove ADWIN outbound block (run as Administrator).
Get-NetFirewallRule -DisplayName 'ADWIN-block-*' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Output 'ADWIN outbound block removed (download mode).'
