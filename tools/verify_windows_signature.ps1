param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$signature = Get-AuthenticodeSignature -FilePath $Path
if ($signature.Status -ne 'Valid') {
    Write-Error "Signature validation failed for $Path with status $($signature.Status)."
    exit 1
}

Write-Output "Signature validation pass: $Path"
