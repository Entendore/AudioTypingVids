import sys

# MUST configure environment BEFORE importing PySide6
from core import configure_environment
configure_environment()

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor

from core import log
from renderer import C
from gui import MainWindow

def _build_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,          QColor(C["base"]))
    pal.setColor(QPalette.ColorRole.WindowText,      QColor(C["text"]))
    pal.setColor(QPalette.ColorRole.Base,            QColor(C["mantle"]))
    pal.setColor(QPalette.ColorRole.Text,            QColor(C["text"]))
    pal.setColor(QPalette.ColorRole.Button,          QColor(C["crust"]))
    pal.setColor(QPalette.ColorRole.ButtonText,      QColor(C["text"]))
    pal.setColor(QPalette.ColorRole.Highlight,       QColor(C["mauve"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(C["crust"]))
    return pal

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Strudel Typing Animator")
    app.setOrganizationName("StrudelAnimator")
    app.setStyle("Fusion")
    app.setPalette(_build_palette())

    fp = sys.argv[1] if len(sys.argv) > 1 else None
    win = MainWindow(fp)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()