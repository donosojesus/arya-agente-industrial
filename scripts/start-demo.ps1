# Arranca la planta ARYA. Con -Build prepara las imagenes (requiere Internet la primera vez).
# Sin -Build es un arranque OFFLINE: solo usa imagenes locales, no construye ni descarga.
param([switch]$Build)
. "$PSScriptRoot\_common.ps1"

Initialize-EnvFile

Assert-DockerEngine

if ($Build) {
    Write-Host 'Preparacion (con Internet): construyendo imagenes...'
    Invoke-Compose build --pull
    if ($LASTEXITCODE -ne 0) { Write-Host 'La construccion de imagenes fallo.'; exit 1 }
} else {
    foreach ($image in $script:AryaImages) {
        if (-not (Test-DockerImage $image)) {
            Write-Host "Falta la imagen local $image."
            Write-Host 'Ejecute una vez, con Internet: .\scripts\start-demo.ps1 -Build'
            exit 1
        }
    }
}

Write-Host 'Arrancando con imagenes locales (sin construir ni descargar)...'
Invoke-Compose up -d --no-build --pull never --wait --wait-timeout 120
if ($LASTEXITCODE -ne 0) { Write-Host 'El arranque fallo. Revise: .\scripts\demo-status.ps1'; exit 1 }
Write-Host ''
Write-Host 'Planta en marcha.'
Write-Host "  SCADA:      $(Get-ScadaUrl)   (para abrirlo con los controles habilitados: .\scripts\open-scada.ps1)"
Write-Host '  Verificar:  .\scripts\preflight.ps1'
