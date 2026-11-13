#!/usr/bin/env python3
import os
import sys
import math
import numpy as np

# Use offscreen platform for testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import Qt, QRectF, QLineF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QRadialGradient, QFont, QPixmap, QImage

def test_render():
    w, h = 800, 600
    pixmap = QPixmap(w, h)
    pixmap.fill(QColor("#030305"))
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Test drawing
    cx, cy = w / 2, h / 2
    r = 200
    
    # Glow
    g = QRadialGradient(cx, cy, r * 0.8)
    g.setColorAt(0.0, QColor(255, 200, 50, 180))
    g.setColorAt(0.3, QColor(255, 140, 20, 80))
    g.setColorAt(0.7, QColor(200, 80, 0, 20))
    g.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.setBrush(QBrush(g))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
    
    p.end()
    pixmap.save("/tmp/test_hud.png")
    print("Render success, file saved to /tmp/test_hud.png")

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    test_render()
