import getpass
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

# Размытие фона окна:
#   "compositor" — окно полупрозрачное, а размывает ВСЁ позади (и другие окна) сам рабочий стол:
#                  GNOME — расширение Blur my Shell (так же, как у заставки «Начать разговор»),
#                  KDE и picom — размытие просим у композитора сами;
#   "wallpaper"  — запасной вариант без расширений: размываются только обои рабочего стола;
#   "off"        — без размытия, окно почти непрозрачное.
BLUR_MODE = "compositor"

# для режима "wallpaper" на GNOME/Wayland берём XWayland: иначе окну нельзя узнать своё место на экране
if (BLUR_MODE == "wallpaper" and os.environ.get("XDG_SESSION_TYPE") == "wayland"
        and "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PySide6.QtCore import (
    QByteArray, QEasingCurve, QPoint, QRect, QRectF, QSize, Qt, QTimer, QUrl, QVariantAnimation,
)
from PySide6.QtGui import (
    QBrush, QColor, QDesktopServices, QGuiApplication, QIcon, QImage, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap, QRegion,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QButtonGroup, QFileDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QInputDialog,
    QGraphicsBlurEffect, QLabel, QLayout, QLineEdit,
    QMenu, QProgressBar, QPushButton, QScrollArea, QStackedLayout, QStackedWidget, QTextEdit,
    QVBoxLayout, QWidget,
)

from github_api import load_token, save_token
from paths import (
    CONFIG_PATH, clean_env, get_app_dir, get_install_parent, get_setting,
    get_version_file, set_install_parent, set_setting,
)
from updater import LaunchWorker, UpdateWorker, installed_version

APP_NAME = "mimi-alpha"
BRAND_NAME = "mimi-assistant"   # название слева сверху в сайдбаре (APP_NAME — это программа/папка установки)
ACCENT = "#4968d1"
MAIN_BG = (26, 29, 34, 252)       # фон рабочего окна (RGBA, чуть прозрачный)
SPLASH_BG = (41, 42, 60, 252)     # фон заставки (RGBA)
BLUR_ALPHA = 200           # прозрачность фона окна, когда за ним работает размытие (0-255)
SPLASH_SIZE = (344, 249)   # окно заставки «Подключение к серверу»
WINDOW_SIZE = (588, 398)   # рабочее окно лоадера (после заставки)
# На GNOME (Blur my Shell) размывается весь прямоугольник окна, а прозрачные скруглённые углы
# клиент вырезать не может — они становятся чёрными. Поэтому там окно делаем с прямыми углами.
# Хочешь скругления назад (с чёрными уголками) — поставь False.
GNOME_SQUARE_CORNERS = True
SIDEBAR_ROUND = "border-top-left-radius: 16px; border-bottom-left-radius: 16px;"
SPLASH_RADIUS = 20          # скругление окна заставки
MAIN_RADIUS = 16            # скругление рабочего окна
TRANSITION_MS = 800        # анимация перехода заставка -> рабочее окно
SPLASH_SECONDS = 1.5       # заставка «Подключение к серверу» показывается ровно столько

# ---------- иконки (контуры в стиле Lucide) ----------
ICONS = {
    "home": '<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/><path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "chevron": '<path d="m9 18 6-6-6-6"/>',
    "refresh": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "tag": '<path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="1"/>',
    "hourglass": '<path d="M5 22h14"/><path d="M5 2h14"/><path d="M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22"/><path d="M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2"/>',
    "branch": '<line x1="6" x2="6" y1="3" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
    "sliders": '<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/>',
    "minus": '<path d="M5 12h14"/>',
    "close": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "package": '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
    "share": '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" x2="15.42" y1="13.51" y2="17.49"/><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"/>',
    "commit": '<path d="M12 3v6"/><circle cx="12" cy="12" r="3"/><path d="M12 15v6"/>',
    "code": '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    "external": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
}


def enable_background_blur(window):
    """Просит композитор размывать всё, что находится за окном (эффект матового стекла).

    Работает под X11 (KDE/KWin, picom и др. понимают _KDE_NET_WM_BLUR_BEHIND_REGION).
    Возвращает True, если запрос отправлен; иначе окно остаётся непрозрачным.
    """
    if QGuiApplication.platformName() != "xcb":
        return False
    try:
        import ctypes
        import ctypes.util

        lib = ctypes.util.find_library("X11")
        if not lib:
            return False
        x11 = ctypes.CDLL(lib)
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XInternAtom.restype = ctypes.c_ulong
        x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x11.XChangeProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
        ]
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

        display = x11.XOpenDisplay(None)
        if not display:
            return False
        try:
            atom = x11.XInternAtom(display, b"_KDE_NET_WM_BLUR_BEHIND_REGION", 0)
            # пустой список прямоугольников = размывать всё окно
            x11.XChangeProperty(display, int(window.winId()), atom, 6, 32, 0, None, 0)
            x11.XFlush(display)
        finally:
            x11.XCloseDisplay(display)
        return True
    except Exception:
        return False


BMS_PATH = "/org/gnome/shell/extensions/blur-my-shell"
BMS_UUID = "blur-my-shell@aunetx"


def _dconf_read(key):
    try:
        return subprocess.run(["dconf", "read", key], capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return ""


def _dconf_write(key, value):
    try:
        return subprocess.run(["dconf", "write", key, value], capture_output=True, timeout=3).returncode == 0
    except Exception:
        return False


def _gv_list(items):
    """Список строк в текстовом виде GVariant (пустой список нужно писать с типом)."""
    return str(list(items)) if items else "@as []"


def _parse_str_list(raw):
    """"['a', 'b']" или "@as []" из dconf -> список строк."""
    return re.findall(r"'([^']*)'", raw or "")


def blur_my_shell_installed():
    """Расширение Blur my Shell установлено (у пользователя или в системе)."""
    for base in (Path.home() / ".local/share/gnome-shell/extensions",
                 Path("/usr/share/gnome-shell/extensions")):
        if (base / BMS_UUID).is_dir():
            return True
    return False


def setup_gnome_blur(app_ids):
    """Вписывает окно в настройки Blur my Shell, чтобы GNOME размывал всё позади него.

    Расширение матчит окна по WM_CLASS / app_id, поэтому добавляем наш app_id в белый список
    (или убираем из чёрного, если включено «размывать все по умолчанию»).
    Возвращает: "ok" | "no_extension" | "disabled" | "error".
    """
    if not blur_my_shell_installed():
        return "no_extension"
    app = f"{BMS_PATH}/applications"
    try:
        if _dconf_read(f"{app}/blur") != "true":
            if not _dconf_write(f"{app}/blur", "true"):
                return "error"
            # компонент включаем ради одного нашего окна: режим «размывать все окна» выключаем,
            # иначе блюр появится вообще у всех приложений
            if _dconf_read(f"{app}/enable-all") == "true":
                _dconf_write(f"{app}/enable-all", "false")
        if _dconf_read(f"{app}/enable-all") == "true":
            black = _parse_str_list(_dconf_read(f"{app}/blacklist"))
            new = [x for x in black if x not in app_ids]
            if new != black and not _dconf_write(f"{app}/blacklist", _gv_list(new)):
                return "error"
        else:
            white = _parse_str_list(_dconf_read(f"{app}/whitelist"))
            new = white + [x for x in app_ids if x not in white]
            if new != white and not _dconf_write(f"{app}/whitelist", _gv_list(new)):
                return "error"
            # иначе расширение делает ФОКУСНОЕ окно непрозрачным — а наше лоадер почти всегда в фокусе
            if _dconf_read(f"{app}/dynamic-opacity") != "false":
                _dconf_write(f"{app}/dynamic-opacity", "false")
    except Exception:
        return "error"
    enabled = _dconf_read("/org/gnome/shell/enabled-extensions")
    return "ok" if BMS_UUID in enabled else "disabled"


def make_blurred_wallpaper(screen):
    """Обои GNOME, размытые и растянутые на весь экран (QPixmap), либо None."""
    if screen is None:
        return None
    try:
        scheme = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=2,
        ).stdout
        keys = ["picture-uri-dark", "picture-uri"] if "dark" in scheme else ["picture-uri", "picture-uri-dark"]
        for key in keys:
            out = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.background", key],
                capture_output=True, text=True, timeout=2,
            ).stdout.strip().strip("'\"")
            if not out.startswith("file://"):
                continue
            img = QImage(QUrl(out).toLocalFile())
            if img.isNull():
                continue
            size = screen.size()
            img = img.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                             Qt.TransformationMode.SmoothTransformation)
            img = img.copy((img.width() - size.width()) // 2, (img.height() - size.height()) // 2,
                           size.width(), size.height())
            # дешёвое размытие: сильно уменьшаем и плавно растягиваем обратно
            for div in (28, 8):
                img = img.scaled(max(1, size.width() // div), max(1, size.height() // div),
                                 Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            img = img.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            return QPixmap.fromImage(img)
    except Exception:
        pass
    return None


def render_svg(svg, size):
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    return pm


def make_pixmap(name, color="#e6e8f2", size=20, fill="none"):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="{fill}" stroke="{color}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f"{ICONS[name]}</svg>"
    )
    return render_svg(svg, size)


def dimmed_pixmap(pm, opacity=0.45):
    out = QPixmap(pm.size())
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setOpacity(opacity)
    painter.drawPixmap(0, 0, pm)
    painter.end()
    return out


def make_icon(name, color="#e6e8f2", size=20, fill="none"):
    return QIcon(make_pixmap(name, color, size, fill))


def nav_icon(name, off="#9aa0b8", on="#4d7cff", size=18):
    icon = QIcon()
    icon.addPixmap(make_pixmap(name, off, size), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(make_pixmap(name, on, size), QIcon.Mode.Normal, QIcon.State.On)
    return icon


def badge_pixmap(kind, color, size=20):
    """Цветной кружок с галочкой, «i» или «!» (как в плашке статуса)."""
    if kind == "check":
        mark = '<path d="m7.5 12.5 3 3 6-7" fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
    elif kind == "info":
        mark = '<path d="M12 11v5.5" fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round"/><circle cx="12" cy="7.6" r="1.3" fill="white"/>'
    else:
        mark = '<path d="M12 6.5v6.5" fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round"/><circle cx="12" cy="16.8" r="1.3" fill="white"/>'
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<circle cx="12" cy="12" r="11" fill="{color}"/>{mark}</svg>'
    )
    return render_svg(svg, size)


def product_pixmap(size):
    """Скруглённая градиентная иконка программы с коробкой внутри."""
    full = size * 2
    pm = QPixmap(full, full)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, full, full)
    grad.setColorAt(0.0, QColor("#7c5cff"))
    grad.setColorAt(1.0, QColor("#3b6cf6"))
    painter.setBrush(QBrush(grad))
    painter.setPen(Qt.PenStyle.NoPen)
    radius = full * 0.26
    painter.drawRoundedRect(QRectF(0, 0, full, full), radius, radius)
    inner = make_pixmap("package", "white", max(int(size * 0.58), 8))
    painter.drawPixmap((full - inner.width()) // 2, (full - inner.height()) // 2, inner)
    painter.end()
    return pm


def repo_url():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        return f"https://github.com/{cfg['owner']}/{cfg['repo']}"
    except (OSError, ValueError, KeyError):
        return "https://github.com"


def fmt_time(ts):
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y (%H:%M)")


class Spinner(QWidget):
    """Крутящееся кольцо для заставки «Подключение к серверу»."""

    def __init__(self, size=26):
        super().__init__()
        self.setFixedSize(size, size)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def start(self):
        self.timer.start(40)

    def stop(self):
        self.timer.stop()

    def tick(self):
        self.angle = (self.angle + 18) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pw = max(3, round(self.width() / 13))
        rect = QRectF(pw, pw, self.width() - 2 * pw, self.height() - 2 * pw)
        painter.setPen(QPen(QColor(255, 255, 255, 40), pw))
        painter.drawEllipse(rect)
        pen = QPen(QColor(ACCENT), pw)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, -self.angle * 16, 100 * 16)


class PillFrame(QFrame):
    """Табличка заставки: полностью скруглённая «таблетка», рисуется вручную."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2
        painter.setBrush(QColor("#30344d"))
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
        painter.drawRoundedRect(rect, radius, radius)


class LoadingOverlay(QWidget):
    """Полупрозрачная панель поверх страницы: за ней видна размытая страница программы."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(25, 24, 30))   # сплошной тёмный фон, страница под ним не просвечивает
        painter.drawRoundedRect(QRectF(self.rect()), 10, 10)


class RootFrame(QFrame):
    """Фон окна: рисуем сами, чтобы цвет и скругление можно было плавно анимировать."""

    def __init__(self):
        super().__init__()
        self.bg = QColor(*SPLASH_BG)
        self.radius = SPLASH_RADIUS
        self.backdrop = None   # размытые обои рабочего стола (на весь экран)
        self.square = False    # True: прямые углы (GNOME + Blur my Shell)

    def paintEvent(self, event):
        radius = 0 if self.square else self.radius
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.backdrop is not None:
            screen = self.screen()
            origin = screen.geometry().topLeft() if screen else QPoint(0, 0)
            offset = self.mapToGlobal(QPoint(0, 0)) - origin
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(self.rect()), radius, radius)
            painter.save()
            painter.setClipPath(clip)
            painter.drawPixmap(-offset, self.backdrop)
            painter.restore()
        painter.setBrush(self.bg)
        painter.drawRoundedRect(QRectF(self.rect()), radius, radius)


STYLE = """
QWidget { color: #e6e8f2; font-family: "Inter", "Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif; font-size: 11px; }
QLabel { background: transparent; }

QFrame#sidebar { background: rgba(30,40,52,0.35); border-top-left-radius: 16px; border-bottom-left-radius: 16px; }
QFrame#line { background: rgba(255,255,255,0.07); max-height: 1px; min-height: 1px; }

QLabel#badge { background: #141825; border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; font-size: 12px; font-weight: 800; }
QLabel#brand { font-size: 12px; font-weight: 800; }
QLabel#navDim { color: #aab0c6; font-size: 11px; font-weight: 600; }
QLabel#navSub { color: #5f8bff; font-size: 9px; font-weight: 600; }
QLabel#section { color: #8b90a6; font-size: 9px; font-weight: 700; }
QLabel#avatar { background: #141825; border-radius: 12px; }
QLabel#user { font-size: 11px; font-weight: 700; }

QPushButton#nav { background: transparent; border: none; border-radius: 8px; padding: 7px 8px; text-align: left; font-size: 11px; font-weight: 600; color: #aab0c6; }
QPushButton#nav:hover { background: rgba(110,110,160,0.15); }
QPushButton#nav:checked { background: rgba(110,110,160,0.33); color: white; }
QPushButton#userbtn { background: transparent; border: none; border-radius: 7px; padding: 2px; text-align: left; }
QPushButton#userbtn:hover { background: rgba(255,255,255,0.05); }

QPushButton#tab { background: transparent; border: none; padding: 4px 2px; color: #aab0c6; font-size: 11px; font-weight: 600; }
QPushButton#tab:hover { color: white; }
QPushButton#tab:checked { color: white; border-bottom: 2px solid #4968d1; }
QPushButton#winbtn { background: transparent; border: none; border-radius: 7px; padding: 5px; }
QPushButton#winbtn:hover { background: rgba(255,255,255,0.10); }

QLabel#pillText { font-size: 13px; font-weight: 500; }

QFrame#newsCard, QFrame#card { background: transparent; border: none; }   /* без рамки и отдельной плашки: справа один общий фон */
QLabel#chipDate { background: rgba(255,255,255,0.07); border-radius: 7px; padding: 2px 7px; font-size: 10px; }
QLabel#newsTitle { font-size: 14px; font-weight: 700; }
QLabel#newsText { color: #b8bdd0; font-size: 11px; }
QPushButton#readMore { background: rgba(255,255,255,0.06); border: none; border-radius: 8px; padding: 7px 11px; font-size: 11px; font-weight: 600; }
QPushButton#readMore:hover { background: rgba(255,255,255,0.11); }

QFrame#banner { border-radius: 10px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.04); }
QFrame#banner[state="warn"] { border-color: #f59e0b; background: rgba(245,158,11,0.13); }
QFrame#banner[state="error"] { border-color: #ef4444; background: rgba(239,68,68,0.13); }
QLabel#bannerText { font-size: 12px; font-weight: 600; }

QLabel#productName { font-size: 17px; font-weight: 800; }
QLabel#rowTitle { font-size: 11px; font-weight: 600; color: #c8cce0; }
QLabel#rowValue { font-size: 11px; font-weight: 600; }

QPushButton#chip { background: rgba(255,255,255,0.07); border: none; border-radius: 8px; padding: 5px 8px; color: #5f8bff; font-size: 11px; font-weight: 700; }
QPushButton#square { background: rgba(70,60,110,0.22); border: none; border-radius: 7px; padding: 5px; }
QPushButton#square::menu-indicator { image: none; width: 0px; }
QPushButton#square:hover { background: rgba(90,80,140,0.40); }

QPushButton#primary { background: #4968d1; border: none; border-radius: 8px; padding: 8px 20px; font-size: 12px; font-weight: 700; min-width: 90px; }
QPushButton#primary:hover { background: #5f7de0; }
QPushButton#primary:disabled { background: #343a52; color: #8b90a6; }

QProgressBar { background: rgba(255,255,255,0.10); border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }
QProgressBar::chunk { background: #d7dbea; border-radius: 2px; }
QLabel#loadName { font-size: 14px; font-weight: 800; }
QLabel#soonText { color: #9aa0b8; font-size: 11px; font-weight: 700; }
QLabel#loadStatus { color: #9aa0b8; font-size: 8px; }

QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 4px; margin: 0; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.15); border-radius: 2px; min-height: 14px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QTextEdit { background: rgba(0,0,0,0.25); border: none; border-radius: 10px; padding: 8px; font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace; font-size: 10px; }

QMenu { background: #22252c; border: 1px solid rgba(255,255,255,0.10); border-radius: 6px; padding: 4px; }
QMenu::item { padding: 6px 14px; border-radius: 5px; }
QMenu::item:selected { background: #4968d1; }
"""


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        # app_id (Wayland) / WM_CLASS (X11): по нему Blur my Shell узнаёт наше окно
        QGuiApplication.setDesktopFileName(APP_NAME)
        QGuiApplication.setApplicationName(APP_NAME)
        self.setWindowTitle(APP_NAME)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(*SPLASH_SIZE)
        self.center_on_screen()
        self.setStyleSheet(STYLE)

        self.splash_bg = SPLASH_BG
        self.main_bg = MAIN_BG
        self.blur_on = False

        self.worker = None
        self.launch_worker = None
        self.latest = None
        self.busy = False
        self.busy_text = ""
        self.error_msg = None
        self.mode = "install"
        self.install_running = False
        self.voice_loading = False
        self.launching = False
        self.nav_index = 1
        self.release_url = repo_url()

        self.build_ui()
        self.log("Лоадер запущен")
        dpr = self.screen().devicePixelRatio() if self.screen() else 1.0
        self.log(
            f"Заставка {SPLASH_SIZE[0]}×{SPLASH_SIZE[1]}, окно {WINDOW_SIZE[0]}×{WINDOW_SIZE[1]}, "
            f"масштаб экрана {dpr:g}"
        )
        self.spinner.start()
        QTimer.singleShot(int(SPLASH_SECONDS * 1000), self.show_main)
        self.refresh_state()
        self.run_worker(check_only=True)

    # ---------- построение интерфейса ----------
    def build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        # окно должно свободно менять размер во время анимации
        outer_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

        root = RootFrame()
        root.setObjectName("root")
        self.root = root
        outer_layout.addWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.outer = QStackedWidget()
        self.outer.addWidget(self.build_splash())
        self.outer.addWidget(self.build_shell())
        root_layout.addWidget(self.outer)

        self.menu = self.build_menu()

    def hline(self):
        line = QFrame()
        line.setObjectName("line")
        return line

    def build_splash(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        pill = PillFrame()
        pill.setObjectName("pill")
        pl = QHBoxLayout(pill)
        pill.setFixedHeight(42)
        pl.setContentsMargins(12, 0, 18, 0)
        pl.setSpacing(11)
        self.spinner = Spinner(24)
        text = QLabel("Подключение к серверу")
        text.setObjectName("pillText")
        pl.addWidget(self.spinner)
        pl.addWidget(text)
        row.addWidget(pill)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        return page

    def build_shell(self):
        shell = QWidget()
        lay = QHBoxLayout(shell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.build_sidebar())
        lay.addWidget(self.build_content(), 1)
        return shell

    def build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(160)
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(11, 13, 11, 11)
        lay.setSpacing(5)

        brand = QHBoxLayout()
        badge = QLabel("MA")
        badge.setObjectName("badge")
        badge.setFixedSize(30, 30)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name = QLabel(BRAND_NAME)
        name.setObjectName("brand")
        brand.addWidget(badge)
        brand.addSpacing(5)
        brand.addWidget(name)
        brand.addStretch()
        lay.addLayout(brand)
        lay.addSpacing(12)

        about = QLabel("ABOUT")
        about.setObjectName("section")
        lay.addWidget(about)
        self.home_btn = QPushButton("  Главная")
        self.home_btn.setObjectName("nav")
        self.home_btn.setCheckable(True)
        self.home_btn.setIcon(nav_icon("home", size=14))
        self.home_btn.setIconSize(QSize(14, 14))
        self.home_btn.clicked.connect(lambda: self.go(0))
        lay.addWidget(self.home_btn)
        lay.addSpacing(10)

        software = QLabel("SOFTWARE")
        software.setObjectName("section")
        lay.addWidget(software)
        self.product_btn = QPushButton("  " + APP_NAME)
        self.product_btn.setObjectName("nav")
        self.product_btn.setCheckable(True)
        self.product_btn.setChecked(True)
        self.product_btn.setIcon(QIcon(product_pixmap(16)))
        self.product_btn.setIconSize(QSize(16, 16))
        self.product_btn.clicked.connect(lambda: self.go(1))
        lay.addWidget(self.product_btn)

        # следующая версия: пока недоступна, просто показываем, что скоро
        self.next_btn = QPushButton()
        self.next_btn.setObjectName("nav")
        self.next_btn.setCheckable(True)
        self.next_btn.setFixedHeight(40)
        self.next_btn.clicked.connect(lambda: self.go(3))
        nl = QHBoxLayout(self.next_btn)
        nl.setContentsMargins(8, 0, 6, 0)
        nl.setSpacing(7)
        next_icon = QLabel()
        next_icon.setPixmap(dimmed_pixmap(product_pixmap(16), 0.7))
        next_icon.setFixedSize(16, 16)
        next_icon.setScaledContents(True)
        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(0)
        next_name = QLabel("mimi-nextgen")
        next_name.setObjectName("navDim")
        next_sub = QLabel("Soon")
        next_sub.setObjectName("navSub")
        texts.addStretch()
        texts.addWidget(next_name)
        texts.addWidget(next_sub)
        texts.addStretch()
        nl.addWidget(next_icon)
        nl.addLayout(texts, 1)
        lay.addWidget(self.next_btn)

        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.home_btn)
        group.addButton(self.product_btn)
        group.addButton(self.next_btn)

        lay.addStretch()
        lay.addWidget(self.hline())

        self.user_btn = QPushButton()
        self.user_btn.setObjectName("userbtn")
        self.user_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ul = QHBoxLayout(self.user_btn)
        ul.setContentsMargins(4, 2, 7, 2)
        avatar = QLabel()
        avatar.setObjectName("avatar")
        avatar.setFixedSize(24, 24)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setPixmap(
            make_pixmap("user", "#e6e8f2", 14).scaled(
                14, 14, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        user = QLabel(getpass.getuser())
        user.setObjectName("user")
        chevron = QLabel()
        chevron.setPixmap(make_pixmap("chevron", "#aab0c6", 12))
        chevron.setFixedSize(12, 12)
        chevron.setScaledContents(True)
        ul.addWidget(avatar)
        ul.addSpacing(5)
        ul.addWidget(user, 1)
        ul.addWidget(chevron)
        self.user_btn.setFixedHeight(34)
        self.user_btn.clicked.connect(self.open_user_menu)
        lay.addWidget(self.user_btn)
        return sidebar

    def build_content(self):
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(18, 8, 18, 13)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self.repo_btn = QPushButton("Репозиторий")
        self.repo_btn.setObjectName("tab")
        self.repo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.repo_btn.clicked.connect(lambda: self.open_url(repo_url()))
        self.logs_btn = QPushButton("Логи")
        self.logs_btn.setObjectName("tab")
        self.logs_btn.setCheckable(True)
        self.logs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logs_btn.toggled.connect(lambda _: self.apply_page())
        top.addWidget(self.repo_btn)
        top.addSpacing(14)
        top.addWidget(self.logs_btn)
        top.addStretch()
        for icon_name, slot in (("minus", self.showMinimized), ("close", self.close)):
            btn = QPushButton()
            btn.setObjectName("winbtn")
            btn.setIcon(make_icon(icon_name, size=14))
            btn.setIconSize(QSize(14, 14))
            btn.clicked.connect(slot)
            top.addWidget(btn)
        lay.addLayout(top)
        lay.addWidget(self.hline())

        self.pages = QStackedWidget()
        self.pages.addWidget(self.build_home())      # 0
        self.pages.addWidget(self.build_product())   # 1
        self.pages.addWidget(self.build_logs())      # 2
        self.pages.addWidget(self.build_soon())      # 3  mimi-nextgen
        self.pages.setCurrentIndex(1)

        holder = QWidget()
        stack = QStackedLayout(holder)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self.pages)
        self.overlay = self.build_loading()
        stack.addWidget(self.overlay)
        stack.setCurrentWidget(self.overlay)   # оверлей поверх страниц
        self.overlay.hide()
        lay.addWidget(holder, 1)
        return content

    # --- страница «Главная» (новости) ---
    def news_card(self, date, title, text, button_text, slot):
        card = QFrame()
        card.setObjectName("newsCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(7)
        head = QHBoxLayout()
        chip = QLabel(date)
        chip.setObjectName("chipDate")
        ttl = QLabel(title)
        ttl.setObjectName("newsTitle")
        head.addWidget(chip)
        head.addSpacing(7)
        head.addWidget(ttl, 1)
        cl.addLayout(head)
        body = QLabel(text)
        body.setObjectName("newsText")
        body.setWordWrap(True)
        cl.addWidget(body)
        row = QHBoxLayout()
        row.addStretch()
        btn = QPushButton(button_text + "  ")
        btn.setObjectName("readMore")
        btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        btn.setIcon(make_icon("external", size=12))
        btn.setIconSize(QSize(12, 12))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        row.addWidget(btn)
        cl.addLayout(row)
        return card, chip, ttl, body

    def build_home(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 7, 5, 7)
        lay.setSpacing(11)

        card1, self.news_date, self.news_title, self.news_text = self.news_card(
            "—", "Последний релиз", "Данные о релизе загружаются…", "Подробнее",
            lambda: self.open_url(self.release_url),
        )
        card2, _, _, _ = self.news_card(
            "Инфо", "Как это работает",
            "Лоадер проверяет обновления на GitHub, докачивает голос Silero в папку data "
            "и запускает приложение. Папку установки можно сменить в меню пользователя.",
            "Открыть папку", self.open_install_dir,
        )
        lay.addWidget(card1)
        lay.addWidget(card2)
        lay.addStretch()
        scroll.setWidget(inner)
        return scroll

    # --- страница программы ---
    def row(self, icon_name, title, value_widget, extras=()):
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 2, 0, 2)
        icon = QLabel()
        icon.setPixmap(make_pixmap(icon_name, "#c8cce0", 14))
        icon.setFixedSize(14, 14)
        icon.setScaledContents(True)
        label = QLabel(title)
        label.setObjectName("rowTitle")
        if isinstance(value_widget, QLabel):
            value_widget.setObjectName("rowValue")
        lay.addWidget(icon)
        lay.addSpacing(8)
        lay.addWidget(label)
        lay.addStretch()
        lay.addWidget(value_widget)
        for extra in extras:
            lay.addSpacing(5)
            lay.addWidget(extra)
        return lay

    def square_button(self, icon_name, slot):
        btn = QPushButton()
        btn.setObjectName("square")
        btn.setIcon(make_icon(icon_name, size=14))
        btn.setIconSize(QSize(14, 14))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    def build_product(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 5, 0, 0)
        lay.setSpacing(7)

        self.banner = QFrame()
        self.banner.setObjectName("banner")
        b = QHBoxLayout(self.banner)
        b.setContentsMargins(12, 8, 12, 8)
        self.banner_icon = QLabel()
        self.banner_icon.setFixedSize(16, 16)
        self.banner_icon.setScaledContents(True)
        self.banner_text = QLabel("...")
        self.banner_text.setObjectName("bannerText")
        b.addWidget(self.banner_icon)
        b.addSpacing(7)
        b.addWidget(self.banner_text, 1)
        lay.addWidget(self.banner)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)   # без рамки отступ как у плашки статуса
        cl.setSpacing(4)

        head = QHBoxLayout()
        pic = QLabel()
        pic.setPixmap(product_pixmap(34))
        pic.setFixedSize(34, 34)
        pic.setScaledContents(True)
        pname = QLabel(APP_NAME)
        pname.setObjectName("productName")
        head.addWidget(pic)
        head.addSpacing(10)
        head.addWidget(pname)
        head.addStretch()
        cl.addLayout(head)
        cl.addSpacing(6)

        self.updated_val = QLabel("—")
        cl.addLayout(self.row("refresh", "Обновлено", self.updated_val,
                              [self.square_button("clock", self.check_now)]))
        self.version_val = QLabel("—")
        cl.addLayout(self.row("tag", "Версия", self.version_val))
        self.dir_val = QLabel("—")
        cl.addLayout(self.row("folder", "Папка", self.dir_val,
                              [self.square_button("folder", self.choose_dir)]))
        self.last_val = QLabel("Никогда")
        cl.addLayout(self.row("hourglass", "Последний запуск", self.last_val))

        chip = QPushButton("  Release")
        chip.setObjectName("chip")
        chip.setIcon(make_icon("code", "#5f8bff", 12))
        chip.setIconSize(QSize(12, 12))
        cl.addLayout(self.row("branch", "Ветка", chip, [
            self.square_button("share", lambda: self.open_url(repo_url())),
            self.square_button("commit", lambda: self.open_url(repo_url() + "/releases")),
        ]))
        cl.addStretch()

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.menu_btn = QPushButton()
        self.menu_btn.setObjectName("square")
        self.menu_btn.setIcon(make_icon("sliders", size=16))
        self.menu_btn.setIconSize(QSize(16, 16))
        self.menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary = QPushButton("Запустить")
        self.primary.setObjectName("primary")
        self.primary.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary.clicked.connect(self.on_primary)
        bottom.addWidget(self.menu_btn)
        bottom.addSpacing(8)
        bottom.addWidget(self.primary)
        bottom.addStretch()
        cl.addLayout(bottom)

        lay.addWidget(card, 1)
        return page

    def build_logs(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 5, 0, 0)
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        lay.addWidget(self.logs)
        return page

    def build_loading(self):
        page = LoadingOverlay()
        lay = QVBoxLayout(page)
        lay.addStretch()
        icon = QLabel()
        icon.setPixmap(product_pixmap(56))
        icon.setFixedSize(60, 60)
        icon.setScaledContents(True)
        name = QLabel(APP_NAME)
        name.setObjectName("loadName")
        self.load_progress = QProgressBar()
        self.load_progress.setTextVisible(False)
        self.load_progress.setRange(0, 100)
        self.load_progress.setFixedWidth(290)
        self.load_status = QLabel("")
        self.load_status.setObjectName("loadStatus")
        for widget in (icon, name, self.load_progress, self.load_status):
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(widget)
            row.addStretch()
            lay.addLayout(row)
            lay.addSpacing(8)
        lay.addStretch()
        return page

    def build_soon(self):
        """Страница mimi-nextgen: только куб без фона, название и надпись Soon (без плашки и полоски)."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addStretch()
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            'stroke="#7f8cff" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">'
            f"{ICONS['package']}</svg>"
        )
        icon = QLabel()
        icon.setPixmap(render_svg(svg, 56))
        icon.setFixedSize(56, 56)
        icon.setScaledContents(True)
        name = QLabel("mimi-nextgen")
        name.setObjectName("loadName")
        soon = QLabel("Soon")
        soon.setObjectName("soonText")
        for widget in (icon, name, soon):
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(widget)
            row.addStretch()
            lay.addLayout(row)
            lay.addSpacing(8)
        lay.addStretch()
        return page

    def build_menu(self):
        menu = QMenu(self)
        menu.addAction("Проверить обновления", self.check_now)
        menu.addAction("Переустановить", self.reinstall)
        menu.addAction("Выбрать папку установки", self.choose_dir)
        menu.addAction("Ввести токен GitHub", self.ask_token)
        menu.addSeparator()
        shortcut = menu.addAction("Создавать ярлык (install_launcher.sh)")
        shortcut.setCheckable(True)
        shortcut.setChecked(bool(get_setting("run_installer", True)))
        shortcut.toggled.connect(lambda v: set_setting("run_installer", v))
        close_after = menu.addAction("Закрывать лоадер после запуска")
        close_after.setCheckable(True)
        close_after.setChecked(bool(get_setting("close_after_launch", True)))
        close_after.toggled.connect(lambda v: set_setting("close_after_launch", v))
        auto = menu.addAction("Запускать после установки")
        auto.setCheckable(True)
        auto.setChecked(bool(get_setting("auto_launch", True)))
        auto.toggled.connect(lambda v: set_setting("auto_launch", v))

        self.menu_btn.setMenu(menu)
        return menu

    def open_user_menu(self):
        pos = self.user_btn.mapToGlobal(QPoint(0, -self.menu.sizeHint().height()))
        self.menu.exec(pos)

    # ---------- навигация ----------
    @property
    def loading(self):
        return self.install_running or self.voice_loading or self.launching

    def go(self, index):
        self.nav_index = index
        self.logs_btn.setChecked(False)
        self.apply_page()

    def apply_page(self):
        logs = self.logs_btn.isChecked()
        self.pages.setCurrentIndex(2 if logs else self.nav_index)
        self.set_loading_visual(self.loading and not logs and self.nav_index == 1)

    def set_loading_visual(self, on):
        """Загрузка: поверх страницы показываем сплошную плашку (страницу под ней прячем)."""
        self.pages.setVisible(not on)
        if on:
            self.overlay.show()
            self.overlay.raise_()
        else:
            self.overlay.hide()

    def open_url(self, url):
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def open_install_dir(self):
        path = get_app_dir()
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.log("Папка приложения ещё не создана")

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_centered_once", False):
            self._centered_once = True
            self.center_on_screen()
            QTimer.singleShot(0, self.center_on_screen)  # повторно, когда окно уже на экране
            on_gnome = "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
            if BLUR_MODE == "compositor":
                # GNOME сам окна не размывает: просто делаем фон полупрозрачным, как у заставки,
                # и размытие даёт расширение. KDE/picom: просим размытие у композитора напрямую.
                self.blur_on = True
                if on_gnome:
                    if GNOME_SQUARE_CORNERS:
                        self.root.square = True
                        self.setStyleSheet(STYLE.replace(SIDEBAR_ROUND, ""))
                    # Wayland: app_id = APP_NAME; XWayland: WM_CLASS = APP_NAME с заглавной
                    status = setup_gnome_blur([APP_NAME, APP_NAME.capitalize()])
                    self.blur_status = status
                    if status == "no_extension":
                        self.log("Для размытия установи расширение Blur my Shell (extensions.gnome.org)")
                    elif status == "disabled":
                        self.log("Blur my Shell установлен, но выключен: gnome-extensions enable blur-my-shell@aunetx")
                else:
                    enable_background_blur(self)
            elif BLUR_MODE == "wallpaper":
                pm = make_blurred_wallpaper(self.screen())
                if pm is not None:
                    self.root.backdrop = pm
                    self.blur_on = True
            if self.blur_on:
                # фон делаем полупрозрачным — сквозь него виден размытый рабочий стол
                self.splash_bg = (*SPLASH_BG[:3], BLUR_ALPHA)
                self.main_bg = (*MAIN_BG[:3], BLUR_ALPHA)
                self.root.bg = QColor(*self.splash_bg)
                self.root.update()

    def center_on_screen(self):
        screen = self.screen()
        if screen is None:
            return
        area = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(area.center())
        self.move(frame.topLeft())

    # ---------- перетаскивание окна без рамки ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 36:
            handle = self.windowHandle()
            if handle is not None:
                handle.startSystemMove()
        super().mousePressEvent(event)

    # ---------- состояние ----------
    def log(self, text):
        self.logs.append(f"[{datetime.now():%H:%M:%S}] {text}")

    def set_banner(self, text, state="info"):
        kinds = {"info": ("info", ACCENT), "ok": ("check", ACCENT),
                 "warn": ("alert", "#f59e0b"), "error": ("alert", "#ef4444")}
        kind, color = kinds[state]
        self.banner.setProperty("state", state)
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner_icon.setPixmap(badge_pixmap(kind, color, 16))
        self.banner_text.setText(text)

    def refresh_state(self):
        ver = installed_version()
        app_dir = get_app_dir()
        installed = bool(ver) and (app_dir / "start.sh").exists()

        self.version_val.setText(ver or "не установлена")
        self.dir_val.setText(
            self.dir_val.fontMetrics().elidedText(
                str(app_dir), Qt.TextElideMode.ElideMiddle, 190
            )
        )
        self.dir_val.setToolTip(str(app_dir))
        vfile = get_version_file()
        self.updated_val.setText(
            fmt_time(vfile.stat().st_mtime) if installed and vfile.exists() else "—"
        )
        last = get_setting("last_launch")
        self.last_val.setText(fmt_time(last) if last else "Никогда")

        if not installed:
            self.mode = "install"
        elif self.latest and self.latest != ver:
            self.mode = "update"
        else:
            self.mode = "launch"

        texts = {"install": "Установить", "update": "Обновить", "launch": "Запустить"}
        self.primary.setText(texts[self.mode])
        is_launch = self.mode == "launch"
        self.primary.setIcon(make_icon("play" if is_launch else "download", "white", 14,
                                       fill="white" if is_launch else "none"))
        self.primary.setIconSize(QSize(14, 14))
        self.primary.setEnabled(not self.busy and not self.launching)

        if self.launching:
            text, state = "Запуск... первый раз может занять несколько минут", "info"
        elif self.busy:
            text, state = self.busy_text, "info"
        elif self.error_msg:
            text, state = f"Ошибка: {self.error_msg}", "error"
        elif self.mode == "install":
            text, state = (f"Доступно: {self.latest}" if self.latest else "Не установлено"), "info"
        elif self.mode == "update":
            text, state = f"Доступно обновление {self.latest}", "warn"
        else:
            text, state = "Программа обновлена", "ok"
        self.set_banner(text, state)
        self.load_status.setText(text)
        self.apply_page()

    # ---------- заставка ----------
    def show_main(self):
        self.spinner.stop()
        self._anim_switched = False
        self._anim_start = self.geometry()
        area = self.screen().availableGeometry() if self.screen() else None
        target = QRect(0, 0, *WINDOW_SIZE)
        if area is not None:
            target.moveCenter(area.center())
        else:
            target.moveCenter(self._anim_start.center())
        self._anim_target = target

        # размер временно не фиксирован, чтобы окно могло плавно расти
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._fade = QGraphicsOpacityEffect(self.outer)
        self._fade.setOpacity(1.0)
        self.outer.setGraphicsEffect(self._fade)

        self._ease = QEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(TRANSITION_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._anim_step)
        self._anim.finished.connect(self._anim_done)
        self._anim.start()

    @staticmethod
    def _lerp(a, b, t):
        return a + (b - a) * t

    def _anim_step(self, t):
        t = float(t)
        # 0.00-0.25: заставка гаснет; 0.20-0.80: окно растёт; 0.75-1.00: появляется интерфейс
        if t < 0.25:
            opacity = 1.0 - t / 0.25
        elif t < 0.75:
            opacity = 0.0
        else:
            opacity = (t - 0.75) / 0.25
        if t >= 0.25 and not self._anim_switched:
            self._anim_switched = True
            self.outer.setCurrentIndex(1)
            self.refresh_state()
        self._fade.setOpacity(max(0.0, min(1.0, opacity)))

        g = self._ease.valueForProgress(max(0.0, min(1.0, (t - 0.2) / 0.6)))
        a, b = self._anim_start, self._anim_target
        self.setGeometry(
            round(self._lerp(a.x(), b.x(), g)), round(self._lerp(a.y(), b.y(), g)),
            round(self._lerp(a.width(), b.width(), g)), round(self._lerp(a.height(), b.height(), g)),
        )
        self.root.bg = QColor(*(round(self._lerp(x, y, g)) for x, y in zip(self.splash_bg, self.main_bg)))
        self.root.radius = self._lerp(SPLASH_RADIUS, MAIN_RADIUS, g)
        self.root.update()
        self.update_mask()

    def _anim_done(self):
        self.outer.setGraphicsEffect(None)
        self.root.bg = QColor(*self.main_bg)
        self.root.radius = MAIN_RADIUS
        self.setFixedSize(*WINDOW_SIZE)
        self.setGeometry(self._anim_target)
        self.outer.setCurrentIndex(1)
        self.refresh_state()
        self.update_mask()

    def update_mask(self):
        """Под X11 без композитора прозрачные углы не работают, поэтому режем окно по форме."""
        if QGuiApplication.platformName() != "xcb" or not hasattr(self, "root"):
            return
        path = QPainterPath()
        radius = 0 if self.root.square else self.root.radius
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_mask()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "root") and self.root.backdrop is not None:
            self.root.update()   # фон привязан к экрану: при сдвиге окна перерисовываем

    # ---------- действия ----------
    def run_worker(self, check_only):
        if self.worker is not None and self.worker.isRunning():
            return
        self.error_msg = None
        self.busy = True
        self.install_running = not check_only
        self.voice_loading = False
        self.busy_text = "Проверка обновлений..." if check_only else "Загрузка..."
        self.load_progress.setRange(0, 100)
        self.load_progress.setValue(0)

        self.worker = UpdateWorker(check_only=check_only)
        self.worker.latest.connect(self.on_latest)
        self.worker.release_info.connect(self.on_release_info)
        self.worker.progress.connect(self.on_progress)
        self.worker.status.connect(self.on_status)
        self.worker.log.connect(self.log)
        self.worker.finished_ok.connect(self.on_done)
        self.worker.error.connect(self.on_error)
        self.refresh_state()
        self.worker.start()

    def on_latest(self, tag):
        self.latest = tag
        self.refresh_state()

    def on_release_info(self, info):
        self.release_url = info.get("url") or repo_url()
        self.news_date.setText(info.get("date") or "—")
        self.news_title.setText(info.get("title") or "Последний релиз")
        self.news_text.setText(info.get("text") or "Описание релиза не указано.")

    def on_progress(self, value):
        self.load_progress.setRange(0, 100)
        self.load_progress.setValue(value)

    def on_status(self, text):
        self.busy_text = text
        if "голос" in text.lower():
            self.voice_loading = True
        if self.busy:
            self.refresh_state()

    def on_done(self, msg):
        self.busy = False
        self.install_running = False
        self.voice_loading = False
        self.log(msg)
        self.refresh_state()
        if getattr(self.worker, "installed_now", False) and get_setting("auto_launch", True):
            self.launch()

    def on_error(self, msg):
        self.busy = False
        self.install_running = False
        self.voice_loading = False
        self.error_msg = msg.splitlines()[0][:90] if msg else "неизвестная ошибка"
        self.log(f"Ошибка: {msg}")
        self.refresh_state()

    def check_now(self):
        if not load_token():
            self.ask_token()
        self.run_worker(check_only=True)

    def reinstall(self):
        if self.busy or self.launching:
            return
        try:
            get_version_file().unlink(missing_ok=True)  # версия «забыта» -> лоадер поставит заново
        except OSError:
            pass
        self.log("Переустановка")
        self.run_worker(check_only=False)

    def on_primary(self):
        if self.mode == "launch":
            self.launch()
        else:
            if not load_token():
                self.ask_token()
            self.run_worker(check_only=False)

    def launch(self):
        if self.launching:
            return
        script = get_app_dir() / "start.sh"
        if not script.exists():
            self.error_msg = "start.sh не найден"
            self.refresh_state()
            return
        self.error_msg = None
        self.launching = True
        self.load_progress.setRange(0, 0)  # бегущая полоса: первый запуск ставит модули
        self.log("Запуск start.sh")
        self.launch_worker = LaunchWorker(script)
        self.launch_worker.log.connect(self.log)
        self.launch_worker.ok.connect(self.on_launch_ok)
        self.launch_worker.failed.connect(self.on_launch_failed)
        self.refresh_state()
        self.launch_worker.start()

    def on_launch_ok(self):
        self.launching = False
        self.load_progress.setRange(0, 100)
        self.load_progress.setValue(0)
        set_setting("last_launch", datetime.now().timestamp())
        self.log("Приложение запущено")
        self.refresh_state()
        if get_setting("close_after_launch", True):
            QTimer.singleShot(100, self.close_after_launch)

    def close_after_launch(self):
        """Лоадер сам закрывается после успешного запуска программы (плавно гаснет)."""
        for worker in (self.launch_worker, self.worker):
            if worker is not None and worker.isRunning():
                worker.wait(3000)
        self._fade_out = QVariantAnimation(self)
        self._fade_out.setDuration(150)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.valueChanged.connect(lambda v: self.setWindowOpacity(float(v)))
        self._fade_out.finished.connect(self.close)
        self._fade_out.start()

    def on_launch_failed(self, msg):
        self.launching = False
        self.load_progress.setRange(0, 100)
        self.load_progress.setValue(0)
        self.error_msg = msg
        self.log(f"Ошибка запуска: {msg}")
        self.refresh_state()

    def choose_dir(self):
        if self.busy or self.launching:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Куда установить " + APP_NAME, str(get_install_parent())
        )
        if not folder:
            return
        set_install_parent(folder)
        self.log(f"Папка установки: {get_app_dir()}")
        self.refresh_state()

    def ask_token(self):
        text, ok = QInputDialog.getText(
            self, "Токен GitHub", "Вставь токен (read-only):",
            QLineEdit.EchoMode.Password,
        )
        if ok and text.strip():
            save_token(text)
            self.log("Токен сохранён")
