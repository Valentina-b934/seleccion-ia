# Crea el repositorio Git del proyecto con commits ordenados por tema y lo sube a GitHub.
#
#   powershell -ExecutionPolicy Bypass -File scripts\subir_a_github.ps1 https://github.com/USUARIO/seleccion-ia.git
#
# Ejecútalo dentro de la carpeta seleccion-ia. Los commits quedan con TU nombre y correo de Git.
# El archivo .env (claves) y la carpeta data/ nunca se suben: están en .gitignore.
param([string]$Remoto = "")

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git no está instalado. Descárgalo de https://git-scm.com/download/win, instálalo, cierra y abre VS Code y vuelve a ejecutar este script." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "app\main.py")) {
    Write-Host "Ejecuta el script desde la carpeta seleccion-ia (donde están app, panel, scripts...)." -ForegroundColor Red
    exit 1
}

Paso "Identidad de Git"
$nombre = git config --global user.name
$correo = git config --global user.email
if (-not $nombre) { $nombre = Read-Host "Tu nombre completo"; git config --global user.name "$nombre" }
if (-not $correo) { $correo = Read-Host "El correo de tu cuenta de GitHub"; git config --global user.email "$correo" }
Write-Host "Los commits quedarán como: $nombre <$correo>"

Paso "Repositorio"
if (-not (Test-Path ".git")) { git init -b main | Out-Null; Write-Host "Repositorio creado." } else { Write-Host "El repositorio ya existía." }

git check-ignore -q .env
if ($LASTEXITCODE -ne 0) { Write-Host ".env NO está ignorado: revisa .gitignore antes de seguir." -ForegroundColor Red; exit 1 }
Write-Host "OK: .env, data/ y .venv/ no se subirán."

$grupos = @(
    @{ m = "Configuración del proyecto, dependencias y variables de entorno de ejemplo";
       f = @(".gitignore", ".dockerignore", "requirements.txt", "requirements-dev.txt", "pytest.ini", ".env.example") },
    @{ m = "Motor de automatización en código: flujos de carga, lista, chat, decisión, Telegram y registro (reemplaza n8n)";
       f = @("app/__init__.py", "app/main.py", "app/db.py", "app/errores.py", "app/config.py", "app/services/__init__.py",
             "app/services/carga.py", "app/services/lista.py", "app/services/chat.py", "app/services/pdf.py",
             "app/services/decision.py", "app/services/telegram.py", "app/services/registro.py") },
    @{ m = "IA con LangChain: extracción estructurada, memoria del chat, reintentos y plan B entre modelos gratuitos";
       f = @("app/services/llm.py", "app/services/privacidad.py") },
    @{ m = "Módulo de visión: OCR local, confianza por campo, revisión humana y cola de reintento";
       f = @("app/services/lectura.py", "app/services/vision.py") },
    @{ m = "Tareas programadas: resumen diario por Telegram y reintento de fotos sin IA";
       f = @("app/services/tareas.py") },
    @{ m = "Seguridad: inicio de sesión, roles, auditoría y protección de datos (Ley 1581)";
       f = @("app/seguridad", "app/servidor.py", "docs/POLITICA_DATOS.md") },
    @{ m = "Panel web: carga de PDF y fotos, cámara del celular, candidatos, revisión, asistente y ejecuciones";
       f = @("panel") },
    @{ m = "Pruebas unitarias y de integración";
       f = @("tests") },
    @{ m = "Evaluación del módulo de visión y scripts de diagnóstico";
       f = @("scripts", "evaluacion") },
    @{ m = "Despliegue con Docker y Render, README, documento técnico y guion del video";
       f = @("Dockerfile", "render.yaml", "DESPLIEGUE.md", "README.md", "docs") }
)

Paso "Commits"
foreach ($g in $grupos) {
    $existentes = $g.f | Where-Object { Test-Path $_ }
    if (-not $existentes) { continue }
    git add -- $existentes
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) { git commit -q -m $g.m; Write-Host "  + $($g.m)" }
}
git add -A
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) { git commit -q -m "Ajustes finales"; Write-Host "  + Ajustes finales" }

if (git ls-files | Select-String -SimpleMatch -Pattern ".env" | Where-Object { $_.Line -eq ".env" }) {
    Write-Host ".env quedó en el repositorio: NO hagas push y avísame." -ForegroundColor Red; exit 1
}

Paso "Historial"
git log --oneline

if (-not $Remoto) {
    Write-Host "`nListo en tu computador. Para subirlo: crea el repositorio vacío en GitHub y ejecuta:" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\subir_a_github.ps1 https://github.com/USUARIO/seleccion-ia.git"
    exit 0
}

Paso "Subiendo a GitHub"
git remote remove origin 2>$null
git remote add origin $Remoto
git push -u origin main
if ($LASTEXITCODE -eq 0) {
    Write-Host "`nSubido: $($Remoto -replace '\.git$','')" -ForegroundColor Green
    Write-Host "Ahora cada integrante debe clonar el repositorio y subir al menos un commit propio (ver DESPLIEGUE.md, sección 2)."
} else {
    Write-Host "`nNo se pudo subir. Si pidió iniciar sesión, completa el inicio de sesión en el navegador y vuelve a ejecutar el script." -ForegroundColor Red
}
