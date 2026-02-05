# .env ファイルを読み込んで環境変数として設定

if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()

            # コメント行をスキップ
            if (-not $name.StartsWith('#')) {
                [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
            }
        }
    }

    Write-Host "✅ Environment variables loaded from .env" -ForegroundColor Green
    Write-Host "   GITHUB_TOKEN: $($env:GITHUB_TOKEN.Substring(0, 10))... (hidden)"
    Write-Host "   DEV_PORT: $env:DEV_PORT"
    Write-Host "   PROD_PORT: $env:PROD_PORT"
} else {
    Write-Host "❌ .env file not found" -ForegroundColor Red
    Write-Host "   Copy .env.example to .env and fill in your values"
    exit 1
}
