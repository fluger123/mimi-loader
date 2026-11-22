import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

_data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
DATA_DIR = _data_home / "mimi-launcher"
DOWNLOAD_FILE = DATA_DIR / "update.zip"

_config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
TOKEN_FILE = _config_home / "mimi-launcher" / "token"
SETTINGS_FILE = _config_home / "mimi-launcher" / "settings.json"
APP_FOLDER_NAME = "Mimi-Assistant"


def _load_settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_setting(key, default=None):
    return _load_settings().get(key, default)


def set_setting(key, value):
    data = _load_settings()
    data[key] = value
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data), encoding="utf-8")


def get_install_parent():
    """Папка, которую выбрал пользователь (по умолчанию ~/.local/share/mimi-launcher)."""
    path = get_setting("install_dir")
    return Path(path).expanduser() if path else DATA_DIR


def set_install_parent(path):
    set_setting("install_dir", str(path))


def get_app_dir():
    """Само приложение всегда в подпапке — при обновлении удаляется только она."""
    return get_install_parent() / APP_FOLDER_NAME


def get_version_file():
    return get_app_dir() / ".mimi_version"


def clean_env():
    """Окружение для запускаемых скриптов: без venv лоадера и без библиотек PyInstaller."""
    env = os.environ.copy()
    venv = env.pop("VIRTUAL_ENV", None)
    if venv:
        env["PATH"] = os.pathsep.join(
            part for part in env.get("PATH", "").split(os.pathsep)
            if not part.startswith(venv)
        )
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    orig = env.get("LD_LIBRARY_PATH_ORIG")
    if orig is not None:
        env["LD_LIBRARY_PATH"] = orig
    elif getattr(sys, "frozen", False):
        env.pop("LD_LIBRARY_PATH", None)

    # сертификаты для дочерних процессов (start.sh, pip, само приложение):
    # битые пути убираем, рабочий бандл (его нашёл github_api) передаём явно
    ca_vars = ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE", "PIP_CERT")
    good = next((env[v] for v in ca_vars if env.get(v) and Path(env[v]).is_file()), None)
    for v in ca_vars:
        env.pop(v, None)
    if good:
        for v in ca_vars:
            env[v] = good
    return env
