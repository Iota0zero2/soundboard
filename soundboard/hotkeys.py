"""Global (system-wide) hotkeys using pynput.

Hotkeys fire even when the soundboard window is not focused, which is the whole
point while you are in a game or a call. pynput's string syntax is used, e.g.
"<ctrl>+<alt>+1".

macOS note: global key monitoring needs Accessibility / Input Monitoring
permission. If the process is *not* trusted, pynput's Quartz event tap cannot
deliver events anyway, and starting it while untrusted can crash the whole app
(a native SIGTRAP once events start flowing alongside Qt's Cocoa run loop). So
we check trust first and simply don't start the listener until permission is
granted -- the on-screen pads keep working regardless.
"""

from __future__ import annotations

import sys
from typing import Callable

try:
    from pynput import keyboard
except Exception:  # pragma: no cover
    keyboard = None


def is_trusted() -> bool:
    """True if the process may monitor input (always True off macOS)."""
    if sys.platform != "darwin":
        return True
    try:
        from ApplicationServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception:
        # Can't tell -- assume not trusted so we never risk the crash.
        return False


class HotkeyManager:
    def __init__(self):
        self._listener = None
        self._bindings: dict[str, Callable[[], None]] = {}
        self.last_error: str | None = None

    @property
    def available(self) -> bool:
        return keyboard is not None

    @property
    def active(self) -> bool:
        return self._listener is not None

    def set_bindings(self, bindings: dict[str, Callable[[], None]]) -> None:
        """Replace all bindings and (re)start the listener if possible."""
        self._bindings = {k: v for k, v in bindings.items() if k}
        self.restart()

    def restart(self) -> None:
        self.stop()
        self.last_error = None
        if keyboard is None or not self._bindings:
            return
        if not is_trusted():
            self.last_error = (
                "Accessibility/Input Monitoring permission not granted; "
                "global hotkeys are disabled. Grant it in System Settings "
                "→ Privacy & Security, then restart the app."
            )
            return
        try:
            self._listener = keyboard.GlobalHotKeys(self._bindings)
            self._listener.start()
        except Exception as exc:  # noqa: BLE001
            self._listener = None
            self.last_error = f"Could not start global hotkeys: {exc}"

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:  # noqa: BLE001
                pass
            self._listener = None
