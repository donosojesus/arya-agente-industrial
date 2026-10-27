# Verificacion previa de la etapa planta. Declara PLANT READY solo si todo esta correcto.
# No declara lista la demo completa: ARYA (agente) aun no existe.
. "$PSScriptRoot\_common.ps1"
$script:failures = 0
function Write-Ok([string]$Text) { Write-Host "[OK] $Text" }
function Write-Fail([string]$Text) { Write-Host "[FAIL] $Text"; $script:failures++ }

Write-Host 'ARYA Industrial Demo - preflight de la planta (equipo anfitrion)'
if (Test-Path $script:EnvFile) { Write-Ok '.env presente' } else { Write-Fail '.env no existe -> ejecute .\scripts\start-demo.ps1 -Build' }

if (Test-DockerEngine) {
    Write-Ok 'Motor Docker disponible'
} else {
    Write-Fail 'El motor Docker no responde -> abra Docker Desktop'
    Write-Host ''
    Write-Host 'PLANT NOT READY'
    exit 1
}

foreach ($image in $script:AryaImages) {
    if (Test-DockerImage $image) { Write-Ok "Imagen local $image" } else { Write-Fail "Falta la imagen local $image" }
}

foreach ($service in $script:AryaServices) {
    $health = 'missing'
    $cid = (Invoke-Compose ps -q $service 2>$null | Select-Object -First 1)
    if ($cid) {
        $health = (& docker inspect -f '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $cid.Trim())
    }
    if ($health -eq 'running/healthy') { Write-Ok "Contenedor $service en marcha y healthy" } else { Write-Fail "Contenedor ${service}: $health" }
}

$code = Get-HttpCode "$(Get-ScadaUrl)/healthz"
if ($code -eq 200) { Write-Ok "SCADA accesible desde el notebook en $(Get-ScadaUrl)" } else { Write-Fail "SCADA no accesible en $(Get-ScadaUrl) (HTTP $code)" }
$code = Get-HttpCode "$(Get-ControlUrl)/api/demo/state"
if ($code -eq 401) { Write-Ok 'API de control accesible en loopback y protegida (401 sin token)' } else { Write-Fail "API de control en $(Get-ControlUrl): HTTP $code (se esperaba 401 sin token)" }

$gw = "http://127.0.0.1:$(Get-EnvValue 'GATEWAY_PORT' '8081')"
$cmms = "http://127.0.0.1:$(Get-EnvValue 'CMMS_PORT' '8082')"
if ((Get-HttpCode "$gw/healthz") -eq 200) { Write-Ok 'OT Gateway sano: recibe OPC UA y escribe en el historian' } else { Write-Fail "OT Gateway en $gw no esta sano" }
if ((Get-HttpCode "$cmms/api/v1/work-orders/WO-2026-0142") -eq 200) { Write-Ok 'CMMS: ordenes historicas disponibles' } else { Write-Fail "CMMS en $cmms no devuelve las ordenes historicas" }

Write-Host ''
Invoke-Compose exec -T plant python -m arya_plant.preflight --checks-only
if ($LASTEXITCODE -ne 0) { $script:failures++ }

Write-Host ''
if ($script:failures -eq 0) {
    Write-Host 'PLANT READY'
    Write-Host 'Alcance: planta, OPC UA, pantalla, historian, gateway y CMMS. ARYA (agente) aun no esta implementado.'
} else {
    Write-Host 'PLANT NOT READY'
    exit 1
}
