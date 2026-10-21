# -*- coding: utf-8 -*-
"""红果短剧 CENC-AES-CTR 解密模块 —— 从 hongguo-downloader (GPL-3.0) 移植。

移植来源:hongguo-downloader 1.1.0 的 src/native/hongguo.js
    https://github.com/hongguo-downloader (GPL-3.0)
本文件保持与 JS 实现一一对应的移植关系(含 avBase64 / key 派生 / MP4 Box 重建),
逻辑照抄,仅做语言适配;命名尽量保留原意,方便与原项目对照。

功能:
    1. av_base64_decode   —— FFmpeg 风格 Base64(容忍尾部队块)
    2. derive_key         —— spade_a -> 16 字节 AES-128 Key
    3. decrypt_sample     —— CENC AES-CTR 单 sample 解密(8 字节 nonce + 8 字节计数器)
    4. decrypt_mp4_buffer —— 整段 CENC MP4 解密 + moov 重建(去保护)
    5. decrypt_mp4_file   —— 文件版

GPL-3.0 说明:本文件基于 GPL-3.0 开源项目移植,分发/修改时须保留 GPL-3.0 协议声明。
"""
from __future__ import annotations

import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# ====================================================================
# 1. FFmpeg 兼容 Base64 解码
# ====================================================================
_B64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_B64_TABLE = {c: i for i, c in enumerate(_B64_CHARS)}


def av_base64_decode(s: str) -> bytes:
    """FFmpeg av_base64_decode 的等价实现。

    与标准 Base64 的区别:
      - 遇到非 base64 字符(如 '='、换行)时不是报错,而是把当前 4 字符组
        里已收集到的字符解码成部分字节后立即停止;
      - 不要求长度是 4 的倍数。
    原 JS 写法:
      while (i + 4 <= s.length) { ... 4 个字符一组,非表内字符则 partial 解码后 break }
    """
    dst = bytearray()
    i, n = 0, len(s)
    while i + 4 <= n:
        vals: list[int] = []
        ok = True
        for j in range(4):
            v = _B64_TABLE.get(s[i + j])
            if v is None:
                ok = False
                break
            vals.append(v)
        if not ok:
            # 尾部队块:3 个字符 -> 2 字节;2 个字符 -> 1 字节;更少则丢弃
            v = 0
            for vv in vals:
                v = (v << 6) | vv
            if len(vals) == 3:
                dst.append((v >> 10) & 0xFF)
                dst.append((v >> 2) & 0xFF)
            elif len(vals) == 2:
                dst.append((v >> 4) & 0xFF)
            break
        v = (vals[0] << 18) | (vals[1] << 12) | (vals[2] << 6) | vals[3]
        dst.append((v >> 16) & 0xFF)
        dst.append((v >> 8) & 0xFF)
        dst.append(v & 0xFF)
        i += 4
    return bytes(dst)


# ====================================================================
# 2. spade_a -> AES-128 Key 派生
# ====================================================================
def derive_key(spade_a: str | None) -> bytes | None:
    """从播放接口返回的 spade_a(obfuscated key blob)派生 16 字节 AES Key。

    算法(与 JS 逐行一致):
      a. spade_a 是 Base64;解码得到 buf。
      b. key0 = buf[0]^buf[1]^buf[2] —— 第 1 个字节由前 3 字节异或得出,
         用来算两个长度字段:
            x27 = key0 - 0x30   (校验/下限)
            w22 = len(buf) - key0 + 0x2f   (key blob 的长度)
      c. 取 buf[1 : 1+w22) 为 x21,做「滚动去混淆」:
         用两个交替寄存器 w11=0x55 / w12=0xfa 轮流异或,再减去
         popcount(i)(当前下标的置位数)与 0xeb 的偏移,得到明文 blob。
         之所以要这样写:key 不直接放在包里,而是藏在混淆后的 blob 里,
         防止被静态抓包/搜字符串直接拿走。
      d. 去混淆后的 x21[0] 必须是一个十六进制字符,由它推出 hval,
         w9 = w22 - hval 就是真正 key 十六进制串的长度(含结束)。
      e. key_hex = x21[1 : 1+w9-1],恰好 32 个字符 = 16 字节 AES-128 Key。

    返回 16 字节 key;任何一步不满足约定则返回 None(调用方报错)。
    """
    if not spade_a:
        return None
    buf = av_base64_decode(spade_a)
    L = len(buf)
    if L < 3:
        return None

    key0 = buf[0] ^ buf[1] ^ buf[2]
    x27 = key0 - 0x30
    w22 = L - key0 + 0x2f
    if x27 < 2 or w22 < 2 or w22 > L - 1:
        return None

    x21 = bytearray(buf[1:1 + w22])
    w11, w12, w10 = 0x55, 0xfa, 0xeb
    for i in range(len(x21)):
        w13 = x21[i]
        pc = bin(i).count("1")  # popcount:原 JS i.toString(2).split('1').length - 1
        w14 = w12 if (i & 1) == 0 else w11
        if (i & 1) == 1:
            w11 = w13
        else:
            w12 = w13
        w13_xor = w14 ^ x21[i]
        w14_sub = w10 - pc
        x21[i] = (w14_sub + w13_xor) & 0xFF

    c0 = x21[0]
    if 0x30 <= c0 <= 0x39:
        hval = c0 - 0x30
    elif 0x61 <= c0 <= 0x7A:
        hval = c0 - 0x57
    else:
        return None

    w9 = w22 - hval
    if w9 < 2:
        return None

    str_a = bytes(x21[1:1 + w9 - 1]).decode("ascii", errors="replace")
    if len(str_a) != 32:
        return None
    try:
        return bytes.fromhex(str_a)
    except ValueError:
        return None


# ====================================================================
# 3. AES-128-ECB(用于生成 CTR 密钥流)
# ====================================================================
def aes128_ecb_encrypt(key: bytes, data: bytes) -> bytes:
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return enc.update(data) + enc.finalize()


def decrypt_sample(key: bytes, nonce: bytes, cipher: bytes) -> bytes:
    """CENC AES-CTR 单 sample 解密。

    CENC 的 AES-CTR 模式:
        密钥流块 k = AES-128-ECB(key, nonce[0:8] || big-endian-64(k))
        plain = ciphertext XOR 密钥流
    nonce 是 senc box 里每个 sample 的 8 字节 IV(加密时由 8 字节 nonce +
    8 字节计数器组成 16 字节 counter block,计数器从 0 开始)。
    """
    if not cipher:
        return b""
    n = len(cipher)
    nblocks = (n + 15) // 16
    # 归一化 nonce 到 8 字节(原 JS 用 Buffer.write 写 8 字节,不足补零;
    # Python bytearray 切片赋值会改变长度,必须先定长)
    nonce8 = (nonce[:8] + b"\x00" * 8)[:8]
    full = bytearray(nblocks * 16)
    for k in range(nblocks):
        full[k * 16:k * 16 + 8] = nonce8
        full[k * 16 + 8:k * 16 + 16] = struct.pack(">Q", k)
    ks = aes128_ecb_encrypt(key, bytes(full))
    # 大整数异或(等价逐字节 XOR,速度更快);ci 只有 n 字节,异或结果要截断到 n 字节
    ci = int.from_bytes(cipher, "big")
    ki = int.from_bytes(ks, "big")
    mask = (1 << (8 * n)) - 1
    return ((ci ^ ki) & mask).to_bytes(n, "big")


# ====================================================================
# 4. MP4 Box 结构解析 / 重建
# ====================================================================
_CONTAINER_TYPES = {"moov", "trak", "mdia", "minf", "stbl", "edts", "dinf", "udta", "meta"}


def parse_boxes(data, start: int, end: int) -> list[dict]:
    """递归解析 MP4 box 树。

    返回 [{typ, off, size, hdr, children}]:
      - size==1 表示 64 位扩展长度;size==0 表示一直延伸到 end
      - 容器型 box(moov/trak/...)递归解析 children
    """
    boxes: list[dict] = []
    off = start
    while off + 8 <= end:
        size = struct.unpack_from(">I", data, off)[0]
        typ = bytes(data[off + 4:off + 8]).decode("latin1")
        hdr = 8
        if size == 1:
            size = struct.unpack_from(">Q", data, off + 8)[0]
            hdr = 16
        elif size == 0:
            size = end - off
        if size < hdr or off + size > end:
            break
        children = None
        if typ in _CONTAINER_TYPES:
            children = parse_boxes(data, off + hdr, off + size)
        boxes.append({"typ": typ, "off": off, "size": size, "hdr": hdr, "children": children})
        off += size
    return boxes


def rebuild_moov(data: bytearray, moov_off: int, moov_size: int, top: list[dict]) -> bytes:
    """重建 moov box(解密后去保护)。

    加密 MP4 的 moov 里带保护信息:
      - senc / saio / saiz / sgpd / sbgp:加密元数据 -> 必须删掉
      - stsd 里的 sample entry 类型是 encv / enca(带 sinf 子 box)
        -> 改回 hvc1 / mp4a,并丢弃 sinf
    重建后 moov 变小,mdat 里 chunk 的偏移(stco)要整体前移 delta。
    """
    moov_box = next((b for b in top if b["typ"] == "moov"), None)
    if moov_box is None:
        raise ValueError("no moov box")

    def clone(box: dict) -> dict:
        return {
            "typ": box["typ"], "off": box["off"], "size": box["size"], "hdr": box["hdr"],
            "children": [clone(c) for c in box["children"]] if box["children"] is not None else None,
        }

    def prune(box: dict) -> dict:
        if box["children"] is None:
            return box
        keep = [prune(c) for c in box["children"] if c["typ"] not in ("senc", "saio", "saiz", "sgpd", "sbgp")]
        box["children"] = keep
        return box

    tree = prune(clone(moov_box))

    def walk_children(box: dict):
        for c in (box["children"] or []):
            yield c
            yield from walk_children(c)

    # ---- 1) 重写 stsd:encv -> hvc1 / enca -> mp4a,去 sinf ----
    patches: dict[int, bytes] = {}
    for b in walk_children(tree):
        if b["typ"] != "stsd":
            continue
        content = b["off"] + 8
        count = struct.unpack_from(">I", data, content + 4)[0]
        p = content + 8
        entries: list[bytes] = []
        for _ in range(count):
            esize = struct.unpack_from(">I", data, p)[0]
            etyp = bytes(data[p + 4:p + 8]).decode("latin1")
            if etyp in ("encv", "enca"):
                new_type = "hvc1" if etyp == "encv" else "mp4a"
                hdr_size = 78 if etyp == "encv" else 28
                entry = bytearray(8 + hdr_size)
                entry[4:8] = new_type.encode("latin1")
                entry[8:8 + hdr_size] = data[p + 8:p + 8 + hdr_size]
                extra = bytearray()
                q = p + 8 + hdr_size
                while q + 8 <= p + esize:
                    s2 = struct.unpack_from(">I", data, q)[0]
                    t2 = bytes(data[q + 4:q + 8]).decode("latin1")
                    if s2 == 1:
                        s2 = struct.unpack_from(">Q", data, q + 8)[0]
                    elif s2 == 0:
                        s2 = p + esize - q
                    if t2 != "sinf":
                        extra += data[q:q + s2]
                    q += s2
                full_entry = bytes(entry) + bytes(extra)
                full_entry = struct.pack(">I", len(full_entry)) + full_entry[4:]
                entries.append(full_entry)
            else:
                entries.append(bytes(data[p:p + esize]))
            p += esize
        stsd_hdr = bytearray(16)
        stsd_hdr[0:12] = data[b["off"]:content + 8]
        struct.pack_into(">I", stsd_hdr, 12, len(entries))
        full_stsd = bytes(stsd_hdr) + b"".join(entries)
        full_stsd = struct.pack(">I", len(full_stsd)) + full_stsd[4:]
        patches[b["off"]] = full_stsd

    # ---- 2) 序列化树 ----
    def serialize(box: dict) -> bytes:
        if box["children"] is None:
            return patches.get(box["off"]) or bytes(data[box["off"]:box["off"] + box["size"]])
        body = b"".join(serialize(c) for c in box["children"])
        hdrb = bytearray(box["hdr"])
        hdrb[0:box["hdr"]] = data[box["off"]:box["off"] + box["hdr"]]
        if box["hdr"] == 8:
            struct.pack_into(">I", hdrb, 0, 8 + len(body))
        else:
            struct.pack_into(">I", hdrb, 0, 1)
            struct.pack_into(">Q", hdrb, 8, 16 + len(body))
        return bytes(hdrb) + body

    first = serialize(tree)
    delta = moov_size - len(first)

    # ---- 3) stco(chunk offset)整体减去 delta(moov 变小了)----
    for b in walk_children(tree):
        if b["typ"] != "stco":
            continue
        nc = struct.unpack_from(">I", data, b["off"] + 12)[0]
        for i in range(nc):
            v = struct.unpack_from(">I", data, b["off"] + 16 + i * 4)[0]
            if v >= delta:
                struct.pack_into(">I", data, b["off"] + 16 + i * 4, v - delta)

    return serialize(tree)


def decrypt_mp4_buffer(data: bytes, key: bytes) -> bytes:
    """解密整段 CENC-AES-CTR 加密的 MP4,返回可播放的明文 MP4。

    步骤:
      1. 解析 box 树,找到 moov
      2. 对每个 track(stbl):
           - stsz:sample 大小;stco:chunk 偏移;stsc:samples-per-chunk
           - senc:每个 sample 的 8 字节 nonce(IV)
           - 由 chunk 偏移 + sample 大小推算出每个 sample 的文件偏移,逐个解密
      3. 重建 moov(去保护:删 senc/saio/saiz/sgpd/sbgp,encv->hvc1,去 sinf,
         stco 偏移调整)
      4. 按顶层 box 重新拼装(moov 用重建版,其余原样)
    注意:本函数会就地修改传入 data(调用方应独占)。
    """
    buf = bytearray(data)
    total = len(buf)
    top = parse_boxes(buf, 0, total)
    moov = next((b for b in top if b["typ"] == "moov"), None)
    if moov is None:
        raise ValueError("no moov box found in MP4")

    def get_box(boxes, typ):
        return next((b for b in (boxes or []) if b["typ"] == typ), None)

    def walk_boxes(boxes):
        for b in boxes:
            if b["children"]:
                yield from walk_boxes(b["children"])
            yield b

    stbls = [b for b in walk_boxes(top) if b["typ"] == "stbl"]
    track_info = []
    for stbl in stbls:
        stsz = get_box(stbl["children"], "stsz")
        stco = get_box(stbl["children"], "stco")
        stsc = get_box(stbl["children"], "stsc")
        senc = get_box(stbl["children"], "senc")
        if not stsz or not stco or not stsc:
            continue

        ss = struct.unpack_from(">I", buf, stsz["off"] + 12)[0]
        n = struct.unpack_from(">I", buf, stsz["off"] + 16)[0]
        if ss == 0:
            sizes = [struct.unpack_from(">I", buf, stsz["off"] + 20 + i * 4)[0] for i in range(n)]
        else:
            sizes = [ss] * n

        nc = struct.unpack_from(">I", buf, stco["off"] + 12)[0]
        chunk_offs = [struct.unpack_from(">I", buf, stco["off"] + 16 + i * 4)[0] for i in range(nc)]

        ns = struct.unpack_from(">I", buf, stsc["off"] + 12)[0]
        stsc_tab = []
        for i in range(ns):
            stsc_tab.append(tuple(struct.unpack_from(">III", buf, stsc["off"] + 16 + i * 12)))

        ivs: list[bytes] = []
        if senc:
            sc = struct.unpack_from(">I", buf, senc["off"] + 12)[0]
            for i in range(sc):
                ivs.append(bytes(buf[senc["off"] + 16 + i * 8:senc["off"] + 24 + i * 8]))

        # samples-per-chunk:由 stsc 分段表推出每个 chunk 的 sample 数
        chunk_spc: dict[int, int] = {}
        for i in range(len(stsc_tab)):
            fc = stsc_tab[i][0]
            spc = stsc_tab[i][1]
            nxt = stsc_tab[i + 1][0] if i + 1 < len(stsc_tab) else nc + 1
            for ci in range(fc - 1, nxt - 1):
                chunk_spc[ci] = spc

        # 逐 sample 的文件偏移
        sample_offs: list[int] = []
        si = 0
        for ci in range(nc):
            off = chunk_offs[ci]
            spc = chunk_spc.get(ci, 1)
            for _ in range(spc):
                if si >= n:
                    break
                sample_offs.append(off)
                off += sizes[si]
                si += 1

        track_info.append({"sizes": sizes, "offs": sample_offs, "ivs": ivs})

    # ---- 解密每个 sample ----
    for ti in track_info:
        for i, off in enumerate(ti["offs"]):
            sz = ti["sizes"][i]
            if off + sz > total:
                continue
            if i < len(ti["ivs"]):
                nonce = ti["ivs"][i][0:8]
                plain = decrypt_sample(key, nonce, bytes(buf[off:off + sz]))
                buf[off:off + sz] = plain

    # ---- 重建 moov 并拼装 ----
    new_moov = rebuild_moov(buf, moov["off"], moov["size"], top)
    out: list[bytes] = []
    off = 0
    while off < total:
        size = struct.unpack_from(">I", buf, off)[0]
        typ = bytes(buf[off + 4:off + 8]).decode("latin1")
        if size == 1:
            size = struct.unpack_from(">Q", buf, off + 8)[0]
        elif size == 0:
            size = total - off
        if typ == "moov":
            out.append(new_moov)
        else:
            out.append(bytes(buf[off:off + size]))
        off += size
    return b"".join(out)


def decrypt_mp4_file(src_path: str, dst_path: str, key: bytes) -> None:
    """解密 MP4 文件并保存(与原 JS decryptMp4File 一致)。"""
    with open(src_path, "rb") as f:
        data = f.read()
    final_buf = decrypt_mp4_buffer(data, key)
    with open(dst_path, "wb") as f:
        f.write(final_buf)
