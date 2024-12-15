from ._client import (
    WasteCollectionStationsService,
    WasteCollectionStationsServiceGetParams,
)
from ._common import logger
from ._models import (
    Accessibility,
    CleaningFrequency,
    Container,
    Coordinates,
    EAccessibilityType,
    EPickDay,
    ETrashType,
    Geometry,
    LastMeasurement,
    TrashType,
    WasteCollectionStation,
    WasteCollectionStationFeature,
    WasteCollectionStationFeatureCollection,
)

__all__ = [
    "WasteCollectionStationsService",
    "WasteCollectionStationsServiceGetParams",
    "logger",
    "Accessibility",
    "CleaningFrequency",
    "Container",
    "Coordinates",
    "EAccessibilityType",
    "EPickDay",
    "ETrashType",
    "Geometry",
    "LastMeasurement",
    "TrashType",
    "WasteCollectionStation",
    "WasteCollectionStationFeature",
    "WasteCollectionStationFeatureCollection",
]
