"""Layered holographic neural core with state-driven synaptic activity."""
import math
import random
from PyQt6.QtCore import QPointF, Qt, QRectF
from PyQt6.QtGui import QColor, QPen, QBrush, QRadialGradient


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
        self.traces = [(rng.uniform(-1.3,1.3),rng.uniform(0,math.tau),
                        rng.uniform(.08,.4),rng.choice((.72,.9,1.02)),rng.random())
                       for _ in range(116)]
        self.nodes=[]
        for _ in range(124):
            lat=rng.uniform(-1.25,1.25);lon=rng.uniform(0,math.tau);radius=rng.uniform(.24,.91)
            self.nodes.append(self._sphere(lat,lon,radius))
        self.edges=[]
        linked=set()
        for i,a in enumerate(self.nodes):
            near=sorted(((sum((x-y)**2 for x,y in zip(a,b)),j) for j,b in enumerate(self.nodes) if j!=i))
            for distance,j in near[:4]:
                pair=tuple(sorted((i,j)))
                if pair not in linked and .008<distance<.48:
                    linked.add(pair)
                    self.edges.append((*pair,rng.random()))
            # Occasional cross-cluster bridges make the inner graph a network.
            if i%9==0:
                candidates=[(distance,j) for distance,j in near if .25<distance<.8]
                if candidates:
                    _,j=rng.choice(candidates)
                    pair=tuple(sorted((i,j)))
                    if pair not in linked:
                        linked.add(pair);self.edges.append((*pair,rng.random()))

    @staticmethod
    def _sphere(lat,lon,rad=1):
        return (rad*math.cos(lat)*math.cos(lon),rad*math.sin(lat),rad*math.cos(lat)*math.sin(lon))

    def step(self,dt,amp,speaking=False,muted=False,state='IDLE'):
        dt=min(.1,max(0,dt))
        self.amp_smooth += (max(0,min(1,amp))-self.amp_smooth)*(1-math.exp(-dt*12))
        thinking=state in ('THINKING','PROCESSING')
        target=0 if muted else (.88 if thinking else (.38+self.amp_smooth*.62 if speaking else 0))
        self.activity += (target-self.activity)*(1-math.exp(-dt*6))
        self.clock += dt*(.7+1.1*self.activity)
        self.phase += dt*(.025 if muted else .085+.10*self.activity)
        # Uneven intervals and smooth interpolation avoid a mechanical heartbeat
        # or frame-to-frame jitter. Speech energy reinforces the organic pulse.
        self._pulse_wait -= dt
        if self._pulse_wait <= 0:
            self._pulse_wait = self._pulse_rng.uniform(.38,1.45)
            depth = .018 + .072*self.activity
            self._pulse_target = 1 + self._pulse_rng.uniform(-1,.85)*depth
        wave = math.sin(self.clock*2.3)*.009 + math.sin(self.clock*3.71+.8)*.006
        target_scale = 1 if muted else self._pulse_target + wave + self.amp_smooth*.018
        self.pulse_scale += (target_scale-self.pulse_scale)*(1-math.exp(-dt*4.8))
        self.pulse_scale = max(.88,min(1.08,self.pulse_scale))

    def paint(self,p,cx,cy,r,W,H,main,acc,bg,name='',state='IDLE',speaking=False,muted=False):
        color=QColor('#75818c') if muted else main
        light=QColor('#b2bdc6') if muted else color.lighter(190)
        hot=QColor('#d0d7dc') if muted else QColor('#f6c3d3')
        activity=0 if muted else self.activity
        t=self.phase
        # Shell, nucleus and graph breathe together, with headroom at the edges.
        r=min(r*self.pulse_scale,min(W,H)*.44)
        def tint(c,a):
            a=max(0,min(1,a))
            return QColor(int(bg.red()+(c.red()-bg.red())*a),int(bg.green()+(c.green()-bg.green())*a),int(bg.blue()+(c.blue()-bg.blue())*a))
        def project(x,y,z):
            x,z=x*math.cos(t)+z*math.sin(t),-x*math.sin(t)+z*math.cos(t)
            roll=.15+.05*math.sin(t)
            y,z=y*math.cos(roll)-z*math.sin(roll),y*math.sin(roll)+z*math.cos(roll)
            k=4.8/(4.8+z)
            return QPointF(cx+r*x*k,cy+r*y*k),z
        def sphere(lat,lon,rad=1):return self._sphere(lat,lon,rad)
        segments=[]
        def path(points,brightness=.5,width=.8,bright=False):
            pts=[project(*v) for v in points]
            for a,b in zip(pts,pts[1:]):
                segments.append(((a[1]+b[1])/2,a[0],b[0],brightness,width,bright))
        # Incomplete curved shells replace the regular globe grid.
        for shell,lat,start,span in ((1.02,-.83,.2,4.2),(.96,-.35,1.3,4.5),(.93,.12,.5,3.8),
                                    (1.02,.58,2.3,4.1),(.76,-.57,.8,4),(.74,.42,2.1,4.4)):
            path([sphere(lat,start+j*span/70,shell) for j in range(71)],.48)
        # Gyroscopic arcs and fine segmented registration marks.
        for index,rad in enumerate((.35,.63,.86,1.07)):
            tilt=.25+index*.57
            for offset in (.2,2.7,4.9):
                pts=[]
                for j in range(34):
                    a=offset+j*.046+t*(1 if index%2 else -1)
                    pts.append((rad*math.cos(a),rad*math.sin(a)*math.sin(tilt),rad*math.sin(a)*math.cos(tilt)))
                path(pts,.70,1.0,True)
            for j in range(38):
                a=j*math.tau/38+t*(1 if index%2 else -1)
                def at(rad):return (rad*math.cos(a),rad*math.sin(a)*math.sin(tilt),rad*math.sin(a)*math.cos(tilt))
                path([at(rad),at(rad+.017 if j%4 else rad+.035)],.5,.65)
        for lat,lon,length,rad,seed in self.traces:
            path([sphere(lat,lon+j*length/8,rad) for j in range(9)],.72,.8,seed>.7)
            path([sphere(lat,lon,rad),sphere(lat+.035,lon,rad),sphere(lat+.035,lon+.045,rad)],.55,.7)
            if seed>.7:
                # Small stepped extensions on the rim create circuit depth.
                path([sphere(lat,lon+length,rad),sphere(lat,lon+length,rad+.055),sphere(lat,lon+length+.08,rad+.055)],.6,.7)
        for i,j,seed in self.edges:
            path([self.nodes[i],self.nodes[j]],.12+activity*.33,.65,True)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for z,a,b,brightness,width,bright in sorted(segments,key=lambda item:item[0],reverse=True):
            alpha=max(.035,min(1,brightness*(1.05-.38*z)))
            p.setPen(QPen(tint(light if bright else color,alpha),width));p.drawLine(a,b)
        # Travelling impulses, driven by speaking/audio amplitude or thinking.
        if activity>.05:
            for i,j,seed in self.edges:
                if seed>activity*.58:continue
                progress=(self.clock*(.7+seed)+seed*3)%1
                a,b=self.nodes[i],self.nodes[j]
                def interpolate(t):return tuple(x+(y-x)*t for x,y in zip(a,b))
                head,z=project(*interpolate(progress))
                tail,_=project(*interpolate(max(0,progress-.16)))
                intensity=activity*(.72-.18*z)
                p.setPen(QPen(tint(color,intensity*.28),4.5));p.drawLine(tail,head)
                p.setPen(QPen(tint(light,intensity),1.25));p.drawLine(tail,head)
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(tint(hot,intensity))
                size=1.3+activity*.9;p.drawEllipse(head,size,size)
        for i,node in enumerate(self.nodes):
            point,z=project(*node)
            pulse=max(0,math.sin(self.clock*4-i*1.7))**8*activity
            alpha=(.22+pulse*.7)*max(.3,1-z*.3)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(tint(light,alpha))
            p.drawEllipse(point,1+pulse*1.6,1+pulse*1.6)
            if pulse>.42:
                p.setPen(QPen(tint(light,pulse*.35),.7));p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(point,3+pulse*3,3+pulse*3)
        # Compact, layered nucleus; no typography or opaque glowing disc.
        for index,scale in enumerate((.072,.105,.15)):
            radius=r*scale
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(tint(light,.42+activity*.2),.8))
            rect=QRectF(cx-radius,cy-radius,radius*2,radius*2)
            p.drawArc(rect,int((self.clock*18*(1 if index%2 else -1)+index*80)*16),245*16)
        glow=QRadialGradient(cx,cy,r*.045)
        glow.setColorAt(0,tint(hot,.48+activity*.35));glow.setColorAt(.25,tint(color,.35));glow.setColorAt(1,bg)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QBrush(glow));p.drawEllipse(QPointF(cx,cy),r*.045,r*.045)
