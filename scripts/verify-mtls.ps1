param(
    [string]$CertsDir = "certs",
    [string]$DeweyHost = "localhost",
    [int]$DeweyPort = 50053,
    [switch]$SkipHandshake
)

$ErrorActionPreference = "Stop"

function Invoke-External {
    param(
        [string]$Command,
        [string[]]$Arguments,
        [string]$FailureMessage
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

function Test-RequiredFile {
    param([string]$Path)

    if (-not (Test-Path -Path $Path -PathType Leaf)) {
        throw "Missing required file: $Path"
    }
}

if (-not (Get-Command openssl -ErrorAction SilentlyContinue)) {
    throw "OpenSSL is required. Install OpenSSL and ensure 'openssl' is on PATH."
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$certsRoot = Join-Path $repoRoot $CertsDir

$clientsCaCert = Join-Path $certsRoot "ca/clients-ca.crt"
$deweyServerCaCert = Join-Path $certsRoot "ca/dewey-server-ca.crt"
$deweyServerCert = Join-Path $certsRoot "dewey/server.crt"
$callerClientCert = Join-Path $certsRoot "clients/caller.crt"
$callerClientKey = Join-Path $certsRoot "clients/caller.key"

$requiredFiles = @(
    $clientsCaCert,
    $deweyServerCaCert,
    $deweyServerCert,
    $callerClientCert,
    $callerClientKey
)

foreach ($path in $requiredFiles) {
    Test-RequiredFile -Path $path
}

Write-Host "[1/3] Verifying certificate trust chains..."
Invoke-External -Command "openssl" -Arguments @("verify", "-CAfile", $deweyServerCaCert, $deweyServerCert) -FailureMessage "Dewey server cert failed CA validation"
Invoke-External -Command "openssl" -Arguments @("verify", "-CAfile", $clientsCaCert, $callerClientCert) -FailureMessage "Caller client cert failed Clients CA validation"

if ($SkipHandshake) {
    Write-Host "[2/3] Handshake checks skipped (--SkipHandshake)."
    Write-Host "mTLS certificate integrity checks passed."
    exit 0
}

Write-Host "[2/3] Checking Dewey inbound mTLS handshake..."
Invoke-External -Command "openssl" -Arguments @(
    "s_client",
    "-connect", "$DeweyHost`:$DeweyPort",
    "-CAfile", $deweyServerCaCert,
    "-cert", $callerClientCert,
    "-key", $callerClientKey,
    "-verify_return_error",
    "-brief"
) -FailureMessage "Failed mTLS handshake to Dewey at $DeweyHost:$DeweyPort"

Write-Host "[3/3] mTLS verification completed successfully."
