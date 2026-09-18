param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f-]{36}$')][string]$Receipt)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$credential = Import-Clixml -LiteralPath (Join-Path $root 'data/cloudflare-setup/credentials.clixml')
$headers = @{ Authorization = 'Bearer ' + $credential.GetNetworkCredential().Password }
try {
    $outputDir = Join-Path $root 'data/error-reports'
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    $outputPath = Join-Path $outputDir ($Receipt + '.json')
    $objectKey = [Uri]::EscapeDataString('reports/' + $Receipt + '.json')
    $uri = 'https://api.cloudflare.com/client/v4/accounts/' + $credential.UserName + '/r2/buckets/handwrite-error-reports/objects/' + $objectKey
    Invoke-WebRequest -UseBasicParsing -Uri $uri -Headers $headers -OutFile $outputPath | Out-Null
    Write-Output ('Saved report: ' + $outputPath)
} finally {
    $headers.Clear()
    $credential = $null
}
