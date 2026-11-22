import json
import os
import sys
from pathlib import Path

import requests

from paths import CONFIG_PATH, TOKEN_FILE

CA_ENV_VARS = ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE")

# системные бандлы сертификатов разных дистрибутивов
SYSTEM_CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",                 # Debian, Ubuntu, Arch (symlink)
    "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",  # Fedora, RHEL
    "/etc/pki/tls/certs/ca-bundle.crt",                   # Fedora, RHEL (старый путь)
    "/etc/ca-certificates/extracted/tls-ca-bundle.pem",   # Arch
    "/var/lib/ca-certificates/ca-bundle.pem",             # openSUSE
    "/etc/ssl/ca-bundle.pem",                             # openSUSE (старый путь)
    "/etc/ssl/cert.pem",                                  # Alpine, BSD
)


def _usable(path):
    try:
        return bool(path) and Path(path).is_file() and Path(path).stat().st_size > 0
    except OSError:
        return False


def find_ca_bundle():
    """Первый реально существующий бандл сертификатов (или None)."""
    candidates = [os.environ.get(v) for v in CA_ENV_VARS]

    # бандл, упакованный PyInstaller-ом
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(os.path.join(base, "certifi", "cacert.pem"))

    candidates.extend(SYSTEM_CA_BUNDLES)

    # certifi.where() — в сборках с Fedora он указывает на системный путь,
    # которого на другой системе нет, поэтому проверяем существование
    try:
        import certifi
        candidates.append(certifi.where())
    except Exception:
        pass

    for c in candidates:
        if _usable(c):
            return c
    return None


def fix_ca_bundle():
    """Убирает битые пути из окружения и подставляет рабочий бандл.
    Вызывается при импорте — до первого запроса requests."""
    bundle = find_ca_bundle()
    for var in CA_ENV_VARS:
        if not _usable(os.environ.get(var)):
            os.environ.pop(var, None)
    if bundle:
        os.environ["REQUESTS_CA_BUNDLE"] = bundle
        os.environ["SSL_CERT_FILE"] = bundle
    return bundle


fix_ca_bundle()


def load_token():
    """Токен: переменная окружения → файл ~/.config/mimi-launcher/token → config.json."""
    env = os.environ.get("MIMI_GITHUB_TOKEN", "").strip()
    if env:
        return env
    try:
        saved = TOKEN_FILE.read_text().strip()
        if saved:
            return saved
    except OSError:
        pass
    # токен, зашитый в config.json (попадает в бинарник при сборке)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("token", "").strip()
    except (OSError, ValueError):
        return ""


def save_token(token):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token.strip())
    TOKEN_FILE.chmod(0o600)  # читать может только владелец


class GitHubAPI:
    def __init__(self, config_path=CONFIG_PATH):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        self.owner = cfg["owner"]
        self.repo = cfg["repo"]
        self.token = load_token()

        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def latest_release(self):
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases/latest"
        r = requests.get(url, headers=self.headers, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"GitHub API error {r.status_code}: {r.text[:300]}")
        return r.json()

    def latest_zip(self):
        """Возвращает (версия, asset, релиз). Один запрос вместо трёх."""
        release = self.latest_release()
        for asset in release.get("assets", []):
            if asset["name"].endswith(".zip"):
                return release["tag_name"], asset, release
        raise RuntimeError("В последнем релизе нет ZIP-файла")
