import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import requests
from PySide6.QtCore import QThread, Signal

from github_api import GitHubAPI
from paths import DATA_DIR, DOWNLOAD_FILE, clean_env, get_app_dir, get_setting, get_version_file


VOICE_NAME = "v5_ru.pt"
VOICE_URL = "https://models.silero.ai/models/tts/ru/v5_ru.pt"
KEEP_DIR = DATA_DIR / ".keep_data"
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}
VOICE_CONNECTIONS = 1   # 1 = один поток; можно поставить 4, если сеть и оболочка выдерживают


def release_summary(release, tag):
    """Короткое описание релиза для карточки новостей."""
    body = (release.get("body") or "").replace("\r", "")
    body = re.sub(r"[#*`>]", "", body)
    body = " ".join(body.split())
    if len(body) > 260:
        body = body[:260].rstrip() + "…"
    date = ""
    published = release.get("published_at") or ""
    if len(published) >= 10:
        y, m, d = published[:10].split("-")
        date = f"{d}.{m}.{y}"
    return {
        "title": release.get("name") or tag,
        "text": body,
        "date": date,
        "url": release.get("html_url") or "",
    }


def installed_version():
    try:
        return get_version_file().read_text().strip()
    except OSError:
        return None


def safe_extract(zip_path, dest):
    dest = Path(dest).resolve()
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            target = (dest / name).resolve()
            if dest not in target.parents and target != dest:
                raise RuntimeError(f"Небезопасный путь в архиве: {name}")
        z.extractall(dest)


class UpdateWorker(QThread):
    """Проверка + скачивание + распаковка в фоне, чтобы окно не вешалось."""

    progress = Signal(int)
    status = Signal(str)
    log = Signal(str)
    version = Signal(str)
    latest = Signal(str)
    release_info = Signal(object)
    finished_ok = Signal(str)
    error = Signal(str)

    def __init__(self, check_only=False):
        super().__init__()
        self.check_only = check_only
        self.installed_now = False

    def ensure_voice(self, app_dir):
        """Скачивает голос Silero в <папка приложения>/data, если его там ещё нет."""
        target = app_dir / "data" / VOICE_NAME
        if target.exists() and target.stat().st_size > 0:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_suffix(".part")
        self.status.emit("Скачивание голоса Silero...")
        self.log.emit(f"Скачивание {VOICE_NAME}")
        self.progress.emit(0)

        started = time.time()
        if VOICE_CONNECTIONS > 1:
            try:
                self.download_parallel(VOICE_URL, part)
            except Exception as e:  # по частям не вышло — обычная загрузка одним потоком
                self.log.emit(f"Загрузка по частям не удалась ({e}), качаю одним потоком")
                part.unlink(missing_ok=True)
                self.download_single(VOICE_URL, part)
        else:
            self.download_single(VOICE_URL, part)

        part.replace(target)
        size_mb = target.stat().st_size / 1048576
        secs = max(time.time() - started, 0.1)
        self.log.emit(f"Голос сохранён: {target} ({size_mb:.0f} МБ, {size_mb / secs:.1f} МБ/с)")

    def report_speed(self, done, total, started):
        """Только полоса прогресса: текст в плашке не меняется (скорость пишется в лог в конце)."""
        if total:
            self.progress.emit(min(100, done * 100 // total))

    def download_single(self, url, dest):
        started = time.time()
        last = 0.0
        done = total = 0
        with requests.get(url, headers=BROWSER_HEADERS, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if time.time() - last > 0.5:
                        last = time.time()
                        self.report_speed(done, total, started)
        if total and done != total:
            raise RuntimeError("Голос скачан не полностью, попробуй ещё раз")

    def download_parallel(self, url, dest, connections=VOICE_CONNECTIONS):
        """Качает файл несколькими потоками (Range), как это делают менеджеры загрузок."""
        head = requests.head(url, headers=BROWSER_HEADERS, allow_redirects=True, timeout=30)
        head.raise_for_status()
        total = int(head.headers.get("content-length", 0))
        if not total or head.headers.get("accept-ranges", "").lower() != "bytes":
            raise RuntimeError("сервер не поддерживает загрузку по частям")

        with open(dest, "wb") as f:
            f.truncate(total)

        done = [0]
        lock = threading.Lock()
        errors = []
        step = total // connections

        def fetch(start, end):
            try:
                headers = dict(BROWSER_HEADERS, Range=f"bytes={start}-{end}")
                with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                    if r.status_code != 206:
                        raise RuntimeError(f"ответ сервера {r.status_code} вместо 206")
                    with open(dest, "r+b") as f:
                        f.seek(start)
                        for chunk in r.iter_content(512 * 1024):
                            f.write(chunk)
                            with lock:
                                done[0] += len(chunk)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(connections):
            start = i * step
            end = total - 1 if i == connections - 1 else start + step - 1
            t = threading.Thread(target=fetch, args=(start, end), daemon=True)
            t.start()
            threads.append(t)

        started = time.time()
        while any(t.is_alive() for t in threads):
            self.report_speed(done[0], total, started)
            time.sleep(0.4)
        for t in threads:
            t.join()

        if errors:
            raise errors[0]
        if done[0] != total:
            raise RuntimeError("Голос скачан не полностью")

    def run(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            app_dir = get_app_dir()
            app_dir.parent.mkdir(parents=True, exist_ok=True)
            api = GitHubAPI()
            self.log.emit(f"CA-бандл: {os.environ.get('REQUESTS_CA_BUNDLE') or 'не найден'}")

            self.status.emit("Проверка обновлений...")
            tag, asset, release = api.latest_zip()
            self.version.emit(tag)
            self.log.emit(f"Последняя версия: {tag}")
            self.release_info.emit(release_summary(release, tag))
            self.latest.emit(tag)
            if self.check_only:
                if (app_dir / "start.sh").exists():
                    self.ensure_voice(app_dir)
                self.finished_ok.emit(f"Последняя версия: {tag}")
                return
            self.log.emit(f"Папка установки: {app_dir}")

            if installed_version() == tag and (app_dir / "start.sh").exists():
                self.ensure_voice(app_dir)
                self.progress.emit(100)
                self.finished_ok.emit(f"Уже установлена {tag}")
                return

            self.status.emit("Скачивание...")
            headers = {"Accept": "application/octet-stream"}
            if api.token:
                headers["Authorization"] = f"Bearer {api.token}"

            # asset["url"] (API-адрес) работает и для приватных репо, browser_download_url — нет
            with requests.get(asset["url"], headers=headers, stream=True, timeout=60) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0)) or asset.get("size", 0)
                done = 0
                with open(DOWNLOAD_FILE, "wb") as f:
                    for chunk in r.iter_content(256 * 1024):
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            self.progress.emit(min(100, done * 100 // total))

            self.status.emit("Установка...")
            with tempfile.TemporaryDirectory(dir=DATA_DIR) as tmp:
                safe_extract(DOWNLOAD_FILE, tmp)
                root = Path(tmp)
                items = list(root.iterdir())
                if len(items) == 1 and items[0].is_dir():  # архив с одной корневой папкой
                    root = items[0]
                kept = None
                if app_dir.exists():
                    old_data = app_dir / "data"
                    if old_data.exists():  # голос и прочие данные переживают обновление
                        if KEEP_DIR.exists():
                            shutil.rmtree(KEEP_DIR)
                        shutil.move(str(old_data), str(KEEP_DIR))
                        kept = KEEP_DIR
                    shutil.rmtree(app_dir)
                shutil.move(str(root), str(app_dir))
                if kept is not None:
                    new_data = app_dir / "data"
                    new_data.mkdir(exist_ok=True)
                    for item in kept.iterdir():  # данные пользователя главнее файлов из релиза
                        dest = new_data / item.name
                        if dest.is_dir() and not dest.is_symlink():
                            shutil.rmtree(dest)
                        elif dest.exists() or dest.is_symlink():
                            dest.unlink()
                        shutil.move(str(item), str(dest))
                    shutil.rmtree(kept, ignore_errors=True)

            start = app_dir / "start.sh"
            if start.exists():
                start.chmod(start.stat().st_mode | 0o111)

            self.ensure_voice(app_dir)

            installer = app_dir / "install_launcher.sh"
            if installer.exists() and get_setting("run_installer", True):
                installer.chmod(installer.stat().st_mode | 0o111)
                self.status.emit("Запуск install_launcher.sh...")
                self.log.emit("Запуск install_launcher.sh")
                proc = subprocess.Popen(
                    ["bash", str(installer)],
                    cwd=app_dir,
                    env=clean_env(),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                for line in proc.stdout:
                    self.log.emit(line.rstrip())
                code = proc.wait()
                if code != 0:
                    # ярлык в меню — не критично, установку не прерываем
                    self.log.emit(
                        f"install_launcher.sh завершился с кодом {code} "
                        "(ярлык не создан), установка продолжается"
                    )

            get_version_file().write_text(tag)
            DOWNLOAD_FILE.unlink(missing_ok=True)
            self.progress.emit(100)
            self.installed_now = True
            self.finished_ok.emit(f"Установлена {tag}")

        except Exception as e:
            msg = str(e)
            if "TLS CA certificate bundle" in msg:
                msg += (
                    "\nВ системе не найден файл с сертификатами. Установи пакет "
                    "ca-certificates (Arch/CachyOS: sudo pacman -S ca-certificates)"
                )
            self.error.emit(msg)


class LaunchWorker(QThread):
    """Запускает start.sh и показывает его вывод, пока он готовит окружение."""

    log = Signal(str)
    ok = Signal()
    failed = Signal(str)

    def __init__(self, script):
        super().__init__()
        self.script = script

    def run(self):
        app_dir = self.script.parent
        try:
            proc = subprocess.Popen(
                ["bash", str(self.script)],
                cwd=app_dir,
                env=clean_env(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                start_new_session=True,
            )
        except OSError as e:
            self.failed.emit(f"не удалось запустить start.sh: {e}")
            return

        # пока скрипт ставит модули, показываем его вывод; после exec python канал закрывается
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                self.log.emit(line)

        try:
            code = proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.ok.emit()  # приложение работает
            return

        if code == 0:
            self.ok.emit()
            return

        log_file = app_dir / "data" / "last_run.log"
        try:
            tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
            for line in tail:
                self.log.emit(line)
        except OSError:
            pass
        self.failed.emit(f"start.sh завершился с кодом {code}, подробности на вкладке «Логи»")
