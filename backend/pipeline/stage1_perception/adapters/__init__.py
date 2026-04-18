"""Import adapters to register with the global registry."""

from . import cubicasa_adapter
from . import deepfloorplan_adapter
from . import floorplan_transform_adapter
from . import polyroom_adapter
from . import raster_to_graph_adapter
from . import roomformer_adapter

__all__ = [
    "cubicasa_adapter",
    "deepfloorplan_adapter",
    "floorplan_transform_adapter",
    "polyroom_adapter",
    "raster_to_graph_adapter",
    "roomformer_adapter",
]
