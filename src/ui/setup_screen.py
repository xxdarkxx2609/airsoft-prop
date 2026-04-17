"""Setup screen for configuring game mode options before starting.

Dynamically builds the setup UI from the selected mode's get_setup_options().
Supports RANGE options (left/right/+/- to adjust) and CODE_INPUT options
(Enter opens a dedicated code-entry sub-screen).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

from src.hal.base import DisplayBase
from src.modes.base_mode import GameContext, PlantingType, SetupOption, SetupOptionType
from src.ui.base_screen import BaseScreen, translate_digit_to_nav
from src.ui.lcd_helpers import center_text, format_timer, pad_text
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.app import App

logger = get_logger(__name__)

# Custom character code for the menu cursor (triangle pointing right).
_CURSOR_CHAR: str = chr(4)


class SetupScreen(BaseScreen):
    """Pre-game setup screen where players configure mode options.

    Reads the selected mode's setup options and renders an interactive
    list.  RANGE options are adjusted with left/right (step) and +/-
    (large step).  CODE_INPUT options open a dedicated code-entry
    sub-screen when the player presses Enter.  Pressing Enter on a
    non-CODE_INPUT option starts the game.

    Numpad digits 8/2/4/6 are translated to up/down/left/right for
    navigation.  In the code-entry sub-screen, digits are passed
    through as-is so the player can type the code.
    """

    # Duration in seconds to show error messages on screen.
    _ERROR_DISPLAY_DURATION: float = 2.0

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.options: list[SetupOption] = []
        self.cursor: int = 0
        self._scroll_offset: int = 0
        self._error_message: str = ""
        self._error_time: float = 0.0
        # Code-entry sub-screen state
        self._code_entry_mode: bool = False
        self._code_entry_input: str = ""
        self._code_entry_option: Optional[SetupOption] = None

    # -- lifecycle ------------------------------------------------------------

    def on_enter(self) -> None:
        """Load setup options from the currently selected mode."""
        mode = self.app.selected_mode
        if mode is None:
            logger.error("SetupScreen entered with no selected mode")
            self.app.screen_manager.switch_to("menu")
            return

        self.options = mode.get_setup_options()
        self._apply_config_defaults()
        self.cursor = 0
        self._scroll_offset = 0
        self._code_entry_mode = False
        self._code_entry_input = ""
        self._code_entry_option = None
        logger.info(
            "Setup screen entered for mode '%s' with %d options",
            mode.name,
            len(self.options),
        )

    def _apply_config_defaults(self) -> None:
        """Override hardcoded option defaults with values from config."""
        config = self.app.config
        mode_name = self.app.selected_mode.name if self.app.selected_mode else ""

        # Map config keys to option defaults
        config_map: dict[str, tuple] = {
            "timer": ("game", "default_timer"),
        }
        # Mode-specific defaults
        if mode_name in ("Random Code", "Random Code+"):
            config_map["digits"] = ("modes", "random_code", "default_digits")
        elif mode_name == "USB Key Cracker":
            config_map["digits"] = ("modes", "usb_key_cracker", "default_digits")

        # Apply timer_step from config
        timer_step = config.get("game", "timer_step")

        for option in self.options:
            if option.key in config_map:
                keys = config_map[option.key]
                cfg_val = config.get(*keys)
                if cfg_val is not None:
                    option.default = cfg_val
                    option.value = cfg_val
            if option.key == "timer" and timer_step is not None:
                option.step = timer_step

    # -- rendering ------------------------------------------------------------

    def render(self, display: DisplayBase) -> None:
        """Draw the setup screen on the 20x4 display.

        Layout (normal mode):
            Line 0: Mode name (centered)
            Lines 1-2: Up to 2 visible options (scrollable)
            Line 3: Navigation footer (context-dependent)

        Layout (code-entry sub-screen):
            Line 0: Mode name (centered)
            Line 1: "Enter Code:"
            Line 2: "> " + typed digits + underscores
            Line 3: "<- Back    Ent Ok"

        When an error is active, lines 1-2 show the error message instead.

        Args:
            display: The display HAL instance to render on.
        """
        mode = self.app.selected_mode
        mode_name = mode.name if mode else "Setup"

        # Line 0: Mode name centered
        display.write_line(0, center_text(mode_name))

        # Code-entry sub-screen
        if self._code_entry_mode:
            self._render_code_entry(display)
            return

        # Show error message for a short duration, then clear it
        if self._error_message and time.time() - self._error_time < self._ERROR_DISPLAY_DURATION:
            display.write_line(1, center_text(""))
            display.write_line(2, center_text(self._error_message))
            display.write_line(3, pad_text(""))
            return
        self._error_message = ""

        # Ensure scroll offset keeps the cursor visible in the 2-line window
        if self.cursor < self._scroll_offset:
            self._scroll_offset = self.cursor
        elif self.cursor >= self._scroll_offset + 2:
            self._scroll_offset = self.cursor - 1

        # Lines 1-2: Render up to 2 options from the visible window
        for row in range(2):
            option_idx = self._scroll_offset + row
            if option_idx < len(self.options):
                option = self.options[option_idx]
                is_selected = option_idx == self.cursor
                line = self._format_option(option, is_selected)
                display.write_line(1 + row, pad_text(line))
            else:
                display.write_line(1 + row, pad_text(""))

        # Line 3: Footer — context-dependent hint
        current = self.options[self.cursor] if self.options else None
        if current and current.option_type == SetupOptionType.CODE_INPUT:
            display.write_line(3, pad_text("<- Back   Ent Edit"))
        else:
            display.write_line(3, pad_text("<- Back   Ent Start"))

    def _render_code_entry(self, display: DisplayBase) -> None:
        """Render the code-entry sub-screen.

        Args:
            display: The display HAL instance to render on.
        """
        option = self._code_entry_option
        max_digits = option.max_val if option else 10
        code = self._code_entry_input
        remaining = max_digits - len(code)
        display_code = code + "_" * remaining
        # Truncate to fit line (18 chars after "> " prefix)
        display_code = display_code[:18]

        display.write_line(1, pad_text("  Enter Code:"))
        display.write_line(2, pad_text(f"  > {display_code}"))
        display.write_line(3, pad_text("<- Back    Ent Ok"))

    def _format_option(self, option: SetupOption, selected: bool) -> str:
        """Format a single setup option line for the display.

        Args:
            option: The SetupOption to format.
            selected: Whether this option is currently cursor-selected.

        Returns:
            Formatted string (max 20 chars).
        """
        cursor = _CURSOR_CHAR if selected else " "

        if option.option_type == SetupOptionType.RANGE:
            value_str = self._format_range_value(option)
            # Layout: "▸ Label:  <value>"
            # Reserve space: 2 for cursor+space, label, 2 for ": ", value
            label = option.label
            available = 20 - 2 - len(": ") - len(value_str)
            label = label[:available]
            return f"{cursor} {label}: {value_str}"

        if option.option_type == SetupOptionType.CODE_INPUT:
            code = str(option.value) if option.value else ""
            if code:
                return f"{cursor} {option.label}: {code}"
            return f"{cursor} {option.label}: [Enter]"

        return f"{cursor} {option.label}"

    @staticmethod
    def _format_range_value(option: SetupOption) -> str:
        """Format a RANGE option's value for display.

        Timer options (key='timer') are formatted as MM:SS.
        All other RANGE values are shown as plain integers.

        Args:
            option: A RANGE-type SetupOption.

        Returns:
            Formatted value string.
        """
        if option.key == "timer":
            return format_timer(int(option.value))
        return str(option.value)

    # -- input ----------------------------------------------------------------

    def handle_input(self, key: str) -> None:
        """Process a key press on the setup screen.

        In the normal option-list view, numpad digits 8/2/4/6 are
        translated to navigation directions.  In the code-entry
        sub-screen, digits are passed through as-is.

        Args:
            key: The key string from the input HAL.
        """
        # Delegate to code-entry sub-screen if active
        if self._code_entry_mode:
            self._handle_code_entry(key)
            return

        if not self.options:
            if key == "backspace":
                self.app.screen_manager.switch_to("menu")
            return

        # Translate numpad digits to navigation directions
        key = translate_digit_to_nav(key)

        current = self.options[self.cursor]

        if key == "up":
            self._move_cursor(-1)
        elif key == "down":
            self._move_cursor(1)
        elif key == "left":
            self._adjust_value(current, -current.step)
        elif key == "right":
            self._adjust_value(current, current.step)
        elif key == "plus":
            self._adjust_value(current, current.large_step)
        elif key == "minus":
            self._adjust_value(current, -current.large_step)
        elif key == "backspace":
            logger.info("Setup screen: returning to menu")
            self.app.screen_manager.switch_to("menu")
        elif key == "enter":
            if current.option_type == SetupOptionType.CODE_INPUT:
                self._enter_code_entry(current)
            else:
                self._start_game()

    def _move_cursor(self, delta: int) -> None:
        """Move the option cursor up or down, clamped to valid range.

        Args:
            delta: Direction to move (-1 for up, +1 for down).
        """
        self.cursor = max(0, min(len(self.options) - 1, self.cursor + delta))

    @staticmethod
    def _adjust_value(option: SetupOption, delta: int) -> None:
        """Adjust a RANGE option's value by a given delta, clamped to bounds.

        Does nothing for non-RANGE options.

        Args:
            option: The option to adjust.
            delta: Amount to add (can be negative).
        """
        if option.option_type != SetupOptionType.RANGE:
            return
        new_value = int(option.value) + delta
        option.value = max(option.min_val, min(option.max_val, new_value))

    def _enter_code_entry(self, option: SetupOption) -> None:
        """Switch to the code-entry sub-screen for a CODE_INPUT option.

        Pre-populates the input buffer with the option's current value
        so the player can continue editing an existing code.

        Args:
            option: The CODE_INPUT option to edit.
        """
        self._code_entry_mode = True
        self._code_entry_option = option
        self._code_entry_input = str(option.value) if option.value else ""
        logger.debug("Entering code entry for '%s' (current: '%s')", option.key, self._code_entry_input)

    def _exit_code_entry(self) -> None:
        """Leave the code-entry sub-screen and return to the option list."""
        self._code_entry_mode = False
        self._code_entry_option = None
        self._code_entry_input = ""
        logger.debug("Exiting code entry sub-screen")

    def _handle_code_entry(self, key: str) -> None:
        """Process input in the code-entry sub-screen.

        Digits 0-9 are appended to the code buffer.  Backspace deletes
        the last digit (or exits when empty).  Enter confirms the code
        and returns to the option list.

        Args:
            key: The raw key string (NOT translated to navigation).
        """
        option = self._code_entry_option
        if option is None:
            self._exit_code_entry()
            return

        max_digits = option.max_val

        if key in "0123456789":
            if len(self._code_entry_input) < max_digits:
                self._code_entry_input += key
                logger.debug("Code entry: appended '%s', now '%s'", key, self._code_entry_input)
        elif key == "backspace":
            if self._code_entry_input:
                self._code_entry_input = self._code_entry_input[:-1]
                logger.debug("Code entry: deleted last digit, now '%s'", self._code_entry_input)
            else:
                # Empty buffer -> exit code entry without saving
                logger.info("Code entry: empty, returning to setup")
                self._exit_code_entry()
        elif key == "enter":
            # Save the entered code to the option and return to setup
            option.value = self._code_entry_input
            logger.info("Code entry: confirmed '%s'", self._code_entry_input)
            self._exit_code_entry()

    def _show_error(self, message: str) -> None:
        """Set a temporary error message to display on screen.

        Args:
            message: Error text to show (max 20 chars for LCD).
        """
        self._error_message = message
        self._error_time = time.time()

    def _start_game(self) -> None:
        """Build the game context from setup options and start the game.

        Creates a GameContext, attaches it to the app, calls the mode's
        on_armed() hook, and transitions to the armed screen.
        """
        mode = self.app.selected_mode
        if mode is None:
            logger.error("Cannot start game: no mode selected")
            return

        # Validate: CODE_INPUT options must have at least 1 digit
        for option in self.options:
            if option.option_type == SetupOptionType.CODE_INPUT:
                code = str(option.value) if option.value else ""
                if not code:
                    logger.warning("Cannot start game: no code set for '%s'", option.key)
                    self._show_error("No Code was set!")
                    return

        # Build setup_values dict from all options
        setup_values: dict[str, object] = {}
        timer_seconds: int = 60  # Default fallback

        for option in self.options:
            setup_values[option.key] = option.value
            if option.key == "timer":
                timer_seconds = int(option.value)

        # Create the game context
        context = GameContext(
            timer_seconds=timer_seconds,
            remaining_seconds=timer_seconds,
            setup_values=setup_values,
        )

        # Provide HAL access and config to modes
        context.custom_data["device_name"] = self.app.config.get(
            "game", "device_name", default="Prop"
        )
        context.custom_data["wires"] = self.app.wires
        context.custom_data["usb_detector"] = self.app.usb_detector
        context.custom_data["penalty_seconds"] = self.app.config.get(
            "game", "penalty_seconds", default=10,
        )
        context.custom_data["crack_interval"] = self.app.config.get(
            "modes", "usb_key_cracker", "crack_interval", default=2.5,
        )

        # Attach context to the app and notify the mode
        self.app.game_context = context
        mode.on_armed(context)

        logger.info(
            "Game started: mode='%s', timer=%ds, setup=%s",
            mode.name,
            timer_seconds,
            setup_values,
        )

        # Route through planting screen unless the mode uses instant planting
        planting_config = mode.get_planting_config()
        if planting_config.planting_type == PlantingType.INSTANT:
            self.app.screen_manager.switch_to("armed")
        else:
            self.app.screen_manager.switch_to("planting")
