#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Decode liveshell_config.wav -> configString

Assumptions (based on observed encoder behavior):
- 16-bit PCM WAV (mono preferred; stereo will be downmixed)
- 1 bit = 32 samples
- 0/1 are represented by two distinct 32-sample waveforms (FSK-like)
- bytes are sent with UART-like framing: start=0, 8 data bits, stop=1
- a short preamble/postamble of many '1' bits exists around each frame
- CRC16 (likely XMODEM or CCITT-FALSE) is appended as last 2 bytes (MSB->LSB)

This decoder is robust-ish because it *learns* the two bit waveforms from the WAV itself
(using a simple 2-cluster k-means over 32-sample blocks).
"""

import sys
import wave
import numpy as np
from typing import List, Optional, Tuple


BIT_SAMPLES = 32


def read_wav_int16(path: str) -> Tuple[np.ndarray, int]:
    with wave.open(path, "rb") as wf:
        nch = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        rate = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    if sampwidth != 2:
        raise ValueError(f"Unsupported sample width: {sampwidth} bytes (expected 16-bit PCM)")

    data = np.frombuffer(raw, dtype="<i2").astype(np.float32)

    if nch == 2:
        # Downmix stereo to mono
        data = data.reshape(-1, 2).mean(axis=1)
    elif nch != 1:
        raise ValueError(f"Unsupported channels: {nch} (expected 1 or 2)")

    return data, rate


def normalize_blocks(x: np.ndarray) -> np.ndarray:
    # x: (N, 32)
    x = x - x.mean(axis=1, keepdims=True)
    norm = np.linalg.norm(x, axis=1, keepdims=True) + 1e-12
    return x / norm


def kmeans2(x: np.ndarray, iters: int = 30, seed: int = 0) -> Tuple[np.ndarray, np.ndarray]:
    """
    Very small 2-means:
      returns (centroids[2,32], labels[N])
    """
    rng = np.random.default_rng(seed)
    n = x.shape[0]
    # init: pick 2 random distinct samples
    idx = rng.choice(n, size=2, replace=False)
    c = x[idx].copy()  # (2,32)

    for _ in range(iters):
        # assign
        d0 = np.sum((x - c[0]) ** 2, axis=1)
        d1 = np.sum((x - c[1]) ** 2, axis=1)
        labels = (d1 < d0).astype(np.int32)

        # update
        new_c = c.copy()
        for k in (0, 1):
            m = x[labels == k]
            if len(m) > 0:
                new_c[k] = m.mean(axis=0)
        # convergence
        if np.allclose(new_c, c, atol=1e-6):
            c = new_c
            break
        c = new_c

    # final labels
    d0 = np.sum((x - c[0]) ** 2, axis=1)
    d1 = np.sum((x - c[1]) ** 2, axis=1)
    labels = (d1 < d0).astype(np.int32)

    return c, labels


def crc16_xmodem(data: bytes, poly: int = 0x1021, init: int = 0x0000) -> int:
    crc = init
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def crc16_ccitt_false(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    return crc16_xmodem(data, poly=poly, init=init)


def bits_to_bytes_uart(bits: List[int], start_pos: int, max_bytes: int = 20000) -> Tuple[bytes, int]:
    """
    Parse UART-framed bytes from bits starting at start_pos.
    Returns (payload_bytes, end_pos_bits).
    Stops when framing breaks or max_bytes reached.
    """
    out = bytearray()
    i = start_pos
    n = len(bits)

    while i + 10 <= n and len(out) < max_bytes:
        if bits[i] != 0:
            break  # expected start bit
        if i + 9 >= n:
            break
        # 8 data bits
        val = 0
        # NOTE: sender bit order could be MSB-first or LSB-first; we try both later.
        data_bits = bits[i + 1:i + 9]
        stop = bits[i + 9]
        if stop != 1:
            break

        # provisional: treat as MSB-first
        for b in data_bits:
            val = (val << 1) | (b & 1)

        out.append(val)
        i += 10

    return bytes(out), i


def try_bit_order_and_crc(payload: bytes) -> Optional[bytes]:
    """
    Payload includes ... + CRC(2 bytes MSB->LSB) at end.
    We don't know whether data bits were MSB-first or LSB-first inside each byte,
    so we try both interpretations and CRC variants.
    """
    if len(payload) < 3:
        return None

    def reverse_bits_in_byte(b: int) -> int:
        x = b
        r = 0
        for _ in range(8):
            r = (r << 1) | (x & 1)
            x >>= 1
        return r

    candidates = []

    # Candidate A: as-is
    candidates.append(payload)

    # Candidate B: bit-reversed per byte (UART might have been LSB-first)
    candidates.append(bytes(reverse_bits_in_byte(b) for b in payload))

    for cand in candidates:
        if len(cand) < 3:
            continue
        body, crc_bytes = cand[:-2], cand[-2:]
        want = (crc_bytes[0] << 8) | crc_bytes[1]

        for crc_fn in (crc16_xmodem, crc16_ccitt_false):
            got = crc_fn(body)
            if got == want:
                return body

    return None


def find_frames(bits: List[int]) -> List[int]:
    """
    Heuristic: find candidate start positions by looking for long runs of 1s (preamble),
    followed by a 0 (start bit) soon after.
    Returns list of candidate bit indices that likely point at a UART start bit.
    """
    starts = []
    n = len(bits)
    run = 0
    for i in range(n):
        if bits[i] == 1:
            run += 1
        else:
            # if we had a long run of 1s, and now we see 0, consider i as a start bit
            if run >= 8:  # tolerant (spec often ~12)
                starts.append(i)
            run = 0

    # de-duplicate nearby starts
    dedup = []
    last = -10**9
    for s in starts:
        if s - last > 50:  # separate frames
            dedup.append(s)
            last = s
    return dedup


def decode_config_string(wav_path: str) -> str:
    pcm, rate = read_wav_int16(wav_path)

    # chop into 32-sample blocks
    n_blocks = len(pcm) // BIT_SAMPLES
    if n_blocks < 200:
        raise ValueError("WAV too short to contain a valid frame")

    blocks = pcm[:n_blocks * BIT_SAMPLES].reshape(n_blocks, BIT_SAMPLES)
    blocks_n = normalize_blocks(blocks)

    # learn 2 waveforms by k-means
    centroids, labels = kmeans2(blocks_n, iters=40, seed=1)

    # Convert each block to a bit by nearest centroid (0/1 labels already do that).
    # But we don't know whether label==1 corresponds to logical '1'. We'll try both mappings.
    raw_bits = labels.tolist()  # 0/1 but unknown polarity

    def decode_with_polarity(flip: bool) -> Optional[str]:
        bits = [(1 - b) if flip else b for b in raw_bits]

        # find candidate frame starts
        starts = find_frames(bits)
        best_text = None
        best_len = -1

        for s in starts[:50]:  # cap
            payload, endpos = bits_to_bytes_uart(bits, s, max_bytes=10000)
            if len(payload) < 10:
                continue

            body = try_bit_order_and_crc(payload)
            if body is None:
                # maybe frame is longer; try extending by relaxing parse break:
                continue

            # decode UTF-8 (configString)
            try:
                text = body.decode("utf-8")
            except UnicodeDecodeError:
                text = body.decode("utf-8", errors="replace")

            # some frames include trailing NULs or extra whitespace
            text = text.replace("\r\n", "\n").strip("\x00")

            if len(text) > best_len:
                best_len = len(text)
                best_text = text

        return best_text

    # Try both bit polarities and take the better result (longer valid decoded text).
    t0 = decode_with_polarity(flip=False)
    t1 = decode_with_polarity(flip=True)

    if t0 is None and t1 is None:
        raise RuntimeError("Failed to decode: no CRC-valid frame found")

    if t0 is None:
        return t1
    if t1 is None:
        return t0
    return t0 if len(t0) >= len(t1) else t1


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} liveshell_config.wav", file=sys.stderr)
        sys.exit(2)

    wav_path = sys.argv[1]
    text = decode_config_string(wav_path)
    print(text)


if __name__ == "__main__":
    main()

