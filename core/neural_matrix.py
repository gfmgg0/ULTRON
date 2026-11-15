"""
Holographic 3D organic bio-slime neural core ('Gosma' neural orgânica)
simulating brain synapses, action potentials, and fluid cortical telemetry.
- Continuous 3D harmonic fluid undulation (simplex/harmonic wave displacement)
- Completely non-concentric: amorphous living slime morphing in real time
- Elastic synaptic protoplasmic fibers that stretch and pulse
- Supports both ULTRON (wine red #922747) and FRIDAY (royal purple #8a2be2)
"""
from __future__ import annotations

import math
import random
from PyQt6.QtCore import Qt, QPointF
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

        # ── 1. Base Spherical Topology (Fibonacci Lattice for Even Coverage) ──
        # We store base spherical coordinates (lat, lon, base_r, layer, phase_offset, speed_mult)
        self.base_nodes = []

        # Layer 1: Outer undulating fluid membrane (110 nodes)
        n_out = 110
        phi = (1.0 + math.sqrt(5.0)) / 2.0
        for i in range(n_out):
            y = 1.0 - (i / float(n_out - 1)) * 2.0
            lat = math.asin(max(-1.0, min(1.0, y)))
            lon = (2.0 * math.pi * i / phi) % math.tau
            # Store phase offsets and speeds so each node undulates naturally
            self.base_nodes.append((lat, lon, 0.95, 0, rng.uniform(0, math.tau), rng.uniform(0.8, 1.2)))

        # Layer 2: Mid visceral neural fibers (55 nodes)
        n_mid = 55
        for i in range(n_mid):
            y = 1.0 - (i / float(n_mid - 1)) * 2.0
            lat = math.asin(max(-1.0, min(1.0, y)))
            lon = (2.0 * math.pi * (i + 0.33) / phi) % math.tau
            self.base_nodes.append((lat, lon, 0.65, 1, rng.uniform(0, math.tau), rng.uniform(0.8, 1.2)))

        # Layer 3: Inner cytoplasmic core (25 nodes)
        n_in = 25
        for i in range(n_in):
            y = 1.0 - (i / float(n_in - 1)) * 2.0
            lat = math.asin(max(-1.0, min(1.0, y)))
            lon = (2.0 * math.pi * (i + 0.67) / phi) % math.tau
            self.base_nodes.append((lat, lon, 0.34, 2, rng.uniform(0, math.tau), rng.uniform(0.8, 1.2)))

        # Selected synaptic glow hubs (only ~35 hubs for sleek subdued points)
        self.glowing_hubs = [i for i in range(len(self.base_nodes)) if i % 5 == 0]

        # ── 2. Interconnected Viscous Synaptic Mesh ───────────────────────────
        self.edges = []
        linked = set()
        for i, (lata, lona, ra, layera, _, _) in enumerate(self.base_nodes):
            xa = ra * math.cos(lata) * math.cos(lona)
            ya = ra * math.sin(lata)
            za = ra * math.cos(lata) * math.sin(lona)
            dists = []
            for j, (latb, lonb, rb, layerb, _, _) in enumerate(self.base_nodes):
                if j == i:
                    continue
                xb = rb * math.cos(latb) * math.cos(lonb)
                yb = rb * math.sin(latb)
                zb = rb * math.cos(latb) * math.sin(lonb)
                d = (xa - xb) ** 2 + (ya - yb) ** 2 + (za - zb) ** 2
                dists.append((d, j))
            dists.sort()

            # Connect local neighbors
            for d, j in dists[:6]:
                pair = tuple(sorted((i, j)))
                if pair not in linked and d < 0.28:
                    linked.add(pair)
                    self.edges.append((*pair, rng.random()))

            # Radial cross-bridges between layers
            for d, j in dists[6:11]:
                pair = tuple(sorted((i, j)))
                if pair not in linked and 0.08 < d < 0.44:
                    if rng.random() > 0.40:
                        linked.add(pair)
                        self.edges.append((*pair, rng.random()))

        # ── 3. Organic Fluid Filaments (Flowing Curved Slime Strands) ─────────
        self.slime_strands = []
        for _ in range(8):
            seed_lat = rng.uniform(-0.8, 0.8)
            seed_lon = rng.uniform(0, math.tau)
            freq_lat = rng.uniform(1.2, 2.5)
            freq_lon = rng.uniform(1.0, 2.0)
            strand_pts = []
            for step in range(36):
                u = (step / 35.0) * math.tau
                lat = seed_lat + 0.35 * math.sin(freq_lat * u)
                lon = seed_lon + u
                rad = rng.uniform(0.85, 0.98)
                strand_pts.append((lat, lon, rad, rng.random()))
            self.slime_strands.append(strand_pts)

    def _morph_node(self, lat, lon, base_r, layer, phase_offset, speed_mult, t, amp):
        """
        Calculates 3D coordinates with continuous organic fluid/slime deformation.
        Harmonic fluid waves cause the shape to bulge, stretch, and flow smoothly.
        """
        clk = self.clock * speed_mult + phase_offset

        # Primary 3D fluid harmonic waves (large undulating bulges)
        w1 = math.sin(2.0 * lat + 1.2 * clk) * math.cos(3.0 * lon + 0.8 * clk)
        w2 = math.cos(3.0 * lat - 0.9 * clk) * math.sin(2.0 * lon - 1.1 * clk)
        # Secondary organic ripples (reacting to audio amplitude)
        w3 = math.sin(4.0 * lon + 2.5 * clk) * (0.04 + 0.08 * amp)

        # Fluid radius displacement
        disp_r = (0.12 * w1 + 0.09 * w2 + w3)
        if layer == 0:
            # Outer membrane stretches most
            r_eff = base_r + disp_r
        elif layer == 1:
            # Mid layer has dampened fluid lag
            r_eff = base_r + disp_r * 0.70
        else:
            # Core has gentle cytoplasmic pulse
            r_eff = base_r + disp_r * 0.40

        # Gentle angular fluid drift
        lat_eff = lat + 0.06 * math.sin(3.0 * lon + clk)
        lon_eff = lon + 0.08 * math.cos(2.0 * lat + clk * 0.7)

        x = r_eff * math.cos(lat_eff) * math.cos(lon_eff)
        y = r_eff * math.sin(lat_eff)
        z = r_eff * math.cos(lat_eff) * math.sin(lon_eff)
        return (x, y, z)

    def step(self, dt, amp, speaking=False, muted=False, state="IDLE"):
        dt = min(0.10, max(0.0, dt))
        self.amp_smooth += (max(0.0, min(1.0, amp)) - self.amp_smooth) * (1.0 - math.exp(-dt * 12))
        thinking = state in ("THINKING", "PROCESSING")
        target = 0.0 if muted else (0.88 if thinking else (0.40 + self.amp_smooth * 0.60 if speaking else 0.16))
        self.activity += (target - self.activity) * (1.0 - math.exp(-dt * 6))
        self.clock += dt * (0.75 + 1.15 * self.activity)
        self.phase += dt * (0.025 if muted else 0.080 + 0.10 * self.activity)

        # ── Amplified Expand & Contract Breathing Motion ─────────────────────
        breath_wave = (
            math.sin(self.clock * 1.8) * 0.065
            + math.sin(self.clock * 0.9 + 0.5) * 0.035
        )

        self._pulse_wait -= dt
        if self._pulse_wait <= 0:
            self._pulse_wait = self._pulse_rng.uniform(0.5, 1.8)
            depth = 0.035 + 0.085 * self.activity
            self._pulse_target = 1.0 + self._pulse_rng.uniform(-1.0, 0.90) * depth

        speech_lift = self.amp_smooth * 0.14 if speaking else self.amp_smooth * 0.06
        think_lift = 0.05 * math.sin(self.clock * 4.5) if thinking else 0.0

        target_scale = (
            1.0 if muted else (self._pulse_target + breath_wave + speech_lift + think_lift)
        )

        self.pulse_scale += (target_scale - self.pulse_scale) * (1.0 - math.exp(-dt * 5.2))
        self.pulse_scale = max(0.80, min(1.22, self.pulse_scale))

    def paint(self, p: QPainter, cx: float, cy: float, r: float, W: float, H: float,
              main: QColor, acc: QColor, bg: QColor, name: str = "",
              state: str = "IDLE", speaking: bool = False, muted: bool = False):
        t = self.phase
        r = r * self.pulse_scale
        amp = self.amp_smooth
        activity = 0.0 if muted else self.activity

        # Detect persona: if name is Friday or main is purple, use Friday's purple palette
        is_friday = "friday" in (name or "").lower() or (main and main.name().lower() in ("#8a2be2", "#9b30ff", "#7b1fa2", "#6a0dad"))

        if muted:
            color = QColor("#75818c")
            light = QColor("#b2bdc6")
            hot   = QColor("#a0aab4")
        elif is_friday:
            # Friday: Royal Purple / Amethyst / Violet
            color = main if (main and main.isValid() and main.name() != "#000000") else QColor("#8a2be2")
            light = color.lighter(155)    # Soft glowing lavender/violet
            hot   = color.lighter(185)    # Subdued violet-white spark
        else:
            # Ultron: Signature Wine Red / Bordeaux
            color = main if (main and main.isValid() and main.name() != "#000000") else QColor("#922747")
            light = color.lighter(150)    # Soft rose-wine highlight
            hot   = color.lighter(180)    # Subdued wine spark

        # Pre-mix color table
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

        # 3D Camera Projection with dynamic organic sway
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

        # ── 1. Calculate Dynamically Morphed 3D Node Positions ────────────────
        curr_nodes = [
            self._morph_node(lat, lon, base_r, layer, phase_offset, speed_mult, t, amp)
            for (lat, lon, base_r, layer, phase_offset, speed_mult) in self.base_nodes
        ]

        segments = []

        # ── 2. Fluid Slime Strands (Undulating Organic Fibers) ───────────────
        for strand in self.slime_strands:
            pts = []
            for lat, lon, rad, seed in strand:
                # Morph strand points along the slime surface
                clk = self.clock * 0.8 + seed * 3.0
                disp = 0.10 * math.sin(2.0 * lat + clk) * math.cos(3.0 * lon + clk * 0.7)
                r_strand = rad + disp
                x = r_strand * math.cos(lat) * math.cos(lon)
                y = r_strand * math.sin(lat)
                z = r_strand * math.cos(lat) * math.sin(lon)
                pts.append(project(x, y, z))

            for a, b in zip(pts, pts[1:]):
                mid_z = (a[1] + b[1]) * 0.5
                segments.append((mid_z, a[0], b[0], 0.38, 0.85, False))

        # ── 3. Synaptic Protoplasmic Axons (Dense Connected Neural Web) ──────
        for i, j, seed in self.edges:
            p1, z1 = project(*curr_nodes[i])
            p2, z2 = project(*curr_nodes[j])
            mid_z = (z1 + z2) * 0.5
            bright = 0.16 + activity * 0.35
            segments.append((mid_z, p1, p2, bright, 0.70, seed > 0.55))

        p.setBrush(Qt.BrushStyle.NoBrush)

        # Draw all 3D fluid lines sorted by depth
        sorted_segs = sorted(segments, key=lambda item: item[0], reverse=True)
        for z, a, b, brightness, width, bright in sorted_segs:
            alpha = max(0.04, min(1.0, brightness * (1.05 - 0.38 * z)))
            col = get_tint(bright, alpha)
            p.setPen(QPen(col, width))
            p.drawLine(a, b)

        # ── 4. Action Potential Pulses Traveling along Morphed Fibers ────────
        if activity > 0.05:
            for i, j, seed in self.edges:
                if seed > activity * 0.40:
                    continue
                progress = (self.clock * (0.70 + seed) + seed * 3.0) % 1.0
                a, b = curr_nodes[i], curr_nodes[j]
                ix = a[0] + (b[0] - a[0]) * progress
                iy = a[1] + (b[1] - a[1]) * progress
                iz = a[2] + (b[2] - a[2]) * progress
                head, z = project(ix, iy, iz)

                ptx = a[0] + (b[0] - a[0]) * max(0.0, progress - 0.14)
                pty = a[1] + (b[1] - a[1]) * max(0.0, progress - 0.14)
                ptz = a[2] + (b[2] - a[2]) * max(0.0, progress - 0.14)
                tail, _ = project(ptx, pty, ptz)

                intensity = activity * (0.65 - 0.15 * z)
                col_trail = get_tint(False, intensity * 0.35)
                col_core = get_tint(True, intensity * 0.75)

                p.setPen(QPen(col_trail, 3.5))
                p.drawLine(tail, head)
                p.setPen(QPen(col_core, 1.1))
                p.drawLine(tail, head)

                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col_core)
                sz = 1.2 + activity * 0.7
                p.drawEllipse(head, sz, sz)

        # ── 5. Soma Nodes (Subdued, Opaque, Only Key Hubs) ───────────────────
        for idx in self.glowing_hubs:
            point, z = project(*curr_nodes[idx])
            pulse = (max(0.0, math.sin(self.clock * 3.6 - idx * 1.5))) ** 8 * activity
            alpha = (0.18 + pulse * 0.45) * max(0.25, 0.90 - z * 0.25)
            col_node = get_tint(False if pulse < 0.30 else True, alpha)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col_node)
            sz = 0.95 + pulse * 1.2
            p.drawEllipse(point, sz, sz)

        # ── 6. Cytoplasmic Core Nucleus (Soft Living Fluid Heart, Non-Concentric) ──
        nuc_r = r * (0.065 + 0.015 * math.sin(self.clock * 2.2) + 0.015 * amp)
        glow = QRadialGradient(cx, cy, nuc_r * 1.4)
        glow.setColorAt(0.00, light)
        glow.setColorAt(0.40, color)
        glow.setColorAt(1.00, bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(cx, cy), nuc_r * 1.4, nuc_r * 1.4)
