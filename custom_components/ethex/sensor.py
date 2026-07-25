"""Sensor platform for the Ethex integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EthexCoordinator, EthexData


@dataclass(frozen=True, kw_only=True)
class EthexSensorDescription(SensorEntityDescription):
    """Describes an Ethex sensor and how to read its value from EthexData."""

    value_fn: Callable[[EthexData], float | None] = lambda data: None


SENSOR_DESCRIPTIONS: tuple[EthexSensorDescription, ...] = (
    EthexSensorDescription(
        key="portfolio_total",
        name="Portfolio total",
        native_unit_of_measurement="GBP",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash-multiple",
        value_fn=lambda data: data.summary.portfolio_total,
    ),
    EthexSensorDescription(
        key="main_account_value",
        name="Main account value",
        native_unit_of_measurement="GBP",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:bank",
        value_fn=lambda data: data.summary.main_account_value,
    ),
    EthexSensorDescription(
        key="ifisa_account_value",
        name="IFISA account value",
        native_unit_of_measurement="GBP",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:bank",
        value_fn=lambda data: data.summary.ifisa_account_value,
    ),
    EthexSensorDescription(
        key="main_invested",
        name="Main account invested",
        native_unit_of_measurement="GBP",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:chart-line",
        value_fn=lambda data: data.main.invested,
    ),
    EthexSensorDescription(
        key="main_cash_balance",
        name="Main account cash balance",
        native_unit_of_measurement="GBP",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash",
        value_fn=lambda data: data.main.cash_balance,
    ),
    EthexSensorDescription(
        key="ifisa_invested",
        name="IFISA invested",
        native_unit_of_measurement="GBP",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:chart-line",
        value_fn=lambda data: data.ifisa.invested,
    ),
    EthexSensorDescription(
        key="ifisa_cash_balance",
        name="IFISA cash balance",
        native_unit_of_measurement="GBP",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash",
        value_fn=lambda data: data.ifisa.cash_balance,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Ethex sensors from a config entry."""
    coordinator: EthexCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        EthexSensor(coordinator, entry, description) for description in SENSOR_DESCRIPTIONS
    ]
    entities.append(EthexCurrentHoldingsSensor(coordinator, entry))
    async_add_entities(entities)


class EthexSensor(CoordinatorEntity[EthexCoordinator], SensorEntity):
    """A single-value Ethex sensor driven by an EthexSensorDescription."""

    entity_description: EthexSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EthexCoordinator,
        entry: ConfigEntry,
        description: EthexSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class EthexCurrentHoldingsSensor(CoordinatorEntity[EthexCoordinator], SensorEntity):
    """Reports the number of current (active) investments.

    The full list of holdings (including repaid/cancelled ones) is exposed
    as an attribute, since a populated-row structure is inferred/unverified
    (see parser.py) and individual per-holding entities would be premature
    until real data can be confirmed.
    """

    _attr_has_entity_name = True
    _attr_name = "Current investments"
    _attr_icon = "mdi:format-list-bulleted"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EthexCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_current_investments"

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return sum(1 for h in self.coordinator.data.holdings if h.status == "current")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        return {
            "holdings": [
                {"status": h.status, **h.fields} for h in self.coordinator.data.holdings
            ]
        }
