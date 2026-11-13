"""Local webcam pose tracking and a perspective-projected 3D hologram window."""
from pathlib import Path
import math
import threading
import time
import numpy as np
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QImage, QPixmap, QPolygonF
from PyQt6.QtWidgets import (QDialog, QWidget, QLabel, QPushButton, QComboBox,
    QCheckBox, QSlider, QHBoxLayout, QVBoxLayout, QFrame, QApplication)

MODEL = Path(__file__).resolve().parent.parent / 'models/pose/pose_landmarker_lite.task'
BONES = [(11,12),(11,13),(13,15),(12,14),(14,16),(11,23),(12,24),
         (23,24),(23,25),(25,27),(24,26),(26,28),(27,29),(29,31),
         (28,30),(30,32),(15,19),(16,20)]

class PoseTracker:
    def __init__(self):
        import mediapipe as mp
        if not MODEL.is_file():
            raise FileNotFoundError('Modelo de rastreamento ausente em models/pose.')
        self.mp = mp
        self.detector = mp.tasks.vision.PoseLandmarker.create_from_options(
            mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=1,
                min_pose_detection_confidence=.5, min_pose_presence_confidence=.5,
                min_tracking_confidence=.5))
        self.last_timestamp = -1

    def detect(self, rgb, timestamp):
        timestamp = max(self.last_timestamp+1, int(timestamp))
        self.last_timestamp = timestamp
        result = self.detector.detect_for_video(
            self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)), timestamp)
        if not result.pose_world_landmarks:
            return None
        world = result.pose_world_landmarks[0]
        image = result.pose_landmarks[0]
        points = np.array([[p.x,p.y,p.z] for p in world],dtype=float)
        confidence = np.array([min(p.visibility or 0,p.presence or 0) for p in image])
        hip_x = (image[23].x+image[24].x)/2
        points[:,0] += (hip_x-.5)*1.6
        if not np.isfinite(points).all():
            return None
        return points, confidence

    def close(self):
        self.detector.close()

class MotionEngine:
    """One worker owns capture/inference; a single-slot mailbox prevents UI backlog."""
    def __init__(self):
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.latest = None
        self.status = 'Câmera desligada'
        self.active = False

    @property
    def running(self):
        return bool(self.thread and self.thread.is_alive())

    def start(self, index=0):
        if self.running:
            return False
        self.stop_event.clear()
        with self.lock:
            self.status='Iniciando câmera…'; self.latest=None
        self.thread=threading.Thread(target=self._run,args=(index,),daemon=True,name='UltronHoloMotion')
        self.thread.start()
        return True

    def stop(self):
        self.stop_event.set()

    def snapshot(self):
        with self.lock:
            return self.status, self.active, self.latest

    def _run(self,index):
        cap=tracker=None
        try:
            import cv2
            cap=cv2.VideoCapture(index)
            if not cap.isOpened():
                raise RuntimeError('Webcam indisponível. Verifique a conexão, permissões ou outro aplicativo usando a câmera.')
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
            cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
            with self.lock:self.active=True;self.status='Carregando rastreamento local…'
            tracker=PoseTracker()
            failures=0
            while not self.stop_event.is_set():
                started=time.monotonic()
                ok,frame=cap.read()
                if not ok:
                    failures+=1
                    if failures>=8:raise RuntimeError('A webcam parou de fornecer imagens. Reconecte e tente novamente.')
                    self.stop_event.wait(.08);continue
                failures=0
                rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                if rgb.shape[1]>640:
                    rgb=cv2.resize(rgb,(640,round(rgb.shape[0]*640/rgb.shape[1])))
                pose=tracker.detect(rgb,started*1000)
                preview=cv2.resize(rgb,(320,round(rgb.shape[0]*320/rgb.shape[1])))
                fps=1/max(.001,time.monotonic()-started)
                with self.lock:
                    self.latest=(time.monotonic(),pose,preview,fps)
                    self.status='Rastreamento ativo' if pose is not None else 'Buscando corpo — afaste-se e enquadre braços e pernas'
                self.stop_event.wait(max(0,1/20-(time.monotonic()-started)))
        except Exception as exc:
            with self.lock:self.status=f'Não foi possível rastrear: {exc}'
        finally:
            if cap is not None:cap.release()
            try:
                if tracker is not None:tracker.close()
            finally:
                with self.lock:
                    self.active=False;self.latest=None
                    if self.stop_event.is_set():self.status='Câmera desligada'

class HologramCanvas(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setMinimumSize(360,380)
        self.points=None;self.confidence=None;self.mesh=None;self.yaw=-.15;self.mirror=True
        self.last_pose=0.;self.phase=0.;self.demo=False
        self.timer=QTimer(self);self.timer.timeout.connect(self._tick);self.timer.start(33)

    def _tick(self):
        self.phase+=.025
        if not self.demo and self.last_pose and time.monotonic()-self.last_pose>.65:
            self.points=None;self.confidence=None
        self.update()

    def set_pose(self,pose):
        if pose is None:
            self.points=None;self.confidence=None;self.mesh=None;return
        points,confidence=pose
        self.points=points.copy() if self.points is None else self.points*.45+points*.55
        self.confidence=confidence.copy();self.last_pose=time.monotonic()
        from core.human_hologram import HumanMesh
        self.mesh=HumanMesh(self.points,self.confidence)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),QColor('#080e16'))
        w,h=self.width(),self.height();scale=min(w*.48,h*.44)
        def project(v):
            x,y,z=v
            if self.mirror:x=-x
            x,z=x*math.cos(self.yaw)+z*math.sin(self.yaw),-x*math.sin(self.yaw)+z*math.cos(self.yaw)
            y,z=y*math.cos(.10)-z*math.sin(.10),y*math.sin(.10)+z*math.cos(.10)
            k=4.5/max(1.5,4.5+z)
            return QPointF(w/2+x*scale*k,h*.5+y*scale*k),z
        def line(a,b,col='#3e8387',width=1):
            p.setPen(QPen(QColor(col),width));p.drawLine(project(a)[0],project(b)[0])
        # A three-dimensional stage remains visible when no pose is detected.
        for n in range(-5,6):
            k=n*.25
            line((k,.95,-1.25),(k,.95,1.25),'#172e35')
            line((-1.25,.95,k),(1.25,.95,k),'#172e35')
        for radius in (.45,.75,1.):
            ring=[(radius*math.cos(a),.94,radius*math.sin(a)) for a in np.linspace(0,math.tau,80)]
            for a,b in zip(ring,ring[1:]):line(a,b,'#28515a')
        p.setFont(QFont('Noto Sans',9));p.setPen(QColor('#699399'))
        p.drawText(22,28,'HOLO MOTION  /  AVATAR HUMANO')
        if self.points is None:
            p.setPen(QColor('#a2b3be'));p.setFont(QFont('Noto Sans',12))
            p.drawText(QRectF(20,h*.35,w-40,70),Qt.AlignmentFlag.AlignCenter,'Seu holograma aparece aqui\nquando um corpo é detectado')
        else:
            mesh=self.mesh
            surfaces=[]
            if mesh is not None:
                for face in mesh.faces:
                    projected=[project(vertex) for vertex in face]
                    depth=sum(item[1] for item in projected)/len(projected)
                    normal=np.cross(face[1]-face[0],face[2]-face[0])
                    norm=np.linalg.norm(normal)
                    illumination=.35+.65*abs(float(np.dot(normal/max(norm,1e-8),[.3,-.35,-.88])))
                    surfaces.append((depth,QPolygonF([item[0] for item in projected]),illumination))
                p.setPen(Qt.PenStyle.NoPen)
                # Translucent shaded surfaces make the silhouette legible;
                # the fine mesh retains the holographic character.
                for depth,polygon,light in sorted(surfaces,key=lambda item:item[0],reverse=True):
                    color=QColor(int(20+35*light),int(80+85*light),int(91+88*light),175)
                    p.setBrush(color);p.drawPolygon(polygon)
                p.setBrush(Qt.BrushStyle.NoBrush)
                for a,b,alpha in mesh.lines:
                    pa,za=project(a);pb,zb=project(b)
                    color=QColor('#9ae8e2');color.setAlphaF(max(.12,min(.8,alpha*(.72-(za+zb)*.1))))
                    p.setPen(QPen(color,.75 if alpha<.8 else 1.3));p.drawLine(pa,pb)
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor('#506c79'));p.setFont(QFont('Noto Sans',8))
        p.drawText(22,h-18,'CORPO ESTILIZADO  ·  PROFUNDIDADE ESTIMADA  ·  LOCAL')
        if self.demo:
            p.setPen(QColor('#ffbf60'));p.drawText(w-250,28,'PRÉVIA COM POSE DE TESTE')
        p.end()

class HologramWindow(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle('ULTRON / Holo Motion')
        self.resize(1100,740);self.setMinimumSize(820,600)
        self.engine=MotionEngine();self.last_frame=0.;self._was_running=False;self._start_pending=False
        self.setStyleSheet('QDialog {background:#0b111b;color:#dfe9ef;} QLabel,QCheckBox {color:#aebfcb;} QPushButton,QComboBox {background:#182432;color:#e4edf2;border:1px solid #304657;border-radius:7px;padding:9px;} QPushButton:hover {border-color:#ffb547;} QPushButton:disabled {color:#586975;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(22,20,22,18);layout.setSpacing(16)
        header=QHBoxLayout();title=QLabel('HOLO MOTION');title.setStyleSheet('font-size:23px;font-weight:600;color:#f3e3bc;letter-spacing:3px;')
        header.addWidget(title);header.addStretch();self.badge=QLabel('● CÂMERA DESLIGADA');header.addWidget(self.badge);layout.addLayout(header)
        sub=QLabel('Seu movimento, reconstruído em luz.');sub.setStyleSheet('font-size:12px;color:#718a9a;');layout.addWidget(sub)
        body=QHBoxLayout();body.setSpacing(18);self.canvas=HologramCanvas();body.addWidget(self.canvas,1)
        panel=QFrame();panel.setFixedWidth(265);side=QVBoxLayout(panel);side.setContentsMargins(0,0,0,0);side.setSpacing(8)
        side.addWidget(QLabel('CONTROLE DE CAPTURA'))
        self.camera=QComboBox()
        try:
            from memory.config_manager import load_api_keys
            saved=int(load_api_keys().get('camera_index',0))
        except Exception:saved=0
        indices=sorted(set([saved,0,1,2,3]))
        for i in indices:self.camera.addItem(f'Câmera {i}',i)
        self.camera.setCurrentIndex(indices.index(saved));side.addWidget(self.camera)
        self.start_button=QPushButton('Iniciar rastreamento');self.start_button.setFixedHeight(36);self.start_button.clicked.connect(self.start_tracking);side.addWidget(self.start_button)
        self.stop_button=QPushButton('Parar e liberar câmera');self.stop_button.setFixedHeight(36);self.stop_button.clicked.connect(self.stop_tracking);self.stop_button.setEnabled(False);side.addWidget(self.stop_button)
        self.preview_toggle=QCheckBox('Mostrar prévia da câmera');self.preview_toggle.setChecked(True);self.preview_toggle.toggled.connect(lambda value:self.preview.setVisible(value));side.addWidget(self.preview_toggle)
        self.preview=QLabel('Prévia local');self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.setFixedSize(265,145);self.preview.setStyleSheet('background:#060b12;border:1px solid #243546;border-radius:9px;color:#536c7d;');side.addWidget(self.preview)
        self.mirror=QCheckBox('Espelhar movimentos');self.mirror.setChecked(True);self.mirror.toggled.connect(self._set_mirror);side.addWidget(self.mirror)
        side.addWidget(QLabel('Ângulo da visualização 3D'))
        self.angle=QSlider(Qt.Orientation.Horizontal);self.angle.setRange(-90,90);self.angle.setValue(-9);self.angle.valueChanged.connect(lambda value:setattr(self.canvas,'yaw',math.radians(value)));side.addWidget(self.angle)
        self.stats=QLabel('Sem captura');side.addWidget(self.stats)
        hint=QLabel('Enquadre o corpo e mantenha boa iluminação. O avatar acompanha o corpo visível. Mãos simplificadas; rosto e proporções são estimados.');hint.setWordWrap(True);hint.setStyleSheet('color:#758e9f;font-size:11px;');side.addWidget(hint)
        side.addStretch();private=QLabel('LOCAL · SEM GRAVAÇÃO\nA câmera é liberada ao fechar.');private.setStyleSheet('color:#67a6a3;font-size:10px;');side.addWidget(private)
        body.addWidget(panel);layout.addLayout(body,1)
        self.status=QLabel('Pronto. Inicie a captura para gerar seu holograma.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.timer=QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(50)
        QApplication.instance().aboutToQuit.connect(self.stop_tracking)

    def _set_mirror(self,value):self.canvas.mirror=value

    def start_tracking(self):
        if self.engine.running or self._start_pending:
            return
        self._start_pending=True
        self.start_button.setEnabled(False)
        parent=self.parent()
        if parent is not None and hasattr(parent,'stop_camera_stream'):
            parent.stop_camera_stream()
        QTimer.singleShot(250,self._begin_capture)

    def _begin_capture(self):
        if not self._start_pending:
            return
        self._start_pending=False
        if self.engine.start(self.camera.currentData()):
            self._was_running=True;self.last_frame=0
            self.start_button.setEnabled(False);self.camera.setEnabled(False);self.stop_button.setEnabled(True)

    def stop_tracking(self):
        self._start_pending=False
        if not self.engine.running:self.start_button.setEnabled(True)
        self.engine.stop();self.canvas.set_pose(None)
        self.preview.clear();self.preview.setText('Câmera desligada')
        if self.engine.running:self.status.setText('Encerrando captura…')

    def poll(self):
        status,active,latest=self.engine.snapshot()
        self.status.setText(status)
        self.badge.setText('● CÂMERA ATIVA' if active else '● CÂMERA DESLIGADA')
        self.badge.setStyleSheet('color:#69ded3;' if active else 'color:#718392;')
        if latest and latest[0]!=self.last_frame and not self.engine.stop_event.is_set():
            stamp,pose,rgb,fps=latest;self.last_frame=stamp
            self.canvas.set_pose(pose)
            if self.preview_toggle.isChecked():
                h,w,_=rgb.shape;image=QImage(rgb.data,w,h,rgb.strides[0],QImage.Format.Format_RGB888).copy()
                if self.mirror.isChecked():image=image.mirrored(True,False)
                self.preview.setPixmap(QPixmap.fromImage(image).scaled(self.preview.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            self.stats.setText(f'{min(20,fps):.0f} quadros/s · '+(f'{int((pose[1]>.45).sum())}/33 pontos visíveis' if pose is not None else 'Sem corpo detectado'))
        if self._was_running and not self.engine.running:
            self._was_running=False;self.start_button.setEnabled(True);self.camera.setEnabled(True);self.stop_button.setEnabled(False)
            self.canvas.set_pose(None);self.preview.clear();self.preview.setText('Câmera desligada');self.stats.setText('Sem captura')

    def reject(self):
        self.stop_tracking()
        super().reject()

    def closeEvent(self,event):
        self.stop_tracking()
        super().closeEvent(event)
