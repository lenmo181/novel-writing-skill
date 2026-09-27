param(
    [string]$Destination = "",
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$source = Split-Path -Parent $PSScriptRoot
if (-not $Destination) {
    $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
    $skillName = -join ([char]0x7F51, [char]0x7EDC, [char]0x5C0F, [char]0x8BF4, [char]0x521B, [char]0x4F5C, [char]0x6280, [char]0x80FD)
    $Destination = Join-Path (Join-Path $codexHome "skills") $skillName
}

$items = @("SKILL.md", "README.md", "templates", "tools", "references", "versions")
if (-not $WhatIf) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
}

foreach ($item in $items) {
    $from = Join-Path $source $item
    $to = Join-Path $Destination $item
    if ($WhatIf) {
        Write-Output "[whatif] $from -> $to"
    } else {
        if (Test-Path -LiteralPath $from -PathType Container) {
            New-Item -ItemType Directory -Force -Path $to | Out-Null
            Get-ChildItem -LiteralPath $from -Force |
                Where-Object { $_.Name -ne "__pycache__" -and $_.Extension -notin @(".pyc", ".pyo") } |
                ForEach-Object {
                Copy-Item -LiteralPath $_.FullName -Destination $to -Recurse -Force
            }
        } else {
            Copy-Item -LiteralPath $from -Destination $to -Force
        }
        Write-Output "[sync] $item"
    }
}

if (-not $WhatIf) {
    Write-Output "[done] synchronized to $Destination"
}
