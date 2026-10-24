# Instalador do freecad-print-mcp para Windows.
# Uso (PowerShell ou Win+R):
#   powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/drmarcelofrodrigues-ctrl/freecad-print-mcp/main/install.ps1 | iex"
#
# O que faz: baixa o repositório em Documentos\freecad-print-mcp, instala o pacote no Python,
# localiza o FreeCADCmd.exe e adiciona o servidor "freecad-print" ao claude_desktop_config.json.

# "Continue": programas nativos (python, pip, git) escrevem avisos em stderr, e com "Stop" isso viraria erro fatal.
$ErrorActionPreference = "Continue"
$Repo = "drmarcelofrodrigues-ctrl/freecad-print-mcp"
$Docs = [Environment]::GetFolderPath("MyDocuments")
$Dest = Join-Path $Docs "freecad-print-mcp"
$OutDir = Join-Path $Docs "Impressão 3D\freecad-mcp"
$Log = Join-Path $env:TEMP "freecad-print-mcp-install.log"
Start-Transcript -Path $Log -Force | Out-Null

function Say($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

try {
    # ---------- Python ----------
    Say "Procurando Python 3.10+"
    # Ignora o Python embutido do FreeCAD e o atalho da Microsoft Store (WindowsApps)
    function Probe-Python($exe, [string[]]$pre) {
        try {
            $out = & $exe @pre -c "import sys;print(sys.executable+'|%d.%d'%sys.version_info[:2])" 2>&1 | Where-Object { $_ -is [string] } | Select-Object -Last 1
            if (-not $out -or $out -notmatch '\|') { return $null }
            $exePath, $ver = $out.Trim().Split('|')
            if ($exePath -match 'FreeCAD|WindowsApps') { return $null }
            if ([version]$ver -lt [version]"3.10") { return $null }
            return $exePath
        } catch { return $null }
    }
    $py = $null
    $pyl = Get-Command py -ErrorAction SilentlyContinue
    if ($pyl) { $py = Probe-Python $pyl.Source @("-3") }
    if (-not $py) {
        foreach ($c in (Get-Command python -All -ErrorAction SilentlyContinue)) {
            $py = Probe-Python $c.Source @()
            if ($py) { break }
        }
    }
    if (-not $py) {
        Say "Python do sistema não encontrado — instalando via winget (Python 3.12)"
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
        Refresh-Path
        $pyl = Get-Command py -ErrorAction SilentlyContinue
        if ($pyl) { $py = Probe-Python $pyl.Source @("-3") }
        if (-not $py) { throw "Python não ficou disponível após a instalação; abra um novo PowerShell e rode o instalador de novo." }
    }
    Say "Python: $py"

    # ---------- Código ----------
    if (Test-Path (Join-Path $Dest ".git")) {
        Say "Repositório já existe em $Dest — atualizando (git pull)"
        git -C $Dest pull --ff-only
    } elseif (Get-Command git -ErrorAction SilentlyContinue) {
        Say "Clonando com git para $Dest"
        git clone "https://github.com/$Repo" $Dest
    } else {
        Say "git não encontrado — baixando o zip"
        $zip = Join-Path $env:TEMP "freecad-print-mcp.zip"
        Invoke-WebRequest "https://github.com/$Repo/archive/refs/heads/main.zip" -OutFile $zip
        $tmp = Join-Path $env:TEMP "freecad-print-mcp-unzip"
        if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
        Expand-Archive $zip $tmp
        if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force }
        Move-Item (Join-Path $tmp "freecad-print-mcp-main") $Dest
    }

    # ---------- pip ----------
    Say "Instalando o pacote (pip install -e .)"
    & $py -m pip install --upgrade pip --quiet 2>&1 | Out-Host
    & $py -m pip install -e $Dest --quiet 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "pip install falhou (código $LASTEXITCODE)" }

    # ---------- FreeCAD ----------
    Say "Procurando FreeCADCmd.exe"
    $fc = Get-ChildItem @("$env:ProgramFiles\FreeCAD*\bin\FreeCADCmd.exe",
                         "${env:ProgramFiles(x86)}\FreeCAD*\bin\FreeCADCmd.exe",
                         "$env:LOCALAPPDATA\Programs\FreeCAD*\bin\FreeCADCmd.exe") -ErrorAction SilentlyContinue |
          Sort-Object FullName -Descending | Select-Object -First 1
    if ($fc) { Say "FreeCAD: $($fc.FullName)" } else { Write-Warning "FreeCADCmd.exe não encontrado. Instale o FreeCAD 1.x e rode este instalador de novo (ou defina FREECAD_CMD no config)." }

    # ---------- Claude Desktop ----------
    $cfgPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    Say "Configurando $cfgPath"
    # Compatível com Windows PowerShell 5.1 (sem -AsHashtable); grava UTF-8 sem BOM
    $cfg = [pscustomobject]@{}
    if (Test-Path $cfgPath) {
        Copy-Item $cfgPath "$cfgPath.bak" -Force
        $raw = (Get-Content $cfgPath -Raw) -replace "^﻿", ""
        if ($raw.Trim()) { $cfg = $raw | ConvertFrom-Json }
    } else {
        New-Item -ItemType Directory -Force (Split-Path $cfgPath) | Out-Null
    }
    if (-not $cfg.PSObject.Properties["mcpServers"]) {
        $cfg | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([pscustomobject]@{})
    }
    $envBlock = [ordered]@{ "FCMCP_OUTPUT_DIR" = $OutDir }
    if ($fc) { $envBlock["FREECAD_CMD"] = $fc.FullName }
    $server = [pscustomobject]@{
        command = $py
        args    = @("-m", "freecad_print_mcp.server")
        env     = [pscustomobject]$envBlock
    }
    if ($cfg.mcpServers.PSObject.Properties["freecad-print"]) {
        $cfg.mcpServers."freecad-print" = $server
    } else {
        $cfg.mcpServers | Add-Member -NotePropertyName "freecad-print" -NotePropertyValue $server
    }
    $json = $cfg | ConvertTo-Json -Depth 10
    [IO.File]::WriteAllText($cfgPath, $json, (New-Object Text.UTF8Encoding $false))
    New-Item -ItemType Directory -Force $OutDir | Out-Null

    # ---------- Teste ----------
    Say "Testando o servidor"
    $env:FCMCP_OUTPUT_DIR = $OutDir
    if ($fc) { $env:FREECAD_CMD = $fc.FullName }
    & $py -c "from freecad_print_mcp import server; print(server.freecad_status())"

    Write-Host ""
    Write-Host "PRONTO. Feche o Claude Desktop pela bandeja do sistema e abra de novo; depois peça: 'rode o freecad_selftest'." -ForegroundColor Green
    Write-Host "Código em: $Dest   |   Saídas em: $OutDir   |   Log: $Log"
}
catch {
    Write-Host ""
    Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Log completo em $Log"
}
finally {
    Stop-Transcript | Out-Null
}
Write-Host ""
Read-Host "Pressione Enter para fechar"
