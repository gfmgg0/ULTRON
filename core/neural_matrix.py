"""
Holographic 3D neural core simulating brain synapses, action potentials,
and cortical telemetry in the signature wine red ('cor vinho') palette.
Evenly distributed Fibonacci spherical mesh for dense, cohesive connectivity without voids or holes.
"""
import math
import random
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QRadialGradient


class HoloNeuralSphere:
    def __init__(self):
        self.phase = 0.0
        self.clock = 0.0
        self.amp_smooth = 0.0
        self.activity = 0.0
        self.pulse_scale = 1.0
        self._pulse_target = 1.0
        self._pulse_wait = 0.0
        self._pulse_rng = random.Random(2026)
        rng = random.Random(42)

        # ── 1. 3D Neural Nodes Distributed by Fibonacci Sphere (Zero Holes) ──
        # 190 nodes distributed uniformly across 3 concentric volumetric layers
        self.nodes = []

        # Outer cortex: 110 nodes
        n_out = 110
        phi = (1.0 + math.sqrt(5.0)) / 2.0
        for i in range(n_out):
            y = 1.0 - (i / float(n_out - 1)) * 2.0
            r_y = math.sqrt(max(0.0, 1.0 - y * y))
            th = 2.0 * math.pi * i / phi
            rad = rng.uniform(0.82, 0.96)
            self.nodes.append((rad * r_y * math.cos(th), rad * y * 0.94, rad * r_y * math.sin(th)))

        # Mid cortex: 55 nodes
        n_mid = 55
        for i in range(n_mid):
            y = 1.0 - (i / float(n_mid - 1)) * 2.0
            r_y = math.sqrt(max(0.0, 1.0 - y * y))
            th = 2.0 * math.pi * (i + 0.33) / phi
            rad = rng.uniform(0.52, 0.72)
            self.nodes.append((rad * r_y * math.cos(th), rad * y * 0.94, rad * r_y * math.sin(th)))

        # Inner core: 25 nodes
        n_in = 25
        for i in range(n_in):
            y = 1.0 - (i / float(n_in - 1)) * 2.0
            r_y = math.sqrt(max(0.0, 1.0 - y * y))
            th = 2.0 * math.pi * (i + 0.67) / phi
            rad = rng.uniform(0.24, 0.44)
            self.nodes.append((rad * r_y * math.cos(th), rad * y * 0.94, rad * r_y * math.sin(th)))

        # ── 2. Highly Connected Synaptic Mesh (No Holes / Comprehensive Web) ──
        # Connect each node to 6 nearest neighbors + cross-layer bridges
        self.edges = []
        linked = set()
        for i, a in enumerate(self.nodes):
            dists = sorted([(sum((x - y) ** 2 for x, y in zip(a, b)), j) for j, b in enumerate(self.nodes) if j != i])
            # Primary local synaptic connections
            for dist, j in dists[:6]:
                pair = tuple(sorted((i, j)))
                if pair not in linked and dist < 0.32:
                    linked.add(pair)
                    self.edges.append((*pair, rng.random()))
            # Radial / cross-layer bridges (connecting inner, mid, and outer layers)
            for dist, j in dists[6:11]:
                pair = tuple(sorted((i, j)))
                if pair not in linked and 0.08 < dist < 0.48:
                    if rng.random() > 0.45:
                        linked.add(pair)
                        self.edges.append((*pair, rng.random()))

        # ── 3. Cortical Surface Circuit Traces ────────────────────────────────
        self.traces = [
            (rng.uniform(-1.25, 1.25), rng.uniform(0, math.tau),
             rng.uniform(0.10, 0.38), rng.choice((0.75, 0.88, 1.01)), rng.random())
            for _ in range(80)
        ]

        # ── 4. Incomplete Curved Spherical Shells ────────────────────────────
        self.shells = [
            (1.02, -0.83, 0.2, 4.2),
            (0.96, -0.35, 1.3, 4.5),
            (0.93,  0.12, 0.5, 3.8),
            (1.02,  0.58, 2.3, 4.1),
            (0.76, -0.57, 0.8, 4.0),
            (0.74,  0.42, 2.1, 4.4),
        ]

        # ── 5. Gyroscopic Arcs ───────────────────────────────────────────────
        self.gyro_arcs = []
        for idx, rad in enumerate((0.35, 0.63, 0.86, 1.07)):
            tilt = 0.25 + idx * 0.57
            self.gyro_arcs.append((rad, tilt, idx))

    @staticmethod
    def _sphere(lat, lon, rad=1.0):
        return (
            rad * math.cos(lat) * math.cos(lon),
            rad * math.sin(lat),
            rad * math.cos(lat) * math.sin(lon)
        )

    def step(self, dt, amp, speaking=False, muted=False, state="IDLE"):
        dt = min(0.10, max(0.0, dt))
        self.amp_smooth += (max(0.0, min(1.0, amp)) - self.amp_smooth) * (1.0 - math.exp(-dt * 12))
        thinking = state in ("THINKING", "PROCESSING")
        target = 0.0 if muted else (0.88 if thinking else (0.38 + self.amp_smooth * 0.62 if speaking else 0.14))
        self.activity += (target - self.activity) * (1.0 - math.exp(-dt * 6))
        self.clock += dt * (0.70 + 1.10 * self.activity)
        self.phase += dt * (0.025 if muted else 0.085 + 0.10 * self.activity)

        # Organic breathing pulse
        self._pulse_wait -= dt
        if self._pulse_wait <= 0:
            self._pulse_wait = self._pulse_rng.uniform(0.38, 1.45)
            depth = 0.018 + 0.072 * self.activity
            self._pulse_target = 1.0 + self._pulse_rng.uniform(-1.0, 0.85) * depth
        wave = math.sin(self.clock * 2.3) * 0.009 + math.sin(self.clock * 3.71 + 0.8) * 0.006
        target_scale = 1.0 if muted else self._pulse_target + wave + self.amp_smooth * 0.018
        self.pulse_scale += (target_scale - self.pulse_scale) * (1.0 - math.exp(-dt * 4.8))
        self.pulse_scale = max(0.88, min(1.08, self.pulse_scale))

    def paint(self, p: QPainter, cx: float, cy: float, r: float, W: float, H: float,
              main: QColor, acc: QColor, bg: QColor, name: str = "",
              state: str = "IDLE", speaking: bool = False, muted: bool = False):
        t = self.phase
        r = min(r * self.pulse_scale, min(W, H) * 0.44)
        activity = 0.0 if muted else self.activity

        if muted:
            color = QColor("#75818c")
            light = QColor("#b2bdc6")
            hot   = QColor("#d0d7dc")
        else:
            color = main if (main and main.isValid() and main.name() != "#000000") else QColor("#922747")
            light = color.lighter(185)
            hot   = QColor("#ffd2de")

        # Pre-mix color table for blazing fast rendering
        bg_r, bg_g, bg_b = bg.red(), bg.green(), bg.blue()
        c_r, c_g, c_b = color.red(), color.green(), color.blue()
        l_r, l_g, l_b = light.red(), light.green(), light.blue()

        color_lut = [
            QColor(int(bg_r + (c_r - bg_r) * (k / 15.0)),
                   int(bg_g + (c_g - bg_g) * (k / 15.0)),
                   int(bg_b + (c_b - bg_b) * (k / 15.0)))
            for k in range(16)
        ]
        light_lut = [
            QColor(int(bg_r + (l_r - bg_r) * (k / 15.0)),
                   int(bg_g + (l_g - bg_g) * (k / 15.0)),
                   int(bg_b + (l_b - bg_b) * (k / 15.0)))
            for k in range(16)
        ]

        def get_tint(is_light: bool, a: float) -> QColor:
            idx = max(0, min(15, int(a * 15.0)))
            return light_lut[idx] if is_light else color_lut[idx]

        # 3D projection
        cos_t = math.cos(t)
        sin_t = math.sin(t)
        roll = 0.15 + 0.05 * math.sin(t)
        cos_roll = math.cos(roll)
        sin_roll = math.sin(roll)

        def project(x, y, z):
            rx = x * cos_t + z * sin_t
            rz = -x * sin_t + z * cos_t
            ry = y * cos_roll - rz * sin_roll
            rz = y * sin_roll + rz * cos_roll
            k = 4.8 / (4.8 + rz)
            return QPointF(cx + r * rx * k, cy + r * ry * k), rz

        def sphere(lat, lon, rad=1.0):
            return self._sphere(lat, lon, rad)

        segments = []

        def path(points, brightness=0.5, width=0.8, bright=False):
            pts = [project(*v) for v in points]
            for a, b in zip(pts, pts[1:]):
                segments.append(((a[1] + b[1]) * 0.5, a[0], b[0], brightness, width, bright))

        # ── 1. Curved Shells ─────────────────────────────────────────────────
        for shell, lat, start, span in self.shells:
            path([sphere(lat, start + j * span / 48.0, shell) for j in range(49)], 0.48)

        # ── 2. Gyro Arcs & Ticks ─────────────────────────────────────────────
        for index, rad in enumerate((0.35, 0.63, 0.86, 1.07)):
            tilt = 0.25 + index * 0.57
            rot_dir = 1 if index % 2 else -1
            cos_tilt = math.cos(tilt)
            sin_tilt = math.sin(tilt)

            for offset in (0.2, 2.7, 4.9):
                pts = []
                for j in range(24):
                    a = offset + j * 0.065 + t * rot_dir
                    pts.append((rad * math.cos(a), rad * math.sin(a) * sin_tilt, rad * math.sin(a) * cos_tilt))
                path(pts, 0.70, 1.0, True)

            for j in range(28):
                a = j * math.tau / 28.0 + t * rot_dir
                def at(r_val):
                    return (r_val * math.cos(a), r_val * math.sin(a) * sin_tilt, r_val * math.sin(a) * cos_tilt)
                path([at(rad), at(rad + (0.018 if j % 4 else 0.036))], 0.50, 0.65)

        # ── 3. Traces ────────────────────────────────────────────────────────
        for lat, lon, length, rad, seed in self.traces:
            path([sphere(lat, lon + j * length / 6.0, rad) for j in range(7)], 0.72, 0.8, seed > 0.7)
            path([sphere(lat, lon, rad), sphere(lat + 0.035, lon, rad), sphere(lat + 0.035, lon + 0.045, rad)], 0.55, 0.7)
            if seed > 0.7:
                path([sphere(lat, lon + length, rad), sphere(lat, lon + length, rad + 0.055), sphere(lat, lon + length + 0.08, rad + 0.055)], 0.60, 0.7)

        # ── 4. Synaptic Axons (Dense Connected Neural Network) ───────────────
        for i, j, seed in self.edges:
            path([self.nodes[i], self.nodes[j]], 0.16 + activity * 0.35, 0.70, seed > 0.55)

        p.setBrush(Qt.BrushStyle.NoBrush)

        # Draw sorted lines
        sorted_segs = sorted(segments, key=lambda item: item[0], reverse=True)
        for z, a, b, brightness, width, bright in sorted_segs:
            alpha = max(0.04, min(1.0, brightness * (1.05 - 0.38 * z)))
            col = get_tint(bright, alpha)
            p.setPen(QPen(col, width))
            p.drawLine(a, b)

        # ── 5. Action Potentials ─────────────────────────────────────────────
        if activity > 0.05:
            for i, j, seed in self.edges:
                if seed > activity * 0.55:
                    continue
                progress = (self.clock * (0.75 + seed) + seed * 3.0) % 1.0
                a, b = self.nodes[i], self.nodes[j]
                ix = a[0] + (b[0] - a[0]) * progress
                iy = a[1] + (b[1] - a[1]) * progress
                iz = a[2] + (b[2] - a[2]) * progress
                head, z = project(ix, iy, iz)

                ptx = a[0] + (b[0] - a[0]) * max(0.0, progress - 0.16)
                pty = a[1] + (b[1] - a[1]) * max(0.0, progress - 0.16)
                ptz = a[2] + (b[2] - a[2]) * max(0.0, progress - 0.16)
                tail, _ = project(ptx, pty, ptz)

                intensity = activity * (0.75 - 0.18 * z)
                col_trail = get_tint(False, intensity * 0.40)
                col_core = get_tint(True, intensity)

                p.setPen(QPen(col_trail, 4.0))
                p.drawLine(tail, head)
                p.setPen(QPen(col_core, 1.25))
                p.drawLine(tail, head)

                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(hot)
                sz = 1.4 + activity * 0.9
                p.drawEllipse(head, sz, sz)

        # ── 6. Soma Nodes ────────────────────────────────────────────────────
        for i, node in enumerate(self.nodes):
            point, z = project(*node)
            pulse = (max(0.0, math.sin(self.clock * 4.0 - i * 1.5))) ** 8 * activity
            alpha = (0.24 + pulse * 0.70) * max(0.30, 1.0 - z * 0.30)
            col_node = get_tint(True, alpha)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col_node)
            p.drawEllipse(point, 1.2 + pulse * 1.6, 1.2 + pulse * 1.6)

            if pulse > 0.40:
                p.setPen(QPen(col_node, 0.70))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(point, 3.2 + pulse * 3.0, 3.2 + pulse * 3.0)

        # ── 7. Nucleus ───────────────────────────────────────────────────────
        for index, scale in enumerate((0.072, 0.105, 0.15)):
            radius = r * scale
            p.setBrush(Qt.BrushStyle.NoBrush)
            col_arc = get_tint(True, 0.42 + activity * 0.20)
            p.setPen(QPen(col_arc, 0.80))
            rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            p.drawArc(rect, int((self.clock * 18 * (1 if index % 2 else -1) + index * 80) * 16), 245 * 16)

        glow = QRadialGradient(cx, cy, r * 0.050)
        glow.setColorAt(0.00, hot)
        glow.setColorAt(0.35, color)
        glow.setColorAt(1.00, bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(cx, cy), r * 0.050, r * 0.050)
