# D:\Aether\run.ps1
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Clear-Host

# 读取 .env 文件并写入当前进程环境变量
Get-Content ".env" -Encoding UTF8 | ForEach-Object `
{
    $line = $_.Trim()

    # 跳过空行和注释
    if ($line.Length -eq 0) { return }
    if ($line.StartsWith("#")) { return }

    # 只按第一个 "=" 切分，避免值里有 "=" 被切烂
    $pair = $line.Split("=", 2)
    if ($pair.Count -ne 2) { return }

    $key = $pair[0].Trim()
    $value = $pair[1].Trim()

    # 去掉包裹的引号（"xxx" 或 'xxx'）
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'")))
    {
        $value = $value.Substring(1, $value.Length - 2)
    }

    # 设置到当前进程环境变量（不会污染系统）
    Set-Item -Path ("Env:{0}" -f $key) -Value $value
}

# 构建 DATABASE_URL（如果你的项目就是靠这个读）
if (-not $env:DB_PASSWORD)
{
    Write-Host "❌ .env 里没读到 DB_PASSWORD，请检查 .env 文件" -ForegroundColor Red
    exit 1
}

$env:DATABASE_URL = "postgresql://postgres:$($env:DB_PASSWORD)@localhost:5432/aether"

Write-Host "🚀 启动本地开发服务器..."
Write-Host "📍 后端地址: http://localhost:8084"
Write-Host "🗄️ 数据库: postgresql://postgres:***@localhost:5432/aether"
Write-Host ""

uv run uvicorn src.main:app --reload --port 8084
