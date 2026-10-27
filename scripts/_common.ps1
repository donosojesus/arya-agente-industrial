# Funciones compartidas por los scripts PowerShell de ARYA Industrial Demo.
# Compatible con Windows PowerShell 5.1. No ejecutar directamente.
$ErrorActionPreference = 'Stop'
$script:AryaRoot = Split-Path -Parent $PSScriptRoot
Set-Location $script:AryaRoot
$script:DefaultEnvFile = Join-Path $script:AryaRoot '.env'
$script:EnvFile = if ($env:ARYA_ENV_FILE) { $env:ARYA_ENV_FILE } else { $script:DefaultEnvFile }
$script:AryaImages = @('arya-industrial-demo/plant:0.1.0', 'arya-industrial-demo/plant-view:0.1.0', 'arya-industrial-demo/ot-gateway:0.1.0', 'arya-industrial-demo/cmms:0.1.0', 'arya-industrial-demo/agent:0.1.0', 'arya-industrial-demo/demo-ui:0.1.0')
$script:AryaServices = @('plant', 'plant-view', 'ot-gateway', 'cmms', 'agent', 'demo-ui')
$script:AryaSecrets = @('DEMO_CONTROL_TOKEN', 'CMMS_AGENT_KEY', 'CMMS_APPROVER_TOKEN', 'AGENT_ADMIN_TOKEN')

# Lee una clave de .env sin ejecutar su contenido.
function Get-EnvValue([string]$Key, [string]$Default = '') {
    if (Test-Path $script:EnvFile) {
        $line = Get-Content $script:EnvFile | Where-Object { $_ -like "$Key=*" } | Select-Object -Last 1
        if ($line) {
            $value = $line.Substring($Key.Length + 1).Trim()
            if ($value) { return $value }
        }
    }
    return $Default
}

# Crea .env si falta y genera localmente cualquier secreto ausente o sin definir. No los imprime.
function Initialize-EnvFile {
    if (-not (Test-Path $script:EnvFile)) {
        Copy-Item (Join-Path $script:AryaRoot '.env.example') $script:EnvFile
        Write-Host 'Se creo .env (no se sube a Git).'
    }
    foreach ($key in $script:AryaSecrets) {
        $current = Get-EnvValue $key
        if ((-not $current) -or $current.StartsWith('replace-')) {
            $bytes = New-Object byte[] 32
            [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
            $token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
            $lines = @(Get-Content $script:EnvFile)
            if ($lines | Where-Object { $_ -like "$key=*" }) {
                $lines = $lines | ForEach-Object { if ($_ -like "$key=*") { "$key=$token" } else { $_ } }
            } else {
                $lines += "$key=$token"
            }
            Set-Content -Path $script:EnvFile -Value $lines -Encoding ASCII
            Write-Host "Secreto $key generado localmente en .env (no se muestra)."
        }
    }
}

function Assert-EnvFile {
    if (-not (Test-Path $script:EnvFile)) {
        Write-Host 'No existe .env. Ejecute primero: .\scripts\start-demo.ps1 -Build'
        exit 1
    }
}

# cmd /c evita que la salida de error de docker se convierta en una excepcion de PowerShell 5.1.
function Test-DockerEngine {
    cmd /c 'docker info >nul 2>&1'
    return ($LASTEXITCODE -eq 0)
}

function Assert-DockerEngine {
    if (-not (Test-DockerEngine)) {
        Write-Host "El motor Docker no responde. Abra Docker Desktop, espere a que diga 'Engine running' y reintente."
        exit 1
    }
}

function Test-DockerImage([string]$Image) {
    cmd /c "docker image inspect $Image >nul 2>&1"
    return ($LASTEXITCODE -eq 0)
}

function Invoke-Compose {
    if ($script:EnvFile -eq $script:DefaultEnvFile) { & docker compose @args }
    else { & docker compose --env-file $script:EnvFile @args }
}

function Get-ControlUrl { return "http://127.0.0.1:$(Get-EnvValue 'CONTROL_PORT' '9001')" }
function Get-ScadaUrl { return "http://127.0.0.1:$(Get-EnvValue 'SCADA_PORT' '8080')" }

# Devuelve el codigo HTTP de un GET (0 si no hay respuesta).
function Get-HttpCode([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
        return [int]$response.StatusCode
    } catch {
        $response = $_.Exception.Response
        if ($response) { return [int]$response.StatusCode }
        return 0
    }
}

# Llama a la API local de control con el token de .env. Devuelve @{ Code; Json }.
function Invoke-Control([string]$Method, [string]$Path, [string]$Body = '{}') {
    Assert-EnvFile
    $token = Get-EnvValue 'DEMO_CONTROL_TOKEN'
    if (-not $token) { Write-Host 'DEMO_CONTROL_TOKEN no esta definido en .env'; exit 1 }
    $url = "$(Get-ControlUrl)$Path"
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Method $Method -Uri $url -TimeoutSec 8 `
            -Headers @{ Authorization = "Bearer $token" } -ContentType 'application/json' -Body $Body
        return @{ Code = [int]$response.StatusCode; Json = ($response.Content | ConvertFrom-Json) }
    } catch {
        $response = $_.Exception.Response
        if ($response) { return @{ Code = [int]$response.StatusCode; Json = $null } }
        return @{ Code = 0; Json = $null }
    }
}

function Write-ControlFailure($Result) {
    switch ($Result.Code) {
        401 { Write-Host 'Token rechazado: revise DEMO_CONTROL_TOKEN en .env.' }
        0 { Write-Host "La API de control no responde en $(Get-ControlUrl). Esta arrancada la planta?" }
        default { Write-Host "Respuesta inesperada de la API de control: HTTP $($Result.Code)" }
    }
}
