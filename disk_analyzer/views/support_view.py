import os
import sys
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)

# When bundled by PyInstaller, resources are extracted to sys._MEIPASS
_BASE_DIR = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
QR_PATH = os.path.join(_BASE_DIR, "resources", "bmc_qr.png")
BMC_URL = "https://buymeacoffee.com/takoora"
GITHUB_SPONSOR_URL = "https://github.com/sponsors/takoora"
GITHUB_REPO_URL = "https://github.com/takoora/DiskAnalyzer"


class SupportView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()

        center = QVBoxLayout()
        center.setSpacing(16)
        center.addStretch()

        # Title
        title = QLabel("Support DiskAnalyzer")
        title.setFont(QFont("Helvetica Neue", 22, QFont.Bold))
        title.setStyleSheet("color: #eee;")
        title.setAlignment(Qt.AlignCenter)
        center.addWidget(title)

        # Subtitle
        subtitle = QLabel(
            "DiskAnalyzer is free and open source.\n"
            "If you find it useful, consider supporting development!"
        )
        subtitle.setFont(QFont("Helvetica Neue", 13))
        subtitle.setStyleSheet("color: #aaa;")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        center.addWidget(subtitle)

        center.addSpacing(8)

        # QR Code
        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignCenter)
        qr_pixmap = QPixmap(os.path.normpath(QR_PATH))
        if not qr_pixmap.isNull():
            qr_label.setPixmap(qr_pixmap.scaled(
                220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        else:
            qr_label.setText("(QR code not found)")
            qr_label.setStyleSheet("color: #888;")
        center.addWidget(qr_label)

        # Scan label
        scan_hint = QLabel("Scan to buy me a coffee")
        scan_hint.setFont(QFont("Helvetica Neue", 11))
        scan_hint.setStyleSheet("color: #888;")
        scan_hint.setAlignment(Qt.AlignCenter)
        center.addWidget(scan_hint)

        center.addSpacing(12)

        # Buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(10)

        coffee_btn = QPushButton("☕  Buy Me a Coffee")
        coffee_btn.setFixedWidth(260)
        coffee_btn.setFixedHeight(40)
        coffee_btn.setFont(QFont("Helvetica Neue", 14, QFont.Bold))
        coffee_btn.setStyleSheet(
            "QPushButton { background: #ffdd00; color: #000; border-radius: 8px; }"
            "QPushButton:hover { background: #ffe84d; }"
        )
        coffee_btn.setCursor(Qt.PointingHandCursor)
        coffee_btn.clicked.connect(lambda: webbrowser.open(BMC_URL))
        btn_row1 = QHBoxLayout()
        btn_row1.addStretch()
        btn_row1.addWidget(coffee_btn)
        btn_row1.addStretch()
        btn_layout.addLayout(btn_row1)

        sponsor_btn = QPushButton("♥  Sponsor on GitHub")
        sponsor_btn.setFixedWidth(260)
        sponsor_btn.setFixedHeight(40)
        sponsor_btn.setFont(QFont("Helvetica Neue", 14))
        sponsor_btn.setStyleSheet(
            "QPushButton { background: #2ea44f; color: white; border-radius: 8px; }"
            "QPushButton:hover { background: #3fb950; }"
        )
        sponsor_btn.setCursor(Qt.PointingHandCursor)
        sponsor_btn.clicked.connect(lambda: webbrowser.open(GITHUB_SPONSOR_URL))
        btn_row2 = QHBoxLayout()
        btn_row2.addStretch()
        btn_row2.addWidget(sponsor_btn)
        btn_row2.addStretch()
        btn_layout.addLayout(btn_row2)

        repo_btn = QPushButton("Star on GitHub")
        repo_btn.setFixedWidth(260)
        repo_btn.setFixedHeight(36)
        repo_btn.setFont(QFont("Helvetica Neue", 13))
        repo_btn.setStyleSheet(
            "QPushButton { background: #333; color: #ddd; border: 1px solid #555; border-radius: 8px; }"
            "QPushButton:hover { background: #444; }"
        )
        repo_btn.setCursor(Qt.PointingHandCursor)
        repo_btn.clicked.connect(lambda: webbrowser.open(GITHUB_REPO_URL))
        btn_row3 = QHBoxLayout()
        btn_row3.addStretch()
        btn_row3.addWidget(repo_btn)
        btn_row3.addStretch()
        btn_layout.addLayout(btn_row3)

        center.addLayout(btn_layout)

        center.addStretch()
        outer.addLayout(center)
        outer.addStretch()
