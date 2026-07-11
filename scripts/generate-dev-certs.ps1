param(
    [string]$CertsDir = "certs",
    [int]$DaysValid = 30,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Invoke-OpenSsl {
    param([string[]]$Arguments)
    & openssl @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "OpenSSL command failed: openssl $($Arguments -join ' ')"
    }
}

function New-Ca {
    param(
        [string]$CommonName,
        [string]$KeyPath,
        [string]$CertPath,
        [int]$Days
    )

    Invoke-OpenSsl @(
        "req", "-x509", "-new", "-newkey", "rsa:4096", "-sha256", "-days", "$Days", "-nodes",
        "-keyout", $KeyPath,
        "-out", $CertPath,
        "-subj", "/CN=$CommonName"
    )
}

function New-SignedCert {
    param(
        [string]$CommonName,
        [string]$KeyPath,
        [string]$CsrPath,
        [string]$CertPath,
        [string]$CaKeyPath,
        [string]$CaCertPath,
        [string]$ExtFilePath,
        [string]$ExtendedKeyUsage,
        [string[]]$Sans,
        [int]$Days
    )

    $sanLines = @()
    for ($i = 0; $i -lt $Sans.Count; $i++) {
        $sanLines += "DNS.$($i + 1) = $($Sans[$i])"
    }

    $extContent = @"
[req]
distinguished_name = req_distinguished_name
req_extensions = req_ext
prompt = no

[req_distinguished_name]
CN = $CommonName

[req_ext]
subjectAltName = @alt_names

[alt_names]
$($sanLines -join "`n")

[v3_ext]
subjectAltName = @alt_names
extendedKeyUsage = $ExtendedKeyUsage
"@

    Set-Content -Path $ExtFilePath -Value $extContent -Encoding ASCII

    Invoke-OpenSsl @(
        "req", "-new", "-newkey", "rsa:4096", "-nodes",
        "-keyout", $KeyPath,
        "-out", $CsrPath,
        "-config", $ExtFilePath
    )

    Invoke-OpenSsl @(
        "x509", "-req",
        "-in", $CsrPath,
        "-CA", $CaCertPath,
        "-CAkey", $CaKeyPath,
        "-CAcreateserial",
        "-out", $CertPath,
        "-days", "$Days",
        "-sha256",
        "-extfile", $ExtFilePath,
        "-extensions", "v3_ext"
    )
}

if (-not (Get-Command openssl -ErrorAction SilentlyContinue)) {
    throw "OpenSSL is required. Install OpenSSL and ensure 'openssl' is on PATH."
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$certsRoot = Join-Path $repoRoot $CertsDir
$caDir = Join-Path $certsRoot "ca"
$deweyDir = Join-Path $certsRoot "dewey"
$clientsDir = Join-Path $certsRoot "clients"
$tmpDir = Join-Path $certsRoot "tmp"

New-Item -ItemType Directory -Path $caDir -Force | Out-Null
New-Item -ItemType Directory -Path $deweyDir -Force | Out-Null
New-Item -ItemType Directory -Path $clientsDir -Force | Out-Null
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

if ($Force) {
    Get-ChildItem -Path $certsRoot -Recurse -Include *.crt,*.key,*.csr,*.srl,*.cnf | Remove-Item -Force -ErrorAction SilentlyContinue
}

$clientsCaKey = Join-Path $caDir "clients-ca.key"
$clientsCaCert = Join-Path $caDir "clients-ca.crt"
$serverCaKey = Join-Path $caDir "dewey-server-ca.key"
$serverCaCert = Join-Path $caDir "dewey-server-ca.crt"

New-Ca -CommonName "Dewey Dev Clients CA" -KeyPath $clientsCaKey -CertPath $clientsCaCert -Days $DaysValid
New-Ca -CommonName "Dewey Dev Server CA" -KeyPath $serverCaKey -CertPath $serverCaCert -Days $DaysValid

$deweyServerExt = Join-Path $tmpDir "dewey-server.cnf"
$deweyServerCertParams = @{
    CommonName = "dewey"
    KeyPath = (Join-Path $deweyDir "server.key")
    CsrPath = (Join-Path $tmpDir "dewey-server.csr")
    CertPath = (Join-Path $deweyDir "server.crt")
    CaKeyPath = $serverCaKey
    CaCertPath = $serverCaCert
    ExtFilePath = $deweyServerExt
    ExtendedKeyUsage = "serverAuth"
    Sans = @("dewey", "localhost", "host.docker.internal")
    Days = $DaysValid
}
New-SignedCert @deweyServerCertParams

$callerClientExt = Join-Path $tmpDir "caller-client.cnf"
$callerClientCertParams = @{
    CommonName = "caller-client"
    KeyPath = (Join-Path $clientsDir "caller.key")
    CsrPath = (Join-Path $tmpDir "caller-client.csr")
    CertPath = (Join-Path $clientsDir "caller.crt")
    CaKeyPath = $clientsCaKey
    CaCertPath = $clientsCaCert
    ExtFilePath = $callerClientExt
    ExtendedKeyUsage = "clientAuth"
    Sans = @("caller-client")
    Days = $DaysValid
}
New-SignedCert @callerClientCertParams

Write-Host "Dev certificates generated under: $certsRoot"
Write-Host "Use docker-compose.mtls.yml to run Dewey in mTLS mode."
