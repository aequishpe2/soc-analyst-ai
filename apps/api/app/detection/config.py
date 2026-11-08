import ipaddress
from datetime import time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

ENGINE_VERSION = "2.0.0"
RULESET_VERSION = "soc-context-1"
MAX_EVENTS = 100_000
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_FINDINGS = 5000
MAX_LINKS = 20_000


class BusinessHours(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: SkipJsonSchema[str | None] = Field(default=None, max_length=100)
    weekdays: list[int] = Field(default=[0, 1, 2, 3, 4], min_length=1, max_length=7)
    start: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    end: str = Field(default="18:00", pattern=r"^\d{2}:\d{2}$")

    @model_validator(mode="after")
    def valid_schedule(self):
        try:
            if self.timezone:
                ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Zona horaria IANA desconocida") from exc
        begin, end = time.fromisoformat(self.start), time.fromisoformat(self.end)
        if begin >= end:
            raise ValueError("El horario debe comenzar y terminar el mismo día, inicio < fin")
        if len(set(self.weekdays)) != len(self.weekdays) or any(
            d < 0 or d > 6 for d in self.weekdays
        ):
            raise ValueError("Días únicos entre 0 (lunes) y 6 (domingo)")
        return self


class DetectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_profile: Literal["auto", "generic", "windows_security"] = "auto"
    brute_min: int = Field(default=10, ge=2, le=1000)
    brute_window: int = Field(default=300, ge=30, le=3600)
    spray_min: int = Field(default=10, ge=2, le=1000)
    spray_window: int = Field(default=600, ge=30, le=3600)
    success_min: int = Field(default=5, ge=2, le=1000)
    success_window: int = Field(default=600, ge=30, le=3600)
    lateral_min: int = Field(default=3, ge=2, le=1000)
    lateral_window: int = Field(default=600, ge=30, le=3600)
    correlation_window: int = Field(default=1800, ge=30, le=3600)
    burst_min: int = Field(default=20, ge=5, le=1000)
    burst_window: int = Field(default=900, ge=30, le=3600)
    transfer_bytes: int = Field(default=104857600, ge=1048576, le=1099511627776)
    business_hours: BusinessHours | None = None
    excluded_users: list[str] = Field(default_factory=list, max_length=50)
    excluded_source_ips: list[str] = Field(default_factory=list, max_length=50)
    privileged_groups: list[str] = Field(
        default=["Administrators", "Domain Admins", "Enterprise Admins", "Administradores"],
        max_length=50,
    )

    @field_validator("excluded_users", "privileged_groups")
    @classmethod
    def identifiers(cls, values):
        if any(not v.strip() or len(v) > 256 for v in values):
            raise ValueError("Identificadores no vacíos de hasta 256 caracteres")
        return sorted(set(v.strip() for v in values))

    @field_validator("excluded_source_ips")
    @classmethod
    def addresses(cls, values):
        addresses = [ipaddress.ip_address(v.strip()) for v in values]
        if any(
            a.is_unspecified or a.is_multicast or str(a) == "255.255.255.255" for a in addresses
        ):
            raise ValueError(
                "Usa direcciones de origen identificables, "
                "no direcciones sin especificar o multicast"
            )
        return sorted({str(address) for address in addresses})
