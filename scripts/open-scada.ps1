# Abre el SCADA en el navegador con los controles del presentador habilitados.
# El token viaja en el fragmento de la URL (#token=...), que el navegador no envia al servidor.
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile
Start-Process "$(Get-ScadaUrl)/#token=$(Get-EnvValue 'DEMO_CONTROL_TOKEN')"
Write-Host "SCADA abierto en $(Get-ScadaUrl)"
