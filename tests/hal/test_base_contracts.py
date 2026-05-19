"""Contract tests for the HAL Mock implementations.

For every abstract method on a HAL base class, the corresponding Mock
must provide a concrete implementation. This guards against the failure
mode "added a new method to base.py, forgot to add it to the mock" —
without these tests the real driver would diverge silently and the
mock-mode dev loop would crash at runtime instead of import.
"""

import inspect

import pytest

from src.hal.audio_mock import MockAudio
from src.hal.base import (
    AudioBase,
    BatteryBase,
    DisplayBase,
    InputBase,
    LedBase,
    UsbDetectorBase,
    WiresBase,
)
from src.hal.battery_mock import MockBattery
from src.hal.battery_none import NoBattery
from src.hal.display_mock import MockDisplay
from src.hal.input_mock import MockInput
from src.hal.led_mock import MockLed
from src.hal.usb_detector_mock import MockUsbDetector
from src.hal.wires_mock import MockWires


def _abstract_method_names(base_class: type) -> set[str]:
    """Return names of all ``@abstractmethod`` members declared on *base_class*."""
    return {
        name
        for name, member in inspect.getmembers(base_class)
        if getattr(member, "__isabstractmethod__", False)
    }


HAL_PAIRS: list[tuple[type, type]] = [
    (DisplayBase, MockDisplay),
    (AudioBase, MockAudio),
    (InputBase, MockInput),
    (WiresBase, MockWires),
    (UsbDetectorBase, MockUsbDetector),
    (BatteryBase, MockBattery),
    (BatteryBase, NoBattery),
    (LedBase, MockLed),
]


@pytest.mark.parametrize(
    ("base", "mock"),
    HAL_PAIRS,
    ids=[f"{m.__name__}_implements_{b.__name__}" for b, m in HAL_PAIRS],
)
def test_mock_implements_all_abstract_methods(
    base: type, mock: type
) -> None:
    """Every @abstractmethod on the base class must be implemented by the mock."""
    abstract_names = _abstract_method_names(base)
    missing = [
        name
        for name in abstract_names
        if getattr(getattr(mock, name, None), "__isabstractmethod__", False)
    ]
    assert not missing, (
        f"{mock.__name__} is missing implementations for "
        f"abstract methods on {base.__name__}: {missing}"
    )


@pytest.mark.parametrize(
    ("base", "mock"),
    HAL_PAIRS,
    ids=[f"{m.__name__}_instantiates" for _, m in HAL_PAIRS],
)
def test_mock_is_instantiable(base: type, mock: type) -> None:
    """The mock can be constructed without arguments and is an instance of its base."""
    instance = mock()
    assert isinstance(instance, base)
