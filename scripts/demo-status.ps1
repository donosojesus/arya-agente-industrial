# Muestra el estado de los contenedores y un resumen de la planta.
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile
Assert-DockerEngine
Invoke-Compose ps
Write-Host ''
Invoke-Compose exec -T plant python -m arya_plant.status
exit $LASTEXITCODE
