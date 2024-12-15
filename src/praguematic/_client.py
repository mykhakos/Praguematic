import asyncio
from typing import Any, AsyncIterator, Iterable, Optional

import httpx
from aiolimiter import AsyncLimiter
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from ._common import logger
from ._models import (
    Coordinates,
    EAccessibilityType,
    WasteCollectionStationFeatureCollection,
)


class WasteCollectionStationServiceGetParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    coordinates: Optional[Coordinates] = Field(
        default=None, serialization_alias='latlng'
    )
    range: Optional[int] = Field(default=None, serialization_alias='range')
    offset: Optional[int] = Field(default=0, ge=0, serialization_alias='offset')
    limit: Optional[int] = Field(default=10000, le=10000, serialization_alias='limit')
    district_numbers: Optional[set[int]] = Field(
        default=None, serialization_alias='districts'
    )
    accessibilities: Optional[set[EAccessibilityType]] = Field(
        default=None, serialization_alias='accessibilities'
    )
    only_monitored: Optional[bool] = Field(
        default=None, serialization_alias='onlyMonitored'
    )
    ksnko_id: Optional[int] = Field(default=None, serialization_alias='ksnkoId')

    @field_serializer('coordinates', when_used='json-unless-none')
    @staticmethod
    def ser_coordinates(value: Coordinates) -> str:
        return f'{value.latitude},{value.longitude}'

    @field_serializer('district_numbers', when_used='json-unless-none')
    @staticmethod
    def ser_district_numbers(value: Iterable[int]) -> str:
        return ','.join(f'praha-{number}' for number in value)

    @field_serializer('accessibilities', when_used='json-unless-none')
    @staticmethod
    def ser_accessibilities(value: Iterable[EAccessibilityType]) -> str:
        return ','.join(a11y.value for a11y in value)


class WasteCollectionStationService:
    BASE_URL = 'https://api.golemio.cz/v2/sortedwastestations'

    def __init__(
        self,
        access_token: str,
        rate_limit_requests: int = 8,
        rate_limit_period: int = 20,
    ) -> None:
        self.access_token = access_token
        self.rate_limit_requests = rate_limit_requests
        self.rate_limit_period = rate_limit_period

    @staticmethod
    def _get_params(params: WasteCollectionStationServiceGetParams) -> dict[str, Any]:
        return params.model_dump(
            mode='json',
            by_alias=True,
            exclude_unset=True,
            exclude_none=True,
            exclude_defaults=True,
        )

    def _get_headers(self) -> dict[str, Any]:
        return {'X-Access-Token': self.access_token}

    async def _get_waste_stations(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, Any],
        params: dict[str, Any],
        max_timeout_retries: int,
    ) -> WasteCollectionStationFeatureCollection:
        attemtp = 1
        while True:
            try:
                resp = await client.get(self.BASE_URL, params=params, headers=headers)
                resp.raise_for_status()
                validation_model = WasteCollectionStationFeatureCollection
                return validation_model.model_validate_json(resp.text)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 429 or attemtp > max_timeout_retries:
                    raise
                logger.warning(
                    'Rate limit exceeded. Waiting for %s seconds before retrying '
                    '(attemt %s of %s).',
                    self.rate_limit_period / 2,
                    attemtp,
                    max_timeout_retries,
                )
                await asyncio.sleep(self.rate_limit_period / 2)
                attemtp += 1

    async def get_waste_stations(
        self,
        params: Optional[WasteCollectionStationServiceGetParams] = None,
        max_timeout_retries: int = 1,
    ) -> WasteCollectionStationFeatureCollection:
        if params is None:
            params = WasteCollectionStationServiceGetParams()
        async with httpx.AsyncClient() as client:
            return await self._get_waste_stations(
                client=client,
                headers=self._get_headers(),
                params=self._get_params(params),
                max_timeout_retries=max_timeout_retries,
            )

    async def iter_waste_stations(
        self,
        params: Optional[WasteCollectionStationServiceGetParams] = None,
        limit_rate: bool = True,
        max_timeout_retries: int = 3,
    ) -> AsyncIterator[WasteCollectionStationFeatureCollection]:
        headers = self._get_headers()

        if params is None:
            params = WasteCollectionStationServiceGetParams()
        param_dict = self._get_params(params)
        if param_dict.get('offset', None) is None:
            param_dict['offset'] = 0

        if limit_rate:
            limiter = AsyncLimiter(self.rate_limit_requests, self.rate_limit_period)
        else:
            limiter = AsyncLimiter(9999, 1)

        async with httpx.AsyncClient() as client:
            while True:
                async with limiter:
                    stations = await self._get_waste_stations(
                        client=client,
                        headers=headers,
                        params=param_dict,
                        max_timeout_retries=max_timeout_retries,
                    )
                yield stations
                if not stations.features:
                    break
                if params.limit:
                    if len(stations.features) < params.limit:
                        break
                    param_dict['offset'] += params.limit
                else:
                    param_dict['offset'] += len(stations.features)
