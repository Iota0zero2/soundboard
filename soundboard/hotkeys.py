"""Global (system-wide) hotkeys using pynput.

Hotkeys fire even when the soundboard window is not focused, which is the whole
point while you are in a game or a call. pynput's string syntax is used, e.g.
"<ctrl>+<alt>+1". On macOS the app needs Accessibility + Input Monitoring
permission for global keys to work.
"""

from __future__ import annotations

from typing import Callable

try:
    from pynput import keyboard
except Exception:  # pragma: no cover
    keyboard = None


class HotkeyManager:
    def __init__(self):
        self._listener = None
        self._bindings: dict[str, Callable[[], None]] = {}

    @property
    def available(self) -> bool:
        return keyboard is not None

    def set_bindings(self, bindings: dict[str, Callable[[], None]]) -> None:
        """Replace all bindings and (re)start the listener."""
        self._bindings = {k: v for k, v in bindings.items() if k}
        self.restart()

    def restart(self) -> None:
        self.stop()
        if keyboard is None or not self._bindings:
            return
        self._listener = keyboard.GlobalHotKeys(self._bindings)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
