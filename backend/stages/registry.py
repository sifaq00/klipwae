from stages.base import Stage

STAGE_REGISTRY: dict[str, Stage] = {}


def register(cls):
    instance = cls()
    STAGE_REGISTRY[instance.name] = instance
    return cls
