"""Abstract base classes for the Hardware Abstraction Layer.

Each hardware component is defined by an ABC here.
Concrete implementations (real hardware or mocks) inherit from these.
"""

from abc import ABC, abstractmethod
from typing import Optional


class DisplayBase(ABC):
    """Abstract base for 20x4 LCD display."""

    COLS: int = 20
    ROWS: int = 4

    @abstractmethod
    def init(self) -> None:
        """Initialize the display hardware."""

    @abstractmethod
    def clear(self) -> None:
        """Clear the entire display."""

    @abstractmethod
    def write_line(self, row: int, text: str) -> None:
        """Write text to a specific row (0-3).

        Text is truncated or padded to COLS characters.

        Args:
            row: Row index (0-3).
            text: Text to display.
        """

    @abstractmethod
    def write_at(self, row: int, col: int, text: str) -> None:
        """Write text at a specific position.

        Args:
            row: Row index (0-3).
            col: Column index (0-19).
            text: Text to display.
        """

    @abstractmethod
    def set_backlight(self, on: bool) -> None:
        """Turn the backlight on or off.

        Args:
            on: True to enable, False to disable.
        """

    @abstractmethod
    def create_custom_char(self, slot: int, pattern: list[int]) -> None:
        """Define a custom character in the given slot (0-7).

        Args:
            slot: Character slot index (0-7).
            pattern: List of 8 ints defining the 5x8 pixel pattern.
        """

    @abstractmethod
    def shutdown(self, clear_display: bool = True) -> None:
        """Clean up display resources.

        Args:
            clear_display: If True (default), clear the display and turn off
                backlight before closing. If False, preserve the current display
                content and backlight state (for graceful exit messages).
        """

    def write_screen(self, lines: list[str]) -> None:
        """Write up to 4 lines to fill the screen.

        Args:
            lines: List of strings (max 4). Each is padded/truncated to 20 chars.
        """
        self.clear()
        for i, line in enumerate(lines[:self.ROWS]):
            self.write_line(i, line)
        self.flush()

    def write_lines(self, lines: list[str]) -> None:
        """Write a set of lines to the display.

        This alias exists for legacy callers that use ``write_lines``.
        """
        self.write_screen(lines)

    def flush(self) -> None:
        """Flush the display buffer to the hardware.

        Called once per frame after all write_line calls are done.
        The default implementation is a no-op (suitable for real LCDs
        that update immediately). Mock displays override this to
        batch-render the terminal output.
        """


class AudioBase(ABC):
    """Abstract base for audio playback."""

    @abstractmethod
    def init(self) -> None:
        """Initialize the audio system."""

    @abstractmethod
    def play(self, sound_name: str) -> None:
        """Play a sound file by name (e.g. 'beep', 'explosion').

        Args:
            sound_name: Key from config audio.sounds mapping.
        """

    @abstractmethod
    def play_loop(self, sound_name: str) -> None:
        """Play a sound in an infinite loop until stop() is called.

        Args:
            sound_name: Key from config audio.sounds mapping.
        """

    @abstractmethod
    def play_file(self, file_path: str) -> None:
        """Play a specific WAV file.

        Args:
            file_path: Path to the WAV file.
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop all currently playing audio."""

    @abstractmethod
    def set_volume(self, volume: float) -> None:
        """Set master volume.

        Args:
            volume: Volume level (0.0 to 1.0).
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Clean up audio resources."""


class InputBase(ABC):
    """Abstract base for user input (USB numpad or keyboard)."""

    @abstractmethod
    def init(self) -> None:
        """Initialize the input device."""

    @abstractmethod
    def get_key(self) -> Optional[str]:
        """Get the next key press (non-blocking).

        Returns:
            Key string ('0'-'9', 'enter', 'backspace', 'up', 'down',
            'left', 'right', 'plus', 'minus', 'dot', 'numlock',
            'slash', 'asterisk') or None if no key is pressed.
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Clean up input resources."""

    def flush(self) -> None:
        """Discard all buffered key events.

        Call this when entering a new screen context to prevent carry-over
        key presses (e.g. held Enter) from being consumed by the new screen.
        Default implementation is a no-op for implementations without a buffer.
        """


class WiresBase(ABC):
    """Abstract base for wire (GPIO) detection."""

    @abstractmethod
    def init(self) -> None:
        """Initialize the wire detection hardware."""

    @abstractmethod
    def get_wire_states(self) -> dict[str, bool]:
        """Get the current state of all wires.

        Returns:
            Dict with keys 'defuse', 'explode', 'halve' and
            boolean values (True=intact/inserted, False=cut/pulled).
        """

    @abstractmethod
    def all_wires_intact(self) -> bool:
        """Check if all wires are currently inserted.

        Returns:
            True if all wires are intact.
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Clean up GPIO resources."""


class UsbDetectorBase(ABC):
    """Abstract base for USB key detection.

    Used by the USB Key Cracker mode to detect insertion of a USB stick
    containing a ``DEFUSE.KEY`` file.
    """

    @abstractmethod
    def init(self) -> None:
        """Initialize the USB detector."""

    @abstractmethod
    def is_key_present(self) -> bool:
        """Check whether a USB stick with the key file is currently inserted.

        Returns:
            True if a mounted USB device contains ``DEFUSE.KEY``.
        """

    @abstractmethod
    def is_tournament_key_present(self) -> bool:
        """Check whether a USB stick with TOURNAMENT.KEY is currently inserted.

        Returns:
            True if a mounted USB device contains ``TOURNAMENT.KEY``.
        """

    @abstractmethod
    def reload_allowlists(
        self,
        defuse_hashes: frozenset[str],
        tournament_hashes: frozenset[str],
    ) -> None:
        """Hot-reload the in-memory token allowlists.

        Called by the web server after a new key is generated or revoked,
        so the running game loop picks up the change without a restart.

        Args:
            defuse_hashes: SHA-256 hex digests of valid DEFUSE.KEY tokens.
            tournament_hashes: SHA-256 hex digests of valid TOURNAMENT.KEY tokens.
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Clean up resources."""


class BatteryBase(ABC):
    """Abstract base for battery/UPS monitoring.

    Returns None for all values if no UPS HAT is present.
    UI code must always check for None before rendering battery info.
    """

    @abstractmethod
    def init(self) -> None:
        """Initialize the battery monitor."""

    @abstractmethod
    def get_battery_level(self) -> Optional[int]:
        """Get battery percentage.

        Returns:
            Battery percentage (0-100) or None if no UPS HAT.
        """

    @abstractmethod
    def get_voltage(self) -> Optional[float]:
        """Get battery voltage.

        Returns:
            Voltage in volts or None if no UPS HAT.
        """

    @abstractmethod
    def is_charging(self) -> Optional[bool]:
        """Check if the battery is currently charging.

        Returns:
            True if charging, False if not, None if no UPS HAT.
        """

    @abstractmethod
    def get_current(self) -> Optional[float]:
        """Get current draw in milliamps.

        Returns:
            Current in mA or None if no UPS HAT.
        """

    @abstractmethod
    def is_power_plugged(self) -> Optional[bool]:
        """Check if external power (USB/Powerbank) is connected.

        Returns:
            True if plugged in, False if not, None if no UPS HAT.
        """

    @abstractmethod
    def get_runtime_minutes(self) -> Optional[int]:
        """Estimate remaining battery runtime.

        Returns:
            Estimated minutes remaining or None if unavailable.
        """

    @abstractmethod
    def get_charge_minutes(self) -> Optional[int]:
        """Estimate minutes until battery is fully charged.

        Returns:
            Estimated minutes to full charge or None if unavailable/already full.
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Clean up battery monitor resources."""


class LedBase(ABC):
    """Abstract base for a status LED output."""

    @abstractmethod
    def init(self) -> None:
        """Initialize the LED hardware."""

    @abstractmethod
    def blink_once(self) -> None:
        """Flash the LED briefly (non-blocking, ~120ms on).

        Intended to be called in sync with the beep sound during the
        armed phase.
        """

    @abstractmethod
    def set_enabled(self, on: bool) -> None:
        """Turn the LED on or off continuously.

        Args:
            on: True to illuminate, False to extinguish.
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Clean up LED resources."""
