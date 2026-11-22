import os
import sys

# Окно должно быть ровно заданного размера в физических пикселях, поэтому отключаем
# масштабирование Qt под HiDPI. Переменные нужно задать ДО создания QApplication.
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ.pop("QT_SCREEN_SCALE_FACTORS", None)

# На Wayland приложение не может само задавать позицию окна (центрирование не работает).
# Запускаем через XWayland (xcb); если он недоступен, Qt откатится на wayland.
if sys.platform.startswith("linux") and "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "xcb;wayland"

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Mimi Launcher")
    app.setOrganizationName("Mimi")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
