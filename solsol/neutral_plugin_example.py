"""Optional second neutral catalog entry for model-switch/reuse examples."""


def convert(config):
    from model_service_client import model_config,CID
    return model_config(config,CID)


def register_models(adapter):
    meta=adapter.model_metadata(adapter.CID);schema=adapter.model_schema(adapter.CID)
    meta['id']=schema['id']='ABC_ALTERNATIVE_V1'
    meta['name']='A/B/C · 다른 범위 조건'
    schema['defaults']['A_radius']=420
    adapter.register_model(meta['id'],meta,schema,convert)
