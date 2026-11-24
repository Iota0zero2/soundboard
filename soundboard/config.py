"""Load and save the soundboard configuration as JSON."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "soundboard" / "config.json"


@dataclass
class SoundEntry:
    name: str
    path: str
    hotkey: str = ""          # e.g. "<ctrl>+<alt>+1" (pynput syntax), "" = none
    gain: float = 1.0
    loop: bool = False
    color: str = ""           # optional button colour, e.g. "#3b82f6"


@dataclass
class Config:
    samplerate: int = 48000
    blocksize: int = 512
    channels: int = 2
    input_device: int | str | None = None
    output_device: int | str | None = None
    mic_passthrough: bool = True
    mic_gain: float = 1.0
    master_gain: float = 1.0
    stop_hotkey: str = "<ctrl>+<alt>+0"   # panic: stop all sounds
    columns: int = 4
    sounds: list[SoundEntry] = field(default_factory=list)

    # ---- serialisation -------------------------------------------------
    @classmethod
    def load(cls, path: str | Path = DEFAULT_CONFIG_PATH) -> "Config":
        path = Path(path)
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text())
        sounds = [SoundEntry(**s) for s in raw.pop("sounds", [])]
        known = {f for f in cls.__dataclass_fields__ if f != "sounds"}
        kwargs = {k: v for k, v in raw.items() if k in known}
        return cls(sounds=sounds, **kwargs)

    def save(self, path: str | Path = DEFAULT_CONFIG_PATH) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        path.write_text(json.dumps(data, indent=2))
