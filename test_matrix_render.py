#!/usr/bin/env python3
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QPixmap
from core.neural_matrix import HoloNeuralSphere

def render_preview():
    app = QApplication.instance() or QApplication(sys.argv)
    
    sphere = HoloNeuralSphere()
    # Step simulation slightly
    sphere.step(0.5, 0.45, speaking=True, state="SPEAKING")
    
    w, h = 900, 700
    pixmap = QPixmap(w, h)
    pixmap.fill(QColor("#030306"))
    
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    cx, cy = w / 2, h / 2
    r = min(w, h) * 0.38
    
    main = QColor("#922747")
    acc = QColor("#c4335c")
    bg = QColor("#030306")
    
    sphere.paint(
        p, cx, cy, r, w, h,
        main=main, acc=acc, bg=bg,
        name="ULTRON", state="SPEAKING",
        speaking=True, muted=False
    )
    
    p.end()
    out_path = "/home/gabriel/.gemini/antigravity-ide/scratch/Mark-LVI/preview_matrix.png"
    pixmap.save(out_path)
    print(f"Preview saved to {out_path}")

if __name__ == "__main__":
    render_preview()
