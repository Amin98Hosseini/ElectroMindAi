"""Dark theme stylesheet and chat bubble HTML templates."""
from html import escape as _escape

DARK = """
QMainWindow, QWidget { background: #1e1f24; color: #e8e8ea; font-size: 13px; }
QGroupBox { border: 1px solid #3a3b42; border-radius: 8px; margin-top: 12px; padding-top: 8px;
            font-weight: bold; color: #aab; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QListWidget, QTextBrowser, QPlainTextEdit, QLineEdit {
    background: #26272e; border: 1px solid #3a3b42; border-radius: 8px; padding: 6px; }
QListWidget::item { padding: 8px; border-radius: 6px; }
QListWidget::item:selected { background: #3d5a99; }
QPushButton { background: #3d5a99; border: none; border-radius: 8px; padding: 8px 14px;
              font-weight: bold; color: white; }
QPushButton:hover { background: #4a6cb4; }
QPushButton:disabled { background: #33343b; color: #777; }
QPushButton#danger { background: #993d3d; }
QPushButton#danger:hover { background: #b44a4a; }
QPushButton#ghost { background: #33343b; }
QPushButton#ghost:hover { background: #41424b; }
QSpinBox, QDoubleSpinBox { background: #26272e; border: 1px solid #3a3b42;
    border-radius: 6px; padding: 4px; }
QSplitter::handle { background: #3a3b42; }
QCheckBox { spacing: 6px; }
QProgressBar { background: #26272e; border: 1px solid #3a3b42; border-radius: 6px;
    text-align: center; height: 14px; }
QProgressBar::chunk { background: #3d5a99; border-radius: 4px; }
QLabel#dim { color: #888; }
"""

BUBBLE_USER = ("<div style='text-align:right; margin:6px 0;'>"
               "<span style='display:inline-block; background:#3d5a99; color:white;"
               " border-radius:10px; padding:8px 12px; max-width:80%; text-align:left;'>__MSG__</span></div>")
BUBBLE_AI = ("<div style='text-align:left; margin:6px 0;'>"
             "<span style='display:inline-block; background:#2f3038; color:#e8e8ea;"
             " border-radius:10px; padding:8px 12px; max-width:85%; text-align:left;'>__MSG__</span></div>")
BUBBLE_THINK = ("<div style='text-align:left; margin:6px 0;'>"
                "<span style='display:inline-block; background:#2a2620; color:#c9a86a;"
                " border-radius:10px; padding:6px 12px; font-style:italic;'>__MSG__</span></div>")


def bubble(template, msg):
    """Fill a bubble template with (already HTML-escaped) message text."""
    return template.replace("__MSG__", msg)


def escaped(text: str) -> str:
    """HTML-escape text for safe embedding in a bubble."""
    return _escape(text)
