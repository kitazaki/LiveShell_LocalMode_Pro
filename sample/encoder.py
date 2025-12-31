#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import wave
from pathlib import Path

# ===== 固定（32サンプル波形テンプレ：Proのオリジナルから実測）=====
# bit = 1（4サンプル周期 × 8）
BIT1 = [
     0,  3276,     0, -3276,
     0,  3276,     0, -3276,
     0,  3276,     0, -3276,
     0,  3276,     0, -3276,
     0,  3276,     0, -3276,
     0,  3276,     0, -3276,
     0,  3276,     0, -3276,
     0,  3276,     0, -3276,
]

# bit = 0（8サンプル周期 × 4）
BIT0 = [
     0,  2317,  3276,  2317,
     0, -2317, -3276, -2317,
     0,  2317,  3276,  2317,
     0, -2317, -3276, -2317,
     0,  2317,  3276,  2317,
     0, -2317, -3276, -2317,
     0,  2317,  3276,  2317,
     0, -2317, -3276, -2317,
]

BIT_SAMPLES = 32
PREAMBLE_ONES = 12
POSTAMBLE_ONES = 12
REPEAT = 3

DEVICE_SAMPLE_RATE = {
    "ls2": 16000,  # LiveShell2
    "pro": 44100,  # LiveShell Pro
    "lsx": 48000,  # LiveShell X
}

# ===== CRC16 XMODEM =====
def crc16_xmodem(data: bytes) -> int:
    crc = 0x0000
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def uart_bits(payload: bytes) -> list[int]:
    """UART framing: start=0, data=8bit MSB-first, stop=1"""
    bits: list[int] = []
    for b in payload:
        bits.append(0)  # start
        for i in range(7, -1, -1):  # MSB-first
            bits.append((b >> i) & 1)
        bits.append(1)  # stop
    return bits


def bits_to_pcm(bits: list[int], amp_scale: float) -> bytes:
    """
    Convert bitstream to PCM (int16 LE bytes).
    amp_scale: 0.0-1.0. 1.0 keeps original template amplitude.
    """
    if not (0.0 < amp_scale <= 1.0):
        raise ValueError("amp_scale must be in (0.0, 1.0].")

    # scale templates (keep integers)
    def scale(arr):
        out = []
        for v in arr:
            sv = int(round(v * amp_scale))
            if sv > 32767: sv = 32767
            if sv < -32768: sv = -32768
            out.append(sv)
        return out

    b0 = scale(BIT0)
    b1 = scale(BIT1)

    # build bytearray directly (faster & simpler)
    out = bytearray()
    for b in bits:
        tmpl = b1 if b else b0
        for s in tmpl:
            out += int(s).to_bytes(2, "little", signed=True)
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config_txt", help="UTF-8 text file containing configString")
    ap.add_argument("-o", "--out", default="liveshell_config.wav", help="Output wav file path")
    ap.add_argument("--device", choices=["ls2", "pro", "lsx"], default="pro", help="Target model")
    ap.add_argument("--sample-rate", type=int, default=0, help="Override sample rate (0 = device default)")
    ap.add_argument("--amp", type=float, default=1.0, help="Amplitude scale (0.0-1.0], default 1.0")
    args = ap.parse_args()

    sr = args.sample_rate if args.sample_rate > 0 else DEVICE_SAMPLE_RATE[args.device]

    text = Path(args.config_txt).read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"

    payload = text.encode("utf-8")
    crc = crc16_xmodem(payload)
    payload += bytes([(crc >> 8) & 0xFF, crc & 0xFF])  # MSB->LSB

    bits = [1] * PREAMBLE_ONES
    bits += uart_bits(payload)
    bits += [1] * POSTAMBLE_ONES
    bits *= REPEAT

    pcm_bytes = bits_to_pcm(bits, amp_scale=args.amp)

    with wave.open(args.out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm_bytes)

    print("OK:", args.out)
    print(" device:", args.device, "sample_rate:", sr)
    print(" payload_bytes:", len(payload), "(includes CRC2)")
    print(" total_bits:", len(bits), "total_samples:", len(bits) * BIT_SAMPLES)


if __name__ == "__main__":
    main()

