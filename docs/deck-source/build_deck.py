from pathlib import Path
import argparse
import math
import random
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, Color

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description='Regenerate the theme park concept slide deck.')
parser.add_argument('--output', type=Path, default=ROOT.parent / 'project-concept.pdf')
OUT = parser.parse_args().output.resolve()
OUT.parent.mkdir(parents=True, exist_ok=True)
for name, file in [('Sans', 'DejaVuSans.ttf'), ('Bold', 'DejaVuSans-Bold.ttf')]:
    pdfmetrics.registerFont(TTFont(name, '/usr/share/fonts/truetype/dejavu/' + file))

W, H = 1280, 720
NAVY = '#102638'
INK = '#163244'
MUTED = '#607583'
BG = '#F3F6F7'
WHITE = '#FFFFFF'
TEAL = '#008D87'
MINT = '#6CE4C1'
BLUE = '#3379B7'
PURPLE = '#7864B6'
ORANGE = '#D98A36'
RED = '#C65F55'
LINE = '#D9E3E7'
PALE = '#E6F3F0'
C = canvas.Canvas(str(OUT), pagesize=(W, H), invariant=1)
C.setTitle('Theme Park Digital Twin | Project Concept & Pilot Plan')
C.setAuthor('Project concept prepared for discussion')
C.setSubject('Connected park operations, API backbone, OpenUSD / Omniverse, use cases and pilot roadmap')
WARNINGS = []

def rect(x,y,w,h,fill=WHITE,r=0,stroke=None):
    C.setFillColor(HexColor(fill))
    C.setStrokeColor(HexColor(stroke or fill))
    if r:
        C.roundRect(x,H-y-h,w,h,r,stroke=bool(stroke),fill=1)
    else:
        C.rect(x,H-y-h,w,h,stroke=bool(stroke),fill=1)

def line(x1,y1,x2,y2,color=LINE,width=1,dash=None):
    C.setStrokeColor(HexColor(color)); C.setLineWidth(width)
    C.setDash(dash or [])
    C.line(x1,H-y1,x2,H-y2)
    C.setDash([])

def poly(points,fill,stroke=None,width=1):
    p=C.beginPath(); p.moveTo(points[0][0],H-points[0][1])
    for x,y in points[1:]: p.lineTo(x,H-y)
    p.close(); C.setFillColor(HexColor(fill)); C.setStrokeColor(HexColor(stroke or fill)); C.setLineWidth(width)
    C.drawPath(p,fill=1,stroke=bool(stroke))

def circle(x,y,r,fill,stroke=None,width=1):
    C.setFillColor(HexColor(fill)); C.setStrokeColor(HexColor(stroke or fill)); C.setLineWidth(width)
    C.circle(x,H-y,r,fill=1,stroke=bool(stroke))

def text(s,x,y,size=18,color=INK,font='Sans',align='left'):
    C.setFillColor(HexColor(color)); C.setFont(font,size)
    yy=H-y-size*.82
    if align=='center': C.drawCentredString(x,yy,s)
    elif align=='right': C.drawRightString(x,yy,s)
    else: C.drawString(x,yy,s)

def wrap(s,width,size=18,font='Sans'):
    result=[]
    for para in s.split('\n'):
        words=para.split(); current=''
        for word in words:
            test=(current+' '+word).strip()
            if pdfmetrics.stringWidth(test,font,size)>width and current:
                result.append(current); current=word
            else: current=test
        result.append(current)
    return result

def body(s,x,y,width,size=18,color=MUTED,leading=None,font='Sans',maxh=None):
    leading=leading or size*1.4
    ls=wrap(s,width,size,font)
    if maxh and len(ls)*leading>maxh: WARNINGS.append((C.getPageNumber(),s[:50],len(ls)*leading,maxh))
    for i,t in enumerate(ls): text(t,x,y+i*leading,size,color,font)
    return y+len(ls)*leading

def tag(s,x,y,color=TEAL,fill=PALE,size=12):
    wid=pdfmetrics.stringWidth(s,'Bold',size)+24
    rect(x,y,wid,26,fill,13); text(s,x+12,y+7,size,color,'Bold')
    return wid

def arrow(x1,y1,x2,y2,color=TEAL,width=2,head=7,dash=None):
    line(x1,y1,x2,y2,color,width,dash)
    a=math.atan2(y2-y1,x2-x1)
    pts=[(x2,y2),(x2-head*math.cos(a-.5),y2-head*math.sin(a-.5)),(x2-head*math.cos(a+.5),y2-head*math.sin(a+.5))]
    poly(pts,color)

def route(points,color=TEAL,width=2,dash=None):
    for a,b in zip(points[:-2],points[1:-1]): line(*a,*b,color,width,dash)
    arrow(*points[-2],*points[-1],color,width,dash=dash)

def header(kicker,title,subtitle=None,dark=False):
    rect(0,0,W,H,NAVY if dark else BG)
    text(kicker.upper(),52,29,12,MINT if dark else TEAL,'Bold')
    text(title,52,67,36,WHITE if dark else INK,'Bold')
    if subtitle: body(subtitle,54,119,1168,17,'#B4C8D3' if dark else MUTED,24,maxh=50)

def footer(n,source='',dark=False):
    color='#8EA9B7' if dark else MUTED
    line(52,671,1228,671,'#294456' if dark else LINE)
    text('PARK DIGITAL TWIN  /  CONCEPT + PILOT',52,687,10,color,'Bold')
    if source: text(source,411,687,10,color)
    text(f'{n:02d} / 10',1228,685,12,color,'Bold','right')
    C.showPage()

def card(x,y,w,h,title,copy,color=TEAL,number=None):
    rect(x,y,w,h,WHITE,12)
    rect(x,y,5,h,color,2)
    yy=y+23
    if number:
        text(number,x+22,yy,12,color,'Bold'); yy+=28
    text(title,x+22,yy,21,INK,'Bold')
    body(copy,x+22,yy+36,w-44,17,maxh=h-(yy-y)-44)

def park_iso(x,y,scale=1):
    def P(u,v,z=0): return x+(u-v)*scale,y+(u+v)*.43*scale-z*scale
    def tile(u,v,w,d,fill): poly([P(u,v),P(u+w,v),P(u+w,v+d),P(u,v+d)],fill)
    def box(u,v,w,d,h,top,side1,side2):
        poly([P(u,v),P(u+w,v),P(u+w,v,h),P(u,v,h)],side1)
        poly([P(u+w,v),P(u+w,v+d),P(u+w,v+d,h),P(u+w,v,h)],side2)
        poly([P(u,v,h),P(u+w,v,h),P(u+w,v+d,h),P(u,v+d,h)],top)
    tile(0,0,420,340,'#183B4B')
    poly([P(0,340),P(420,340),P(420,340, -18),P(0,340,-18)],'#0A1B2A')
    poly([P(420,0),P(420,340),P(420,340,-18),P(420,0,-18)],'#173242')
    tile(18,160,382,24,'#466273');tile(190,12,23,308,'#466273')
    tile(210,230,180,16,'#466273');tile(32,40,140,100,'#205064')
    tile(270,20,110,94,'#1C5C68')
    for u,v,w,d,h in [(240,195,65,44,32),(305,260,76,40,25),(48,220,64,55,55),(118,227,42,48,38),(240,65,50,44,28)]:
        box(u,v,w,d,h,'#95C9C8','#4C8E96','#356B7A')
    box(320,125,55,30,18,'#D0AF83','#9A7C5D','#685948')
    # Coaster track, supports, and train.
    track=[]
    for i in range(101):
        t=i/100*math.tau
        u=105+65*math.cos(t);v=89+38*math.sin(t);z=42+30*math.sin(t*2)
        track.append(P(u,v,z))
        if i%10==0: line(*P(u,v),*P(u,v,z),'#628194',1.2)
    for a,b in zip(track[:-1],track[1:]):line(*a,*b,MINT,3)
    for i in [16,18,20]:circle(*track[i],4,ORANGE)
    # Ferris wheel in a vertical plane.
    center=P(335,65,65);rad=43*scale
    line(*P(315,67),center[0],center[1],'#A9CBD3',3)
    line(*P(355,67),center[0],center[1],'#A9CBD3',3)
    C.setStrokeColor(HexColor('#9BC6CF'));C.setLineWidth(2)
    C.circle(center[0],H-center[1],rad,fill=0,stroke=1)
    for i in range(10):
        t=i/10*math.tau;pt=(center[0]+rad*math.cos(t),center[1]+rad*math.sin(t))
        line(*center,*pt,'#5C8B9B',1);circle(*pt,4*scale,MINT)
    random.seed(3)
    for u,v in [(30,185),(50,300),(150,300),(230,300),(390,210),(390,45),(230,18),(18,15),(20,120),(150,190),(280,290)]:
        px,py=P(u,v);line(px,py,px,py-15*scale,'#658F86',2);circle(px,py-20*scale,10*scale,'#3C8C7B')
    for u,v in [(190,175),(210,240),(245,175),(90,175),(200,100),(350,242),(200,290)]:
        px,py=P(u,v);circle(px,py,3*scale,'#D5E7E4')
    return P

def map_park(x,y,w,h):
    rect(x,y,w,h,'#E9F1EF',10)
    def P(u,v):return x+u*w,y+v*h
    # Pond and green areas.
    C.setFillColor(HexColor('#BDDEE4'));C.ellipse(x+w*.63,H-y-h*.45,x+w*.91,H-y-h*.14,fill=1,stroke=0)
    for u,v,r in [(.12,.18,.075),(.2,.68,.07),(.65,.74,.055),(.86,.76,.06)]:circle(*P(u,v),w*r,'#D3E5D9')
    for a,b in [((.1,.5),(.9,.5)),((.45,.1),(.45,.9)),((.45,.7),(.87,.7)),((.15,.5),(.15,.78)),((.72,.5),(.72,.28))]:
        line(*P(*a),*P(*b),'#FFFFFF',17)
        line(*P(*a),*P(*b),'#CFDAD9',1)
    for u,v,ww,hh in [(.08,.25,.22,.14),(.55,.14,.13,.14),(.1,.79,.16,.09),(.53,.78,.12,.1),(.78,.55,.14,.09)]:
        rect(x+w*u,y+h*v,w*ww,h*hh,'#ADBCBD',5)
    # Stylized coaster loop.
    pts=[P(.19+.085*math.cos(t/40*math.tau),.32+.085*math.sin(t/40*math.tau)) for t in range(41)]
    for a,b in zip(pts[:-1],pts[1:]): line(*a,*b,INK,2)
    # Pressure overlay (illustrative).
    circle(*P(.42,.50),w*.105,'#F0D4A9');circle(*P(.59,.50),w*.07,'#F0D4A9')
    for u,v,label,col in [(.2,.32,'R1',RED),(.6,.2,'S1',PURPLE),(.84,.59,'F1',TEAL),(.17,.83,'R2',TEAL)]:
        px,py=P(u,v);circle(px,py,17,col);text(label,px,py-7,12,WHITE,'Bold','center')
    arrow(*P(.28,.48),*P(.49,.48),ORANGE,3)
    arrow(*P(.6,.29),*P(.6,.43),PURPLE,3)
    return P

# 01 / vision
rect(0,0,W,H,NAVY)
text('PROJECT CONCEPT  /  OCTOBER 2026',54,34,12,MINT,'Bold')
text('A living twin',54,130,58,WHITE,'Bold')
text('of your',54,203,58,WHITE,'Bold')
text('theme park.',54,276,58,MINT,'Bold')
body('Connect the park. Understand the ripple effects. Coordinate a better day.',58,382,445,23,'#BED0D9',33)
tag('OPERATIONS',56,526,MINT,'#203F4D')
tag('SIMULATION',197,526,MINT,'#203F4D')
tag('GUEST EXPERIENCE',341,526,MINT,'#203F4D')
park_iso(886,236,.86)
text('ONE PARK · MANY CONNECTED SYSTEMS',858,599,12,'#9FBDC9','Bold','center')
footer(1,'Illustrative park concept; no real park data.',True)

# 02 / value
header('01 / The opportunity','A park is a city, a factory and a hospitality business.',
       'A shared capacity model connects guest demand to the assets, people and services that can fulfill it.')
for i,(title,copy,col) in enumerate([
    ('Guest experience','Shorter waits. Clearer guidance. Accessible routes. More time enjoying the park.',TEAL),
    ('Operational resilience','Faster incident understanding. Coordinated recovery. Fewer delayed openings.',BLUE),
    ('Asset productivity','Maintenance informed by condition, parts availability and operational impact.',PURPLE),
    ('Resource efficiency','Staff, energy, water and food aligned with actual demand.',ORANGE)]):
    card(52+i*300,190,280,208,title,copy,col)
text('THE VALUE COMES FROM CONNECTING CONSEQUENCES',54,438,12,TEAL,'Bold')
nodes=[('Ride closes','Capacity falls'),('Guests move','Demand shifts'),('Queues grow','Service pressure'),('Teams respond','Recovery begins')]
for i,(a,b) in enumerate(nodes):
    xx=54+i*300;rect(xx,476,272,106,WHITE,10);text(a,xx+20,497,22,INK,'Bold');text(b,xx+20,535,17,MUTED)
    if i<3:arrow(xx+273,529,xx+296,529,TEAL,2)
body('Success = better guest outcomes + reliable operations + measurable resource savings.',54,614,1150,18,INK)
footer(2,'Value hypotheses to validate against a park-specific baseline.')

# 03 / API ecosystem
header('02 / Connected systems','One backbone. Many operational connections.',
       'Adapters normalize identifiers, time and meaning before information reaches the twin.')
left=[('Rides + SCADA','States · cycles · alarms','OPC UA / vendor gateway',BLUE),
      ('Ticketing + queues','Admissions · reservations · waits','REST / webhooks / exports',TEAL),
      ('Cameras + sensors','Counts · occupancy · events','Analytics API / ONVIF / MQTT',TEAL),
      ('ERP + maintenance','Costs · stock · work orders','REST / OData / events',PURPLE),
      ('People + entertainment','Shifts · skills · show schedules','Workforce / scheduling APIs',PURPLE)]
right=[('Buildings + utilities','HVAC · power · water','BMS gateway / meters',ORANGE),
       ('Retail + hospitality','Orders · inventory · hotel demand','POS / property-management APIs',ORANGE),
       ('Weather + transport','Forecasts · traffic · arrivals','Provider APIs / transit feeds',BLUE),
       ('Spatial + engineering','Terrain · buildings · equipment','GIS / BIM / CAD / OpenUSD',BLUE),
       ('Operational channels','Tasks · signage · guest messages','Authorized business APIs',TEAL)]
for i,(a,b,p,col) in enumerate(left):
    yy=177+i*88;rect(52,yy,325,76,WHITE,9);rect(52,yy,4,76,col,1)
    text(a,67,yy+10,17,INK,'Bold');text(b,67,yy+34,13,MUTED);text(p,67,yy+54,11,col)
    route([(377,yy+38),(409,yy+38),(409,365),(448,365)],'#9AAEB8',1.2)
for i,(a,b,p,col) in enumerate(right):
    yy=177+i*88;rect(903,yy,325,76,WHITE,9);rect(903,yy,4,76,col,1)
    text(a,918,yy+10,17,INK,'Bold');text(b,918,yy+34,13,MUTED);text(p,918,yy+54,11,col)
    if i<4:route([(903,yy+38),(871,yy+38),(871,365),(832,365)],'#9AAEB8',1.2)
    else: route([(832,426),(853,426),(853,yy+38),(903,yy+38)],TEAL,2,dash=[5,4])
rect(448,224,384,278,NAVY,16)
text('PARK DATA BACKBONE',640,251,21,WHITE,'Bold','center')
body('One identity for each asset.\nOne spatial and temporal context.',480,299,325,17,'#B8CFD9',26)
for j,s in enumerate(['Live state + event history','Capacity + dependencies','Data quality + access policies']):
    circle(485,381+j*30,3,MINT);text(s,499,373+j*30,15,WHITE)
tag('OBSERVE',461,527,TEAL,PALE)
tag('PREDICT',575,527,BLUE,'#E4EDF6')
tag('COORDINATE',688,527,PURPLE,'#EDE9F4')
text('Solid: observations into the twin. Dashed: authorized actions with acknowledgement.',52,634,12,MUTED)
footer(3,'Candidate interfaces; vendor support, access and write permissions require discovery. [4–7]')

# 04 / architecture
header('03 / Platform design','Separate the data backbone, simulation and experience.',
       'ERP owns business records. Park execution coordinates daily work. The twin connects context across both.')
cols=[(52,'01','CONNECT',BLUE,['Edge gateways','API adapters','Event ingestion'], 'Normalize IDs, units and timestamps.'),
      (292,'02','CONTEXT',TEAL,['Asset registry','Spatial relationships','State + history'], 'Track provenance, freshness and uncertainty.'),
      (532,'03','PREDICT',PURPLE,['Queue + crowd models','Reliability + energy','Constraint solvers'], 'Calibrate models against actual outcomes.'),
      (772,'04','EXPERIENCE',BLUE,['Maps + mobile','OpenUSD + Omniverse','Evidence-based copilot'], 'Show observed, estimated and simulated states.'),
      (1012,'05','EXECUTE',ORANGE,['Task workflows','Operator approvals','Business system APIs'], 'Confirm completion and measure the result.')]
for xx,num,title,col,items,note in cols:
    rect(xx,188,216,296,WHITE,12);text(num,xx+18,209,28,col,'Bold');text(title,xx+18,257,15,INK,'Bold')
    for j,s in enumerate(items):text(s,xx+18,303+j*31,14,INK)
    body(note,xx+18,410,180,13,MUTED,19,maxh=65)
    if num!='05':arrow(xx+217,332,xx+237,332,TEAL,2)
route([(1120,487),(1120,518),(160,518),(160,486)],TEAL,1.7)
rect(52,551,566,83,'#E2EFED',10);text('OPERATIONAL DATA',71,567,12,TEAL,'Bold')
body('Context API + event history + spatial and telemetry stores. NGSI-LD or a device-twin framework are candidates.',71,591,527,14,INK,20)
rect(638,551,590,83,'#E7EDF4',10);text('SPATIAL EXPERIENCE',657,567,12,BLUE,'Bold')
body('OpenUSD composes the scene. A live adapter binds asset IDs to overlays. Omniverse renders and streams the experience.',657,591,548,14,INK,20)
footer(4,'Ride safety remains in dedicated local control systems. Proposed architecture. [1–4]')

# 05 / control room
header('04 / The operator experience','See the park. Follow a dependency. Test a response.',
       'Illustrative control-room concept: the same operational context powers maps, 3D investigation and mobile tasks.')
rect(52,179,1176,451,WHITE,12)
rect(52,179,1176,48,NAVY,10)
text('PARK OPERATIONS',73,195,15,WHITE,'Bold')
for xx,s in [(370,'LIVE'),(456,'REPLAY'),(568,'SCENARIO')]:text(s,xx,197,11,MINT if s=='LIVE' else '#B4C8D3','Bold')
text('ILLUSTRATIVE DATA',1207,197,10,'#B4C8D3','Bold','right')
map_park(70,246,711,325)
tag('R1  CLOSED',88,260,RED,'#FBECE8',11)
tag('S1  SHOW ENDING',88,296,PURPLE,'#EFEAF7',11)
text('Estimated crowd pressure',91,548,11,MUTED)
rect(802,246,405,325,'#F3F6F7',10)
text('Ride R1 · Adventure Zone',822,266,19,INK,'Bold')
text('Observed: unavailable',822,302,15,RED,'Bold')
body('Source: ride status feed\nLast event: 14:10 · illustrative',822,330,360,13,MUTED,20)
line(822,385,1187,385)
text('DEPENDENCIES',822,401,11,TEAL,'Bold')
body('Feeder E7 · Queue Q12\nQualified team · Plaza P4',822,425,352,15,INK,24)
rect(822,494,365,54,TEAL,8);text('Compare response scenarios',1004,512,16,WHITE,'Bold','center')
text('Observed',89,594,12,INK);circle(78,600,4,TEAL)
text('Estimated',231,594,12,INK);circle(220,600,4,ORANGE)
text('Simulated',388,594,12,INK);circle(377,600,4,PURPLE)
text('3D drill-down: equipment, routes, utilities and sightlines',803,594,11,MUTED)
footer(5,'UI concept only; no live connections. 2D for overview, RTX 3D for spatial investigation. [2–3]')

# 06 / flagship scenario
header('05 / Flagship pilot scenario','A ride closes just before a nearby show ends.',
       'The twin connects the closure to displaced demand, staffing, guest guidance and recovery.')
stages=[('01','DETECT','Ride status changes.\nCheck signal freshness.',BLUE),
        ('02','UNDERSTAND','Link queues, show exit,\npaths and available staff.',TEAL),
        ('03','COMPARE','Simulate demand shifts\nand feasible responses.',PURPLE),
        ('04','COORDINATE','Operator approves tasks\nand guest messaging.',ORANGE),
        ('05','LEARN','Verify execution. Compare\nforecast and outcome.',TEAL)]
for i,(n,t,copy,col) in enumerate(stages):
    xx=52+i*240;circle(xx+30,218,26,col);text(n,xx+30,207,21,WHITE,'Bold','center')
    if i<4:arrow(xx+62,218,xx+216,218,'#A4B8C1',2)
    text(t,xx,269,15,col,'Bold');body(copy,xx,305,222,15,INK,24,maxh=80)
rect(52,414,732,205,NAVY,12)
text('THE QUESTION AN OPERATOR CAN ASK',76,437,12,MINT,'Bold')
body('“Which response reduces crowd pressure without creating a new bottleneck?”',76,474,675,27,WHITE,38)
rect(809,414,419,205,WHITE,12)
text('Compare practical options',831,438,20,INK,'Bold')
body('A  Reassign qualified staff\nB  Offer alternate guest routes\nC  Adjust permitted service capacity',831,479,370,16,INK,31)
text('Predictions carry uncertainty.',831,586,13,MUTED)
footer(6,'Scenario timing and asset labels are illustrative. Actions follow existing operating procedures.')

# 07 / use case portfolio
header('06 / Expand the value','Six connected use cases, one reusable foundation.',
       'Prioritize by measurable operational pain, available data and the ability to complete a useful workflow.')
cases=[('01','Guest flow','Balance physical and virtual queues; guide guests using current capacity.','Measure: wait distribution + route success',TEAL),
       ('02','Opening readiness','Combine inspections, staff qualifications, equipment status and access.','Measure: delayed openings + resolution time',BLUE),
       ('03','Maintenance','Link condition, faults, parts and technician availability to park impact.','Measure: downtime + repair duration',PURPLE),
       ('04','Energy + water','Coordinate permitted flexible loads; locate leaks and utility dependencies.','Measure: peak demand + use per guest',ORANGE),
       ('05','Food + service','Anticipate local demand; dispatch replenishment and cleaning tasks.','Measure: service time + waste + stockouts',TEAL),
       ('06','Design + expansion','Test new attractions, layouts and show schedules before investment.','Measure: capacity gained + bottlenecks',BLUE)]
for i,(num,title,copy,metric,col) in enumerate(cases):
    xx=52+(i%3)*400; yy=180+(i//3)*229
    rect(xx,yy,376,207,WHITE,12)
    tag(num,xx+20,yy+18,col,'#EDF2F4',11)
    text(title,xx+75,yy+22,21,INK,'Bold')
    body(copy,xx+20,yy+68,337,17,INK,25,maxh=89)
    line(xx+20,yy+160,xx+356,yy+160)
    body(metric,xx+20,yy+174,338,12,col,17,maxh=33)
footer(7,'Predictive models need park-specific calibration. Pedestrian simulation reference: [8].')

# 08 / start roadmap
header('07 / How to start','A focused 12-week pilot, with evidence at each gate.',
       'Planning assumption: one themed area, 2–3 attractions, one show venue and access to the core data feeds.')
phases=[('WEEKS 1–2','Discover + baseline',BLUE,['Map systems and owners','Confirm API access + latency','Measure current response'], 'Gate: usable data + agreed KPIs'),
        ('WEEKS 3–5','Build the shadow',TEAL,['Create IDs + spatial map','Connect 4–6 priority feeds','Show live state + replay'], 'Gate: trusted state + freshness'),
        ('WEEKS 6–8','Calibrate scenarios',PURPLE,['Model queues + show exits','Replay historical incidents','Validate against held-out days'], 'Gate: acceptable forecast error'),
        ('WEEKS 9–12','Trial + evaluate',ORANGE,['Run in advisory mode','Trial approved workflows','Compare outcomes + costs'], 'Gate: evidence to expand or stop')]
for i,(when,title,col,items,gate) in enumerate(phases):
    xx=52+i*300;rect(xx,188,280,280,WHITE,12);rect(xx,188,280,8,col,4)
    text(when,xx+20,219,12,col,'Bold');text(title,xx+20,251,21,INK,'Bold')
    for j,s in enumerate(items):body(s,xx+20,300+j*34,241,14,INK,20,maxh=30)
    body(gate,xx+20,418,240,12,col,18,maxh=40)
rect(52,496,1176,143,NAVY,12)
text('FIRST WEEK',74,518,12,MINT,'Bold')
body('Name the operations sponsor. Select the incident. Inventory the feeds. Agree how success will be measured.',74,551,540,19,WHITE,26,maxh=80)
text('CORE TEAM',674,518,12,MINT,'Bold')
body('Park operations + integration/data engineer + twin/visualization engineer + simulation specialist. Involve IT/OT and ride vendors.',674,551,524,16,'#C1D2DA',24,maxh=80)
footer(8,'Indicative sequence, not a delivery commitment. Vendor access and data quality may change the schedule.')

# 09 / economics and decision
header('08 / Added value and decision','Fund a measurable operating improvement.',
       'Agree the baseline and acceptance thresholds before building. Expand only when the pilot produces useful evidence.')
rect(52,183,752,353,WHITE,12)
text('PILOT SCORECARD',75,205,12,TEAL,'Bold')
rows=[('Guest outcome','Wait-time distribution; crowd pressure; accessibility'),
      ('Operations','Detection-to-action time; task completion; recovery'),
      ('Model quality','Forecast error; uncertainty calibration; stale data'),
      ('Adoption','Operator use; accepted recommendations; trust'),
      ('Economics','Avoided disruption + resource savings − recurring cost')]
for i,(a,b) in enumerate(rows):
    yy=250+i*53;text(a,75,yy,15,INK,'Bold');body(b,251,yy,526,14,MUTED,19,maxh=40)
    if i<4:line(75,yy+38,780,yy+38)
rect(829,183,399,353,NAVY,12)
text('COSTS TO MAKE VISIBLE',853,207,12,MINT,'Bold')
body('Integration + data cleanup\nModel creation + calibration\nGPU rendering + compute\nSoftware + operations\nTraining + process change',853,250,348,18,WHITE,43,maxh=236)
rect(52,563,1176,76,'#E1EFEB',10)
text('RECOMMENDED NEXT STEP',73,579,11,TEAL,'Bold')
body('Authorize discovery for one zone and one incident workflow. Use the evidence to choose the next investment.',73,603,1125,17,INK,24)
footer(9,'No ROI or performance improvement is claimed. Compare matched operating conditions and avoid double-counting benefits.')

# 10 / research and assumptions
header('09 / Research basis','Reference architecture + a park-specific design proposal.',
       'Based on NVIDIA FOX and supporting platform documentation. This is a concept deck, not a validated park deployment.')
sources=[
('1','NVIDIA Factory Operations (FOX)','Agent coordination and operational-twin pattern. Article links to an availability notification page.','https://blogs.nvidia.com/blog/factory-operations-fox-blueprint-ai-brain/'),
('2','OpenUSD: Introduction','Scene composition, references, layers and time-varying properties.','https://openusd.org/release/intro.html'),
('3','NVIDIA Omniverse: rendering + streaming','RTX Real-Time 2.0; streaming documentation points new deployments toward NVCF.','https://docs.omniverse.nvidia.com/ovas/latest/index.html'),
('4','FIWARE: Digital Twins','NGSI-LD context integration; a candidate for the shared park model.','https://www.fiware.org/wp-content/uploads/FF_PositionPaper_FIWARE4DigitalTwins.pdf'),
('5','OPC Foundation: OPC UA','Industrial information exchange and information modeling.','https://opcfoundation.org/about/opc-technologies/opc-ua/'),
('6','IBM Maximo: Integration framework','Business objects and REST integration for maintenance workflows.','https://www.ibm.com/docs/en/masv-and-l/maximo-manage/cd?topic=applications-integration-framework-overview'),
('7','ONVIF: Profile M','Interfaces for analytics metadata and events.','https://www.onvif.org/profiles/profile-m/'),
('8','AnyLogic: Pedestrian Library','Queue, density and service-point modeling, including amusement parks.','https://anylogic.help/library-reference-guides/pedestrian-library/index.html')]
for i,(num,title,desc,url) in enumerate(sources):
    xx=52+(i%2)*600;yy=183+(i//2)*93
    text(num,xx,yy,14,TEAL,'Bold');text(title,xx+28,yy,17,INK,'Bold')
    body(desc,xx+28,yy+29,538,13,MUTED,18,maxh=48)
    C.linkURL(url,(xx,H-yy-72,xx+570,H-yy),relative=0,thickness=0)
rect(52,570,1176,68,WHITE,10)
body('TO CONFIRM IN DISCOVERY  •  Vendor access and licensing  •  Geometry and asset IDs  •  Data latency and quality\nOperating constraints  •  Model acceptance criteria  •  Ownership and cost of ongoing maintenance',72,585,1136,13,INK,21)
footer(10,'Sources reviewed 15 October 2026. Reference entries are clickable; full links in accompanying sources file.')
C.save()
if WARNINGS:
    print('LAYOUT WARNINGS:',WARNINGS)
else:
    print('No text-box overflow warnings.')
print(OUT)
