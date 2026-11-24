"""Real-time audio engine: mic passthrough + mixed soundboard playback.

The engine runs a single duplex stream. Its callback does two things every
block:

1. Mic passthrough -- copy the (gain-scaled) input into the output.
2. Soundboard mixing -- add any currently-playing clips into the output.

Mixing one duplex stream keeps mic and effects perfectly sample-aligned, which
is what you want when the output is routed into a virtual audio device
(BlackHole on macOS, VB-Cable on Windows) that other apps read as a microphone.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - sounddevice needs system audio libs
    sd = None

try:
    import soundfile as sf
except Exception:  # pragma: no cover
    sf = None


def _resample(data: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Linear resample along axis 0. Good enough for short effect clips."""
    if src_rate == dst_rate:
        return data
    n_src = data.shape[0]
    n_dst = int(round(n_src * dst_rate / src_rate))
    if n_dst <= 0:
        return data[:0]
    src_idx = np.linspace(0.0, n_src - 1, n_dst)
    base = np.floor(src_idx).astype(np.int64)
    frac = (src_idx - base).reshape(-1, 1)
    nxt = np.minimum(base + 1, n_src - 1)
    return data[base] * (1.0 - frac) + data[nxt] * frac


@dataclass
class Clip:
    """A decoded sound effect, held as float32 samples at the engine rate."""

    name: str
    data: np.ndarray  # shape (frames, channels), float32
    path: str = ""

    @property
    def channels(self) -> int:
        return self.data.shape[1]


@dataclass
class _Voice:
    """A playing instance of a clip."""

    clip: Clip
    pos: int = 0
    gain: float = 1.0
    loop: bool = False
    stop_flag: bool = False


@dataclass
class EngineConfig:
    samplerate: int = 48000
    blocksize: int = 512
    channels: int = 2
    input_device: int | str | None = None
    output_device: int | str | None = None
    mic_passthrough: bool = True
    mic_gain: float = 1.0
    master_gain: float = 1.0


class AudioEngine:
    def __init__(self, config: EngineConfig | None = None):
        self.config = config or EngineConfig()
        self._voices: list[_Voice] = []
        self._lock = threading.Lock()
        self._stream = None
        self._cache: dict[str, Clip] = {}

    # ---- lifecycle -----------------------------------------------------
    @property
    def running(self) -> bool:
        return self._stream is not None and self._stream.active

    def start(self) -> None:
        if sd is None:
            raise RuntimeError(
                "sounddevice is not available. Install it with "
                "`pip install sounddevice` and ensure PortAudio is present."
            )
        if self.running:
            return
        cfg = self.config
        in_ch, out_ch = self._resolve_channels()
        # The callback mixes at the OUTPUT width; the mic (possibly mono) is
        # up/down-mixed to match inside the callback.
        cfg.channels = out_ch
        self._stream = sd.Stream(
            samplerate=cfg.samplerate,
            blocksize=cfg.blocksize,
            channels=(in_ch, out_ch),
            dtype="float32",
            device=(cfg.input_device, cfg.output_device),
            callback=self._callback,
        )
        self._stream.start()

    def _resolve_channels(self) -> tuple[int, int]:
        """Pick valid input/output channel counts for the chosen devices.

        A duplex stream opened with a fixed channel count fails outright on a
        mono microphone (common: laptop and headset mics report 1 input
        channel). Clamp each side to what its device actually supports.
        """
        cfg = self.config
        want = cfg.channels or 2

        def info(dev, kind):
            try:
                if dev is not None:
                    return sd.query_devices(dev, kind)
                return sd.query_devices(kind=kind)
            except Exception:
                return None

        in_info = info(cfg.input_device, "input")
        out_info = info(cfg.output_device, "output")
        in_max = int(in_info["max_input_channels"]) if in_info else want
        out_max = int(out_info["max_output_channels"]) if out_info else want
        in_ch = max(1, min(want, in_max)) if in_max > 0 else 1
        out_ch = max(1, min(want, out_max)) if out_max > 0 else want
        return in_ch, out_ch

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def restart(self) -> None:
        self.stop()
        self.start()

    # ---- clip management ----------------------------------------------
    def load_clip(self, path: str, name: str | None = None) -> Clip:
        """Decode a sound file to the engine's rate/channel layout and cache it."""
        if sf is None:
            raise RuntimeError(
                "soundfile is not available. Install it with `pip install soundfile`."
            )
        key = str(Path(path).resolve())
        if key in self._cache:
            return self._cache[key]

        data, src_rate = sf.read(path, dtype="float32", always_2d=True)
        data = _resample(data, src_rate, self.config.samplerate)

        # Match channel count to the engine (mono -> duplicate, down-mix extras).
        ch = self.config.channels
        if data.shape[1] == ch:
            pass
        elif data.shape[1] == 1:
            data = np.repeat(data, ch, axis=1)
        elif data.shape[1] > ch:
            data = data[:, :ch]
        else:  # fewer channels than needed: tile what we have
            reps = int(np.ceil(ch / data.shape[1]))
            data = np.tile(data, (1, reps))[:, :ch]

        clip = Clip(name=name or Path(path).stem, data=np.ascontiguousarray(data), path=path)
        self._cache[key] = clip
        return clip

    # ---- playback ------------------------------------------------------
    def play(self, clip: Clip, gain: float = 1.0, loop: bool = False) -> None:
        with self._lock:
            self._voices.append(_Voice(clip=clip, gain=gain, loop=loop))

    def play_file(self, path: str, gain: float = 1.0, loop: bool = False) -> Clip:
        clip = self.load_clip(path)
        self.play(clip, gain=gain, loop=loop)
        return clip

    def stop_all(self) -> None:
        with self._lock:
            self._voices.clear()

    @property
    def active_voices(self) -> int:
        with self._lock:
            return len(self._voices)

    # ---- the real-time callback ---------------------------------------
    def _callback(self, indata, outdata, frames, time_info, status):  # noqa: D401
        cfg = self.config
        out = np.zeros((frames, cfg.channels), dtype=np.float32)

        if cfg.mic_passthrough and indata is not None:
            mic = indata
            if mic.shape[1] == cfg.channels:
                pass
            elif mic.shape[1] == 1:
                mic = np.repeat(mic, cfg.channels, axis=1)
            else:
                mic = mic[:, : cfg.channels]
            out += mic * cfg.mic_gain

        with self._lock:
            surviving: list[_Voice] = []
            for v in self._voices:
                if v.stop_flag:
                    continue
                data = v.clip.data
                n = data.shape[0]
                remaining = n - v.pos
                take = min(frames, remaining)
                if take > 0:
                    out[:take] += data[v.pos : v.pos + take] * v.gain
                    v.pos += take
                if v.pos >= n:
                    if v.loop:
                        v.pos = 0
                        surviving.append(v)
                    # else: finished, drop it
                else:
                    surviving.append(v)
            self._voices = surviving

        np.multiply(out, cfg.master_gain, out)
        np.clip(out, -1.0, 1.0, out)
        outdata[:] = out


# ---- device discovery (no stream required) ----------------------------
def list_devices() -> list[dict]:
    """Return available audio devices as plain dicts (empty if unavailable)."""
    if sd is None:
        return []
    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        devices.append(
            {
                "index": idx,
                "name": dev["name"],
                "max_input_channels": dev["max_input_channels"],
                "max_output_channels": dev["max_output_channels"],
                "default_samplerate": dev["default_samplerate"],
            }
        )
    return devices
