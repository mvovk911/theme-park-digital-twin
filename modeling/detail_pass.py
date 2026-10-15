"""Deterministic scenic detail pass executed within the generator's USD context.

No external content: all modeled landscaping and guest/operations detail is
procedural. This file shares the generator's modeling helpers when executed.
"""
# Readability at park and guest scale: paving joints are one merged mesh per zone.
def paving_grid(parent,name,x,y,width,depth,spacing=3,z=.26):
    verts=[];faces=[]
    def strip(x0,y0,x1,y1):
        i=len(verts);verts.extend([(x0,y0,z),(x1,y0,z),(x1,y1,z),(x0,y1,z)]);faces.append((i,i+1,i+2,i+3))
    for k in range(1,int(width/spacing)+1):
        xx=x-width/2+k*spacing
        if xx<x+width/2:strip(xx-.02,y-depth/2,xx+.02,y+depth/2)
    for k in range(1,int(depth/spacing)+1):
        yy=y-depth/2+k*spacing
        if yy<y+depth/2:strip(x-width/2,yy-.02,x+width/2,yy+.02)
    if faces:mesh(parent,name,verts,faces,'path_joint')


def planter(parent,x,y,r=1.5,color='pink'):
    cyl(parent,'PlanterRim',(x,y,.27),r,.35,'cream')
    cyl(parent,'PlantingSoil',(x,y,.46),r-.14,.04,'soil')
    for j in range(7):
        a=j*2*math.pi/7;rr=r*.62
        sphere(parent,'LowShrub',(x+rr*math.cos(a),y+rr*math.sin(a),.66),r*.27,'leaf2',scale=(1,1,.75))
        sphere(parent,'Flower',(x+rr*math.cos(a),y+rr*math.sin(a),.87),.17,color,scale=(1,1,.6))


def trash_station(parent,x,y):
    for xx,col in [(x-.42,'teal'),(x+.42,'roof')]:
        box(parent,'Bin',(xx,y,.72),(.65,.65,1.05),col)
        box(parent,'BinLid',(xx,y,1.26),(.72,.72,.12),'steel')
        box(parent,'BinOpening',(xx,y-.334,.98),(.37,.025,.17),'dark')


p='/World/Park/LANDSCAPE'
for x,y,w,d in [(0,-33,10,28),(-37,-7,48,9),(38,-7,48,9),(-62,18,7,46),(62,18,7,46),(35,4,7,24)]:
    paving_grid(p,'PavingJoints',x,y,w,d,spacing=3)
# Low curbs delineate green islands while leaving path junctions open.
for x,y,w,d in [(-5.1,-33,0.22,27),(5.1,-33,.22,27),(-38,-11.6,46,.22),(-38,-2.4,46,.22),(43,-11.6,30,.22),(44,-2.4,31,.22),(-65.6,19,.22,42),(65.6,19,.22,42)]:
    box(p,'PathCurb',(x,y,.26),(w,d,.25),'cream')
# Curated planting breaks the former empty grass expanses without blocking routes.
for x,y,r,col in [(-10,-32,1.7,'pink'),(9,-23,1.5,'yellow'),(-11,-43,1.5,'flower_lilac'),(9,-44,1.5,'orange'),(-16,-16,1.7,'flower_lilac'),(23,-13,1.7,'pink'),(-55,11,1.8,'yellow'),(54,4,1.8,'orange'),(-45,16,2.4,'pink'),(-29,25,2.4,'flower_lilac'),(-34,14,2.1,'yellow')]:
    planter(p,x,y,r,col)
# Rock outcrops and a small garden within the coaster's open infield.
for x,y,r,sx,sy in [(-39,24,1.5,1.6,.8),(-37,25,1.2,1.1,.9),(-40,22,1,1.4,1),(-26,15,1.2,1.2,.8),(-24,14,.8,1.3,1)]:
    sphere(p,'GardenRock',(x,y,.55),r,'stone',scale=(sx,sy,.65))
for x,y,size in [(-34,24,.9),(-43,16,.85),(-25,22,.85),(54,28,1),(4,36,.9),(-10,26,.85)]:tree(p,x,y,size)
# Scenic lake island, lilies and reed groups use a few simple meshes/gprims.
cyl(p,'LakeIsland',(10,26,.34),2.4,.28,'sand')
cyl(p,'IslandGrass',(10,26,.5),2.1,.13,'grass_light')
tree(p,10,26,.65)
for x,y in [(3,27),(2,25),(15,24),(17,23),(13,19),(6,30)]:
    cyl(p,'LilyPad',(x,y,.267),.42,.025,'leaf2')
    sphere(p,'WaterLily',(x+.07,y,.35),.15,'pink',scale=(1,1,.6))
for x,y in [(-3,24),(-2,27),(2,32),(16,31),(20,27)]:
    for k in range(4):
        xx=x+(k%2)*.22;yy=y+(k//2)*.22;hh=.8+.18*k
        beam(p,'ReedStem',(xx,yy,.3),(xx+.08,yy,hh),.025,'leaf1')
        cyl(p,'ReedHead',(xx+.08,yy,hh),.06,.25,'bark')
# Deck handrails, plank seams, two accessible approach ramps.
deck=UsdGeom.Xform.Define(stage,p+'/LakeDeckDetails');xf(deck,(15,15,0),rot=(0,0,20));q=str(deck.GetPath())
for x in range(-8,9):box(q,'DeckPlankJoint',(x,0,.817),(.025,2.95,.012),'dark')
for y in [-1.45,1.45]:
    for x in [-8,-4,0,4,8]:box(q,'DeckPost',(x,y,1.25),(.11,.11,1.25),'timber')
    beam(q,'DeckTopRail',(-8,y,1.85),(8,y,1.85),.065,'timber')
    beam(q,'DeckMidRail',(-8,y,1.25),(8,y,1.25),.04,'timber')
for x,ang in [(-9.7,-8),(9.7,8)]:box(q,'DeckRamp',(x,0,.48),(3.4,3,.16),'bark',rot=(0,ang,0))
for x,y in [(-8,-22),(8,-39),(-53,-11),(26,8),(43,13),(58,38)]:trash_station(p,x,y)
# Wayfinding totems near crossroads, attached to relevant operational asset IDs.
for aid,label,x,y in [('ENTRY_GATE','WELCOME',6,-47),('RIDE_COASTER','COASTER',-17,-5),('RIDE_WHEEL','WHEEL',40,-1),('FOOD_COURT','DINING',-11,-17),('FIRST_AID','CARE',9,-33)]:
    root='/World/Park/'+aid
    box(root,'WayfindingPost',(x,y,1.4),(.18,.18,2.8),'teal');sign(root,label,(x,y-.1,2.6),2.6)
# Coaster queue: roof rhythm, fans, accessible entry gate, inspection cabinet.
p='/World/Park/RIDE_COASTER'
for x in [-26,-24,-22,-20]:box(p,'QueueRoofRib',(x,-.3,3.34),(.07,5,.07),'cream')
for x in [-25,-21]:
    cyl(p,'QueueFan',(x,-.3,2.98),.38,.08,'steel');beam(p,'QueueFanMount',(x,-.3,2.98),(x,-.3,3.15),.04,'steel')
box(p,'QueueGatePost',(-18,-2,1),(.18,.18,1.6),'teal')
box(p,'QueueReader',(-18,-2.14,1.4),(.35,.12,.4),'dark')
box(p,'RideControlCabinet',(-43,1,1.35),(1.1,.7,2.3),'cream')
box(p,'ControlScreen',(-43,.63,1.7),(.7,.045,.65),'glass')
# Wheel shaded waiting area with stretched sail fabric and a clear loading gap.
p='/World/Park/RIDE_WHEEL'
for x,y,z in [(27,8,4.4),(43,8,4.4),(27,14,4.8),(43,14,4.8)]:
    beam(p,'ShadeMast',(x,y,.2),(x,y,z),.08,'steel')
mesh(p,'QueueSailA',[(27,8,4.4),(43,8,4.4),(35,11,4.05),(27,14,4.8)],[(0,1,2),(0,2,3)],'cream')
mesh(p,'QueueSailB',[(43,8,4.4),(43,14,4.8),(27,14,4.8),(35,11,4.05)],[(0,1,3),(1,2,3)],'yellow')
box(p,'BoardingControl',(43,17,1.3),(.7,.7,1.8),'teal')
box(p,'BoardingScreen',(43,16.63,1.6),(.45,.04,.4),'glass')
# Food-outlet counters, menu boards and waste separation; no fabricated live numbers.
p='/World/Park/FOOD_COURT'
for x in [-35,-25,-15]:
    box(p,'ServingCounter',(x,-29.9,1.15),(5.4,.9,.15),'timber')
    box(p,'MenuBoard',(x+3,-29.8,2),(1,.15,1.7),'dark')
    for row in range(4):box(p,'MenuLine',(x+3,-29.9,2.5-row*.28),(.7,.025,.055),'cream')
trash_station(p,-40,-20);trash_station(p,-12,-28)
# Hotel windows on the east facade, facade ledges and rooftop mechanical equipment.
p='/World/Park/HOTEL'
for row in range(3):
    for col in range(5):
        y=-36+col*3.5;z=2.3+row*2.8
        box(p,'EastHotelWindow',(-49.45,y,z),(.08,1.7,1.7),'glass')
        box(p,'EastWindowFrame',(-49.36,y,z-.92),(.2,1.9,.13),'cream')
for z in [3.5,6.3,9.1]:box(p,'FacadeBand',(-49.34,-29,z),(.25,19,.14),'teal')
for x in [-63,-56]:
    box(p,'RoofHVAC',(x,-27,11.1),(3,3,1.1),'steel')
    cyl(p,'HVACFan',(x,-27,11.7),.8,.12,'dark')
for x in [-67.8,-50.2]:box(p,'RoofParapet',(x,-29,10.9),(.3,18,.6),'cream')
for y in [-37.8,-20.2]:box(p,'RoofParapet',(-59,y,10.9),(18,.3,.6),'cream')
# Utilities gain recognizable maintenance hardware; routes remain schematic API overlays.
p='/World/Park/POWER_HUB'
for x in [48,51,54]:
    for z in [.7,1,1.3]:box(p,'BatteryVent',(x,47.46,z),(1.3,.04,.08),'dark')
box(p,'Transformer',(48,43,1.2),(2.4,2.3,1.8),'steel')
for x in [47.4,48,48.6]:cyl(p,'Insulator',(x,43,2.4),.14,.55,'cream')
box(p,'TransformerPad',(48,43,.25),(3,3,.3),'stone')
p='/World/Park/WATER_PLANT'
for x in [-69,-62]:
    beam(p,'TankLadderSide',(x-.45,45.45,.3),(x-.45,45.45,4.3),.04,'steel')
    beam(p,'TankLadderSide',(x+.45,45.45,.3),(x+.45,45.45,4.3),.04,'steel')
    for z in [.5,1,1.5,2,2.5,3,3.5,4]:beam(p,'TankLadderRung',(x-.45,45.45,z),(x+.45,45.45,z),.03,'steel')
    cyl(p,'ValveStem',(x,43,1.5),.06,.8,'steel')
    ring=[(x+.3*math.cos(a*2*math.pi/24),43+.3*math.sin(a*2*math.pi/24),1.9) for a in range(24)]
    tube(p,'ValveHandwheel',ring,.035,'red',sides=6,closed=True)
# Dedicated accessible parking pavement, pedestrian crossing, charger cable loops.
p='/World/Park/PARKING'
for x in [36,41]:
    box(p,'AccessibleBay',(x,-48,.306),(4.1,6.5,.025),'blue')
    ring=[(x+.65*math.cos(a*2*math.pi/24),-48+.65*math.sin(a*2*math.pi/24),.335) for a in range(24)]
    tube(p,'AccessibleSymbolRing',ring,.06,'white',sides=4,closed=True)
    box(p,'AccessibleSymbolStem',(x,-47.4,.34),(.12,1.4,.025),'white')
    cyl(p,'AccessibleSymbolHead',(x,-46.5,.34),.17,.025,'white')
for x in range(33,44,2):box(p,'CrosswalkStripe',(x,-37,.32),(.9,4,.03),'stripe')
for x in [36,41,46]:
    cable=[(x+.42,-22,1.5),(x+.65,-22,.9),(x+.65,-22,.4),(x+.3,-22,.3),(x+.2,-22,.6)]
    tube(p,'ChargingCable',cable,.035,'dark',sides=6)
# The entrance now has banner poles and clear guest-scale ticket kiosk detail.
p='/World/Park/ENTRY_GATE'
for x,col in [(-17,'orange'),(17,'teal')]:
    cyl(p,'BannerPole',(x,-52,3),.06,6,'steel')
    box(p,'Banner',(x+.65,-52,4.8),(1.2,.08,2),col)
for x in [-13,13]:
    box(p,'TicketWindow',(x,-51.04,1.8),(2.4,.08,1.25),'glass')
    box(p,'TicketCounter',(x,-51.3,1.1),(2.6,.6,.12),'timber')
