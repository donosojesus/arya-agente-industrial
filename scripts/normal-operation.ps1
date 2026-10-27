# Retira la falla: las senales vuelven gradualmente a lo normal (no es un reinicio).
. "$PSScriptRoot\_common.ps1"
$result = Invoke-Control 'POST' '/api/demo/normal'
if ($result.Code -ne 200) { Write-ControlFailure $result; exit 1 }
if ($result.Json.mode -eq 'RECOVERY') {
    Write-Host 'FALLA RETIRADA. Los valores vuelven gradualmente; para reiniciar de inmediato use reset-demo.'
} else {
    Write-Host 'No habia una falla activa. La planta sigue en operacion normal.'
}
