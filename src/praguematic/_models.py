import sys
from collections.abc import Collection
from datetime import date, datetime
from enum import Enum
from typing import Iterator, List, NamedTuple, Optional

from haversine import Unit as DistanceUnit
from haversine import haversine
from pydantic import BaseModel

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


class EAccessibilityType(Enum):
    ACCESSIBLE = 1
    ONLY_FOR_HOUSE_RESIDENTS = 2
    UNKNOWN = 3


class ETrashType(Enum):
    TINTED_GLASS = 1
    ELECTRIC_WASTE = 2
    METALS = 3
    BEVERAGE_CARTONS = 4
    PAPER = 5
    PLASTICS = 6
    CLEAR_GLASS = 7
    EDIBLE_FATS_AND_OILS = 8
    MULTICOMMODITY = 9


class EPickDay(str, Enum):
    MONDAY = 'Po'
    TUESDAY = 'Út'
    WEDNESDAY = 'St'
    THURSDAY = 'Čt'
    FRIDAY = 'Pá'
    SATURDAY = 'So'
    SUNDAY = 'Ne'


class Accessibility(BaseModel):
    description: str
    id: EAccessibilityType


class CleaningFrequency(BaseModel):
    duration: Optional[str] = None
    frequency: Optional[int] = None
    id: Optional[int] = None
    pick_days: Optional[str] = None
    next_pick: Optional[date] = None

    @property
    def period(self) -> Optional[int]:
        if self.id is None:
            return None
        if not (10 <= self.id <= 99):
            raise ValueError('The value must be a two-digit integer')
        return self.id // 10

    @property
    def pick_days_list(self) -> List[EPickDay]:
        if self.pick_days is None:
            return []
        return [EPickDay(day.strip()) for day in self.pick_days.split(',')]


class TrashType(BaseModel):
    description: Optional[str] = None
    id: Optional[ETrashType] = None


class LastMeasurement(BaseModel):
    measured_at_utc: Optional[datetime] = None
    percent_calculated: Optional[int] = None
    prediction_utc: Optional[datetime] = None

    @property
    def percent_decimal(self) -> Optional[float]:
        if self.percent_calculated is None:
            return None
        return self.percent_calculated / 100


class Container(BaseModel):
    cleaning_frequency: Optional[CleaningFrequency] = None
    container_type: Optional[str] = None
    trash_type: Optional[TrashType] = None
    last_measurement: Optional[LastMeasurement] = None
    last_pick: Optional[datetime] = None
    ksnko_id: Optional[int] = None
    container_id: Optional[int] = None
    sensor_code: Optional[str] = None
    sensor_supplier: Optional[str] = None
    sensor_id: Optional[str] = None
    is_monitored: Optional[bool] = None

    def is_suited_for(self, trash_type: ETrashType) -> Optional[bool]:
        if self.trash_type is None or self.trash_type.id is None:
            return None
        return self.trash_type.id == trash_type

    def is_picked_on(self, day: EPickDay) -> Optional[bool]:
        if self.cleaning_frequency is None or self.cleaning_frequency.pick_days is None:
            return None
        return day.value.casefold() in self.cleaning_frequency.pick_days.casefold()

    def is_empty(self, threshold: int = 5) -> Optional[bool]:
        if (
            not self.is_monitored
            or self.last_measurement is None
            or self.last_measurement.percent_calculated is None
        ):
            return None
        return self.last_measurement.percent_calculated <= threshold

    def is_full(self, threshold: int = 95) -> Optional[bool]:
        if (
            not self.is_monitored
            or self.last_measurement is None
            or self.last_measurement.percent_calculated is None
        ):
            return None
        return self.last_measurement.percent_calculated >= threshold


class WasteCollectionStation(BaseModel):
    id: int
    name: str
    accessibility: Optional[Accessibility] = None
    containers: Optional[List[Container]] = None
    district: Optional[str] = None
    is_monitored: Optional[bool] = None
    station_number: Optional[str] = None
    updated_at: Optional[datetime] = None

    @property
    def district_number(self) -> Optional[int]:
        if self.district is None:
            return None
        return int(self.district.split('-')[-1])

    def is_accessible_for(self, user_type: EAccessibilityType) -> Optional[bool]:
        if self.accessibility is None or self.accessibility.id is None:
            return None
        return self.accessibility.id == user_type

    def has_container_for(self, trash_type: ETrashType) -> Optional[bool]:
        if self.containers is None:
            return None
        return any(cont.is_suited_for(trash_type) for cont in self.containers)


class Coordinates(NamedTuple):
    longitude: float
    latitude: float

    def calculate_distance(
        self,
        other: 'Coordinates',
        unit: DistanceUnit = DistanceUnit.KILOMETERS,
    ) -> float:
        return haversine(
            (self.latitude, self.longitude),
            (other.latitude, other.longitude),
            unit=unit,
        )


class Geometry(BaseModel):
    coordinates: Optional[Coordinates] = None
    type: Optional[str] = None


class WasteCollectionStationFeature(BaseModel):
    type: Optional[str] = None
    geometry: Optional[Geometry] = None
    properties: Optional[WasteCollectionStation] = None

    @property
    def station(self) -> Optional[WasteCollectionStation]:
        """Read-only alias for the `properties` attribute."""
        return self.properties


class WasteCollectionStationFeatureCollection(
    BaseModel, Collection[WasteCollectionStationFeature]
):
    type: Optional[str] = None
    features: Optional[List[WasteCollectionStationFeature]] = None

    def __contains__(self, value: WasteCollectionStationFeature) -> bool:
        if self.features is None:
            return False
        name = value.properties.name
        return any(name == feature.properties.name for feature in self.features)

    def __iter__(self) -> Iterator[WasteCollectionStationFeature]:
        if self.features is None:
            return iter([])
        return iter(self.features)

    def __len__(self) -> int:
        if self.features is None:
            return 0
        return len(self.features)

    def __add__(self, other: 'WasteCollectionStationFeatureCollection') -> Self:
        features = []
        this_waste_station_names = set()
        if self.features:
            for feature in self.features:
                features.append(feature)
                if feature.properties:
                    this_waste_station_names.add(feature.properties.name)
        if other.features:
            for feature in other.features:
                if feature.properties:
                    if feature.properties.name not in this_waste_station_names:
                        features.append(feature)
        return type(self).model_construct(type=self.type, features=features)

    def __sub__(self, other: 'WasteCollectionStationFeatureCollection') -> Self:
        if not self.features:
            return type(self).model_construct(type=self.type, features=[])
        if not other.features:
            features = self.features.copy()
            return type(self).model_construct(type=self.type, features=features)
        features = []
        other_waste_station_names = set()
        for feature in other.features:
            if feature.properties:
                other_waste_station_names.add(feature.properties.name)
        for feature in self.features:
            if feature.properties:
                if feature.properties.name not in other_waste_station_names:
                    features.append(feature)
        return type(self).model_construct(type=self.type, features=features)

    @property
    def stations(self) -> List[WasteCollectionStationFeature]:
        """Read-only alias for the `features` attribute."""
        if self.features is None:
            return []
        return self.features.copy()
