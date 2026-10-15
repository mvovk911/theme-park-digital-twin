#!/usr/bin/env python3
"""Build Aster Park, a self-contained procedural OpenUSD operational-twin scene."""
from pathlib import Path
import json, math, random
from pxr import Usd, UsdGeom, UsdShade, UsdLux, Gf, Sdf
from animate import CoasterRoute, train_transforms, TRAIN_ROOT

OUT = Path(__file__).resolve().parents[1] / 'assets'
OUT.mkdir(exist_ok=True)
stage = Usd.Stage.CreateNew(str(OUT/'park.usda'))
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
stage.SetStartTimeCode(0); stage.SetEndTimeCode(720); stage.SetTimeCodesPerSecond(30)
world=UsdGeom.Xform.Define(stage,'/World'); stage.SetDefaultPrim(world.GetPrim())
UsdGeom.Xform.Define(stage,'/World/Park')
random.seed(42)
materials={}; counts={}; registry=[]

def material(name,color,rough=.5,metal=0,opacity=1):
    m=UsdShade.Material.Define(stage,'/World/Materials/'+name)
    s=UsdShade.Shader.Define(stage,m.GetPath().AppendChild('Surface')); s.CreateIdAttr('UsdPreviewSurface')
    s.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    s.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(rough)
    s.CreateInput('metallic',Sdf.ValueTypeNames.Float).Set(metal)
    if opacity<1: s.CreateInput('opacity',Sdf.ValueTypeNames.Float).Set(opacity)
    m.CreateSurfaceOutput().ConnectToSource(s.ConnectableAPI(),'surface')
    materials[name]=m
for args in [
 ('grass',(.22,.43,.22),.95),('grass_light',(.34,.58,.29),.9),('paver',(.72,.68,.56),.9),
 ('path',(.83,.77,.65),.8),('road',(.12,.15,.18),.9),('stripe',(.95,.91,.72),.6),
 ('teal',(.025,.46,.46),.3,.45),('blue',(.055,.24,.54),.35,.3),('orange',(1,.30,.06),.35,.25),
 ('yellow',(1,.71,.14),.45,.1),('cream',(.94,.90,.76),.7),('white',(.92,.95,.95),.4),
 ('dark',(.035,.065,.085),.5,.3),('steel',(.37,.46,.49),.3,.7),('roof',(.14,.23,.28),.7,.15),
 ('glass',(.10,.39,.49),.12,.45),('leaf1',(.12,.35,.18),.9),('leaf2',(.19,.47,.21),.9),
 ('leaf3',(.36,.59,.23),.9),('bark',(.27,.15,.07),.95),('water',(.055,.46,.64),.10,.6),
 ('water_light',(.23,.68,.76),.15,.25),('pink',(.83,.13,.34),.5),('purple',(.38,.19,.59),.5),
 ('solar',(.025,.09,.20),.16,.6),('red',(.85,.08,.08),.5),('stone',(.50,.52,.46),.9),
 ('skin',(.67,.41,.25),.8),('sand',(.81,.72,.49),.9),
 ('soil',(.17,.105,.055),1),('gravel',(.59,.57,.49),.95),('flower_lilac',(.67,.32,.71),.8),
 ('path_joint',(.51,.49,.43),.95),('timber',(.48,.30,.14),.85)]: material(*args)

def uniq(parent,name):
    k=parent+'/'+name; n=counts.get(k,0); counts[k]=n+1
    return k+(f'_{n:04d}' if n else '')
def bind(obj,mat): UsdShade.MaterialBindingAPI.Apply(obj.GetPrim()).Bind(materials[mat])
def xf(obj,pos=None,scale=None,rot=None):
    x=UsdGeom.Xformable(obj)
    if pos is not None: x.AddTranslateOp().Set(Gf.Vec3d(*pos))
    if rot is not None: x.AddRotateXYZOp().Set(Gf.Vec3f(*rot))
    if scale is not None: x.AddScaleOp().Set(Gf.Vec3f(*scale))
    return obj

def box(p,n,pos,size,mat,rot=None):
    o=UsdGeom.Cube.Define(stage,uniq(p,n)); o.CreateSizeAttr(1); xf(o,pos,size,rot); bind(o,mat); return o

def sphere(p,n,pos,r,mat,scale=None):
    o=UsdGeom.Sphere.Define(stage,uniq(p,n)); o.CreateRadiusAttr(r); xf(o,pos,scale); bind(o,mat); return o

def cyl(p,n,pos,r,h,mat,rot=None):
    o=UsdGeom.Cylinder.Define(stage,uniq(p,n)); o.CreateRadiusAttr(r); o.CreateHeightAttr(h); xf(o,pos,rot=rot); bind(o,mat); return o

def cone(p,n,pos,r,h,mat):
    o=UsdGeom.Cone.Define(stage,uniq(p,n)); o.CreateRadiusAttr(r); o.CreateHeightAttr(h); xf(o,pos); bind(o,mat); return o

def beam(p,n,a,b,r,mat):
    a,b=Gf.Vec3d(*a),Gf.Vec3d(*b); d=b-a
    o=UsdGeom.Cylinder.Define(stage,uniq(p,n)); o.CreateRadiusAttr(r); o.CreateHeightAttr(d.GetLength())
    x=UsdGeom.Xformable(o); x.AddTranslateOp().Set((a+b)/2)
    q=Gf.Rotation(Gf.Vec3d(0,0,1),d.GetNormalized()).GetQuat(); x.AddOrientOp().Set(Gf.Quatf(q))
    bind(o,mat); return o

def mesh(p,n,verts,faces,mat):
    o=UsdGeom.Mesh.Define(stage,uniq(p,n)); o.CreatePointsAttr(verts)
    o.CreateFaceVertexCountsAttr([len(f) for f in faces]); o.CreateFaceVertexIndicesAttr([i for f in faces for i in f])
    o.CreateSubdivisionSchemeAttr('none'); o.CreateDoubleSidedAttr(True); bind(o,mat); return o

def tube(p,n,pts,r,mat,sides=8,closed=False):
    verts=[]; faces=[]; nn=len(pts)
    for i,pt in enumerate(pts):
        prev=Gf.Vec3d(*pts[(i-1)%nn if closed else max(0,i-1)])
        nxt=Gf.Vec3d(*pts[(i+1)%nn if closed else min(nn-1,i+1)])
        t=(nxt-prev).GetNormalized(); v=Gf.Cross(t,Gf.Vec3d(0,0,1))
        if v.GetLength()<.01: v=Gf.Cross(t,Gf.Vec3d(0,1,0))
        v=v.GetNormalized(); w=Gf.Cross(t,v).GetNormalized(); c=Gf.Vec3d(*pt)
        for j in range(sides):
            a=j*2*math.pi/sides; vv=c+r*(math.cos(a)*v+math.sin(a)*w); verts.append(tuple(vv))
    for i in range(nn if closed else nn-1):
        for j in range(sides): faces.append((i*sides+j,i*sides+(j+1)%sides,((i+1)%nn)*sides+(j+1)%sides,((i+1)%nn)*sides+j))
    return mesh(p,n,verts,faces,mat)

FONT={
'A':['01110','11011','11011','11111','11011','11011','11011'],
'B':['11110','11011','11011','11110','11011','11011','11110'],
'C':['01111','11000','11000','11000','11000','11000','01111'],
'D':['11110','11011','11011','11011','11011','11011','11110'],
'E':['11111','11000','11000','11110','11000','11000','11111'],
'F':['11111','11000','11000','11110','11000','11000','11000'],
'G':['01111','11000','11000','11011','11011','11011','01111'],
'H':['11011','11011','11011','11111','11011','11011','11011'],
'I':['11111','00100','00100','00100','00100','00100','11111'],
'J':['00111','00011','00011','00011','11011','11011','01110'],
'K':['11011','11011','11110','11100','11110','11011','11011'],
'L':['11000','11000','11000','11000','11000','11000','11111'],
'M':['10001','11011','11111','10101','10001','10001','10001'],
'N':['11001','11101','11101','11011','11011','11011','11001'],
'O':['01110','11011','11011','11011','11011','11011','01110'],
'P':['11110','11011','11011','11110','11000','11000','11000'],
'Q':['01110','11011','11011','11011','11111','01110','00011'],
'R':['11110','11011','11011','11110','11100','11010','11011'],
'S':['01111','11000','11000','01110','00011','00011','11110'],
'T':['11111','00100','00100','00100','00100','00100','00100'],
'U':['11011','11011','11011','11011','11011','11011','01110'],
'V':['10001','10001','10001','11011','11011','01110','00100'],
'W':['10001','10001','10001','10101','11111','11011','10001'],
'X':['11011','11011','01110','00100','01110','11011','11011'],
'Y':['11011','11011','01110','00100','00100','00100','00100'],
'Z':['11111','00011','00110','00100','01100','11000','11111'],
' ':['00000']*7,
'1':['00100','01100','00100','00100','00100','00100','01110'],
'2':['01110','11011','00011','00110','01100','11000','11111']}

def text_mesh(p,text,pos,width,mat='cream'):
    cell=width/max(1,len(text)*6-1); verts=[]; faces=[]; x0=pos[0]-width/2
    for ci,ch in enumerate(text.upper()):
        for row,bits in enumerate(FONT.get(ch,FONT[' '])):
            for col,bit in enumerate(bits):
                if bit=='1':
                    x=x0+(ci*6+col)*cell; z=pos[2]+(6-row)*cell
                    i=len(verts); verts += [(x,pos[1],z),(x+cell*.91,pos[1],z),(x+cell*.91,pos[1],z+cell*.91),(x,pos[1],z+cell*.91)]
                    faces.append((i,i+1,i+2,i+3))
    mesh(p,'Lettering',verts,faces,mat)

def sign(p,label,pos,width=8):
    h=width/max(len(label)*6,12)*9+.3
    box(p,'SignBoard',pos,(width+.5,.22,h),'dark')
    text_mesh(p,label,(pos[0],pos[1]-.13,pos[2]-h/2+.15),width,'cream')

def asset(id,name,cat,pos,bounds,systems):
    p='/World/Park/'+id; root=UsdGeom.Xform.Define(stage,p)
    root.GetPrim().SetCustomDataByKey('assetId',id)
    root.GetPrim().SetCustomDataByKey('assetName',name)
    root.GetPrim().CreateAttribute('park:assetId',Sdf.ValueTypeNames.String,True).Set(id)
    registry.append(dict(asset_id=id,prim_path=p,name=name,category=cat,position=pos,bounds=bounds,systems=systems))
    return p

def fence(p,a,b,h=1.45,spacing=2.2,mat='teal'):
    dx=b[0]-a[0];dy=b[1]-a[1]; dist=math.hypot(dx,dy); n=max(1,round(dist/spacing))
    for i in range(n+1):
        t=i/n; cyl(p,'FencePost',(a[0]+dx*t,a[1]+dy*t,h/2+.1),.065,h,mat)
    for z in [.45,h]: beam(p,'FenceRail',(a[0],a[1],z),(b[0],b[1],z),.045,mat)
    for i in range(n*3+1):
        t=i/(n*3); beam(p,'FencePicket',(a[0]+dx*t,a[1]+dy*t,.18),(a[0]+dx*t,a[1]+dy*t,h-.12),.022,mat)

def building(p,pos,size,mat='cream',roof='teal'):
    x,y,z=pos; w,d,h=size
    box(p,'Foundation',(x,y,.18),(w+.6,d+.6,.35),'stone')
    box(p,'Building',(x,y,h/2+.3),(w,d,h),mat)
    box(p,'Roof',(x,y,h+.55),(w+.7,d+.7,.55),roof)
    for wx in [x-w*.30,x+w*.30]:
        box(p,'Window',(wx,y-d/2-.03,h*.56),(w*.20,.07,h*.38),'glass')
        box(p,'Awning',(wx,y-d/2-.6,h*.81),(w*.25,1.3,.17),roof,rot=(12,0,0))
    box(p,'Door',(x,y-d/2-.04,1.55),(1.45,.08,2.5),'glass')
    for xx in [-.45,.45]: box(p,'DoorFrame',(x+xx,y-d/2-.09,1.55),(.05,.06,2.5),'steel')
    for yy in [y-d*.24,y+d*.24]:
        box(p,'SideWindow',(x+w/2+.035,yy,h*.56),(.08,d*.23,h*.35),'glass')
        box(p,'WindowSill',(x+w/2+.12,yy,h*.38),(.25,d*.26,.12),'cream')
    for xx in [x-w/2,x+w/2]:
        box(p,'CornerTrim',(xx,y-d/2-.05,h/2+.3),(.22,.15,h),roof)
    box(p,'Fascia',(x,y-d/2-.12,h+.22),(w,.2,.35),roof)


def tree(p,x,y,size=1):
    cyl(p,'Trunk',(x,y,1.7*size),.22*size,3.4*size,'bark')
    leaf=random.choice(['leaf1','leaf2','leaf3'])
    for dx,dy,dz,r in [(0,0,4.1,1.6),(-.8,.15,3.4,1.15),(.7,.25,3.7,1.3),(0,-.6,3.5,1.1)]:
        sphere(p,'Crown',(x+dx*size,y+dy*size,dz*size),r*size,leaf,scale=(1,1,1.15))

def bench(p,x,y,rot=0):
    root=UsdGeom.Xform.Define(stage,uniq(p,'Bench')); xf(root,(x,y,0),rot=(0,0,rot)); q=str(root.GetPath())
    box(q,'Seat',(0,0,.62),(2,.65,.16),'bark'); box(q,'Back',(0,.3,1.05),(2,.12,.75),'bark')
    for xx in [-.7,.7]: box(q,'Leg',(xx,0,.3),(.1,.5,.6),'dark')

def lamp(p,x,y):
    cyl(p,'LampPost',(x,y,2.6),.07,5.2,'dark'); box(p,'LampHead',(x,y,5.15),(.65,.65,.25),'cream')

# TERRAIN / WATER / LANDSCAPE
p='/World/Park/LANDSCAPE'; UsdGeom.Xform.Define(stage,p)
box(p,'EarthPlinth',(0,0,-1.3),(165,125,2.5),'dark')
box(p,'Ground',(0,0,-.03),(160,120,.28),'grass')
# Main paths define a clear connected guest circulation network.
box(p,'MainPromenade',(0,-20,.15),(10,71,.18),'path')
box(p,'CrossPromenade',(0,-7,.15),(126,9,.18),'path')
box(p,'NorthernPromenade',(0,43,.15),(126,7,.18),'path')
box(p,'WestPromenade',(-62,17,.15),(7,55,.18),'path')
box(p,'EastPromenade',(62,17,.15),(7,55,.18),'path')
box(p,'WheelApproach',(35,6,.16),(7,30,.2),'path')
box(p,'HotelApproach',(-47,-30,.16),(7,40,.2),'path')
box(p,'ServiceRoute',(0,53,.15),(155,5,.15),'road')
# Central plaza and fountain.
cyl(p,'CentralPlaza',(0,-7,.21),11.5,.25,'paver')
cyl(p,'FountainBasin',(0,-7,.55),3.7,.65,'cream')
cyl(p,'FountainWater',(0,-7,.93),3.35,.08,'water')
cyl(p,'FountainCore',(0,-7,1.3),.7,1.2,'teal')
sphere(p,'FountainOrb',(0,-7,2.1),.85,'water_light',scale=(.65,.65,1.8))
# Kidney-shaped lake northeast of plaza.
pond=[]
for i in range(80):
    a=2*math.pi*i/80; pond.append((9+14*math.cos(a)*(1+.1*math.sin(3*a)),23+10*math.sin(a),.22))
mesh(p,'Lake',[(9,23,.22)]+pond,[(0,i+1,(i+1)%80+1) for i in range(80)],'water')
tube(p,'LakeShore',[(x,y,.26) for x,y,z in pond],.32,'sand',sides=6,closed=True)
for j in range(4):
    pts=[(5+j*3+math.cos(i*.15)*2,19+math.sin(i*.15)*1.1,.245) for i in range(15)]
    tube(p,'WaterRipple',pts,.025,'water_light',sides=4)
# Boardwalk across southeast edge of pond.
box(p,'Boardwalk',(15,15,.65),(17,3,.32),'bark',rot=(0,0,20))
# perimeter full fence leaving entry opening
for a,b in [((-77,-57),(-8,-57)),((8,-57),(77,-57)),((77,-57),(77,57)),((77,57),(-77,57)),((-77,57),(-77,-57))]: fence(p,a,b,1.8,3)
for x,y in [(-70,-48),(-69,-36),(-69,-20),(-72,3),(-73,17),(-71,36),(-73,45),(70,-44),(70,-29),(71,-16),(71,4),(71,20),(71,39),(69,49),(-57,-48),(-33,-48),(-20,-43),(17,-47),(27,-46),(-15,3),(-12,13),(-15,29),(23,36),(18,42),(29,45),(-51,43),(-38,44),(-26,43),(-47,-14),(-33,-13),(-22,-18),(44,-16),(28,-39),(28,-26),(10,-29),(20,-15),(43,35)]: tree(p,x,y,random.uniform(.8,1.25))
for x,y in [(-11,-20),(11,-20),(-16,-7),(16,-7),(-54,-7),(54,-7),(-62,32),(62,32),(0,-42),(0,40)]: lamp(p,x,y)
for x,y,r in [(-13,-4,90),(13,-4,-90),(-9,-20,90),(9,-20,-90),(24,13,0),(27,39,0),(-54,-12,0),(52,-12,0)]: bench(p,x,y,r)
# Coaster: closed, bank-free tubular double-rail course with tall lift, camelbacks, and sweeping turns.
p=asset('RIDE_COASTER','Comet Run Coaster','ride',[-35,18,7],[[-60,-1,0],[-12,39,26]],['ride_scada','queues','maintenance','energy','workforce'])
track=[]; n=240
for i in range(n):
    t=2*math.pi*i/n
    x=-36+23*math.cos(t); y=19+17*math.sin(t)
    z=5+17*max(0,math.sin(t))**3 + 4*max(0,-math.sin(t*2))**3
    track.append((x,y,z))
for offset in [-.68,.68]:
    pts=[]
    for i,pt in enumerate(track):
        prev=track[(i-1)%n]; nxt=track[(i+1)%n]; dx=nxt[0]-prev[0];dy=nxt[1]-prev[1];ll=math.hypot(dx,dy)
        pts.append((pt[0]-dy/ll*offset,pt[1]+dx/ll*offset,pt[2]))
    tube(p,'RunningRail',pts,.105,'orange',sides=10,closed=True)
tube(p,'Spine',[(x,y,z-.5) for x,y,z in track],.22,'blue',closed=True)
for i in range(0,n,4):
    x,y,z=track[i]; prev=track[(i-1)%n]; nxt=track[(i+1)%n];dx=nxt[0]-prev[0];dy=nxt[1]-prev[1];ll=math.hypot(dx,dy)
    beam(p,'TrackTie',(x-dy/ll*.88,y+dx/ll*.88,z),(x+dy/ll*.88,y-dx/ll*.88,z),.07,'orange')
for i in range(0,n,12):
    x,y,z=track[i]
    cyl(p,'Footing',(x,y,.3),.65,.5,'stone'); beam(p,'Support',(x,y,.5),(x,y,z-.5),.17,'steel')
    if z>9:
        beam(p,'Brace',(x+2,y+1,.5),(x,y,z*.7),.13,'steel')
        cyl(p,'BraceFoot',(x+2,y+1,.25),.5,.4,'stone')
building(p,(-35,2,0),(13,7,4),'cream','blue'); sign(p,'COMET RUN',(-35,-1.7,5),11)
# Queue canopy and zigzag rail lanes.
box(p,'QueueShade',(-23,-.3,3.2),(9,5,.18),'yellow')
for x in [-27,-19]:
    for y in [-2.3,1.7]: cyl(p,'CanopyPost',(x,y,1.6),.07,3.2,'steel')
for y in [-1.6,-.3,1]: fence(p,(-27,y),(-19,y),.95,3,'steel')
for a,b in [((-60,0),(-47,0)),((-60,0),(-60,38)),((-60,38),(-14,38))]: fence(p,a,b,1.15,4)
route=CoasterRoute(track); initial_phase=.77
poses=train_transforms(route,initial_phase)
lead=poses[TRAIN_ROOT]; forward=lead[0,:3]
train=UsdGeom.Xform.Define(stage,p+'/Train')
xf(train,lead[3,:3],rot=(0,-math.degrees(math.asin(forward[2])),math.degrees(math.atan2(forward[1],forward[0]))))
for i in range(3):
    car=UsdGeom.Xform.Define(stage,p+f'/Train/Car_{i:02d}')
    UsdGeom.Xformable(car).AddTransformOp().Set(Gf.Matrix4d(poses[f'{TRAIN_ROOT}/Car_{i:02d}'].tolist()))
    car.GetPrim().SetCustomDataByKey('carIndex',i)
    q=str(car.GetPath()); xx=0
    box(q,'CarBody',(xx,0,.55),(2,1.5,.65),'yellow'); box(q,'Nose',(xx+.72,0,.8),(.4,1.5,.7),'orange')
    for yy in [-.4,.4]:
        box(q,'Seat',(xx-.2,yy,1.05),(.75,.55,.18),'dark'); box(q,'SeatBack',(xx-.55,yy,1.35),(.15,.55,.6),'dark')
        beam(q,'Restraint',(xx+.1,yy-.22,1.2),(xx+.1,yy+.22,1.2),.055,'steel')
        sphere(q,'RiderHead',(-.2,yy,1.68),.17,'skin')
        box(q,'RiderBody',(-.2,yy,1.35),(.34,.3,.4),['teal','blue','pink'][i])
    for yy in [-.75,.75]:
        for wx in [-.55,.55]: cyl(q,'Wheel',(xx+wx,yy,.2),.22,.12,'dark',rot=(90,0,0))
    beam(q,'Coupler',(-1,0,.45),(-1.26,0,.45),.06,'steel')
# Ferris wheel structure and 12 colorful gondolas.
p=asset('RIDE_WHEEL','Aster Observation Wheel','ride',[35,25,18],[[19,16,0],[51,31,35]],['ride_scada','queues','maintenance','energy','workforce'])
box(p,'WheelPlaza',(35,23,.23),(29,19,.35),'paver')
for yy in [21,29]:
    for xx in [26,44]: beam(p,'AFrame',(xx,yy,.5),(35,yy,19),.38,'cream')
    beam(p,'BaseTie',(26,yy,.6),(44,yy,.6),.3,'teal')
beam(p,'Axle',(35,19,19),(35,31,19),.55,'steel')
rotor=UsdGeom.Xform.Define(stage,p+'/Rotor'); xr=UsdGeom.Xformable(rotor); xr.AddTranslateOp().Set((35,25,19)); xr.AddRotateYOp().Set(0); q=str(rotor.GetPath())
for yy in [-1.1,1.1]:
    rim=[(14*math.cos(i*2*math.pi/96),yy,14*math.sin(i*2*math.pi/96)) for i in range(96)]
    tube(q,'OuterRim',rim,.22,'teal',closed=True)
    rim2=[(12.8*math.cos(i*2*math.pi/96),yy,12.8*math.sin(i*2*math.pi/96)) for i in range(96)]
    tube(q,'InnerRim',rim2,.09,'yellow',closed=True)
for i in range(12):
    a=2*math.pi*i/12;xx=14*math.cos(a);zz=14*math.sin(a)
    for yy in [-1.1,1.1]: beam(q,'Spoke',(0,yy,0),(xx,yy,zz),.095,'cream')
    beam(q,'RimCrossbar',(xx,-1.1,zz),(xx,1.1,zz),.10,'teal')
    gond=UsdGeom.Xform.Define(stage,q+f'/Gondola_{i:02d}'); xf(gond,(xx,0,zz)); gg=str(gond.GetPath())
    beam(gg,'Suspension',(0,0,0),(0,0,-1),.07,'steel')
    box(gg,'Cabin',(0,0,-1.8),(1.9,2.8,1.4),['orange','yellow','teal','pink'][i%4])
    box(gg,'CabinWindow',(0,-1.42,-1.5),(1.5,.05,.7),'glass'); box(gg,'CabinRoof',(0,0,-.95),(2.1,3,.18),'cream')
    for yy in [-.85,.85]: box(gg,'Seat',(0,yy,-1.8),(1.6,.4,.22),'dark')
sphere(q,'Hub',(0,-1.4,0),1.1,'yellow',scale=(1,.45,1))
box(p,'Platform',(35,19,.8),(11,5,1.2),'teal')
box(p,'Ramp',(35,14,.42),(4,6,.25),'paver',rot=(7,0,0))
sign(p,'ASTER WHEEL',(35,16.4,4.4),12)
for y in [10,12]: fence(p,(28,y),(42,y),1,3,'steel')
# Show amphitheatre: stepped seating, stage, overhead truss, speakers.
p=asset('SHOW_ARENA','Starlight Show Arena','entertainment',[-5,45,2],[[-17,37,0],[10,52,8]],['shows','crowds','workforce','energy'])
box(p,'Stage',(-5,48,.8),(18,7,1.2),'roof'); box(p,'Backdrop',(-5,51,3.5),(18,.4,6),'purple')
sign(p,'STARLIGHT',(-5,50.7,5.1),13)
for x in [-15,5]:
    beam(p,'StageTruss',(x,44,0),(x,44,7),.12,'steel'); box(p,'Speaker',(x,43.8,3),(1,1,2),'dark')
beam(p,'StageTruss',(-15,44,7),(5,44,7),.12,'steel')
for x in [-12,-8,-4,0,3]: sphere(p,'StageLight',(x,43.8,6.8),.25,'yellow')
for row in range(3):
    box(p,'SeatingTier',(-5,40-row*1.5,.3+row*.2),(19,1.1,.6+row*.4),'cream')
# Food court southwest.
p=asset('FOOD_COURT','Market Square Food Court','food',[-25,-28,2],[[-41,-38,0],[-11,-17,7]],['pos','inventory','queues','workforce','energy'])
box(p,'DiningPlaza',(-26,-27,.2),(29,23,.25),'paver')
for x,label,col in [(-35,'PIZZA','orange'),(-25,'CAFE','teal'),(-15,'TREATS','pink')]:
    building(p,(x,-34,0),(8,7,4),'cream',col); sign(p,label,(x,-37.6,4.8),6)
    box(p,'ServiceWindow',(x,-30.45,2.3),(5,.1,1.5),'glass')
for x,y in [(-35,-24),(-25,-24),(-15,-24),(-30,-18),(-20,-18)]:
    cyl(p,'Table',(x,y,.9),1.2,.15,'cream'); cyl(p,'TablePost',(x,y,.45),.12,.9,'steel')
    cyl(p,'UmbrellaPost',(x,y,1.6),.055,3.2,'steel'); cone(p,'Umbrella',(x,y,3.1),2,.65,random.choice(['yellow','orange','teal']))
    for a in range(4):
        xx=x+1.55*math.cos(a*math.pi/2);yy=y+1.55*math.sin(a*math.pi/2)
        box(p,'Chair',(xx,yy,.6),(.6,.6,.16),'teal'); box(p,'ChairLeg',(xx,yy,.3),(.12,.12,.6),'steel')
# Utilities northeast and northwest.
p=asset('POWER_HUB','Energy Hub and Solar Canopy','utility',[57,47,2],[[46,40,0],[69,55,7]],['energy','maintenance','grid','weather'])
building(p,(61,48,0),(11,8,4),'cream','roof'); sign(p,'ENERGY',(61,43.8,4.9),8)
for x in [48,51,54]:
    box(p,'BatteryCabinet',(x,49,1.6),(2,3,3),'white'); box(p,'BatteryStatus',(x,47.48,2),(.65,.04,.25),'teal')
for row in range(2):
    for col in range(5):
        x=53+col*2.8;y=45+row*3
        box(p,'SolarPanel',(x,y,5.3),(2.6,2.6,.1),'solar',rot=(10,0,0))
        for dx in [-.85,0,.85]: box(p,'SolarCellLine',(x+dx,y,5.365),(.018,2.5,.015),'steel',rot=(10,0,0))
for a,b in [((46,40),(69,40)),((46,40),(46,54))]: fence(p,a,b,1.6,3,'steel')
p=asset('WATER_PLANT','Water Treatment and Irrigation','utility',[-61,48,2],[[-73,41,0],[-49,55,6]],['water','maintenance','weather'])
building(p,(-55,49,0),(8,8,3.5),'cream','teal'); sign(p,'WATER',(-55,44.8,4.3),6)
for x in [-69,-62]:
    cyl(p,'WaterTank',(x,48,2.1),2.5,4,'steel'); cyl(p,'TankTop',(x,48,4.15),2.55,.2,'teal')
    beam(p,'Pipe',(x,48,1),(x,43,1),.23,'blue'); beam(p,'Pipe',(x,43,1),(-56,43,1),.23,'blue')
# Hotel southwest.
p=asset('HOTEL','Aster Lodge','hospitality',[-58,-29,3],[[-70,-42,0],[-47,-17,12]],['hotel','energy','workforce','erp'])
building(p,(-59,-29,0),(19,19,10),'cream','roof'); sign(p,'ASTER LODGE',(-59,-38.7,10.9),16)
for row in range(3):
    for col in range(5): box(p,'HotelWindow',(-66+col*3.5,-38.55,2.3+row*2.8),(1.7,.08,1.7),'glass')
box(p,'EntranceCanopy',(-59,-40,3.5),(8,5,.25),'teal')
for x in [-62.5,-55.5]: cyl(p,'CanopyPost',(x,-42,1.7),.12,3.4,'steel')
# Parking with marked bays, EVs and gate.
p=asset('PARKING','South Parking and EV Charging','mobility',[52,-36,1],[[30,-54,0],[74,-19,5]],['parking','ev_charging','transport','energy'])
box(p,'ParkingAsphalt',(52,-37,.19),(43,34,.2),'road')
for row,y in enumerate([-48,-28]):
    for i in range(8):
        x=34+i*5
        box(p,'BayLine',(x,y,.31),(.11,7,.025),'stripe')
        if (i+row)%3!=0:
            col=['teal','white','orange','blue','yellow'][i%5]
            box(p,'CarBody',(x+2,y,.95),(2.2,4.2,1.0),col); box(p,'CarCabin',(x+2,y+.1,1.65),(1.9,2.3,.8),'glass')
            for dx in [-1.08,1.08]:
                for dy in [-1.25,1.25]: cyl(p,'CarWheel',(x+2+dx,y+dy,.65),.38,.18,'dark',rot=(0,90,0))
for x in [36,41,46]:
    box(p,'EVCharger',(x,-22,1.1),(.7,.6,2),'teal'); box(p,'EVScreen',(x,-22.33,1.5),(.45,.04,.55),'dark')
sign(p,'PARK AND CHARGE',(52,-20,4.5),17)
# Medical and restrooms right of entry.
p=asset('FIRST_AID','First Aid and Guest Care','guest_service',[18,-35,2],[[11,-42,0],[25,-28,6]],['incidents','workforce','guest_services'])
building(p,(18,-35,0),(12,11,4),'white','teal'); sign(p,'FIRST AID',(18,-40.7,4.9),10)
box(p,'MedicalCrossV',(18,-40.58,2.5),(.45,.1,1.7),'red'); box(p,'MedicalCrossH',(18,-40.60,2.5),(1.7,.1,.45),'red')
p=asset('RESTROOMS','Central Restrooms','guest_service',[53,-16,2],[[46,-21,0],[60,-11,5]],['cleaning','water','maintenance'])
building(p,(53,-16,0),(12,8,3.4),'cream','teal'); sign(p,'RESTROOMS',(53,-20.2,4.2),10)
p=asset('WEATHER_STATION','Weather and Environment Station','sensor',[16,43,3],[[14,41,0],[18,45,10]],['weather','environment'])
cyl(p,'Mast',(16,43,4.5),.12,9,'steel'); box(p,'SensorBox',(16,43,6.5),(.6,.8,.9),'white')
beam(p,'Crossarm',(14.5,43,8.8),(17.5,43,8.8),.06,'steel')
for x in [14.5,17.5]: sphere(p,'Anemometer',(x,43,9.0),.25,'white')
box(p,'WeatherSolar',(16,43,4.4),(1.3,.9,.07),'solar',rot=(25,0,0))
# Arrival gate, turnstiles and branded entry arch.
p=asset('ENTRY_GATE','Aster Park Main Entrance','admission',[0,-53,2],[[-13,-58,0],[13,-47,9]],['ticketing','admission','crowds','guest_services'])
box(p,'EntryPaving',(0,-53,.2),(25,11,.3),'paver')
for x in [-10,10]:
    box(p,'GatePillar',(x,-53,3.5),(1.8,2,7),'teal'); sphere(p,'GateFinial',(x,-53,7.4),.7,'yellow')
box(p,'EntryArch',(0,-53,7),(22,1.5,2),'teal'); sign(p,'ASTER PARK',(0,-53.8,7.2),18)
for x in [-7,-3.5,3.5,7]:
    box(p,'Turnstile',(x,-53,1),(.6,1.5,1.8),'steel'); box(p,'Reader',(x,-53.8,1.7),(.4,.15,.3),'teal')
    beam(p,'TurnstileArm',(x,-53,1),(x+1.1,-53,1),.06,'steel')
for x in [-13,13]: building(p,(x,-49,0),(4,4,3),'cream','orange')
# Visitors grouped naturally on promenades, under all operational roots for picking context.
for j in range(70):
    if j<25: x=random.uniform(-5,5);y=random.uniform(-47,-15); root='/World/Park/ENTRY_GATE'
    elif j<45: x=random.uniform(-50,50);y=random.uniform(-10,-4);root='/World/Park/LANDSCAPE'
    elif j<57: x=random.uniform(29,41);y=random.uniform(9,15);root='/World/Park/RIDE_WHEEL'
    else: x=random.uniform(-39,-14);y=random.uniform(-28,-17);root='/World/Park/FOOD_COURT'
    hh=random.uniform(.88,1.1); col=random.choice(['teal','orange','pink','yellow','blue','purple','cream'])
    cyl(root,'GuestBody',(x,y,1.05*hh),.19*hh,.7*hh,col); sphere(root,'GuestHead',(x,y,1.65*hh),.18*hh,'skin')
    for dx in [-.1,.1]: beam(root,'GuestLeg',(x+dx,y,.25),(x+dx,y,.8*hh),.07,'dark')
    for dx in [-.24,.24]: beam(root,'GuestArm',(x+dx,y,1.31*hh),(x+dx*1.2,y+.10,.87*hh),.07,col)

# Scoped procedural detail pass; shares deterministic modeling helpers and stage.
exec(compile((Path(__file__).parent/'detail_pass.py').read_text(), 'detail_pass.py', 'exec'), globals())
# Camera, warm sun, sky illumination.
cam=UsdGeom.Camera.Define(stage,'/World/Camera'); camera_pos=Gf.Vec3d(142,-180,155); target=Gf.Vec3d(0,0,2)
view=Gf.Matrix4d().SetLookAt(camera_pos,target,Gf.Vec3d(0,0,1)); UsdGeom.Xformable(cam).AddTransformOp().Set(view.GetInverse())
cam.CreateFocalLengthAttr(42); cam.CreateHorizontalApertureAttr(36); cam.CreateVerticalApertureAttr(20.25); cam.CreateClippingRangeAttr((.1,1500))
light=UsdLux.DistantLight.Define(stage,'/World/Sun'); light.CreateIntensityAttr(2800); light.CreateAngleAttr(1.2); light.CreateColorAttr((1,.91,.76)); xf(light,rot=(-35,-25,-35))
dome=UsdLux.DomeLight.Define(stage,'/World/Sky'); dome.CreateIntensityAttr(650); dome.CreateColorAttr((.68,.82,1.0))
# Extents and asset metadata make object selection robust in USD viewers.
cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render],useExtentsHint=True)
for item in registry:
    bbox=cache.ComputeWorldBound(stage.GetPrimAtPath(item['prim_path'])).ComputeAlignedBox()
    item['computed_bounds']=[list(bbox.GetMin()),list(bbox.GetMax())]
    root=stage.GetPrimAtPath(item['prim_path']); root.SetCustomDataByKey('systems',', '.join(item['systems']))
stage.GetRootLayer().Save()
stage.Export(str(OUT/'park.usdc'))
(OUT/'asset_registry.json').write_text(json.dumps({'park':'Aster Park','units':'meters','up_axis':'Z','assets':registry},indent=2))
(OUT/'ride_paths.json').write_text(json.dumps({'coaster':{'prim_path':'/World/Park/RIDE_COASTER/Train','points':track,'loop':True,'period_seconds':65,'transform_ops':['xformOp:translate','xformOp:rotateXYZ'],'cars':[f'/World/Park/RIDE_COASTER/Train/Car_{i:02d}' for i in range(3)],'car_offsets_m':[0,-2.3,-4.6],'motion_contract':'Train world pose; Car_NN local poses from modeling.animate.train_transforms'},'wheel':{'prim_path':'/World/Park/RIDE_WHEEL/Rotor','center':[35,25,19],'axis':'Y','period_seconds':100,'transform_op':'xformOp:rotateY','gondolas':[f'/World/Park/RIDE_WHEEL/Rotor/Gondola_{i:02d}' for i in range(12)]}},indent=2))
# Blender's USD importer omits bindings on analytic gprims; handoff manifest repairs these.
material_manifest={'materials':{},'bindings':{}}
for name,mat in materials.items():
    shader=UsdShade.Shader(stage.GetPrimAtPath(str(mat.GetPath())+'/Surface'))
    material_manifest['materials'][name]={'color':list(shader.GetInput('diffuseColor').Get()),'roughness':shader.GetInput('roughness').Get(),'metallic':shader.GetInput('metallic').Get()}
for prim in stage.Traverse():
    if prim.IsA(UsdGeom.Gprim):
        mat=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
        if mat:material_manifest['bindings'][str(prim.GetPath())]=mat.GetPrim().GetName()
(OUT/'blender_materials.json').write_text(json.dumps(material_manifest,indent=2))
summary={'scene_revision':2,'prim_count':len(list(stage.Traverse())),'mesh_count':sum(1 for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)),'asset_count':len(registry),'bounds':[-80,-60,80,60],'camera':[142,-180,155],'target':[0,0,2],'files':['park.usda','park.usdc','asset_registry.json','ride_paths.json']}
(OUT/'scene_validation.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
