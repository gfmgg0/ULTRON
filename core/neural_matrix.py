"""
Layered holographic neural core with Stark Industries J.A.R.V.I.S. golden spiral accretion vortex.
Features:
- Dense tangled golden neural filament web & 3D synaptic network
- Multi-track logarithmic spiral accretion arms with high-density stardust & micro-circuits
- Concentric 3D orbital guide reticles and radial telemetry ticks
- Dynamic traveling synaptic energy pulses driven by voice amplitude and AI state
- Stark Industries corporate banner and HUD telemetry readout
"""
import math
import random
from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush,
    QRadialGradient, QFont, QPainterPath
)


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

        # ── 1. Central Neural Filaments & Synaptic Web (Tangled Golden Fibers) ─
        self.core_nodes = []
        for _ in range(320):
            lat = rng.uniform(-1.5, 1.5)
            lon = rng.uniform(0, math.tau)
            r_node = (rng.uniform(0.04, 0.44) ** 0.78) * 0.42
            self.core_nodes.append((
                r_node * math.cos(lat) * math.cos(lon),
                r_node * math.sin(lat) * 0.88,
                r_node * math.cos(lat) * math.sin(lon)
            ))

        self.core_edges = []
        linked = set()
        for i, a in enumerate(self.core_nodes):
            dists = sorted([(sum((x - y) ** 2 for x, y in zip(a, b)), j) for j, b in enumerate(self.core_nodes) if j != i])
            for d, j in dists[:8]:
                pair = tuple(sorted((i, j)))
                if pair not in linked and 0.0003 < d < 0.042:
                    linked.add(pair)
                    self.core_edges.append((*pair, rng.random()))

        self.core_hubs = [i for i in range(len(self.core_nodes)) if i % 4 == 0]

        # ── 2. Interleaved Logarithmic Spiral Arms (Accretion Whirlpool) ───────
        self.spiral_ribbons = []
        self.spiral_particles = []
        self.spiral_blocks = []
        self.spiral_ticks = []

        num_arms = 3
        for arm in range(num_arms):
            arm_offset = arm * (math.tau / num_arms)
            steps = 460
            for sub in range(6):
                sub_shift = (sub - 2.5) * 0.026
                pts = []
                for s in range(steps):
                    prog = s / steps
                    theta = 0.12 + prog * (3.6 * math.pi)
                    rad = 0.22 * math.exp(0.22 * theta) + sub_shift * (0.6 + 0.5 * prog)
                    if rad > 1.28:
                        break
                    angle = theta + arm_offset

                    py = 0.10 * math.sin(theta * 0.65 + arm_offset) * (rad ** 0.65)
                    px = rad * math.cos(angle)
                    pz = rad * math.sin(angle)
                    pts.append((px, py, pz))

                    if s % 2 == 0:
                        count = rng.randint(2, 5)
                        for _ in range(count):
                            jit_r = rng.gauss(0, 0.026 + 0.038 * prog)
                            jit_y = rng.gauss(0, 0.016 + 0.022 * prog)
                            jit_z = rng.gauss(0, 0.026 + 0.038 * prog)
                            spx = (rad + jit_r) * math.cos(angle)
                            spy = py + jit_y
                            spz = (rad + jit_r) * math.sin(angle) + jit_z
                            sz = rng.uniform(0.7, 2.2) if rng.random() > 0.08 else rng.uniform(2.4, 4.5)
                            bright = rng.uniform(0.40, 1.0)
                            self.spiral_particles.append((spx, spy, spz, sz, bright, arm))

                    if sub in (1, 3, 4) and s % 4 == 0 and s > 8:
                        tang_x = -math.sin(angle)
                        tang_z = math.cos(angle)
                        b_len = rng.uniform(0.018, 0.058)
                        b_wid = rng.uniform(0.006, 0.016)
                        self.spiral_blocks.append(((px, py, pz), (tang_x, 0.0, tang_z), b_len, b_wid, rng.uniform(0.55, 0.98)))

                    if sub in (0, 5) and s % 2 == 0 and s > 6:
                        norm_x = math.cos(angle)
                        norm_z = math.sin(angle)
                        is_maj = (s % 7 == 0)
                        t_len = rng.uniform(0.022, 0.046) if is_maj else rng.uniform(0.007, 0.016)
                        direction = 1.0 if sub == 5 else -1.0
                        p1 = (px, py, pz)
                        p2 = (px + norm_x * t_len * direction, py, pz + norm_z * t_len * direction)
                        self.spiral_ticks.append((p1, p2, rng.uniform(0.40, 0.92), is_maj))

                self.spiral_ribbons.append((pts, sub))

        self.ambient_dust = []
        for _ in range(320):
            a_rad = rng.uniform(0.06, 1.30)
            a_ang = rng.uniform(0, math.tau)
            a_y = rng.uniform(-0.32, 0.32)
            self.ambient_dust.append((
                a_rad * math.cos(a_ang),
                a_y,
                a_rad * math.sin(a_ang),
                rng.uniform(0.6, 2.2),
                rng.uniform(0.20, 0.75)
            ))

        self.orbital_radii = [0.28, 0.44, 0.65, 0.86, 1.06, 1.24]

    def step(self, dt, amp, speaking=False, muted=False, state="IDLE"):
        dt = min(0.1, max(0.0, dt))
        self.amp_smooth += (max(0.0, min(1.0, amp)) - self.amp_smooth) * (1.0 - math.exp(-dt * 12))
        thinking = state in ("THINKING", "PROCESSING")
        target = 0.0 if muted else (0.88 if thinking else (0.42 + self.amp_smooth * 0.58 if speaking else 0.18))
        self.activity += (target - self.activity) * (1.0 - math.exp(-dt * 6))
        self.clock += dt * (0.8 + 1.2 * self.activity)
        self.phase += dt * (0.025 if muted else 0.09 + 0.12 * self.activity)

        self._pulse_wait -= dt
        if self._pulse_wait <= 0:
            self._pulse_wait = self._pulse_rng.uniform(0.4, 1.4)
            depth = 0.02 + 0.07 * self.activity
            self._pulse_target = 1.0 + self._pulse_rng.uniform(-1.0, 0.85) * depth
        wave = math.sin(self.clock * 2.3) * 0.010 + math.sin(self.clock * 3.7 + 0.8) * 0.007
        target_scale = 1.0 if muted else self._pulse_target + wave + self.amp_smooth * 0.022
        self.pulse_scale += (target_scale - self.pulse_scale) * (1.0 - math.exp(-dt * 4.8))
        self.pulse_scale = max(0.88, min(1.10, self.pulse_scale))

    def paint(self, p: QPainter, cx: float, cy: float, r: float, W: float, H: float,
              main: QColor, acc: QColor, bg: QColor, name: str = "J.A.R.V.I.S.",
              state: str = "IDLE", speaking: bool = False, muted: bool = False):
        t = self.phase
        r = min(r * self.pulse_scale, min(W, H) * 0.44)
        amp = self.amp_smooth
        activity = 0.0 if muted else self.activity

        if muted:
            c_hot   = QColor(165, 175, 185)
            c_gold  = QColor(115, 125, 135)
            c_amber = QColor(85, 95, 105)
            c_deep  = QColor(50, 58, 65)
        else:
            c_hot   = QColor(255, 248, 205) # Radiant white-yellow
            c_gold  = QColor(255, 185, 30)  # Vibrant warm gold
            c_amber = QColor(255, 120, 10)  # Rich amber orange
            c_deep  = QColor(215, 65, 5)    # Burnt fiery orange

        def alpha_col(col: QColor, a: float) -> QColor:
            k = max(0.0, min(1.0, a))
            return QColor(col.red(), col.green(), col.blue(), int(255 * k))

        # 3D Camera tilt (perspective view matching reference photo angle)
        pitch = 0.52 + 0.03 * math.sin(t * 0.45)
        yaw = t

        def project(x, y, z):
            rx = x * math.cos(yaw) + z * math.sin(yaw)
            rz = -x * math.sin(yaw) + z * math.cos(yaw)
            ry = y * math.cos(pitch) - rz * math.sin(pitch)
            rz = y * math.sin(pitch) + rz * math.cos(pitch)
            k = 4.6 / (4.6 + rz)
            return QPointF(cx + r * rx * k, cy + r * ry * k), rz

        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── 1. Soft Warm Ambient Vignette & Corona Glow (Additive Alpha) ─────
        p.setPen(Qt.PenStyle.NoPen)
        for g_rad, g_alpha in (
            (r * 1.35, 0.06 + amp * 0.04),
            (r * 0.85, 0.12 + amp * 0.06),
            (r * 0.50, 0.22 + amp * 0.10),
            (r * 0.26, 0.38 + amp * 0.15),
        ):
            grad = QRadialGradient(cx, cy, g_rad)
            grad.setColorAt(0.00, alpha_col(c_hot, g_alpha))
            grad.setColorAt(0.35, alpha_col(c_gold, g_alpha * 0.75))
            grad.setColorAt(0.70, alpha_col(c_deep, g_alpha * 0.30))
            grad.setColorAt(1.00, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(grad))
            p.drawEllipse(QRectF(cx - g_rad, cy - g_rad, g_rad * 2, g_rad * 2))

        # ── 2. Concentric 3D Orbital Reticle Rings ───────────────────────────
        p.setBrush(Qt.BrushStyle.NoBrush)
        for idx, rad_scale in enumerate(self.orbital_radii):
            rad_orb = r * rad_scale
            a_ring = 0.26 if idx in (1, 3) else 0.14
            w_ring = 1.1 if idx in (1, 3) else 0.8
            orb_pts = [project(rad_orb * math.cos(math.radians(deg)), 0.0, rad_orb * math.sin(math.radians(deg)))[0] for deg in range(0, 360, 4)]
            poly = QPainterPath()
            poly.moveTo(orb_pts[0])
            for pt in orb_pts[1:]:
                poly.lineTo(pt)
            poly.closeSubpath()
            p.setPen(QPen(alpha_col(c_amber if idx % 2 else c_gold, a_ring), w_ring))
            p.drawPath(poly)

        draw_items = []  # (depth_z, type, data)

        # ── 3. Spiral Ribbons ────────────────────────────────────────────────
        for pts, sub in self.spiral_ribbons:
            proj_pts = [project(*pt) for pt in pts]
            for i in range(len(proj_pts) - 1):
                p1, z1 = proj_pts[i]
                p2, z2 = proj_pts[i + 1]
                mid_z = (z1 + z2) / 2.0
                prog = i / len(proj_pts)
                pulse_shimmer = 0.85 + 0.15 * math.sin(self.clock * 4.0 - prog * 10.0)
                bright = (0.32 + 0.55 * (1.0 - prog * 0.35)) * pulse_shimmer
                draw_items.append((mid_z, "ribbon", (p1, p2, bright, sub)))

        # ── 4. Spiral Data Blocks ────────────────────────────────────
        for (bx, by, bz), (tx, ty, tz), blen, bwid, bbright in self.spiral_blocks:
            p_c, z_c = project(bx, by, bz)
            p_t, _ = project(bx + tx * blen, by + ty * blen, bz + tz * blen)
            dx = p_t.x() - p_c.x()
            dy = p_t.y() - p_c.y()
            leng = math.hypot(dx, dy)
            if leng > 0.5:
                ang = math.degrees(math.atan2(dy, dx))
                draw_items.append((z_c, "block", (p_c, leng, bwid * r, ang, bbright)))

        # ── 5. Spiral Ticks ──────────────────────────────────────────────────
        for p1, p2, bright, is_maj in self.spiral_ticks:
            pt1, z1 = project(*p1)
            pt2, z2 = project(*p2)
            draw_items.append(((z1 + z2) / 2.0, "tick", (pt1, pt2, bright, is_maj)))

        # ── 6. Tangled Core Neural Filaments (Dense Golden Fibers) ───────────
        for i, j, seed in self.core_edges:
            a, b = self.core_nodes[i], self.core_nodes[j]
            pt1, z1 = project(*a)
            pt2, z2 = project(*b)
            mid_z = (z1 + z2) / 2.0
            draw_items.append((mid_z, "core_edge", (pt1, pt2, 0.52 + activity * 0.45, seed)))

        # Core hub synaptic nodes
        for hub_idx in self.core_hubs:
            hub_pt, z_hub = project(*self.core_nodes[hub_idx])
            draw_items.append((z_hub, "core_hub", (hub_pt, 0.65 + activity * 0.35)))

        # Dynamic Synaptic Impulses traveling through the core & arms
        if activity > 0.05:
            for idx, (i, j, seed) in enumerate(self.core_edges):
                if seed > activity * 0.45:
                    continue
                prog_imp = (self.clock * (0.8 + seed * 1.2) + seed * 4.0) % 1.0
                a, b = self.core_nodes[i], self.core_nodes[j]
                ix = a[0] + (b[0] - a[0]) * prog_imp
                iy = a[1] + (b[1] - a[1]) * prog_imp
                iz = a[2] + (b[2] - a[2]) * prog_imp
                imp_pt, z_imp = project(ix, iy, iz)
                draw_items.append((z_imp, "impulse", (imp_pt, 0.85 + 0.15 * amp)))

        # ── 7. Stardust Particles & Ambient Dust ─────────────────────────────
        for px, py, pz, sz, bright, arm in self.spiral_particles:
            pt, z = project(px, py, pz)
            draw_items.append((z, "particle", (pt, sz, bright, True)))

        for px, py, pz, sz, bright in self.ambient_dust:
            pt, z = project(px, py, pz)
            draw_items.append((z, "particle", (pt, sz, bright, False)))

        # Sort all 3D items back-to-front for proper depth layering
        draw_items.sort(key=lambda item: item[0], reverse=True)

        # ── 8. Draw Sorted Depth Items ───────────────────────────────────────
        for z, kind, data in draw_items:
            depth_dim = max(0.20, min(1.0, 1.10 - 0.35 * z))

            if kind == "ribbon":
                p1, p2, bright, sub = data
                alpha = max(0.04, min(1.0, bright * depth_dim))
                col = c_gold if sub in (0, 2, 4) else c_amber
                p.setPen(QPen(alpha_col(col, alpha), 1.3 if sub == 2 else 0.85))
                p.drawLine(p1, p2)

            elif kind == "block":
                p_c, leng, b_wid, ang, bright = data
                alpha = max(0.12, min(0.98, bright * depth_dim * (0.8 + 0.25 * amp)))
                p.save()
                p.translate(p_c)
                p.rotate(ang)
                p.setPen(QPen(alpha_col(c_hot, alpha), 0.7))
                p.setBrush(QBrush(alpha_col(c_amber, alpha * 0.80)))
                p.drawRect(QRectF(-leng * 0.5, -b_wid * 0.5, leng, b_wid))
                p.restore()

            elif kind == "tick":
                p1, p2, bright, is_maj = data
                alpha = max(0.08, min(0.95, bright * depth_dim))
                pen_w = 1.3 if is_maj else 0.75
                p.setPen(QPen(alpha_col(c_gold if is_maj else c_amber, alpha), pen_w))
                p.drawLine(p1, p2)

            elif kind == "core_edge":
                p1, p2, alpha_raw, seed = data
                alpha = max(0.18, min(0.99, alpha_raw * depth_dim))
                col = c_hot if seed > 0.60 else (c_gold if seed > 0.25 else c_amber)
                p.setPen(QPen(alpha_col(col, alpha), 1.3 if seed > 0.70 else 0.85))
                p.drawLine(p1, p2)

            elif kind == "core_hub":
                hub_pt, b_hub = data
                alpha = max(0.25, min(0.99, b_hub * depth_dim))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(alpha_col(c_hot, alpha)))
                p.drawEllipse(hub_pt, 1.8, 1.8)

            elif kind == "impulse":
                imp_pt, b_imp = data
                alpha = max(0.35, min(0.99, b_imp * depth_dim))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(alpha_col(c_hot, alpha)))
                p.drawEllipse(imp_pt, 2.4, 2.4)
                p.setBrush(QBrush(alpha_col(c_gold, alpha * 0.50)))
                p.drawEllipse(imp_pt, 4.2, 4.2)

            elif kind == "particle":
                pt, sz, bright, is_stream = data
                alpha = max(0.12, min(0.99, bright * depth_dim))
                p.setPen(Qt.PenStyle.NoPen)
                if sz > 1.8:
                    p.setBrush(QBrush(alpha_col(c_amber, alpha * 0.40)))
                    p.drawEllipse(pt, sz * 1.4, sz * 1.4)
                p.setBrush(QBrush(alpha_col(c_hot if bright > 0.70 else c_gold, alpha)))
                p.drawEllipse(pt, sz * 0.65, sz * 0.65)

        # ── 9. Radiant Center Focus Reticle & Core Bloom ─────────────────────
        core_r = r * (0.13 + 0.025 * amp + 0.01 * math.sin(self.clock * 4.5))

        # Soft central bloom
        nuc_grad = QRadialGradient(cx, cy, core_r * 1.2)
        nuc_grad.setColorAt(0.00, alpha_col(c_hot, 0.75 + 0.20 * amp))
        nuc_grad.setColorAt(0.40, alpha_col(c_gold, 0.45 + 0.15 * amp))
        nuc_grad.setColorAt(0.75, alpha_col(c_amber, 0.18))
        nuc_grad.setColorAt(1.00, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(nuc_grad))
        p.drawEllipse(QPointF(cx, cy), core_r * 1.2, core_r * 1.2)

        # Concentric thin golden rings (bullseye center seen in reference image)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha_col(c_hot, 0.98), 2.4))
        p.drawEllipse(QPointF(cx, cy), core_r * 0.82, core_r * 0.82)

        p.setPen(QPen(alpha_col(c_gold, 0.80), 1.2))
        p.drawEllipse(QPointF(cx, cy), core_r * 1.28, core_r * 1.28)

        ret_r = core_r * 1.72
        p.setPen(QPen(alpha_col(c_gold, 0.68), 1.4))
        p.drawArc(QRectF(cx - ret_r, cy - ret_r, ret_r * 2, ret_r * 2), int((self.clock * 20) * 16), 260 * 16)

        # ── 10. Top-Left: STARK INDUSTRIES Corporate Logo ────────────────────
        stark_x = cx - r * 1.28
        stark_y = cy - r * 0.98
        f_stark = QFont("Helvetica", max(11, int(r * 0.048)), QFont.Weight.Bold)
        f_stark.setItalic(True)
        p.setFont(f_stark)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha_col(c_gold, 0.92), 1.8))
        chev = QPainterPath()
        chev.moveTo(stark_x, stark_y + 14)
        chev.lineTo(stark_x + 18, stark_y + 14)
        chev.lineTo(stark_x + 30, stark_y)
        chev.lineTo(stark_x + 12, stark_y)
        chev.closeSubpath()
        p.drawPath(chev)

        p.setPen(QPen(alpha_col(c_gold, 0.95), 1.0))
        p.drawText(QPointF(stark_x + 36, stark_y + 12), "STARK INDUSTRIES")

        # ── 11. Bottom-Center: Golden "J . A . R . V . I . S ." with HUD Brackets ───
        bot_y = cy + r * 1.10
        raw_name = (name or "J.A.R.V.I.S.").strip()
        chars = [c for c in raw_name if c not in (" ", ".")]
        name_str = " . ".join(chars) + " ." if chars else "J . A . R . V . I . S ."

        f_name = QFont("Courier New", max(12, int(r * 0.054)), QFont.Weight.Bold)
        f_name.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.2)
        p.setFont(f_name)

        metrics = p.fontMetrics()
        txt_w = metrics.horizontalAdvance(name_str)
        txt_h = metrics.height()

        # Movie HUD golden yellow lettering
        p.setPen(QPen(alpha_col(c_gold, 0.98), 1.2))
        p.drawText(QRectF(cx - txt_w / 2.0, bot_y - txt_h / 2.0, txt_w, txt_h), Qt.AlignmentFlag.AlignCenter, name_str)

        # Technical bracket lines and arrows matching reference image:
        # |<────── [ J . A . R . V . I . S . ] ──────>|
        pad = 22.0
        line_w = r * 0.35
        lx = cx - txt_w / 2.0 - pad
        rx = cx + txt_w / 2.0 + pad

        p.setPen(QPen(alpha_col(c_amber, 0.78), 1.3))
        # Left side
        p.drawLine(QLineF(lx, bot_y, lx - line_w, bot_y))
        p.drawLine(QLineF(lx - line_w, bot_y - 5, lx - line_w, bot_y + 5))
        # Left arrow head <
        p.drawLine(QLineF(lx - line_w * 0.55, bot_y, lx - line_w * 0.55 + 5, bot_y - 4))
        p.drawLine(QLineF(lx - line_w * 0.55, bot_y, lx - line_w * 0.55 + 5, bot_y + 4))

        # Right side
        p.drawLine(QLineF(rx, bot_y, rx + line_w, bot_y))
        p.drawLine(QLineF(rx + line_w, bot_y - 5, rx + line_w, bot_y + 5))
        # Right arrow head >
        p.drawLine(QLineF(rx + line_w * 0.55, bot_y, rx + line_w * 0.55 - 5, bot_y - 4))
        p.drawLine(QLineF(rx + line_w * 0.55, bot_y, rx + line_w * 0.55 - 5, bot_y + 4))
