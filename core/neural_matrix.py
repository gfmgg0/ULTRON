"""
Holographic 3D neural core simulating brain synapses, action potentials,
and cortical telemetry in the signature wine red ('cor vinho') palette.
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

        # ── 1. Cortical Surface Circuit Traces ────────────────────────────────
        self.traces = [
            (rng.uniform(-1.3, 1.3), rng.uniform(0, math.tau),
             rng.uniform(0.08, 0.40), rng.choice((0.72, 0.90, 1.02)), rng.random())
            for _ in range(128)
        ]

        # ── 2. 3D Neural Nodes (Brain Synapse Network) ────────────────────────
        # 148 nodes distributed across 3D sphere with hemisphere organization
        self.nodes = []
        for i in range(148):
            hemi = 1 if i % 2 == 0 else -1
            lat = rng.uniform(-1.25, 1.25)
            # Subtle hemisphere division simulating brain lobes
            lon = rng.uniform(0.12, math.pi - 0.12) if hemi == 1 else rng.uniform(math.pi + 0.12, math.tau - 0.12)
            rad = rng.uniform(0.24, 0.92)
            self.nodes.append(self._sphere(lat, lon, rad))

        # ── 3. Synaptic Axons & Inter-Hemispheric Bridges ─────────────────────
        self.edges = []
        linked = set()
        for i, a in enumerate(self.nodes):
            near = sorted([(sum((x - y) ** 2 for x, y in zip(a, b)), j) for j, b in enumerate(self.nodes) if j != i])
            # Connect local synapses
            for dist, j in near[:5]:
                pair = tuple(sorted((i, j)))
                if pair not in linked and 0.008 < dist < 0.38:
                    linked.add(pair)
                    self.edges.append((*pair, rng.random()))
            # Cross-corpus callosum bridges (synaptic connections between hemispheres)
            if i % 7 == 0:
                cross = [j for d, j in near if 0.22 < d < 0.65]
                if cross:
                    j = rng.choice(cross)
                    pair = tuple(sorted((i, j)))
                    if pair not in linked:
                        linked.add(pair)
                        self.edges.append((*pair, rng.random()))

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

        # ── Color Palette: "Cor Vinho" (Wine Red / Burgundy / Bordeaux) ──────
        if muted:
            color = QColor("#75818c")
            light = QColor("#b2bdc6")
            hot   = QColor("#d0d7dc")
        else:
            # Respect user's wine red theme (#922747)
            color = main if (main and main.isValid() and main.name() != "#000000") else QColor("#922747")
            light = color.lighter(185)  # Glowing rose-wine highlight
            hot   = QColor("#ffd2de")   # Incandescent synaptic impulse spark

        def tint(c: QColor, a: float) -> QColor:
            k = max(0.0, min(1.0, a))
            return QColor(
                int(bg.red()   + (c.red()   - bg.red())   * k),
                int(bg.green() + (c.green() - bg.green()) * k),
                int(bg.blue()  + (c.blue()  - bg.blue())  * k),
            )

        # 3D Perspective Projection
        def project(x, y, z):
            rx = x * math.cos(t) + z * math.sin(t)
            rz = -x * math.sin(t) + z * math.cos(t)
            roll = 0.15 + 0.05 * math.sin(t)
            ry = y * math.cos(roll) - rz * math.sin(roll)
            rz = y * math.sin(roll) + rz * math.cos(roll)
            k = 4.8 / (4.8 + rz)
            return QPointF(cx + r * rx * k, cy + r * ry * k), rz

        def sphere(lat, lon, rad=1.0):
            return self._sphere(lat, lon, rad)

        segments = []

        def path(points, brightness=0.5, width=0.8, bright=False):
            pts = [project(*v) for v in points]
            for a, b in zip(pts, pts[1:]):
                segments.append(((a[1] + b[1]) / 2.0, a[0], b[0], brightness, width, bright))

        # ── 1. Incomplete Curved Spherical Shells (Cortical Gyri) ────────────
        for shell, lat, start, span in (
            (1.02, -0.83, 0.2, 4.2),
            (0.96, -0.35, 1.3, 4.5),
            (0.93,  0.12, 0.5, 3.8),
            (1.02,  0.58, 2.3, 4.1),
            (0.76, -0.57, 0.8, 4.0),
            (0.74,  0.42, 2.1, 4.4),
        ):
            path([sphere(lat, start + j * span / 70.0, shell) for j in range(71)], 0.48)

        # ── 2. Gyroscopic Latitude/Longitude Arcs & Telemetry Registration ───
        for index, rad in enumerate((0.35, 0.63, 0.86, 1.07)):
            tilt = 0.25 + index * 0.57
            rot_dir = 1 if index % 2 else -1
            for offset in (0.2, 2.7, 4.9):
                pts = []
                for j in range(34):
                    a = offset + j * 0.046 + t * rot_dir
                    pts.append((rad * math.cos(a), rad * math.sin(a) * math.sin(tilt), rad * math.sin(a) * math.cos(tilt)))
                path(pts, 0.70, 1.0, True)

            for j in range(38):
                a = j * math.tau / 38.0 + t * rot_dir
                def at(r_val):
                    return (r_val * math.cos(a), r_val * math.sin(a) * math.sin(tilt), r_val * math.sin(a) * math.cos(tilt))
                path([at(rad), at(rad + (0.017 if j % 4 else 0.035))], 0.50, 0.65)

        # ── 3. Cortical Surface Circuit Traces with Stepped Extensions ───────
        for lat, lon, length, rad, seed in self.traces:
            path([sphere(lat, lon + j * length / 8.0, rad) for j in range(9)], 0.72, 0.8, seed > 0.7)
            path([sphere(lat, lon, rad), sphere(lat + 0.035, lon, rad), sphere(lat + 0.035, lon + 0.045, rad)], 0.55, 0.7)
            if seed > 0.7:
                path([sphere(lat, lon + length, rad), sphere(lat, lon + length, rad + 0.055), sphere(lat, lon + length + 0.08, rad + 0.055)], 0.60, 0.7)

        # ── 4. Synaptic Axons (The 3D Brain Neural Web) ──────────────────────
        for i, j, seed in self.edges:
            path([self.nodes[i], self.nodes[j]], 0.14 + activity * 0.35, 0.68, True)

        p.setBrush(Qt.BrushStyle.NoBrush)

        # Draw all 3D segments sorted by depth
        for z, a, b, brightness, width, bright in sorted(segments, key=lambda item: item[0], reverse=True):
            alpha = max(0.035, min(1.0, brightness * (1.05 - 0.38 * z)))
            p.setPen(QPen(tint(light if bright else color, alpha), width))
            p.drawLine(a, b)

        # ── 5. Travelling Action Potential Impulses (Synaptic Firing) ────────
        if activity > 0.05:
            for i, j, seed in self.edges:
                if seed > activity * 0.58:
                    continue
                progress = (self.clock * (0.70 + seed) + seed * 3.0) % 1.0
                a, b = self.nodes[i], self.nodes[j]
                def interpolate(val):
                    return tuple(x + (y - x) * val for x, y in zip(a, b))
                head, z = project(*interpolate(progress))
                tail, _ = project(*interpolate(max(0.0, progress - 0.16)))
                intensity = activity * (0.75 - 0.18 * z)

                # Glowing wine impulse trail
                p.setPen(QPen(tint(color, intensity * 0.30), 4.5))
                p.drawLine(tail, head)
                p.setPen(QPen(tint(light, intensity), 1.25))
                p.drawLine(tail, head)
                # Incandescent action potential head
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(tint(hot, intensity))
                size = 1.4 + activity * 0.9
                p.drawEllipse(head, size, size)

        # ── 6. Neural Nodes (Synapse Soma Hubs) ──────────────────────────────
        for i, node in enumerate(self.nodes):
            point, z = project(*node)
            pulse = (max(0.0, math.sin(self.clock * 4.0 - i * 1.7))) ** 8 * activity
            alpha = (0.22 + pulse * 0.70) * max(0.30, 1.0 - z * 0.30)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(tint(light, alpha))
            p.drawEllipse(point, 1.0 + pulse * 1.6, 1.0 + pulse * 1.6)
            if pulse > 0.42:
                p.setPen(QPen(tint(light, pulse * 0.35), 0.70))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(point, 3.0 + pulse * 3.0, 3.0 + pulse * 3.0)

        # ── 7. Layered Holographic Nucleus & Core Glow ───────────────────────
        for index, scale in enumerate((0.072, 0.105, 0.15)):
            radius = r * scale
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(tint(light, 0.42 + activity * 0.20), 0.80))
            rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            p.drawArc(rect, int((self.clock * 18 * (1 if index % 2 else -1) + index * 80) * 16), 245 * 16)

        glow = QRadialGradient(cx, cy, r * 0.050)
        glow.setColorAt(0.00, tint(hot, 0.52 + activity * 0.35))
        glow.setColorAt(0.30, tint(color, 0.38))
        glow.setColorAt(1.00, bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(cx, cy), r * 0.050, r * 0.050)
