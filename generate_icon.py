
#!/usr/bin/env python3
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QPixmap
from core.neural_matrix import HoloNeuralSphere

def render_icon():
    app = QApplication.instance() or QApplication(sys.argv)
    sphere = HoloNeuralSphere()
    for _ in range(10):
        sphere.step(0.4, 0.5, speaking=True, state="OPTIMAL")
    
    w, h = 256, 256
    pixmap = QPixmap(w, h)
    pixmap.fill(QColor(0, 0, 0, 0)) # transparent background
    
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    cx, cy = w / 2, h / 2
    r = 100
    
    main = QColor("#922747")
    acc = QColor("#c4335c")
    bg = QColor("#08080c")
    
    sphere.paint(
        p, cx, cy, r, w, h,
        main=main, acc=acc, bg=bg,
        name="ULTRON", state="ONLINE",
        speaking=True, muted=False
    )
    p.end()
    
    out_path = "/home/gabriel/Documentos/ULTRON/ultron_icon.png"
    pixmap.save(out_path)
    print(f"Icon saved to {out_path}")

if __name__ == "__main__":
    render_icon()
