# Inyecta la falla de demostracion. Uso: inject-fault.ps1 [-DurationSeconds 180]
param([ValidateRange(30, 900)][double]$DurationSeconds)
. "$PSScriptRoot\_common.ps1"
$body = '{}'
if ($PSBoundParameters.ContainsKey('DurationSeconds')) {
    $body = '{"duration_seconds": ' + $DurationSeconds.ToString([System.Globalization.CultureInfo]::InvariantCulture) + '}'
}
$result = Invoke-Control 'POST' '/api/demo/inject-fault' $body
switch ($result.Code) {
    200 { Write-Host "FALLA INYECTADA. Ensayo $($result.Json.run_id), duracion $($result.Json.fault_duration_s) s." }
    409 { Write-Host 'Ya hay una falla activa en este ensayo. Use reset-demo para comenzar de nuevo.'; exit 1 }
    422 { Write-Host 'Duracion no valida: debe estar entre 30 y 900 segundos.'; exit 1 }
    default { Write-ControlFailure $result; exit 1 }
}
