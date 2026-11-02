"""Named model-derived data calls; no model equations or defaults."""
from model_service_client import module_attribute
def call(name,*args,**kwargs):return module_attribute('model_derivatives',name)(*args,**kwargs)
def cost(model,x):return call('cost',model,x)
def operational(performance,targets=None,tolerance=1e-12):return call('operational',performance,targets,tolerance)
def __getattr__(name):return module_attribute('model_derivatives',name)
