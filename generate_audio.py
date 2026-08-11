"""使用 Python 标准库生成本项目的原创占位音效和背景音乐。"""
from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path
from typing import Callable

SAMPLE_RATE = 22050
AUDIO_DIR = Path(__file__).resolve().parents[1] / "assets" / "audio"


def clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def write_wav(name: str, duration: float, sample_fn: Callable[[float, int], float]) -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    sample_count = int(duration * SAMPLE_RATE)
    frames = bytearray()
    for index in range(sample_count):
        t = index / SAMPLE_RATE
        sample = int(clamp(sample_fn(t, index)) * 32767)
        frames.extend(struct.pack("<h", sample))

    with wave.open(str(AUDIO_DIR / name), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(frames)


def make_shoot() -> None:
    rng = random.Random(1042)

    def sample(t: float, _: int) -> float:
        noise = rng.uniform(-1.0, 1.0)
        crack = math.sin(2 * math.pi * (190 - 450 * t) * t)
        body = math.sin(2 * math.pi * 92 * t)
        envelope = math.exp(-24 * t)
        return (0.56 * noise + 0.31 * crack + 0.20 * body) * envelope

    write_wav("shoot.wav", 0.24, sample)


def make_hit() -> None:
    rng = random.Random(2207)

    def sample(t: float, _: int) -> float:
        noise = rng.uniform(-1.0, 1.0)
        thud = math.sin(2 * math.pi * (115 - 90 * t) * t)
        click = math.sin(2 * math.pi * 720 * t)
        return (0.55 * thud + 0.20 * noise + 0.10 * click) * math.exp(-17 * t)

    write_wav("hit.wav", 0.30, sample)


def make_pickup() -> None:
    def sample(t: float, _: int) -> float:
        frequency = 620 + 950 * t
        tone = math.sin(2 * math.pi * frequency * t)
        overtone = math.sin(2 * math.pi * frequency * 2 * t)
        envelope = min(1.0, t * 35) * math.exp(-5.0 * t)
        return (0.50 * tone + 0.18 * overtone) * envelope

    write_wav("pickup.wav", 0.48, sample)


def note_frequency(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def make_bgm() -> None:
    # 8 秒原创卡通循环：C-Am-F-G，每拍 0.5 秒。
    duration = 8.0
    chords = [
        (60, 64, 67),
        (57, 60, 64),
        (53, 57, 60),
        (55, 59, 62),
    ]
    melody = [72, 76, 79, 76, 69, 72, 76, 72, 65, 69, 72, 69, 67, 71, 74, 71]

    def sample(t: float, _: int) -> float:
        beat = 0.5
        beat_index = int(t / beat) % 16
        local = (t % beat) / beat
        chord = chords[(beat_index // 4) % len(chords)]

        pad = 0.0
        for midi in chord:
            freq = note_frequency(midi)
            pad += math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(2 * math.pi * freq * 2 * t)
        pad *= 0.055

        melody_freq = note_frequency(melody[beat_index])
        melody_env = min(1.0, local * 10.0) * math.exp(-2.4 * local)
        lead = (
            math.sin(2 * math.pi * melody_freq * t)
            + 0.20 * math.sin(2 * math.pi * melody_freq * 2 * t)
        ) * 0.17 * melody_env

        bass_freq = note_frequency(chord[0] - 24)
        bass_env = math.exp(-3.0 * local)
        bass = math.sin(2 * math.pi * bass_freq * t) * 0.15 * bass_env

        kick_phase = t % 1.0
        kick = math.sin(2 * math.pi * (72 - 38 * kick_phase) * t) * math.exp(-25 * kick_phase) * 0.14

        return pad + lead + bass + kick

    write_wav("cartoon_bgm.wav", duration, sample)


if __name__ == "__main__":
    make_shoot()
    make_hit()
    make_pickup()
    make_bgm()
    print(f"音频已生成到：{AUDIO_DIR}")
