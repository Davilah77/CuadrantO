import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from core.backup import create_database_backup
from core.paths import APP_DIR
from core.version import __version__


# GitHub mantiene redirecciones cuando cambia el nombre del repositorio. Usar
# esta ruta histórica permite actualizar instalaciones anteriores al cambio.
GITHUB_REPOSITORY = "Davilah77/CuadrantO"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases?per_page=20"
RELEASES_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases"
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    tag: str
    title: str
    notes: str
    page_url: str
    asset_name: str
    download_url: str
    digest: str


def version_key(value: str):
    match = _VERSION_RE.match(value.strip())
    if not match:
        return None
    major, minor, patch, prerelease = match.groups()
    if prerelease is None:
        suffix = (1, ())
    else:
        tokens = tuple((0, int(token)) if token.isdigit() else (1, token.lower()) for token in prerelease.split("."))
        suffix = (0, tokens)
    return int(major), int(minor), int(patch), suffix


def is_newer(candidate: str, current: str = __version__) -> bool:
    candidate_key = version_key(candidate)
    current_key = version_key(current)
    return bool(candidate_key and current_key and candidate_key > current_key)


def _asset_suffix() -> str:
    machine = platform.machine().lower()
    if machine not in {"amd64", "x86_64"}:
        raise UpdateError("Las actualizaciones automáticas todavía solo están disponibles para sistemas x64.")
    if sys.platform == "win32":
        return "-windows-x64.zip"
    if sys.platform.startswith("linux"):
        return "-linux-x64.tar.gz"
    raise UpdateError("Este sistema todavía no admite actualizaciones automáticas.")


def check_for_update(include_prereleases=True, timeout=4) -> UpdateInfo | None:
    request = urllib.request.Request(
        RELEASES_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"CuadrantO/{__version__}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            releases = json.load(response)
    except Exception as exc:
        raise UpdateError("No se ha podido conectar con GitHub.") from exc
    suffix = _asset_suffix()
    candidates = []
    for release in releases:
        if release.get("draft") or (release.get("prerelease") and not include_prereleases):
            continue
        tag = str(release.get("tag_name") or "")
        if not is_newer(tag):
            continue
        asset = next((item for item in release.get("assets", []) if str(item.get("name", "")).endswith(suffix)), None)
        if asset:
            candidates.append((version_key(tag), release, asset))
    if not candidates:
        return None
    _key, release, asset = max(candidates, key=lambda item: item[0])
    tag = str(release["tag_name"])
    return UpdateInfo(
        version=tag.removeprefix("v"), tag=tag,
        title=str(release.get("name") or tag), notes=str(release.get("body") or ""),
        page_url=str(release.get("html_url") or RELEASES_URL), asset_name=str(asset["name"]),
        download_url=str(asset["browser_download_url"]), digest=str(asset.get("digest") or ""),
    )


def _safe_target(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if root.resolve() not in target.parents:
        raise UpdateError("El paquete de actualización contiene una ruta no válida.")
    return target


def download_and_stage(info: UpdateInfo) -> Path:
    if not getattr(sys, "frozen", False):
        raise UpdateError("La instalación automática solo está disponible en la versión portable.")
    update_root = APP_DIR / ".updates" / info.version
    if update_root.exists():
        shutil.rmtree(update_root)
    stage = update_root / "nuevo"
    stage.mkdir(parents=True)
    archive = update_root / info.asset_name
    request = urllib.request.Request(info.download_url, headers={"User-Agent": f"CuadrantO/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
    except Exception as exc:
        raise UpdateError("No se pudo descargar la actualización.") from exc
    expected = info.digest.removeprefix("sha256:").lower()
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if not expected or actual != expected:
        raise UpdateError("No se pudo verificar la integridad de la actualización.")
    executable_name = "CuadrantO.exe" if sys.platform == "win32" else "CuadrantO"
    try:
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as package:
                member = next(item for item in package.infolist() if Path(item.filename).name == executable_name)
                target = _safe_target(stage, executable_name)
                with package.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        else:
            with tarfile.open(archive, "r:gz") as package:
                member = next(item for item in package.getmembers() if Path(item.name).name == executable_name and item.isfile())
                target = _safe_target(stage, executable_name)
                source = package.extractfile(member)
                if source is None:
                    raise UpdateError("No se encontró el ejecutable en el paquete.")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o755)
    except (OSError, KeyError, StopIteration, zipfile.BadZipFile, tarfile.TarError) as exc:
        raise UpdateError("El paquete de actualización no es válido.") from exc
    create_database_backup(reason="antes_actualizar")
    return target


def launch_installer(staged_executable: Path) -> None:
    current = Path(sys.executable).resolve()
    helper_root = staged_executable.parent.parent
    if sys.platform == "win32":
        script = helper_root / "instalar_actualizacion.ps1"
        script.write_text(
            "param([int]$WaitProcessId,[string]$Source,[string]$Target,[string]$WorkDir)\n"
            "while (Get-Process -Id $WaitProcessId -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 300 }\n"
            "$backup=\"$Target.anterior\"\n$replacement=\"$Target.nuevo\"\n$ok=$false\n"
            "for($i=0;$i -lt 20;$i++){try{Copy-Item -LiteralPath $Source -Destination $replacement -Force;"
            "if(!(Test-Path -LiteralPath $Target)){throw 'No se encuentra el ejecutable actual'};"
            "if(Test-Path -LiteralPath $backup){Remove-Item -LiteralPath $backup -Force};Move-Item -LiteralPath $Target -Destination $backup -Force;"
            "try{Move-Item -LiteralPath $replacement -Destination $Target -Force}catch{Move-Item -LiteralPath $backup -Destination $Target -Force;throw};"
            "$ok=$true;break}catch{if(!(Test-Path -LiteralPath $Target) -and (Test-Path -LiteralPath $backup)){Move-Item -LiteralPath $backup -Destination $Target -Force};Start-Sleep -Milliseconds 500}}\n"
            "if($ok){try{Start-Process -FilePath $Target -WorkingDirectory $WorkDir}catch{"
            "if(Test-Path -LiteralPath $Target){Remove-Item -LiteralPath $Target -Force};Move-Item -LiteralPath $backup -Destination $Target -Force;"
            "Start-Process -FilePath $Target -WorkingDirectory $WorkDir}}\n",
            encoding="utf-8",
        )
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
             str(os.getpid()), str(staged_executable), str(current), str(APP_DIR)],
            creationflags=creation_flags,
        )
    else:
        script = helper_root / "instalar_actualizacion.sh"
        script.write_text(
            "#!/bin/sh\npid=\"$1\"\nsource_file=\"$2\"\ntarget=\"$3\"\nworkdir=\"$4\"\n"
            "while kill -0 \"$pid\" 2>/dev/null; do sleep 1; done\n"
            "backup=\"$target.anterior\"\nreplacement=\"$target.nuevo\"\n"
            "cp \"$source_file\" \"$replacement\" && chmod +x \"$replacement\" || exit 1\n"
            "rm -f \"$backup\" && mv \"$target\" \"$backup\" && mv \"$replacement\" \"$target\" || { mv \"$backup\" \"$target\"; exit 1; }\n"
            "cd \"$workdir\" && nohup \"$target\" >/dev/null 2>&1 &\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        subprocess.Popen(["sh", str(script), str(os.getpid()), str(staged_executable), str(current), str(APP_DIR)], start_new_session=True)
