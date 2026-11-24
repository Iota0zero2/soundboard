"""Tests for the pure-DSP parts of the engine (no audio hardware required)."""

import numpy as np

from soundboard.audio_engine import AudioEngine, Clip, EngineConfig, _resample


def test_resample_lengths():
    data = np.ones((100, 2), dtype=np.float32)
    up = _resample(data, 24000, 48000)
    down = _resample(data, 48000, 24000)
    assert up.shape[0] == 200
    assert down.shape[0] == 50
    # Same rate is a no-op.
    assert _resample(data, 48000, 48000) is data


def _render(engine, frames):
    """Drive the callback once with silence on the mic, return the output block."""
    indata = np.zeros((frames, engine.config.channels), dtype=np.float32)
    outdata = np.zeros((frames, engine.config.channels), dtype=np.float32)
    engine._callback(indata, outdata, frames, None, None)
    return outdata


def test_mix_and_finish():
    cfg = EngineConfig(samplerate=48000, blocksize=0, channels=2, mic_passthrough=False)
    engine = AudioEngine(cfg)
    clip = Clip(name="c", data=np.full((5, 2), 0.5, dtype=np.float32))
    engine.play(clip, gain=1.0)
    assert engine.active_voices == 1

    out = _render(engine, 4)
    assert np.allclose(out[:4], 0.5)
    # One voice, 5 frames: still 1 frame left.
    assert engine.active_voices == 1

    out = _render(engine, 4)
    assert np.allclose(out[0], 0.5)      # last frame
    assert np.allclose(out[1:], 0.0)     # then silence
    assert engine.active_voices == 0     # voice retired


def test_mic_passthrough_and_clip():
    cfg = EngineConfig(channels=2, mic_passthrough=True, mic_gain=2.0, master_gain=1.0)
    engine = AudioEngine(cfg)
    frames = 8
    indata = np.full((frames, 2), 0.8, dtype=np.float32)
    outdata = np.zeros((frames, 2), dtype=np.float32)
    engine._callback(indata, outdata, frames, None, None)
    # 0.8 * mic_gain 2.0 = 1.6, clipped to 1.0.
    assert np.allclose(outdata, 1.0)


def test_loop_keeps_voice():
    cfg = EngineConfig(channels=1, mic_passthrough=False)
    engine = AudioEngine(cfg)
    clip = Clip(name="c", data=np.ones((3, 1), dtype=np.float32))
    engine.play(clip, loop=True)
    _render(engine, 10)
    assert engine.active_voices == 1  # loop never retires

    engine.stop_all()
    assert engine.active_voices == 0
