# -*- coding: utf-8 -*-
"""
Pack Studio
-----------
يولّد ملفي build.bat و installer.iss لأي مشروع PyQt5،
ويشغّل PyInstaller ثم Inno Setup من داخل البرنامج مع سجل مباشر.
"""
import sys
import os
import re
import ast
import json
import math
import shutil
import subprocess

from PyQt5.QtGui import (
    QIcon, QPainter, QLinearGradient, QRadialGradient, QColor, QBrush,
    QDesktopServices, QTextCursor
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLineEdit, QPushButton, QFrame, QVBoxLayout,
    QHBoxLayout, QLabel, QMessageBox, QFileDialog, QListWidget, QComboBox,
    QCheckBox, QPlainTextEdit
)
from PyQt5.QtCore import (
    Qt, QTimer, QPointF, QEvent, QProcess, QProcessEnvironment, QUrl, QSettings
)

APP_TITLE = "Pack Studio"
PROJECT_FILE = "pack_project.json"


def resource_path(name):
    """مسار الملفات المرفقة سواء من الكود أو من ملف exe"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# ======================================================================
#  توليد الملفات (منطق نقي بدون واجهة)
# ======================================================================
def safe_exe_name(name):
    n = re.sub(r"[^A-Za-z0-9_\-]", "", name.replace(" ", "_"))
    return n or "App"


def to_win(path):
    return path.replace("/", "\\")


def rel_or_abs(path, base):
    path = os.path.abspath(path)
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


def esc_echo(text):
    """تهريب النص داخل أمر echo في ملفات bat"""
    text = text.replace("%", "%%")
    for ch in "^&|<>()":
        text = text.replace(ch, "^" + ch)
    return text


def split_packages(text):
    return [p for p in re.split(r"[,\s]+", text.strip()) if p]


def make_build_bat(cfg, base):
    exe = safe_exe_name(cfg["name"])
    script = to_win(rel_or_abs(cfg["script"], base))
    icon = to_win(rel_or_abs(cfg["icon"], base)) if cfg["icon"] else ""
    py = "python" if cfg["venv"] else "%PY%"

    L = []
    a = L.append
    a("@echo off")
    a("setlocal")
    a("title %s Build" % exe)
    a('cd /d "%~dp0"')
    a("")
    a("set PY=python")
    a("where python >nul 2>nul")
    a("if errorlevel 1 (")
    a("    where py >nul 2>nul")
    a("    if errorlevel 1 (")
    a("        echo [ERROR] Python was not found. Install Python and tick Add Python to PATH.")
    a("        goto :fail")
    a("    )")
    a("    set PY=py")
    a(")")
    a("")

    required = [script]
    if icon:
        required.append(icon)
    for item in cfg["data"]:
        required.append(to_win(rel_or_abs(item, base)))
    seen = set()
    for p in required:
        if p.lower() in seen:
            continue
        seen.add(p.lower())
        a('if not exist "%s" (' % p)
        a("    echo [ERROR] Missing: %s" % esc_echo(p))
        a("    goto :fail")
        a(")")
    a("")

    pkgs = ["pyinstaller"]
    if cfg["pyqt5"]:
        pkgs.append("PyQt5")
    pkgs += split_packages(cfg["packages"])
    pkg_text = " ".join('"%s"' % p for p in pkgs)

    if cfg["venv"]:
        a("echo [1/3] Creating a clean virtual environment...")
        a("if not exist build_env\\Scripts\\activate.bat (")
        a("    %PY% -m venv build_env")
        a("    if errorlevel 1 goto :fail")
        a(")")
        a("call build_env\\Scripts\\activate.bat")
        a("if errorlevel 1 goto :fail")
        a("")
        a("echo [2/3] Installing packages...")
        a("python -m pip install --upgrade pip --disable-pip-version-check --progress-bar off")
    else:
        a("echo [1/3] Using the Python installed on this computer...")
        a("echo [2/3] Installing packages...")
    a("%s -m pip install --disable-pip-version-check --progress-bar off %s" % (py, pkg_text))
    a("if errorlevel 1 goto :fail")
    a("")

    a("echo [3/3] Building the application...")
    parts = [py, "-m PyInstaller --noconfirm --clean"]
    parts.append("--onefile" if cfg["mode"] == "onefile" else "--onedir")
    if cfg["windowed"]:
        parts.append("--windowed")
    parts.append("--name %s" % exe)
    if icon:
        parts.append('--icon "%s"' % icon)
    for item in cfg["data"]:
        src = to_win(rel_or_abs(item, base))
        dest = os.path.basename(item.rstrip("/\\")) if os.path.isdir(item) else "."
        parts.append('--add-data "%s;%s"' % (src, dest))
    for mod in cfg.get("exclude", []):
        parts.append("--exclude-module %s" % mod)
    parts.append('"%s"' % script)
    a(" ".join(parts))
    a("if errorlevel 1 goto :fail")
    a("")
    a("echo.")
    if cfg["mode"] == "onefile":
        a("echo DONE. Your app is in: dist\\%s.exe" % exe)
    else:
        a("echo DONE. Your app is in: dist\\%s\\%s.exe" % (exe, exe))
    a('if /i not "%~1"=="nopause" pause')
    a("exit /b 0")
    a("")
    a(":fail")
    a("echo.")
    a("echo [ERROR] The build failed. Read the messages above.")
    a('if /i not "%~1"=="nopause" pause')
    a("exit /b 1")
    return "\r\n".join(L) + "\r\n"


def iss_text(value):
    return value.replace('"', "").replace("{", "").replace("}", "").strip()


def make_iss(cfg, base):
    exe = safe_exe_name(cfg["name"])
    name = iss_text(cfg["name"]) or exe
    icon = to_win(rel_or_abs(cfg["icon"], base)) if cfg["icon"] else ""

    L = []
    a = L.append
    a("; Inno Setup script (works with Inno Setup 5.5 and newer)")
    a("; Generated by %s" % APP_TITLE)
    a("[Setup]")
    a("AppName=%s" % name)
    a("AppVersion=%s" % (iss_text(cfg["version"]) or "1.0"))
    if cfg["publisher"].strip():
        a("AppPublisher=%s" % iss_text(cfg["publisher"]))
    a("DefaultDirName={pf}\\%s" % name)
    a("DefaultGroupName=%s" % name)
    a("OutputBaseFilename=%s_Setup" % exe)
    if icon:
        a("SetupIconFile=%s" % icon)
    a("UninstallDisplayIcon={app}\\%s.exe" % exe)
    a("Compression=lzma2/max")
    a("SolidCompression=yes")
    a("")
    a("[Files]")
    if cfg["mode"] == "onefile":
        a('Source: "dist\\%s.exe"; DestDir: "{app}"; Flags: ignoreversion' % exe)
    else:
        a('Source: "dist\\%s\\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion' % exe)
    a("")
    a("[Icons]")
    a('Name: "{group}\\%s"; Filename: "{app}\\%s.exe"' % (name, exe))
    if cfg["desktop"]:
        a('Name: "{commondesktop}\\%s"; Filename: "{app}\\%s.exe"; Tasks: desktopicon' % (name, exe))
        a("")
        a("[Tasks]")
        a('Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked')
    return "\r\n".join(L) + "\r\n"


def has_non_ascii(*texts):
    for t in texts:
        try:
            t.encode("ascii")
        except UnicodeEncodeError:
            return True
    return False


def oem_encoding():
    try:
        import ctypes
        return "cp%d" % ctypes.windll.kernel32.GetOEMCP()
    except Exception:
        return "utf-8"


# ======================================================================
#  اكتشاف المكتبات المستوردة تلقائيًا
# ======================================================================
STDLIB = set("""
__future__ _thread abc aifc antigravity argparse array ast asynchat asyncio asyncore atexit audioop
base64 bdb binascii binhex bisect builtins bz2 cProfile calendar cgi cgitb chunk cmath cmd code codecs
codeop collections colorsys compileall concurrent configparser contextlib contextvars copy copyreg
crypt csv ctypes curses dataclasses datetime dbm decimal difflib dis distutils doctest email encodings
ensurepip enum errno faulthandler fcntl filecmp fileinput fnmatch fractions ftplib functools gc
genericpath getopt getpass gettext glob graphlib grp gzip hashlib heapq hmac html http idlelib imaplib
imghdr imp importlib inspect io ipaddress itertools json keyword lib2to3 linecache locale logging lzma
mailbox mailcap marshal math mimetypes mmap modulefinder msilib msvcrt multiprocessing netrc nis nntplib
nt ntpath nturl2path numbers opcode operator optparse os ossaudiodev pathlib pdb pickle pickletools
pipes pkgutil platform plistlib poplib posix posixpath pprint profile pstats pty pwd py_compile pyclbr
pydoc pydoc_data pyexpat queue quopri random re readline reprlib resource rlcompleter runpy sched
secrets select selectors shelve shlex shutil signal site smtpd smtplib sndhdr socket socketserver spwd
sqlite3 sre_compile sre_constants sre_parse ssl stat statistics string stringprep struct subprocess
sunau symtable sys sysconfig syslog tabnanny tarfile telnetlib tempfile termios test textwrap this
threading time timeit tkinter token tokenize tomllib trace traceback tracemalloc tty turtle turtledemo
types typing unicodedata unittest urllib uu uuid venv warnings wave weakref webbrowser winreg winsound
wsgiref xdrlib xml xmlrpc zipapp zipfile zipimport zlib zoneinfo
""".split())

# اسم الاستيراد  ->  اسم الحزمة في pip (عندما يختلفان)
PIP_NAMES = {
    "cv2": "opencv-python", "PIL": "Pillow", "yaml": "PyYAML", "sklearn": "scikit-learn",
    "skimage": "scikit-image", "bs4": "beautifulsoup4", "serial": "pyserial",
    "dateutil": "python-dateutil", "docx": "python-docx", "pptx": "python-pptx",
    "fitz": "PyMuPDF", "OpenGL": "PyOpenGL", "Crypto": "pycryptodome", "jwt": "PyJWT",
    "dotenv": "python-dotenv", "attr": "attrs", "usb": "pyusb", "win32com": "pywin32",
    "win32api": "pywin32", "win32con": "pywin32", "win32gui": "pywin32", "win32file": "pywin32",
    "pythoncom": "pywin32", "pywintypes": "pywin32", "win32clipboard": "pywin32",
    "win32process": "pywin32", "win32print": "pywin32", "win32event": "pywin32",
    "magic": "python-magic", "zmq": "pyzmq", "git": "GitPython", "ruamel": "ruamel.yaml",
}
SKIP_IMPORTS = {"PyQt5", "PyInstaller", "__main__", "sip"}
SKIP_DIRS = {"build", "dist", "build_env", "venv", ".venv", "env", "__pycache__", "output", "Output"}


def _imports_of(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        tree = ast.parse(f.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def scan_imports(script):
    """يحلل الملف الرئيسي وكل الملفات المحلية التي يستوردها، ويرجع المكتبات الخارجية"""
    base = os.path.dirname(os.path.abspath(script))
    visited, queue = set(), [os.path.abspath(script)]
    all_names, local, errors = set(), set(), []
    while queue:
        path = queue.pop()
        if path in visited:
            continue
        visited.add(path)
        try:
            names = _imports_of(path)
        except (OSError, SyntaxError, ValueError) as exc:
            errors.append("%s: %s" % (os.path.basename(path), exc))
            continue
        for n in names:
            all_names.add(n)
            as_file = os.path.join(base, n + ".py")
            as_pkg = os.path.join(base, n)
            if os.path.isfile(as_file):
                local.add(n)
                queue.append(as_file)
            elif os.path.isdir(as_pkg):
                local.add(n)
                for root, dirs, files in os.walk(as_pkg):
                    dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
                    queue.extend(os.path.join(root, f) for f in files if f.endswith(".py"))
    third = sorted(n for n in all_names
                   if n not in STDLIB and n not in local and n not in SKIP_IMPORTS)
    pip_names = []
    for n in third:
        p = PIP_NAMES.get(n, n)
        if p not in pip_names:
            pip_names.append(p)
    return {
        "packages": pip_names,
        "uses_pyqt5": "PyQt5" in all_names,
        "local": sorted(local),
        "errors": errors,
        "files": len(visited),
    }


# ======================================================================
#  التصميم
# ======================================================================
STYLE = """
QWidget {
    font-family: "Segoe UI", "Cairo", "Tahoma";
    font-size: 13px;
    color: #e8ecff;
}
QLabel#title { font-size: 22px; font-weight: 700; color: #ffffff; letter-spacing: 1px; }
QLabel#subtitle { font-size: 11px; color: rgba(190, 200, 255, 150); }
QLabel#card_title { font-size: 14px; font-weight: 700; color: #9ff7ff; }
QLabel#field { font-size: 12px; color: rgba(200, 210, 255, 190); }

QFrame#card {
    background: rgba(255, 255, 255, 14);
    border: 1px solid rgba(94, 242, 255, 90);
    border-radius: 16px;
}

QLineEdit, QComboBox {
    background: rgba(255, 255, 255, 18);
    border: 1px solid rgba(255, 255, 255, 40);
    border-radius: 10px;
    padding: 7px 10px;
    color: #ffffff;
    selection-background-color: #7c5cff;
    min-height: 20px;
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid #5ef2ff;
    background: rgba(94, 242, 255, 22);
}
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView {
    background: #1a1440;
    color: #ffffff;
    border: 1px solid #7c5cff;
    selection-background-color: #7c5cff;
}

QListWidget {
    background: rgba(255, 255, 255, 14);
    border: 1px solid rgba(255, 255, 255, 40);
    border-radius: 10px;
    padding: 4px;
    color: #ffffff;
}
QListWidget::item { padding: 4px; border-radius: 6px; }
QListWidget::item:selected { background: rgba(124, 92, 255, 160); color: #ffffff; }

QPlainTextEdit {
    background: rgba(5, 8, 22, 190);
    border: 1px solid rgba(255, 255, 255, 40);
    border-radius: 12px;
    padding: 8px;
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-size: 12px;
    color: #b9f7d6;
}

QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 18px; height: 18px;
    border-radius: 5px;
    border: 1px solid rgba(255, 255, 255, 100);
    background: rgba(255, 255, 255, 20);
}
QCheckBox::indicator:checked {
    border: 1px solid #5ef2ff;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #22e1ff, stop:1 #7c5cff);
}

QPushButton {
    border: none;
    border-radius: 12px;
    font-weight: 600;
    min-height: 34px;
    padding: 0 14px;
    color: #f4f6ff;
    background: rgba(255, 255, 255, 22);
    border: 1px solid rgba(255, 255, 255, 30);
}
QPushButton:hover { background: rgba(255, 255, 255, 46); border: 1px solid rgba(94, 242, 255, 200); }
QPushButton:pressed { background: rgba(94, 242, 255, 90); }
QPushButton:disabled { color: rgba(255, 255, 255, 80); background: rgba(255, 255, 255, 10); border: 1px solid rgba(255,255,255,15); }

QPushButton[kind="small"] { min-height: 30px; padding: 0 10px; font-size: 12px; }

QPushButton[kind="ha"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 rgba(124, 92, 255, 150), stop:1 rgba(190, 90, 255, 150));
    border: 1px solid rgba(190, 150, 255, 140);
}
QPushButton[kind="ha"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 rgba(150, 120, 255, 220), stop:1 rgba(215, 120, 255, 220));
}

QPushButton[kind="eq"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22e1ff, stop:1 #7c5cff);
    color: #0b1020;
    font-weight: 800;
    font-size: 14px;
    min-height: 44px;
}
QPushButton[kind="eq"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6af0ff, stop:1 #9b82ff);
}
QPushButton[kind="eq"]:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #14b8d4, stop:1 #5a3fe0);
}
QPushButton[kind="eq"]:disabled { color: rgba(11,16,32,120); background: rgba(255,255,255,25); }

QPushButton[kind="clear"] {
    background: rgba(255, 90, 120, 60);
    border: 1px solid rgba(255, 110, 140, 130);
    color: #ffb3c1;
}
QPushButton[kind="clear"]:hover { background: rgba(255, 90, 120, 120); }

QPushButton#info {
    border-radius: 19px;
    min-height: 38px; max-height: 38px; min-width: 38px; max-width: 38px;
    padding: 0; font-size: 16px; font-weight: 700;
}

QMessageBox { background-color: #151033; }
QMessageBox QLabel { color: #e8ecff; font-size: 14px; background: transparent; }
QMessageBox QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #22e1ff, stop:1 #7c5cff);
    color: #0b1020; border-radius: 10px; min-width: 90px; min-height: 32px; font-weight: 700;
}
QToolTip { background: #1a1440; color: #ffffff; border: 1px solid #7c5cff; padding: 4px; }
"""

DEFAULTS = {
    "script": "", "name": "", "version": "1.0", "publisher": "", "icon": "",
    "data": [], "packages": "", "mode": "onedir", "windowed": True,
    "venv": True, "pyqt5": True, "desktop": True,
}


class PackStudio(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon(resource_path("packstudio.ico")))
        self.resize(960, 780)
        self.setMinimumSize(900, 740)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)

        self.settings = QSettings("PackStudio", "PackStudio")
        self._enc = oem_encoding()
        self._on_done = None

        # خلفية متحركة
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

        # العملية الخارجية
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyRead.connect(self._read_output)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._proc_error)

        self._build_ui()
        self.log_line("✦ %s جاهز. اختر الملف الرئيسي (.py) أو اسحبه إلى النافذة." % APP_TITLE)

    # ------------------------------------------------------------------
    #  بناء الواجهة
    # ------------------------------------------------------------------
    def _field(self, text, widget):
        box = QVBoxLayout()
        box.setSpacing(4)
        lbl = QLabel(text)
        lbl.setObjectName("field")
        box.addWidget(lbl)
        if isinstance(widget, QWidget):
            box.addWidget(widget)
        else:
            box.addLayout(widget)
        return box

    def _ltr(self, widget):
        widget.setLayoutDirection(Qt.LeftToRight)
        return widget

    def _button(self, text, kind, slot, tip=""):
        b = QPushButton(text)
        b.setProperty("kind", kind)
        b.setCursor(Qt.PointingHandCursor)
        if tip:
            b.setToolTip(tip)
        b.clicked.connect(slot)
        return b

    def _path_row(self, edit, slot):
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(edit, 1)
        row.addWidget(self._button("تصفّح", "small", slot))
        return row

    def _build_ui(self):
        # الترويسة
        title = QLabel("✦ %s" % APP_TITLE)
        title.setObjectName("title")
        subtitle = QLabel("مولّد ملفات build و installer لبرامج PyQt5")
        subtitle.setObjectName("subtitle")
        tbox = QVBoxLayout()
        tbox.setSpacing(0)
        tbox.addWidget(title)
        tbox.addWidget(subtitle)

        info = QPushButton("i")
        info.setObjectName("info")
        info.setCursor(Qt.PointingHandCursor)
        info.setToolTip("معلومات حول البرنامج")
        info.clicked.connect(self.show_info)

        header = QHBoxLayout()
        header.addLayout(tbox)
        header.addStretch()
        header.addWidget(info)

        # بطاقة 1: بيانات البرنامج
        self.script_edit = self._ltr(QLineEdit())
        self.script_edit.setPlaceholderText("C:\\...\\main.py")
        self.script_edit.setAcceptDrops(False)
        self.script_edit.editingFinished.connect(self._script_changed)
        self.name_edit = self._ltr(QLineEdit())
        self.name_edit.setPlaceholderText("Armatures")
        self.version_edit = self._ltr(QLineEdit("1.0"))
        self.publisher_edit = self._ltr(QLineEdit())
        self.icon_edit = self._ltr(QLineEdit())
        self.icon_edit.setPlaceholderText("calculator.ico")
        self.icon_edit.setAcceptDrops(False)
        self.pkg_edit = self._ltr(QLineEdit())
        self.pkg_edit.setPlaceholderText("numpy matplotlib ...")

        c1 = QFrame()
        c1.setObjectName("card")
        l1 = QVBoxLayout(c1)
        l1.setContentsMargins(16, 12, 16, 14)
        l1.setSpacing(8)
        t1 = QLabel("① بيانات البرنامج")
        t1.setObjectName("card_title")
        l1.addWidget(t1)
        l1.addLayout(self._field("الملف الرئيسي (.py)", self._path_row(self.script_edit, self.browse_script)))
        l1.addLayout(self._field("اسم البرنامج", self.name_edit))
        vp = QHBoxLayout()
        vp.setSpacing(8)
        vp.addLayout(self._field("الإصدار", self.version_edit), 1)
        vp.addLayout(self._field("الناشر / المطوّر", self.publisher_edit), 2)
        l1.addLayout(vp)
        l1.addLayout(self._field("الأيقونة (.ico)", self._path_row(self.icon_edit, self.browse_icon)))
        pkg_row = QHBoxLayout()
        pkg_row.setSpacing(6)
        pkg_row.addWidget(self.pkg_edit, 1)
        pkg_row.addWidget(self._button("🔍 اكتشاف تلقائي", "small", self.detect_packages,
                                       "يحلل الكود ويستخرج المكتبات التي يستوردها"))
        l1.addLayout(self._field("مكتبات إضافية (تُثبَّت في البيئة)", pkg_row))
        l1.addStretch()

        # بطاقة 2: الملفات المرفقة والخيارات
        self.data_list = self._ltr(QListWidget())
        self.data_list.setMinimumHeight(110)
        self.data_list.setSelectionMode(QListWidget.ExtendedSelection)
        brow = QHBoxLayout()
        brow.setSpacing(6)
        brow.addWidget(self._button("＋ ملفات", "small", self.add_files))
        brow.addWidget(self._button("＋ مجلد", "small", self.add_folder))
        brow.addWidget(self._button("حذف", "clear", self.remove_selected))
        data_box = QVBoxLayout()
        data_box.setSpacing(6)
        data_box.addWidget(self.data_list)
        data_box.addLayout(brow)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("مجلد (onedir) – إقلاع أسرع، يُنصح به", "onedir")
        self.mode_combo.addItem("ملف واحد (onefile) – إقلاع أبطأ", "onefile")
        self.chk_windowed = QCheckBox("إخفاء نافذة الأوامر (برنامج واجهة)")
        self.chk_pyqt5 = QCheckBox("البرنامج يستعمل PyQt5")
        self.chk_venv = QCheckBox("بيئة افتراضية نظيفة (حجم أصغر)")
        self.chk_desktop = QCheckBox("خيار اختصار سطح المكتب في المثبّت")
        for c in (self.chk_windowed, self.chk_pyqt5, self.chk_venv, self.chk_desktop):
            c.setChecked(True)
            c.setCursor(Qt.PointingHandCursor)

        c2 = QFrame()
        c2.setObjectName("card")
        l2 = QVBoxLayout(c2)
        l2.setContentsMargins(16, 12, 16, 14)
        l2.setSpacing(8)
        t2 = QLabel("② الملفات المرفقة والخيارات")
        t2.setObjectName("card_title")
        l2.addWidget(t2)
        l2.addLayout(self._field("ملفات/مجلدات يحتاجها البرنامج (أيقونات، صور، بيانات)", data_box))
        l2.addLayout(self._field("طريقة التجميع", self.mode_combo))
        l2.addWidget(self.chk_windowed)
        l2.addWidget(self.chk_pyqt5)
        l2.addWidget(self.chk_venv)
        l2.addWidget(self.chk_desktop)
        l2.addStretch()

        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(c1, 1)
        body.addWidget(c2, 1)

        # الأزرار
        self.btn_gen = self._button("① توليد الملفات", "ha", self.generate_files,
                                    "يكتب build.bat و installer.iss بجانب الملف الرئيسي")
        self.btn_exe = self._button("② بناء EXE", "eq", self.build_exe,
                                    "يولّد الملفات ثم يشغّل PyInstaller")
        self.btn_setup = self._button("③ بناء ملف التثبيت", "eq", self.build_installer,
                                      "يشغّل Inno Setup على installer.iss")
        self.btn_open = self._button("📂 فتح المجلد", "ha", self.open_folder)
        self.btn_stop = self._button("■ إيقاف", "clear", self.stop_process)
        self.btn_stop.setEnabled(False)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self.btn_gen)
        actions.addWidget(self.btn_exe, 1)
        actions.addWidget(self.btn_setup, 1)
        actions.addWidget(self.btn_open)
        actions.addWidget(self.btn_stop)

        # السجل
        self.log = self._ltr(QPlainTextEdit())
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 18)
        root.setSpacing(12)
        root.addLayout(header)
        root.addLayout(body)
        root.addLayout(actions)
        root.addWidget(self.log, 1)

    # ------------------------------------------------------------------
    #  خلفية متحركة
    # ------------------------------------------------------------------
    def _tick(self):
        self._phase += 0.025
        self.update()

    def showEvent(self, event):
        self._timer.start(50)
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                self._timer.stop()
            else:
                self._timer.start(50)
        super().changeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0.0, QColor("#0a0e22"))
        base.setColorAt(1.0, QColor("#1a1140"))
        p.fillRect(self.rect(), QBrush(base))
        t = self._phase
        blobs = [
            (0.20 + 0.18 * math.sin(t * 0.9), 0.20 + 0.15 * math.cos(t * 0.7), 300, (94, 242, 255)),
            (0.85 + 0.10 * math.cos(t * 0.8), 0.45 + 0.20 * math.sin(t * 1.1), 320, (160, 90, 255)),
            (0.50 + 0.25 * math.sin(t * 0.6 + 2), 0.92 + 0.06 * math.cos(t * 0.9), 300, (255, 90, 170)),
        ]
        p.setPen(Qt.NoPen)
        for fx, fy, radius, (r, g, b) in blobs:
            center = QPointF(fx * w, fy * h)
            grad = QRadialGradient(center, radius)
            grad.setColorAt(0.0, QColor(r, g, b, 80))
            grad.setColorAt(1.0, QColor(r, g, b, 0))
            p.setBrush(QBrush(grad))
            p.drawEllipse(center, radius, radius)
        p.end()

    # ------------------------------------------------------------------
    #  السحب والإفلات
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith((".py", ".pyw")):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".py", ".pyw")):
                self.script_edit.setText(os.path.normpath(path))
                self._script_changed()
                break

    # ------------------------------------------------------------------
    #  السجل
    # ------------------------------------------------------------------
    def log_line(self, text):
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText(text + "\n")
        self.log.moveCursor(QTextCursor.End)
        self.log.ensureCursorVisible()

    # ------------------------------------------------------------------
    #  اختيار الملفات
    # ------------------------------------------------------------------
    def browse_script(self):
        start = os.path.dirname(self.script_edit.text()) or ""
        path, _ = QFileDialog.getOpenFileName(self, "اختر الملف الرئيسي", start, "Python (*.py *.pyw)")
        if path:
            self.script_edit.setText(os.path.normpath(path))
            self._script_changed()

    def browse_icon(self):
        start = os.path.dirname(self.script_edit.text()) or ""
        path, _ = QFileDialog.getOpenFileName(self, "اختر الأيقونة", start, "Icon (*.ico)")
        if path:
            self.icon_edit.setText(os.path.normpath(path))

    def add_files(self):
        start = os.path.dirname(self.script_edit.text()) or ""
        paths, _ = QFileDialog.getOpenFileNames(self, "اختر ملفات مرفقة", start, "All files (*)")
        for p in paths:
            self._add_data(os.path.normpath(p))

    def add_folder(self):
        start = os.path.dirname(self.script_edit.text()) or ""
        path = QFileDialog.getExistingDirectory(self, "اختر مجلدًا مرفقًا", start)
        if path:
            self._add_data(os.path.normpath(path))

    def _add_data(self, path):
        existing = [self.data_list.item(i).text() for i in range(self.data_list.count())]
        if path not in existing:
            self.data_list.addItem(path)

    def remove_selected(self):
        for item in self.data_list.selectedItems():
            self.data_list.takeItem(self.data_list.row(item))

    # ------------------------------------------------------------------
    #  الإعدادات
    # ------------------------------------------------------------------
    def collect_cfg(self):
        return {
            "script": self.script_edit.text().strip().strip('"'),
            "name": self.name_edit.text().strip(),
            "version": self.version_edit.text().strip(),
            "publisher": self.publisher_edit.text().strip(),
            "icon": self.icon_edit.text().strip().strip('"'),
            "data": [self.data_list.item(i).text() for i in range(self.data_list.count())],
            "packages": self.pkg_edit.text().strip(),
            "mode": self.mode_combo.currentData(),
            "windowed": self.chk_windowed.isChecked(),
            "venv": self.chk_venv.isChecked(),
            "pyqt5": self.chk_pyqt5.isChecked(),
            "desktop": self.chk_desktop.isChecked(),
        }

    def apply_cfg(self, cfg):
        c = dict(DEFAULTS)
        c.update(cfg)
        base = os.path.dirname(self.script_edit.text().strip())

        def absolute(p):
            return p if (not p or os.path.isabs(p)) else os.path.normpath(os.path.join(base, p))

        self.name_edit.setText(c["name"])
        self.version_edit.setText(c["version"])
        self.publisher_edit.setText(c["publisher"])
        self.icon_edit.setText(absolute(c["icon"]))
        self.pkg_edit.setText(c["packages"])
        self.mode_combo.setCurrentIndex(1 if c["mode"] == "onefile" else 0)
        self.chk_windowed.setChecked(bool(c["windowed"]))
        self.chk_venv.setChecked(bool(c["venv"]))
        self.chk_pyqt5.setChecked(bool(c["pyqt5"]))
        self.chk_desktop.setChecked(bool(c["desktop"]))
        self.data_list.clear()
        for p in c["data"]:
            self._add_data(absolute(p))

    def detect_packages(self, checked=False, auto=False):
        script = self.script_edit.text().strip().strip('"')
        if not script or not os.path.isfile(script):
            if not auto:
                QMessageBox.warning(self, APP_TITLE, "اختر الملف الرئيسي (.py) أولًا.")
            return
        result = scan_imports(script)
        current = split_packages(self.pkg_edit.text())
        merged = list(current)
        for p in result["packages"]:
            if p.lower() not in [c.lower().split("==")[0].split(">=")[0] for c in merged]:
                merged.append(p)
        self.pkg_edit.setText(" ".join(merged))
        if result["uses_pyqt5"]:
            self.chk_pyqt5.setChecked(True)
        self.log_line("🔍 حُلّل %d ملف py. المكتبات الخارجية: %s" % (
            result["files"], " ".join(result["packages"]) or "لا شيء"))
        if result["local"]:
            self.log_line("   ملفات محلية تابعة للمشروع (لا تُثبَّت): %s" % " ".join(result["local"]))
        for err in result["errors"]:
            self.log_line("⚠ تعذّر تحليل %s" % err)
        if result["packages"]:
            self.log_line("   تحقق من الأسماء: أي مكتبة اختيارية أو تُستورد ديناميكيًا قد لا تظهر هنا.")

    def _script_changed(self):
        script = self.script_edit.text().strip().strip('"')
        if not script or not os.path.isfile(script):
            return
        folder = os.path.dirname(os.path.abspath(script))
        project = os.path.join(folder, PROJECT_FILE)
        if os.path.isfile(project):
            try:
                with open(project, "r", encoding="utf-8") as f:
                    self.apply_cfg(json.load(f))
                self.log_line("↺ تم تحميل إعدادات المشروع المحفوظة (%s)." % PROJECT_FILE)
                return
            except Exception as exc:
                self.log_line("⚠ تعذّر قراءة %s: %s" % (PROJECT_FILE, exc))
        # مشروع جديد: اقتراحات تلقائية
        if not self.name_edit.text().strip():
            stem = os.path.splitext(os.path.basename(script))[0]
            self.name_edit.setText(stem.replace("_", " ").strip().title().replace(" ", ""))
        icons = sorted(f for f in os.listdir(folder) if f.lower().endswith(".ico"))
        if icons:
            if not self.icon_edit.text().strip():
                pick = next((i for i in icons if "calc" in i.lower() or "app" in i.lower()), icons[0])
                self.icon_edit.setText(os.path.join(folder, pick))
            if self.data_list.count() == 0:
                for i in icons:
                    self._add_data(os.path.join(folder, i))
            self.log_line("✦ عُثر على %d أيقونة (.ico) في المجلد وأُضيفت للملفات المرفقة." % len(icons))
        if not self.pkg_edit.text().strip():
            self.detect_packages(auto=True)

    # ------------------------------------------------------------------
    #  التوليد
    # ------------------------------------------------------------------
    def _validate(self, cfg):
        if not cfg["script"] or not os.path.isfile(cfg["script"]):
            QMessageBox.warning(self, APP_TITLE, "اختر ملف البرنامج الرئيسي (.py) أولًا.")
            return False
        if not cfg["name"]:
            QMessageBox.warning(self, APP_TITLE, "اكتب اسم البرنامج.")
            return False
        if cfg["icon"] and not os.path.isfile(cfg["icon"]):
            QMessageBox.warning(self, APP_TITLE, "ملف الأيقونة غير موجود:\n%s" % cfg["icon"])
            return False
        return True

    def generate_files(self):
        cfg = self.collect_cfg()
        if not self._validate(cfg):
            return False
        base = os.path.dirname(os.path.abspath(cfg["script"]))

        # لا نستبعد tkinter إذا كان البرنامج يستعمله
        try:
            with open(cfg["script"], "r", encoding="utf-8", errors="ignore") as f:
                source = f.read()
        except OSError:
            source = ""
        exclude = ["unittest"]
        if not re.search(r"\b[Tt]kinter\b", source):
            exclude.append("tkinter")
        cfg["exclude"] = exclude

        bat = make_build_bat(cfg, base)
        iss = make_iss(cfg, base)
        try:
            with open(os.path.join(base, "build.bat"), "w", encoding="ascii", errors="replace", newline="") as f:
                f.write(bat)
            with open(os.path.join(base, "installer.iss"), "w", encoding="ascii", errors="replace", newline="") as f:
                f.write(iss)
            saved = dict(cfg)
            saved.pop("exclude", None)
            saved["script"] = os.path.basename(cfg["script"])
            saved["icon"] = rel_or_abs(cfg["icon"], base) if cfg["icon"] else ""
            saved["data"] = [rel_or_abs(p, base) for p in cfg["data"]]
            with open(os.path.join(base, PROJECT_FILE), "w", encoding="utf-8") as f:
                json.dump(saved, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            QMessageBox.critical(self, APP_TITLE, "تعذّرت الكتابة في المجلد:\n%s" % exc)
            return False

        self.log_line("✔ تم إنشاء build.bat و installer.iss في:\n   %s" % base)
        if has_non_ascii(bat, iss, base):
            self.log_line("⚠ توجد أحرف غير إنجليزية في الأسماء أو المسارات؛ "
                          "قد لا يعمل build.bat أو Inno Setup 5 معها. الأفضل استعمال أسماء ومسارات إنجليزية.")
        return True

    # ------------------------------------------------------------------
    #  تشغيل العمليات
    # ------------------------------------------------------------------
    def _set_busy(self, busy):
        for b in (self.btn_gen, self.btn_exe, self.btn_setup):
            b.setEnabled(not busy)
        self.btn_stop.setEnabled(busy)

    def _start(self, program, args, cwd, on_done=None):
        if self.proc.state() != QProcess.NotRunning:
            return
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        self.proc.setProcessEnvironment(env)
        self.proc.setWorkingDirectory(cwd)
        self._on_done = on_done
        self._set_busy(True)
        self.log_line("\n▶ %s %s" % (os.path.basename(program), " ".join(args)))
        self.proc.start(program, args)

    def _read_output(self):
        text = bytes(self.proc.readAll()).decode(self._enc, errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(QTextCursor.End)
        self.log.ensureCursorVisible()

    def _finished(self, code, status):
        self._set_busy(False)
        ok = code == 0 and status == QProcess.NormalExit
        self.log_line("✔ انتهت العملية بنجاح." if ok else "✖ فشلت العملية (الرمز %s). راجع الرسائل أعلاه." % code)
        callback, self._on_done = self._on_done, None
        if callback:
            callback(ok)

    def _proc_error(self, error):
        if error == QProcess.FailedToStart:
            self._set_busy(False)
            self._on_done = None
            self.log_line("✖ تعذّر تشغيل البرنامج الخارجي. تأكد أنه مثبّت وأن المسار صحيح.")

    def stop_process(self):
        if self.proc.state() == QProcess.NotRunning:
            return
        if os.name == "nt":
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(self.proc.processId())],
                            creationflags=0x08000000)
        else:
            self.proc.kill()
        self.log_line("■ تم إيقاف العملية.")

    def build_exe(self):
        if not self.generate_files():
            return
        base = os.path.dirname(os.path.abspath(self.script_edit.text().strip().strip('"')))
        if os.name != "nt":
            QMessageBox.information(self, APP_TITLE, "بناء ملف exe يعمل على ويندوز فقط. تم توليد الملفات.")
            return
        self._start("cmd.exe", ["/c", "build.bat", "nopause"], base)

    def _output_exe(self, cfg, base):
        exe = safe_exe_name(cfg["name"])
        if cfg["mode"] == "onefile":
            return os.path.join(base, "dist", exe + ".exe")
        return os.path.join(base, "dist", exe, exe + ".exe")

    def _detect_iscc(self):
        """يبحث عن كل نسخ Inno Setup المثبّتة ويرجع الأحدث أولًا"""
        roots = []
        for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            root = os.environ.get(var)
            if root and root not in roots:
                roots.append(root)
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(os.path.join(local, "Programs"))
        found = []
        for root in roots:
            if not os.path.isdir(root):
                continue
            for entry in os.listdir(root):
                if entry.lower().startswith("inno setup"):
                    path = os.path.join(root, entry, "ISCC.exe")
                    if os.path.isfile(path) and path not in found:
                        found.append(path)
        which = shutil.which("ISCC.exe")
        if which and which not in found:
            found.append(which)

        def version_key(path):
            m = re.search(r"Inno Setup\s*(\d+)", path, re.I)
            return int(m.group(1)) if m else 0

        found.sort(key=version_key, reverse=True)
        return found

    def find_iscc(self):
        detected = self._detect_iscc()
        if detected:
            self.settings.setValue("iscc", detected[0])
            return detected[0]
        saved = self.settings.value("iscc", "")
        if saved and os.path.isfile(saved):
            return saved
        QMessageBox.information(self, APP_TITLE,
                                "لم أجد Inno Setup تلقائيًا.\nاختر الملف ISCC.exe من مجلد تثبيته.")
        path, _ = QFileDialog.getOpenFileName(self, "ISCC.exe", "C:\\Program Files", "ISCC.exe")
        if path:
            self.settings.setValue("iscc", path)
            return path
        return ""

    def build_installer(self):
        if not self.generate_files():
            return
        cfg = self.collect_cfg()
        base = os.path.dirname(os.path.abspath(cfg["script"]))
        if not os.path.isfile(self._output_exe(cfg, base)):
            QMessageBox.warning(self, APP_TITLE, "ملف exe غير موجود بعد.\nاضغط «② بناء EXE» أولًا.")
            return
        iscc = self.find_iscc()
        if not iscc:
            return
        self.log_line("• Inno Setup المستعمل: %s" % iscc)
        self._start(iscc, [os.path.join(base, "installer.iss")], base, self._installer_done)

    def _installer_done(self, ok):
        if ok:
            self.log_line("🎉 ملف التثبيت جاهز في المجلد Output بجانب installer.iss")

    def open_folder(self):
        script = self.script_edit.text().strip().strip('"')
        if not script or not os.path.isfile(script):
            QMessageBox.warning(self, APP_TITLE, "اختر الملف الرئيسي أولًا.")
            return
        base = os.path.dirname(os.path.abspath(script))
        out = os.path.join(base, "Output")
        target = out if os.path.isdir(out) else base
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    # ------------------------------------------------------------------
    def show_info(self):
        link = "color:#5ef2ff; text-decoration:none;"
        html = (
            "🔹 %s – مولّد ملفات التجميع والتثبيت<br>"
            "👨‍💻 المطوّر: مرسلي حمو<br>"
            "📧 البريد الإلكتروني: "
            "<a style='%s' href='mailto:hammoutota@gmail.com'>hammoutota@gmail.com</a><br>"
            "💬 حساب التلجرام : "
            "<a style='%s' href='https://t.me/MorsliHammou'>https://t.me/MorsliHammou</a><br>"
            "📅 الإصدار: 1.0" % (APP_TITLE, link, link)
        )
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("معلومات عن البرنامج")
        box.setTextFormat(Qt.RichText)
        box.setText(html)
        label = box.findChild(QLabel, "qt_msgbox_label")
        if label is not None:
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        box.exec_()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PackStudio()
    window.show()
    sys.exit(app.exec_())
