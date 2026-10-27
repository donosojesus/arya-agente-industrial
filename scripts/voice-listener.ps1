# ARYA - escucha de voz local en Windows (sin Internet).
# Usa el reconocedor de voz en espanol instalado en Windows y entrega el texto a la pantalla de la demo
# por http://localhost:8095. Prioriza las frases de data\voice-phrases.txt; lo demas lo transcribe libremente.
#   Servicio:  powershell -ExecutionPolicy Bypass -File scripts\voice-listener.ps1
#   Prueba:    powershell -ExecutionPolicy Bypass -File scripts\voice-listener.ps1 -TestPhrase "cual es tu diagnostico"
#              (sintetiza la frase con una voz de Windows y la reconoce, sin microfono)
param([int]$Port = 8095, [string]$TestPhrase = '')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$root = Split-Path -Parent $PSScriptRoot

$info = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() | Where-Object { $_.Culture.Name -like 'es-*' } | Select-Object -First 1
if (-not $info) { Write-Host 'No hay un reconocedor de voz en espanol instalado en Windows.'; exit 1 }
$engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine($info)

$phrases = @(Get-Content -Encoding UTF8 (Join-Path $root 'data\voice-phrases.txt') | Where-Object { $_.Trim() -and -not $_.StartsWith('#') } | ForEach-Object { $_.Trim() })
$choices = New-Object System.Speech.Recognition.Choices
$choices.Add([string[]]$phrases)
$builder = New-Object System.Speech.Recognition.GrammarBuilder
$builder.Culture = $info.Culture
$builder.Append($choices)
$script_grammar = New-Object System.Speech.Recognition.Grammar($builder)
$script_grammar.Name = 'guion'; $script_grammar.Weight = 1.0; $script_grammar.Priority = 10
$engine.LoadGrammar($script_grammar)
$dictation = New-Object System.Speech.Recognition.DictationGrammar
$dictation.Name = 'dictado'; $dictation.Weight = 0.4
$engine.LoadGrammar($dictation)
$engine.InitialSilenceTimeout = [TimeSpan]::FromSeconds(6)
$engine.EndSilenceTimeout = [TimeSpan]::FromMilliseconds(900)
$engine.BabbleTimeout = [TimeSpan]::FromSeconds(12)

function Get-Result($result) {
    if (-not $result) { return @{ ok = $true; text = ''; confidence = 0; source = 'none' } }
    return @{ ok = $true; text = $result.Text; confidence = [math]::Round($result.Confidence, 2); source = $result.Grammar.Name }
}

if ($TestPhrase) {
    $wav = Join-Path $env:TEMP 'arya-voice-test.wav'
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $voice = $synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es-*' } | Select-Object -First 1
    if ($voice) { $synth.SelectVoice($voice.VoiceInfo.Name) }
    $synth.SetOutputToWaveFile($wav); $synth.Speak($TestPhrase); $synth.Dispose()
    $engine.SetInputToWaveFile($wav)
    $r = Get-Result ($engine.Recognize())
    Write-Host ("dicho: '" + $TestPhrase + "' | entendido: '" + $r.text + "' | confianza " + $r.confidence + " | " + $r.source)
    exit 0
}

$inputName = 'microfono'
try { $engine.SetInputToDefaultAudioDevice() } catch { $inputName = 'sin microfono'; Write-Host 'No se encontro un microfono.' }

$allowed = @('http://127.0.0.1:8090', 'http://localhost:8090')
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
$listener.Start()
Write-Host "Escucha de voz lista en http://localhost:$Port (reconocedor $($info.Culture.Name), $($phrases.Count) frases del guion)"

while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    $req = $ctx.Request; $res = $ctx.Response
    $origin = $req.Headers['Origin']
    if ($origin -and ($allowed -contains $origin)) {
        $res.Headers.Add('Access-Control-Allow-Origin', $origin)
        $res.Headers.Add('Access-Control-Allow-Methods', 'GET, POST')
        $res.Headers.Add('Access-Control-Allow-Headers', 'Content-Type')
    }
    $body = $null
    try {
        if ($req.HttpMethod -eq 'OPTIONS') { $res.StatusCode = 204 }
        elseif ($req.Url.AbsolutePath -eq '/health') {
            $body = @{ ok = ($inputName -eq 'microfono'); recognizer = $info.Culture.Name; input = $inputName; phrases = $phrases.Count }
        }
        elseif ($req.Url.AbsolutePath -eq '/listen' -and $req.HttpMethod -eq 'POST') {
            if ($origin -and -not ($allowed -contains $origin)) { $res.StatusCode = 403; $body = @{ ok = $false; error = 'forbidden' } }
            elseif ($inputName -ne 'microfono') { $res.StatusCode = 503; $body = @{ ok = $false; error = 'sin microfono' } }
            else { $body = Get-Result ($engine.Recognize([TimeSpan]::FromSeconds(14))) }
        }
        else { $res.StatusCode = 404; $body = @{ ok = $false; error = 'not found' } }
    } catch {
        $res.StatusCode = 500; $body = @{ ok = $false; error = $_.Exception.Message }
    }
    if ($body) {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Compress))
        $res.ContentType = 'application/json; charset=utf-8'
        $res.OutputStream.Write($bytes, 0, $bytes.Length)
    }
    $res.Close()
}
