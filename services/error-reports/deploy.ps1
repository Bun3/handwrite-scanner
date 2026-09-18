$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$credential = Import-Clixml -LiteralPath (Join-Path $root 'data/cloudflare-setup/credentials.clixml')
try {
    $env:CLOUDFLARE_ACCOUNT_ID = $credential.UserName
    $env:CLOUDFLARE_API_TOKEN = $credential.GetNetworkCredential().Password
    & (Join-Path $root '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'deploy.py')
    if ($LASTEXITCODE -ne 0) { throw 'Report server deployment failed.' }
} finally {
    Remove-Item Env:CLOUDFLARE_ACCOUNT_ID -ErrorAction SilentlyContinue
    Remove-Item Env:CLOUDFLARE_API_TOKEN -ErrorAction SilentlyContinue
    $credential = $null
}
