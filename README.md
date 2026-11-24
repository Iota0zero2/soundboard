# Soundboard

A simple, customizable software soundboard with live **mic passthrough**.

Route your microphone *plus* sound effects into a single audio stream, so apps
like Discord, OBS, Zoom or games hear both. Trigger sounds from an on-screen
grid or with global hotkeys that work even when the window isn't focused.

## How it works

The engine runs one duplex audio stream. Every audio block it:

1. copies your mic input into the output (passthrough), and
2. mixes in any sound effects you've triggered.

To send the result to other apps, point the **output** at a *virtual audio
device* and select that same device as the "microphone" in the other app:

- **macOS** — [BlackHole](https://github.com/ExistentialAudio/BlackHole)
- **Windows** — [VB-CABLE](https://vb-audio.com/Cable/)
- **Linux** — a PulseAudio/PipeWire null sink (`pactl load-module module-null-sink`)

Set the soundboard **output** to the virtual device, and (optionally) keep a
second copy going to your speakers with the mic/master sliders so you can
monitor yourself.

## Install

```bash
git clone https://github.com/Iota0zero2/soundboard.git
cd soundboard
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

`soundfile` needs libsndfile and `sounddevice` needs PortAudio. On macOS:
`brew install libsndfile portaudio`.

## Run

```bash
python -m soundboard
```

List audio devices (to find your virtual device index):

```bash
python -m soundboard --list-devices
```

Use a specific config file:

```bash
python -m soundboard --config ./config.json
```

## Usage

- **Start / Stop** — opens and closes the audio stream.
- **In / Out** — pick input (mic) and output (speakers or virtual device).
- **Mic passthrough** — toggle whether the mic is mixed into the output.
- **Mic / Master** sliders — input and overall volume.
- **+ Add sound** — pick a file and (optionally) assign a global hotkey.
- **Click a pad** to play; **right-click** to edit or remove it.
- **Stop all** (default hotkey `Ctrl+Alt+0`) — panic-stop every playing sound.

Config is saved automatically to `~/.config/soundboard/config.json`
(see [`config.example.json`](config.example.json) for the format). Hotkeys use
[pynput](https://pynput.readthedocs.io/) syntax, e.g. `<ctrl>+<alt>+1`.

### macOS permissions

Global hotkeys and microphone capture need permission under **System Settings →
Privacy & Security**: grant your terminal/Python **Microphone**, **Accessibility**
and **Input Monitoring** access.

## License

MIT — see [LICENSE](LICENSE).
