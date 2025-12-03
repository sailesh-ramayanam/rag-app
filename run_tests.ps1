# RAG Pipeline Test Runner for Windows PowerShell
# Usage:
#   .\run_tests.ps1              - Run all tests
#   .\run_tests.ps1 biography    - Run specific test
#   .\run_tests.ps1 -Build       - Rebuild and run tests

param(
    [switch]$Build,
    [string]$Filter = ""
)

Write-Host "🧪 RAG Pipeline Test Runner" -ForegroundColor Green
Write-Host ""

# Check if required services are running
Write-Host "Checking if backend services are running..." -ForegroundColor Yellow

$appRunning = docker ps --filter "name=vault_app" --filter "status=running" -q
$celeryRunning = docker ps --filter "name=vault_celery_worker" --filter "status=running" -q

if (-not $appRunning) {
    Write-Host "❌ ERROR: vault_app is not running." -ForegroundColor Red
    Write-Host "Please start the backend services first:" -ForegroundColor Yellow
    Write-Host "  docker-compose up -d" -ForegroundColor Cyan
    exit 1
}

if (-not $celeryRunning) {
    Write-Host "❌ ERROR: vault_celery_worker is not running." -ForegroundColor Red
    Write-Host "Please start the backend services first:" -ForegroundColor Yellow
    Write-Host "  docker-compose up -d" -ForegroundColor Cyan
    exit 1
}

Write-Host "✅ Backend services are running." -ForegroundColor Green
Write-Host ""

# Build test container if needed
if ($Build) {
    Write-Host "Building test container..." -ForegroundColor Yellow
    docker-compose -f docker-compose.test.yml build test
}

# Run tests
Write-Host "Running tests..." -ForegroundColor Green
Write-Host ""

if ($Filter) {
    # Run specific test
    docker-compose -f docker-compose.test.yml run --rm test pytest test_rag_pipeline.py -v --tb=short -k $Filter
} else {
    # Run all tests
    docker-compose -f docker-compose.test.yml run --rm test
}

$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "✅ All tests passed!" -ForegroundColor Green
} else {
    Write-Host "❌ Some tests failed." -ForegroundColor Red
}

exit $exitCode
