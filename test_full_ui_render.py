#!/usr/bin/env python3
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from ui import JarvisUI

def test_full_ui():
    app = QApplication.instance() or QApplication(sys.argv)
    
    ui = JarvisUI("face.png")
    win = ui._win
    win.resize(1280, 800)
    
    # Process events and step animation
    win._apply_state("LISTENING")
    for _ in range(25):
        app.processEvents()
        win.hud._step()
    
    out_img = "/home/gabriel/Documentos/ULTRON/ultron_app_preview.png"
    pixmap = win.grab()
    pixmap.save(out_img)
    print(f"Full UI screenshot saved to: {out_img}")

if __name__ == "__main__":
    test_full_ui()
