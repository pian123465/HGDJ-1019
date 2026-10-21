"""苹果风格 QSS — 模仿 macOS / iOS 视觉。

设计语言:
    - 浅灰背景 #F5F5F7(系统灰)
    - 白色卡片 + 圆角 12px
    - 主色 #007AFF(iOS Blue)
    - 文本层级: #1D1D1F(主) / #6E6E73(次) / #AEAEB2(提示)
    - Segoe UI Variable / 系统字体
"""

# 完整样式表(直接 setStyleSheet 用)
APPLE_QSS = """
/* ========== 全局 ========== */
QWidget {
    font-family: "Segoe UI Variable Display", "Segoe UI", -apple-system, "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
    color: #1D1D1F;
}

QMainWindow {
    background: #F5F5F7;
}

/* ========== 顶栏 ========== */
QFrame#sidebar {
    background: rgba(255, 255, 255, 0.85);
    border-right: 1px solid #E5E5E7;
}
QPushButton#sidebarBtn {
    background: transparent;
    border: none;
    color: #1D1D1F;
    font-size: 14px;
    padding: 10px 14px;
    text-align: left;
    border-radius: 8px;
}
QPushButton#sidebarBtn:hover {
    background: rgba(0, 0, 0, 0.04);
}
QPushButton#sidebarBtn:checked {
    background: #007AFF;
    color: white;
}
QPushButton#sidebarBtn:checked:hover {
    background: #006FE6;
}

QFrame#titlebar {
    background: rgba(245, 245, 247, 0.9);
    border-bottom: 1px solid #E5E5E7;
}
QLabel#titleLabel {
    font-size: 22px;
    font-weight: 600;
    color: #1D1D1F;
}
QLabel#subtitleLabel {
    font-size: 13px;
    color: #6E6E73;
}

/* ========== 卡片 ========== */
QFrame#card {
    background: white;
    border-radius: 12px;
    border: 1px solid #E5E5E7;
}
QFrame#card:hover {
    border: 1px solid #D2D2D7;
}

QLabel#cardTitle {
    font-size: 16px;
    font-weight: 600;
    color: #1D1D1F;
}
QLabel#cardMeta {
    font-size: 13px;
    color: #6E6E73;
}
QLabel#cardDesc {
    font-size: 13px;
    color: #6E6E73;
    background: transparent;
}

/* ========== 输入 ========== */
QLineEdit, QTextEdit, QPlainTextEdit {
    background: white;
    border: 1px solid #D2D2D7;
    border-radius: 10px;
    padding: 10px 14px;
    color: #1D1D1F;
    selection-background-color: #007AFF;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 2px solid #007AFF;
    padding: 9px 13px;
}
QLineEdit::placeholder {
    color: #AEAEB2;
}

/* ========== 按钮 ========== */
QPushButton#primaryBtn {
    background: #007AFF;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 500;
}
QPushButton#primaryBtn:hover { background: #006FE6; }
QPushButton#primaryBtn:pressed { background: #005FCC; }
QPushButton#primaryBtn:disabled { background: #AEAEB2; }

QPushButton#secondaryBtn {
    background: rgba(0, 0, 0, 0.05);
    color: #1D1D1F;
    border: none;
    border-radius: 10px;
    padding: 10px 16px;
    font-size: 14px;
}
QPushButton#secondaryBtn:hover { background: rgba(0, 0, 0, 0.08); }
QPushButton#secondaryBtn:pressed { background: rgba(0, 0, 0, 0.12); }

QPushButton#ghostBtn {
    background: transparent;
    color: #007AFF;
    border: 1px solid #007AFF;
    border-radius: 10px;
    padding: 10px 16px;
    font-size: 14px;
}
QPushButton#ghostBtn:hover { background: rgba(0, 122, 255, 0.08); }

/* ========== 分段控件(iOS style) ========== */
QWidget#segmented {
    background: rgba(0, 0, 0, 0.05);
    border-radius: 9px;
    padding: 2px;
}
QPushButton#segBtn {
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 6px 16px;
    color: #1D1D1F;
    font-size: 13px;
    font-weight: 500;
}
QPushButton#segBtn:checked {
    background: white;
    color: #1D1D1F;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
QPushButton#segBtn:!checked:hover {
    background: rgba(0, 0, 0, 0.04);
}

/* ========== 下拉 / Spin ========== */
QComboBox, QSpinBox {
    background: white;
    border: 1px solid #D2D2D7;
    border-radius: 8px;
    padding: 6px 10px;
    color: #1D1D1F;
    min-height: 18px;
}
QComboBox:hover, QSpinBox:hover { border-color: #B8B8BD; }
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background: white;
    border: 1px solid #D2D2D7;
    border-radius: 8px;
    selection-background-color: #007AFF;
    selection-color: white;
    padding: 4px;
}

/* ========== Checkbox ========== */
QCheckBox {
    spacing: 8px;
    color: #1D1D1F;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1.5px solid #D2D2D7;
    background: white;
}
QCheckBox::indicator:checked {
    background: #007AFF;
    border: 1.5px solid #007AFF;
    image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMiAxMiI+PHBvbHlnb24gcG9pbnRzPSIzLDYgOSwyIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIGZpbGw9Im5vbmUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPjwvc3ZnPg==);
}

/* ========== 列表 ========== */
QListWidget {
    background: transparent;
    border: none;
    outline: none;
}
QListWidget::item {
    background: white;
    border: 1px solid #E5E5E7;
    border-radius: 10px;
    padding: 12px;
    margin: 4px 0;
    color: #1D1D1F;
}
QListWidget::item:hover {
    border: 1px solid #D2D2D7;
    background: #FAFAFA;
}
QListWidget::item:selected {
    background: #E5F1FF;
    border: 1px solid #007AFF;
    color: #007AFF;
}

/* ========== 表格 ========== */
QTableWidget {
    background: white;
    border: 1px solid #E5E5E7;
    border-radius: 12px;
    gridline-color: #F5F5F7;
    selection-background-color: #E5F1FF;
    selection-color: #1D1D1F;
}
QHeaderView::section {
    background: #FAFAFA;
    border: none;
    padding: 8px;
    color: #6E6E73;
    font-weight: 600;
    font-size: 12px;
}

/* ========== 进度条 ========== */
QProgressBar {
    background: #E5E5E7;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background: #007AFF;
    border-radius: 4px;
}

/* ========== 滚动条 ========== */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: rgba(0, 0, 0, 0.35); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
}
QScrollBar::handle:horizontal {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 4px;
    min-width: 30px;
}

/* ========== 状态栏 ========== */
QStatusBar {
    background: transparent;
    color: #6E6E73;
    font-size: 12px;
}

/* ========== Tooltip ========== */
QToolTip {
    background: #1D1D1F;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
}
"""


# 调色板(程序里其他地方可以引用)
class Colors:
    BG = "#F5F5F7"
    CARD = "#FFFFFF"
    BORDER = "#E5E5E7"
    BORDER_HOVER = "#D2D2D7"
    PRIMARY = "#007AFF"
    PRIMARY_HOVER = "#006FE6"
    TEXT_PRIMARY = "#1D1D1F"
    TEXT_SECONDARY = "#6E6E73"
    TEXT_TERTIARY = "#AEAEB2"
    SUCCESS = "#34C759"
    WARNING = "#FF9500"
    DANGER = "#FF3B30"


# 字号
class Fonts:
    HUGE = 32
    LARGE = 24
    TITLE = 22
    BODY = 14
    SMALL = 12
    TINY = 11