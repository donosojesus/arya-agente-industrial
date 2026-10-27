# Detiene y retira SOLO los contenedores y la red del proyecto arya-industrial-demo.
# No borra imagenes ni toca recursos de otros proyectos.
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile
Assert-DockerEngine
Invoke-Compose down
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host 'Planta detenida. Las imagenes locales se conservan para el arranque offline.'
