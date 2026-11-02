"""Explicit common evaluation regions; independent of sensor type/physics."""
import math


def region(width,factor,shape):
    center=[width/2,width/2];radius=width*factor/2
    if shape=='square':
        lo=width/2-radius;hi=width/2+radius
        g=dict(kind='square',center=center,vertices=[[lo,lo],[hi,lo],[hi,hi],[lo,hi]],radius=radius,area_km2=4*radius**2/1e6)
    elif shape=='circle':g=dict(kind='circle',center=center,radius=radius,area_km2=math.pi*radius**2/1e6)
    elif shape=='hexagon':
        vertices=[[center[0]+radius*math.cos(i*math.pi/3),center[1]+radius*math.sin(i*math.pi/3)] for i in range(6)]
        g=dict(kind='hexagon',center=center,vertices=vertices,radius=radius,area_km2=3*math.sqrt(3)*radius**2/2e6)
    elif shape=='overlap':
        g=dict(kind='overlap',center=center,radius=radius,centers=[[center[0]-radius/2,center[1]],[center[0]+radius/2,center[1]]],semantics='intersection',area_km2=(2*math.pi/3-math.sqrt(3)/2)*radius**2/1e6)
    else:raise ValueError('Unknown evaluation region shape')
    return g


def contains(g,x,y):
    if g['kind']=='circle':return math.hypot(x-g['center'][0],y-g['center'][1])<=g['radius']+1e-9
    if g['kind']=='overlap':return all(math.hypot(x-cx,y-cy)<=g['radius']+1e-9 for cx,cy in g['centers'])
    vertices=g['vertices'];signs=[]
    for (ax,ay),(bx,by) in zip(vertices,vertices[1:]+vertices[:1]):signs.append((bx-ax)*(y-ay)-(by-ay)*(x-ax))
    return all(v>=-1e-9 for v in signs) or all(v<=1e-9 for v in signs)


def apply_resources(result,resource):
    if not resource:return result
    if resource.get('version')!='SHARED_RESOURCES_V1':raise ValueError('Resource contract version')
    sensors=result['sensors'];sites=result['sites'];counts=resource['sensor_counts']
    if set(counts)!={s['id'] for s in sensors}:raise ValueError('Resource sensor order/identity')
    for s in sensors:
        item=counts[s['id']];mode=item['mode']
        if mode=='OFF':s['minimum']=0;s['maximum']=len(sites)
        elif mode=='EXACT':s['minimum']=s['maximum']=item['value']
        elif mode=='MAX':s['minimum']=0;s['maximum']=item['max']
        elif mode=='RANGE':s['minimum']=item['min'];s['maximum']=item['max']
        else:raise ValueError('Unknown count mode')
        s['cost']=resource['cost']['sensor_unit_costs'][s['id']]
    for site in sites:site['activation_cost']=resource['cost']['site_cost']
    budget=resource['budget']
    if budget['mode']=='MAX':result['budget']=budget['limit']
    elif budget['mode']=='OFF':result['budget']=None
    else:raise ValueError('Unknown budget mode')
    return result
