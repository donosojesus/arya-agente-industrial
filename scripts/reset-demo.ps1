# Reinicia la simulacion al estado inicial con un nuevo ensayo (run_id).
. "$PSScriptRoot\_common.ps1"
$result = Invoke-Control 'POST' '/api/demo/reset'
if ($result.Code -eq 200) { Write-Host "DEMO REINICIADA. Nuevo ensayo: $($result.Json.run_id)." }
else { Write-ControlFailure $result; exit 1 }
