"""Set Code game mode.

The organiser sets a secret code during setup. During gameplay the code
is NOT displayed -- the player must figure it out through other game
mechanics (e.g. a hint in a briefing or intel found on the field).
"""

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


class SetCodeMode(BaseMode):
    """Set Code mode: enter a pre-configured secret code to defuse.

    Setup options:
        - Timer: duration in seconds (30-5999).
        - Code: a numeric code of 1-10 digits entered during setup.

    During gameplay the code is hidden. The player types their guess
    and it is checked when the input length matches the code length.
    A mismatch clears the input for another attempt.
    """

    name: str = "Set Code"
    description: str = "Enter the secret code to defuse"
    menu_key: str = "2"

    def get_planting_config(self) -> PlantingConfig:
        """Require a 10-digit random activation code to plant."""
        return PlantingConfig(
            planting_type=PlantingType.CODE_ENTRY,
            code_length=10,
        )

    def get_setup_options(self) -> list[SetupOption]:
        """Return timer and secret-code setup options.

        Returns:
            List containing timer and code options.
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
                key="code",
                label="Code",
                option_type=SetupOptionType.CODE_INPUT,
                default="",
                min_val=1,
                max_val=10,
            ),
        ]

    def on_armed(self, context: GameContext) -> None:
        """Store the secret code and initialise the input buffer.

        The code is taken from ``context.setup_values['code']``.

        Args:
            context: The game context for this round.
        """
        code: str = str(context.setup_values.get("code", "1234"))
        context.custom_data["code"] = code
        context.custom_data["input"] = ""
        logger.info("Set code mode armed (code length: %d)", len(code))

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
                    logger.info("Secret code matched - device defused")
                    return ModeResult.DEFUSED
                else:
                    logger.info("Secret code mismatch - clearing input")
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
        """Build the input display string with typed digits and underscores.

        Formats as ``> {typed}{underscores}`` (code is hidden).

        Args:
            context: The current game context.

        Returns:
            Formatted input string, e.g. '> 34______'.
        """
        code: str = context.custom_data["code"]
        current_input: str = context.custom_data["input"]
        remaining = len(code) - len(current_input)
        return f"> {current_input}{'_' * remaining}"

    def render(self, display: object, remaining_seconds: int, context: GameContext) -> None:
        """Render the armed screen with hidden code and input field.

        Layout:
            Line 1: ** {device_name} ARMED **
            Line 2: Timer MM:SS (centered)
            Line 3: 'Enter Code:'
            Line 4: '> {input}____'

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
        input_display = self._build_input_display(context)
        dn = context.custom_data.get("device_name", "Prop").upper()

        display.write_line(0, _center(f"** {dn} ARMED **"))
        display.write_line(1, _center(_format_timer(remaining_seconds)))
        display.write_line(2, _center("Enter Code:"))
        display.write_line(3, _center(input_display))

    def render_last_10s(self, display: object, remaining_seconds: int, context: GameContext) -> None:
        """Render during the last 10 seconds.

        Line 1 is handled by the armed screen (!! MM:SS !! ARMED !!).
        Line 2: empty
        Line 3: 'Enter Code:'
        Line 4: input

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
        input_display = self._build_input_display(context)

        display.write_line(1, _center(""))
        display.write_line(2, _center("Enter Code:"))
        display.write_line(3, _center(input_display))
