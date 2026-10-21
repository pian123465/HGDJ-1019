# -*- coding: utf-8 -*-
"""红果内核移植自测脚本。

验证内容:
  1. av_base64_decode(FFmpeg 风格,容错尾部)
  2. derive_key(spade_a -> AES Key):用逆算法构造合法 spade_a,再正向解出 key
  3. decrypt_sample(CENC-AES-CTR 密钥流)
  4. 合成 CENC MP4 全流程解密 + moov 重建
  5. 官网 HTML 卡片提取(_extract_cards)
  6. 纯函数(URL 归一化 / JSON 字段提取 / 选流)与模块导入

运行:
    python -X utf8 test_hongguo_port.py
"""
from __future__ import annotations

import base64
import json
import struct
import sys

# 让脚本可以从仓库根直接跑
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shortdrama.core.hongguo_crypto import (  # noqa: E402
    aes128_ecb_encrypt,
    av_base64_decode,
    decrypt_mp4_buffer,
    decrypt_sample,
    derive_key,
)
from shortdrama.core.hongguo_client import (  # noqa: E402
    normalize_video_url,
    parse_model_video,
    pick_json_string,
    resolve_series_id,
)
from shortdrama.platforms.hongguo import _extract_cards  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


# ====================================================================
# 1. av_base64_decode
# ====================================================================
def test_av_b64():
    print("[1] av_base64_decode")
    check("foobar", av_base64_decode("Zm9vYmFy") == b"foobar")
    check("empty", av_base64_decode("") == b"")
    # "Zm9vYg==" -> '=' 触发尾部 partial:2 字符 -> 1 字节 'b'
    check("partial-pad", av_base64_decode("Zm9vYg==") == b"foob")
    # 标准 37 字节 base64(带 ==),与 FFmpeg 行为一致
    raw = bytes(range(37))
    check("37bytes", av_base64_decode(base64.b64encode(raw).decode()) == raw)


# ====================================================================
# 2. derive_key(逆算法构造合法 spade_a)
# ====================================================================
def _make_spade_a(key_hex: str) -> str:
    """按 derive_key 的约束逆推一个合法 spade_a:
    plain x21 = '0'(hval 标记) + 32 位 key_hex;对去混淆循环做逆变换编码。"""
    plain = bytearray(b"0" + key_hex.encode())
    w22 = len(plain)  # 33
    encoded = bytearray(len(plain))
    w11, w12, w10 = 0x55, 0xFA, 0xEB
    for i, p in enumerate(plain):
        pc = bin(i).count("1")
        w14 = w12 if (i & 1) == 0 else w11
        w13 = w14 ^ ((p - (w10 - pc)) & 0xFF)
        if (i & 1) == 1:
            w11 = w13
        else:
            w12 = w13
        encoded[i] = w13
    key0 = 0x33  # x27 = 3 >= 2;w22 = L - key0 + 0x2f = 33
    b1, b2 = encoded[0], encoded[1]
    buf = bytes([key0 ^ b1 ^ b2]) + bytes(encoded) + b"\x00\x01\x02"
    return base64.b64encode(buf).decode()


def test_derive_key():
    print("[2] derive_key")
    key_hex = "00112233445566778899aabbccddeeff"
    spade = _make_spade_a(key_hex)
    key = derive_key(spade)
    check("roundtrip", key is not None and key.hex() == key_hex, f"got {key.hex() if key else None}")
    check("empty->None", derive_key("") is None)
    check("short->None", derive_key("aGVsbG8=") is None)  # 长度 < 3
    check("bad-hex-marker->None", derive_key(base64.b64encode(b"\x33" * 40).decode()) is None)


# ====================================================================
# 3. decrypt_sample(CENC-AES-CTR)
# ====================================================================
def test_decrypt_sample():
    print("[3] decrypt_sample")
    key = bytes(range(16))
    nonce = bytes.fromhex("0102030405060708")
    # 密钥流块0 = AES-ECB(key, nonce || BE64(0))
    ks0 = aes128_ecb_encrypt(key, nonce + struct.pack(">Q", 0))
    check("ks-block0", decrypt_sample(key, nonce, ks0) == b"\x00" * 16)
    # 非 16 倍数长度
    cipher = bytes(range(1, 30))
    plain = decrypt_sample(key, nonce, cipher)
    check("len", len(plain) == len(cipher))
    check("involution", decrypt_sample(key, nonce, plain) == cipher)
    check("empty", decrypt_sample(key, nonce, b"") == b"")


# ====================================================================
# 4. 合成 CENC MP4 全流程
# ====================================================================
def _box(typ: str, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + typ.encode("latin1") + payload


def _fullbox(typ: str, flags: int, payload: bytes) -> bytes:
    return _box(typ, struct.pack(">I", flags) + payload)


def _make_cenc_mp4(key: bytes, samples: list[bytes], nonces: list[bytes]) -> bytes:
    """构造一个最小但结构完整的 CENC 加密 MP4:
    ftyp + moov(trak>mdia>minf>stbl: stsd(encv+sinf)/stsz/stco/stsc/senc) + mdat。
    mdat 里放的是用同一个 CENC-CTR 逻辑加密后的 sample 密文。
    """
    ciphers = [decrypt_sample(key, n, s) for n, s in zip(nonces, samples)]  # XOR 自逆

    # --- stsd:encv + sinf ---
    encv_payload = bytes(78)
    sinf = _box("sinf", b"FRMAdummy") + _box("schm", b"\x00\x00\x00\x00cec1")
    encv_entry = struct.pack(">I", 8 + 78 + len(sinf)) + b"encv" + encv_payload + sinf
    stsd = _fullbox("stsd", 0, struct.pack(">I", 1) + encv_entry)

    # --- stsz / stsc / senc(先占位,stco 需要最终 moov 长度算偏移)---
    stsz = _fullbox("stsz", 0, struct.pack(">II", 0, len(samples)) + b"".join(struct.pack(">I", len(s)) for s in samples))
    # stsc 全 box:version/flags + entry_count + 3*entry(first_chunk, samples_per_chunk, sample_description_index)
    stsc = _fullbox("stsc", 0, struct.pack(">I", 1) + struct.pack(">III", 1, len(samples), 1))
    senc = _fullbox("senc", 0, struct.pack(">I", len(nonces)) + b"".join(nonces))

    ftyp = _box("ftyp", b"isom\x00\x00\x00\x00isom")
    stbl_no_stco = stsd + stsz + stsc + senc
    # 先用 stco=0 占位算 moov 长度,再回填真实 mdat 偏移
    stco0 = _fullbox("stco", 0, struct.pack(">I", 1) + struct.pack(">I", 0))
    moov0 = _box("moov", _box("trak", _box("mdia", _box("minf", _box("stbl", stbl_no_stco + stco0)))))
    mdat_data_off = len(ftyp) + len(moov0) + 8
    stco = _fullbox("stco", 0, struct.pack(">I", 1) + struct.pack(">I", mdat_data_off))
    moov = _box("moov", _box("trak", _box("mdia", _box("minf", _box("stbl", stbl_no_stco + stco)))))

    mdat_payload = b"".join(ciphers)
    mdat = _box("mdat", mdat_payload)
    return ftyp + moov + mdat


def test_cenc_mp4():
    print("[4] 合成 CENC MP4 全流程")
    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    samples = [bytes(range(16)), bytes(range(30)), b"\xaa" * 48]  # 含非 16 倍数
    nonces = [struct.pack(">Q", i) for i in range(1, 4)]  # 8 字节 nonce
    cenc = _make_cenc_mp4(key, samples, nonces)

    out = decrypt_mp4_buffer(cenc, key)
    # 1) mdat 明文应等于原始 samples 拼接
    orig = b"".join(samples)
    # 找输出里的 mdat(最后一个 box)
    mdat_off = out.rindex(b"mdat")
    mdat_len = struct.unpack_from(">I", out, mdat_off - 4)[0]
    payload = out[mdat_off + 4:mdat_off - 4 + mdat_len]
    check("mdat-decrypted", payload == orig, f"len {len(payload)} vs {len(orig)}")
    # 2) 输出里不应再有 senc / encv
    check("no-senc", b"senc" not in out)
    check("no-encv", b"encv" not in out)
    check("has-hvc1", b"hvc1" in out)
    # 3) 顶层 box 完整(ftyp 8+12 / moov / mdat)
    check("top-boxes", out[:4] == struct.pack(">I", 20) and out[4:8] == b"ftyp")


# ====================================================================
# 5. 官网 HTML 卡片提取
# ====================================================================
def test_extract_cards():
    print("[5] _extract_cards")
    html = """
    <div class="list">
      <a href="/detail?series_id=123456789">
        <picture><source srcset="https://cdn.example/cover1.jpg 2x"></picture>
        <img alt="龙王驾到" src="https://cdn.example/thumb1.jpg">
        <span class="episode-tag">全86集</span>
        <span class="tag-text">逆袭</span><span class="tag-text">战神</span>
      </a>
      <a href="/detail?series_id=987654321">
        <img alt="都市神医" data-src="https://cdn.example/cover2.jpg">
        <span class="episode-count">全120集</span>
      </a>
      <a href="/other">no-id</a>
    </div>
    """
    cards = _extract_cards(html)
    check("count==2", len(cards) == 2, f"{len(cards)}")
    if cards:
        c = cards[0]
        check("id", c.drama_id == "123456789")
        check("title-from-alt", c.title == "龙王驾到", c.title)
        check("cover-from-picture", c.cover == "https://cdn.example/cover1.jpg", c.cover)
        check("episode-count", c.episode_count == 86)
        check("tags", c.tags == ["逆袭", "战神"], str(c.tags))
        check("platform", c.platform == "红果短剧")
        c2 = cards[1]
        check("cover-data-src", c2.cover == "https://cdn.example/cover2.jpg", c2.cover)
        check("count2", c2.episode_count == 120)


# ====================================================================
# 6. 纯函数
# ====================================================================
def test_helpers():
    print("[6] 纯函数")
    check("normalize-url",
          normalize_video_url("https://cdn/a.mp4\\u002Fb?Range=bytes=0-1&x=1&amp;y=2") ==
          "https://cdn/a.mp4/b?&x=1&y=2"  # 与原 JS 一致:Range 剥离后保留空分隔符(CDN 容忍)
          )
    # 与原 JS 一致:pickJsonString 只解 \u002F 与 \u0026,其它 \uXXXX 保持原样
    check("pick-json", pick_json_string('{"series_name":"\\u9f99\\u738b","x":1}', "series_name") == "\\u9f99\\u738b")
    vm = json.dumps({
        "video_list": [
            {"main_url": "https://low", "video_meta": {"definition": "360p", "vwidth": "640", "vheight": "360", "bitrate": "300"}, "encrypt_info": {"spade_a": "S1"}},
            {"main_url": "https://high", "video_meta": {"definition": "1080p", "vwidth": "1920", "vheight": "1080", "bitrate": "2000"}, "encrypt_info": {"spade_a": "S2"}},
        ]
    })
    url, spade, codec = parse_model_video(vm)
    check("best-stream", url == "https://high" and spade == "S2", f"{url} {spade}")
    check("model-not-string", parse_model_video(123) == (None, None, None))

    import asyncio
    sid = asyncio.run(resolve_series_id("123456789"))
    check("numeric-series-id", sid == "123456789")

    # 模块导入(打包 hiddenimports 兜底)
    import shortdrama.core.hongguo_client  # noqa: F401
    import shortdrama.core.hongguo_crypto  # noqa: F401
    import shortdrama.platforms.hongguo    # noqa: F401
    check("imports", True)


if __name__ == "__main__":
    test_av_b64()
    test_derive_key()
    test_decrypt_sample()
    test_cenc_mp4()
    test_extract_cards()
    test_helpers()
    print(f"\n结果:{PASS} 通过,{FAIL} 失败")
    sys.exit(1 if FAIL else 0)
