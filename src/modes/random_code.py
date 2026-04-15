"""Random Code game mode.

A random numeric code is generated and displayed on the LCD.
The player must type the exact same code to defuse the device before
the timer runs out.
"""

import random

from src.modes.base_mode import (
    BaseMode,
    GameContext,
    ModeResult,
    PlantingConfig,
    PlantingType,
    SetupOption,
    SetupOptionType,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _format_timer(seconds: int) -> str:
    """Format seconds as MM:SS string.

    Args:
        seconds: Time in seconds (0-5999).

    Returns:
        Formatted timer string, e.g. '05:00'.
    """
    minutes, secs = divmod(max(seconds, 0), 60)
    return f"{minutes:02d}:{secs:02d}"


def _center(text: str, width: int = 20) -> str:
    """Center text within the given width.

    Args:
        text: Text to center.
        width: Total width (default 20 for LCD).

    Returns:
        Centered string padded to width.
    """
    return text.center(width)


class RandomCodeMode(BaseMode):
    """Random Code mode: match a randomly generated numeric code to defuse.

    Setup options:
        - Timer: duration in seconds (30-5999).
        - Digits: code length (4-20).

    During gameplay the generated code is shown on the display.
    The player enters digits one-by-one; backspace removes the last digit.
    When the input reaches the full code length it is automatically checked.
    A correct match defuses the device; a mismatch clears the input.
    """

    name: str = "Random Code"
    description: str = "Type the displayed code to defuse"
    menu_key: str = "1"

    def get_planting_config(self) -> PlantingConfig:
        """Require code entry to plant: player must type the game code."""
        return PlantingConfig(planting_type=PlantingType.CODE_ENTRY)

    def get_setup_options(self) -> list[SetupOption]:
        """Return timer and digit-count setup options.

        Returns:
            List containing timer and digits options.
        """
        return [
            SetupOption(
                key="timer",
                label="Timer",
                option_type=SetupOptionType.RANGE,
                default=300,
                min_val=30,
                max_val=5999,
                step=30,
                large_step=300,
            ),
            SetupOption(
                key="digits",
                label="Digits",
                option_type=SetupOptionType.RANGE,
                default=6,
                min_val=4,
                max_val=20,
                step=1,
                large_step=5,
            ),
        ]

    def on_armed(self, context: GameContext) -> None:
        """Generate a random numeric code and initialise input buffer.

        The code length is taken from ``context.setup_values['digits']``.
        Both the code and an empty input string are stored in
        ``context.custom_data``.

        Args:
            context: The game context for this round.
        """
        digits: int = context.setup_values.get("digits", 6)
        code = "".join(str(random.randint(0, 9)) for _ in range(digits))
        context.custom_data["code"] = code
        context.custom_data["input"] = ""
        logger.info("Random code generated (%d digits)", digits)

    def on_input(self, key: str, context: GameContext) -> ModeResult:
        """Handle digit entry and backspace.

        Digits '0'-'9' are appended to the input buffer. 'backspace'
        removes the last character. When the input reaches the code
        length it is compared automatically.

        Args:
            key: The pressed key string.
            context: The current game context.

        Returns:
            DEFUSED on correct code, CONTINUE otherwise.
        """
        code: str = context.custom_data["code"]
        current_input: str = context.custom_data["input"]

        if key == "backspace":
            if current_input:
                context.custom_data["input"] = current_input[:-1]
            return ModeResult.CONTINUE

        if key in "0123456789" and len(current_input) < len(code):
            current_input += key
            context.custom_data["input"] = current_input

            # Check when input reaches full length
            if len(current_input) == len(code):
                if current_input == code:
                    logger.info("Code matched - device defused")
                    return ModeResult.DEFUSED
                else:
                    logger.info("Code mismatch - clearing input")
                    context.custom_data["input"] = ""

        return ModeResult.CONTINUE

    def on_tick(self, remaining_seconds: int, context: GameContext) -> ModeResult:
        """No periodic logic needed for this mode.

        Args:
            remaining_seconds: Seconds left on the timer.
            context: The current game context.

        Returns:
            Always CONTINUE (timer expiry handled by armed screen).
        """
        return ModeResult.CONTINUE

    def _build_input_display(self, context: GameContext) -> str:
        """Build the input display string with underscores for remaining digits.

        Args:
            context: The current game context.

        Returns:
            String with typed digits followed by underscores, e.g. '34____'.
        """
        code: str = context.custom_data["code"]
        current_input: str = context.custom_data["input"]
        remaining = len(code) - len(current_input)
        return current_input + "_" * remaining

    def render(self, display: object, remaining_seconds: int, context: GameContext) -> None:
        """Render the armed screen with code and input fields.

        Layout:
            Line 1: ** {device_name} ARMED **
            Line 2: Timer MM:SS (centered)
            Line 3: The generated code (centered, no label)
            Line 4: Input with underscores (centered)

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
        code: str = context.custom_data["code"]
        input_display = self._build_input_display(context)

        dn = context.custom_data.get("device_name", "Prop").upper()
        display.write_line(0, _center(f"** {dn} ARMED **"))
        display.write_line(1, _center(_format_timer(remaining_seconds)))
        display.write_line(2, _center(code))
        display.write_line(3, _center(input_display))

    def render_last_10s(self, display: object, remaining_seconds: int, context: GameContext) -> None:
        """Render during the last 10 seconds.

        Line 1 is handled by the armed screen (!! MM:SS !! ARMED !!).

        If code is 10 digits or fewer:
            Line 2: empty, Line 3: code, Line 4: input
        If code exceeds 10 digits:
            Line 2: code, Line 3: input, Line 4: empty

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
        code: str = context.custom_data["code"]
        input_display = self._build_input_display(context)

        if len(code) <= 10:
            display.write_line(1, _center(""))
            display.write_line(2, _center(code))
            display.write_line(3, _center(input_display))
        else:
            display.write_line(1, _center(code))
            display.write_line(2, _center(input_display))
            display.write_line(3, _center(""))
