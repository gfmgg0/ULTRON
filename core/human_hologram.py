"""Anatomical hologram mesh driven by the existing 33 pose landmarks.

A stylized body, not an identity reconstruction. Hands use pose landmarks,
so individual finger articulation is deliberately not invented.
"""
import math
import numpy as np


def unit(v, fallback=(0,1,0)):
    length=np.linalg.norm(v)
    return v/length if length>1e-7 else np.array(fallback,dtype=float)


class HumanMesh:
    def __init__(self,points,confidence):
        self.points=np.asarray(points,dtype=float)
        self.confidence=np.asarray(confidence,dtype=float)
        self.faces=[]
        self.lines=[]
        self._build()

    def visible(self,*indices):
        return all(self.confidence[i]>=.45 for i in indices)

    def loft(self,rings,wire=True):
        """Connect anatomical cross-sections into a closed surface."""
        count=len(rings[0])
        for j in range(len(rings)-1):
            for i in range(count):
                k=(i+1)%count
                self.faces.append(np.array([rings[j][i],rings[j][k],rings[j+1][k],rings[j+1][i]]))
                if wire and (j%2==0):self.lines.append((rings[j][i],rings[j][k],.26))
                if wire and i%3==0:self.lines.append((rings[j][i],rings[j+1][i],.4))
        self.faces.append(np.array(list(reversed(rings[0]))))
        self.faces.append(np.array(rings[-1]))

    def tube(self,a,b,radii,depth=.9):
        axis=unit(b-a)
        side=unit(np.cross(axis,[0,0,1]),(1,0,0))
        front=unit(np.cross(side,axis),(0,0,-1))
        rings=[]
        for t,radius in radii:
            center=a*(1-t)+b*t
            rings.append([center+side*radius*math.cos(angle)+front*radius*depth*math.sin(angle)
                          for angle in np.linspace(0,math.tau,12,endpoint=False)])
        self.loft(rings)

    def ellipsoid(self,center,right,down,front,size):
        rings=[]
        for latitude in np.linspace(-math.pi/2+.05,math.pi/2-.05,9):
            rings.append([center+right*size[0]*math.cos(latitude)*math.cos(a)
                          +down*size[1]*math.sin(latitude)
                          +front*size[2]*math.cos(latitude)*math.sin(a)
                          for a in np.linspace(0,math.tau,16,endpoint=False)])
        self.loft(rings)

    def _build(self):
        p=self.points
        shoulder_width=np.linalg.norm(p[12]-p[11]) if self.visible(11,12) else .36
        scale=float(np.clip(shoulder_width/.36,.7,1.35))
        # Curved chest, narrower waist and rounded pelvis, all posed in 3D.
        if self.visible(11,12,23,24):
            shoulders=(p[11]+p[12])/2;hips=(p[23]+p[24])/2
            right=unit(p[12]-p[11],(1,0,0));down=unit(hips-shoulders)
            front=unit(np.cross(right,down),(0,0,1))
            hip_width=np.linalg.norm(p[24]-p[23])
            rings=[]
            profile=[(-.035,.80,.075),(0,.96,.10),(.15,1.0,.125),(.32,.95,.12),
                     (.53,.78,.095),(.72,.76,.09),(.88,.9,.105),(1.,1.,.115),(1.13,.74,.08)]
            for t,width_factor,depth in profile:
                center=shoulders*(1-t)+hips*t
                half=(shoulder_width*(1-max(0,t))+hip_width*max(0,t))*.5*width_factor
                rings.append([center+right*half*math.cos(a)+front*depth*scale*math.sin(a)
                              for a in np.linspace(0,math.tau,20,endpoint=False)])
            self.loft(rings)
        # Tapered muscle volumes, instead of uniform skeletal cylinders.
        for a,b,profile in [
            (11,13,[(0,.056),(.15,.068),(.45,.06),(.8,.042),(1,.037)]),
            (12,14,[(0,.056),(.15,.068),(.45,.06),(.8,.042),(1,.037)]),
            (13,15,[(0,.037),(.25,.048),(.55,.039),(1,.023)]),
            (14,16,[(0,.037),(.25,.048),(.55,.039),(1,.023)]),
            (23,25,[(0,.085),(.2,.093),(.55,.076),(.85,.052),(1,.048)]),
            (24,26,[(0,.085),(.2,.093),(.55,.076),(.85,.052),(1,.048)]),
            (25,27,[(0,.046),(.3,.062),(.53,.052),(.8,.031),(1,.025)]),
            (26,28,[(0,.046),(.3,.062),(.53,.052),(.8,.031),(1,.025)])]:
            if self.visible(a,b) and np.linalg.norm(p[b]-p[a])>.025:
                self.tube(p[a],p[b],[(t,r*scale) for t,r in profile])
        # Round joints remove visual seams while preserving measured articulation.
        for index,radius in [(11,.061),(12,.061),(13,.038),(14,.038),(25,.049),(26,.049)]:
            if self.visible(index):
                self.ellipsoid(p[index],np.array([1,0,0]),np.array([0,1,0]),np.array([0,0,1]),np.array([radius]*3)*scale)
        # Head orientation comes from ears, eyes and mouth, not a fixed sphere.
        if self.visible(0,7,8):
            right=unit(p[8]-p[7],(1,0,0))
            eyes=(p[2]+p[5])/2;mouth=(p[9]+p[10])/2
            down=unit(mouth-eyes,(0,1,0))
            down=unit(down-right*np.dot(down,right))
            front=unit(np.cross(right,down),(0,0,-1))
            ears=(p[7]+p[8])/2
            if np.dot(front,p[0]-ears)<0:front=-front
            width=float(np.clip(np.linalg.norm(p[8]-p[7])*.55,.065,.105))
            center=ears+down*.015
            # Skull to jaw profile: forehead, cheeks, jaw and chin.
            rings=[]
            for height,width_factor,depth_factor in [(-1,.15,.2),(-.85,.68,.72),(-.55,.96,.95),(-.1,1,1),(.25,.9,.95),(.57,.73,.78),(.85,.48,.6),(1,.15,.3)]:
                rings.append([center+down*(height*.125*scale)+right*(width*width_factor*math.cos(a))
                              +front*(.09*scale*depth_factor*math.sin(a))
                              for a in np.linspace(0,math.tau,20,endpoint=False)])
            self.loft(rings)
            # Simple, pose-driven facial landmarks provide a recognizable face.
            nose=center+front*.112*scale+down*.012
            bridge=center+front*.088*scale-down*.026
            base=center+front*.089*scale+down*.037
            self.faces.extend([np.array([bridge,nose,base-right*.016]),np.array([bridge,base+right*.016,nose])])
            for side in (-1,1):
                eye=center+right*(side*width*.43)-down*.027*scale+front*.08*scale
                self.lines.append((eye-right*.018*scale,eye+right*.018*scale,.95))
                brow=eye-down*.018*scale
                self.lines.append((brow-right*.022*scale,brow+right*.022*scale,.7))
            lip=center+down*.061*scale+front*.075*scale
            self.lines.append((lip-right*.027*scale,lip+right*.027*scale,.85))
            if self.visible(11,12):
                self.tube((p[11]+p[12])/2,center+down*.1*scale,[(0,.052*scale),(.5,.043*scale),(1,.042*scale)])
        # Simplified palms and thumbs follow the existing hand pose landmarks.
        for wrist,index,pinky,thumb in [(15,19,17,21),(16,20,18,22)]:
            if self.visible(wrist,index,pinky):
                tip=(p[index]+p[pinky])/2
                axis=unit(tip-p[wrist]);right=unit(p[index]-p[pinky],(1,0,0));front=unit(np.cross(right,axis),(0,0,1))
                center=(p[wrist]+tip)*.5
                length=float(np.clip(np.linalg.norm(tip-p[wrist])*.62,.04,.085))
                self.ellipsoid(center,right,axis,front,(.038*scale,length,.018*scale))
                if self.visible(thumb):self.tube(p[wrist]+(tip-p[wrist])*.25,p[thumb],[(0,.014*scale),(1,.009*scale)])
        for ankle,heel,toe in [(27,29,31),(28,30,32)]:
            if self.visible(ankle,heel,toe):
                axis=unit(p[toe]-p[heel],(0,0,-1));right=unit(np.cross(axis,[0,1,0]),(1,0,0));up=unit(np.cross(right,axis),(0,-1,0))
                center=(p[heel]+p[toe])/2
                self.ellipsoid(center,right,axis,up,(.045*scale,max(.07,np.linalg.norm(p[toe]-p[heel])*.6),.035*scale))
