"""NumPy-only ride transforms for OVStage omni:xform row-vector matrices.

No pxr, OVRTX, GPU, or runtime imports. Position occupies matrix[3, :3].
Local-to-world composition is local @ parent. Angles are radians.
"""
from __future__ import annotations
import math
import numpy as np

WHEEL_ROOT='/World/Park/RIDE_WHEEL/Rotor'
TRAIN_ROOT='/World/Park/RIDE_COASTER/Train'


def rotation_y(angle: float) -> np.ndarray:
    """Return right-handed Y rotation in USD/OVStage row-vector convention."""
    c,s=math.cos(angle),math.sin(angle)
    m=np.eye(4,dtype=np.float64)
    m[:3,:3]=[[c,0,-s],[0,1,0],[s,0,c]]
    return m


def wheel_transforms(angle: float, center=(35.,25.,19.), radius=14., gondola_count=12) -> dict[str,np.ndarray]:
    """Rotor and gondola LOCAL transforms that keep all cabins upright.

    Write every returned matrix at the same OVStage ordinal, then advance the
    write floor. A gondola is attached at radius in the rotor's XZ plane. Its
    rotation cancels the rotor's orientation; translation still travels around
    the wheel. Do not rotate an already transformed world-space translation.
    """
    rotor=rotation_y(angle); rotor[3,:3]=center
    result={WHEEL_ROOT:rotor}
    for index in range(gondola_count):
        theta=2*math.pi*index/gondola_count
        cabin=rotation_y(-angle)
        cabin[3,:3]=[radius*math.cos(theta),0.,radius*math.sin(theta)]
        result[f'{WHEEL_ROOT}/Gondola_{index:02d}']=cabin
    return result


class CoasterRoute:
    """Arc-length lookup plus smooth tangent frame for a closed track.

    phase is normalized [0,1), advancing by dt / lap_seconds. Arc-length lookup
    gives uniform travel speed. This is presentation motion, not a physical
    ride dynamics or safety model.
    """
    def __init__(self,points):
        self.points=np.asarray(points,dtype=np.float64)
        if self.points.ndim!=2 or self.points.shape[1]!=3 or len(self.points)<3:
            raise ValueError('A closed route requires at least 3 XYZ points')
        self.edges=np.roll(self.points,-1,axis=0)-self.points
        self.lengths=np.linalg.norm(self.edges,axis=1)
        if np.any(self.lengths<1e-9):
            raise ValueError('Consecutive route points must be distinct')
        self.distances=np.concatenate(([0.],np.cumsum(self.lengths)))
        self.total_length=float(self.distances[-1])
        tangent=np.roll(self.points,-1,axis=0)-np.roll(self.points,1,axis=0)
        self.tangents=tangent/np.linalg.norm(tangent,axis=1)[:,None]

    def transform(self,phase: float,offset_m=0.) -> np.ndarray:
        """+X points forward, +Y left, +Z up; optional rearward offset in meters."""
        distance=(float(phase)*self.total_length+offset_m)%self.total_length
        i=min(int(np.searchsorted(self.distances,distance,side='right'))-1,len(self.points)-1)
        f=(distance-self.distances[i])/self.lengths[i]
        j=(i+1)%len(self.points)
        position=(1-f)*self.points[i]+f*self.points[j]
        forward=(1-f)*self.tangents[i]+f*self.tangents[j]
        forward/=np.linalg.norm(forward)
        left=np.cross([0.,0.,1.],forward)
        if np.linalg.norm(left)<1e-8:
            left=np.cross([0.,1.,0.],forward)
        left/=np.linalg.norm(left)
        up=np.cross(forward,left)
        result=np.eye(4,dtype=np.float64)
        result[0,:3]=forward;result[1,:3]=left;result[2,:3]=up;result[3,:3]=position
        return result


def train_transforms(route: CoasterRoute,phase: float,car_offsets=(0.,-2.3,-4.6)) -> dict[str,np.ndarray]:
    """Train root world pose plus car-local poses for an articulated train.

    All returned matrices must be written at the same ordinal. Each car is
    modeled around its own +X-forward local origin and follows an independent
    arc-length position, preserving constant inter-car distance along the rail.
    """
    lead=route.transform(phase)
    inverse=np.linalg.inv(lead)
    result={TRAIN_ROOT:lead}
    for index,offset in enumerate(car_offsets):
        result[f'{TRAIN_ROOT}/Car_{index:02d}']=route.transform(phase,offset_m=offset)@inverse
    return result


def advance_phase(phase: float,dt: float,period_seconds: float,running: bool=True) -> float:
    if period_seconds<=0:
        raise ValueError('Period must be positive')
    return (phase+max(0.,dt)/period_seconds)%1. if running else phase


if __name__=='__main__':
    import json
    from pathlib import Path
    rides=json.loads((Path(__file__).resolve().parents[1]/'assets/ride_paths.json').read_text())
    for angle in np.linspace(0,2*math.pi,25):
        transforms=wheel_transforms(angle)
        rotor=transforms[WHEEL_ROOT]
        for path,cabin in transforms.items():
            if path==WHEEL_ROOT:continue
            world=cabin@rotor
            assert np.allclose(world[:3,:3],np.eye(3),atol=1e-12),path
            assert abs(np.linalg.norm(world[3,:3]-rotor[3,:3])-14)<1e-10,path
    route=CoasterRoute(rides['coaster']['points'])
    for phase in np.linspace(0,1,401):
        mat=route.transform(phase)
        assert np.allclose(mat[:3,:3]@mat[:3,:3].T,np.eye(3),atol=1e-12)
        assert abs(np.linalg.det(mat[:3,:3])-1)<1e-12
        assert mat[2,2]>0
        # Forward direction must agree with the increasing-phase path.
        delta=route.transform(phase+1e-5)[3,:3]-mat[3,:3]
        assert np.dot(delta,mat[0,:3])>0
    for phase in np.linspace(0,1,101):
        poses=train_transforms(route,phase)
        for i in range(3):
            world=poses[f'{TRAIN_ROOT}/Car_{i:02d}']@poses[TRAIN_ROOT]
            assert np.allclose(world,route.transform(phase,offset_m=-2.3*i),atol=1e-10)
    assert np.allclose(train_transforms(route,0)[TRAIN_ROOT],train_transforms(route,1)[TRAIN_ROOT])
    assert advance_phase(.3,.1,100,False)==.3
    print(f'PASS: upright cabins at 25 angles; right-handed coaster frames at 401 phases; 3 articulated cars at 101 phases; track length {route.total_length:.2f} m')
