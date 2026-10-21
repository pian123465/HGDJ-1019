"""签名插件系统。

短剧平台的接口基本都需要带签名的 header,这个签名要单独逆向。
我们提供插件机制:你逆向出一个平台的签名后,塞到 plugins/signatures.py
里注册,SearchOrchestrator 会自动调用。

典型签名模式:
    sign = md5(path + sorted_query_params + secret + timestamp)
    X-Bogus = crc32_encrypt(body + ua + timestamp) + base64
"""
from __future__ import annotations

import hashlib
import hmac
import time
from abc import ABC, abstractmethod
from typing import Callable


class BaseSigner(ABC):
    """签名器基类。每个平台一个子类。"""

    name: str = "base"

    @abstractmethod
    def sign(self, method: str, url: str, params: dict, headers: dict) -> dict:
        """返回需要 merge 进请求 headers 的额外 header 字典。
        - method: HTTP 方法
        - url: 完整 URL 或 path
        - params: query params
        - headers: 已有的 headers(UA / Referer 等),你可以读取后追加
        """
        raise NotImplementedError


class SimpleMd5Signer(BaseSigner):
    """最常见的签名模式:md5(path + sorted_params + secret + ts)。"""

    name = "simple_md5"

    def __init__(self, secret: str, include_ts: bool = True):
        self.secret = secret
        self.include_ts = include_ts

    def sign(self, method: str, url: str, params: dict, headers: dict) -> dict:
        ts = int(time.time())
        # 排序后的 query 拼接
        q = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        path = url.split("?")[0]
        pieces = [path, q, self.secret]
        if self.include_ts:
            pieces.insert(2, str(ts))
        s = hashlib.md5("".join(pieces).encode()).hexdigest()
        return {"X-Sign": s, "X-Timestamp": str(ts)}


class HmacSha256Signer(BaseSigner):
    name = "hmac_sha256"

    def __init__(self, secret: str):
        self.secret = secret.encode()

    def sign(self, method: str, url: str, params: dict, headers: dict) -> dict:
        ts = str(int(time.time()))
        msg = f"{method.upper()}\n{url}\n{ts}".encode("utf-8")
        sig = hmac.new(self.secret, msg, hashlib.sha256).hexdigest()
        return {"X-Auth-Signature": sig, "X-Auth-Timestamp": ts}


# 全局签名器注册表
_REGISTRY: dict[str, BaseSigner] = {}


def register(signer: BaseSigner):
    """把签名器注册进全局表,搜索器自动按平台名调用。"""
    _REGISTRY[signer.name] = signer
    return signer


def get_signer(name: str) -> BaseSigner | None:
    return _REGISTRY.get(name)


def list_signers() -> list[str]:
    return list(_REGISTRY.keys())