# -*- coding: utf-8 -*-
"""红果短剧协议客户端 —— 从 hongguo-downloader (GPL-3.0) 移植。

移植来源:hongguo-downloader 1.1.0 的 src/native/hongguo.js(API / 官网数据源部分),
保持函数与逻辑一一对应。为什么这么设计(原项目注释保留):

  1. 双数据源兜底:
     - 官方 App 接口(api5-normal-sinfonlineb.fqnovel.com):返回完整分集 +
       播放直链 + spade_a(加密 key)。这套接口带固定的设备指纹参数
       (device_id / iid / aid ...)即可访问,无需签名。
     - 官网网页版(hongguoduanju.com):player 页是服务端渲染,分集 vid 列表
       与可下载的 MP4 直链都内嵌在 HTML 里,无需任何签名。官方接口不可用时
       自动降级到这里(明文 MP4,无需解密)。
  2. 容错:apiCall 对「HTTP 非 200 / 空响应 / 非 JSON」都做了带 logid 的
     可诊断报错,并带指数退避重试,避免被网关限流一次打挂。
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from urllib.parse import quote

import aiohttp
from loguru import logger

API = "https://api5-normal-sinfonlineb.fqnovel.com"
HONGGUO_UA = "com.phoenix.read/71532 (Linux; U; Android 9; SM-N9860; Build/PQ3A.190705.10241111;tt-ok/3.12.13.20)"
VIDEO_REFERER = "https://novelquickapp.com/"

# ===== 官网网页版数据源 =====
SITE_ORIGIN = "https://hongguoduanju.com"
WEB_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
WEB_REFERER = SITE_ORIGIN + "/"

# 官方 App 接口的固定公共参数(设备指纹 + App 版本信息)
COMMON_QUERY = {
    "klink_egdi": "AAI29o4dI-eMiO73_SRSbZ_0By1v3fUSriNeu8-L951MoXhWT88pzj5B",
    "iid": "3788260546453235",
    "device_id": "538083340353620",
    "ac": "wifi",
    "channel": "oppo_8662_64",
    "aid": "8662",
    "app_name": "novelread",
    "version_code": "71532",
    "version_name": "7.1.5.32",
    "device_platform": "android",
    "os": "android",
    "ssmix": "a",
    "device_type": "SM-N9860",
    "device_brand": "Samsung",
    "language": "zh",
    "os_api": "28",
    "os_version": "9",
    "manifest_version_code": "71532",
    "resolution": "900*1600",
    "dpi": "320",
    "update_version_code": "71532",
    "host_abi": "arm64-v8a",
    "dragon_device_type": "pad",
    "pv_player": "71532",
    "compliance_status": "0",
    "need_personal_recommend": "1",
    "player_so_load": "1",
    "is_android_pad_screen": "0",
    "rom_version": "PQ3A.190705.10241111+release-keys",
    "cdid": "b4f93387-5319-4134-aab9-2cd4e9279b8f",
}

HEADERS = {
    "User-Agent": HONGGUO_UA,
    "Accept-Encoding": "gzip",
    "Accept": "application/json; charset=utf-8,application/x-protobuf",
    "Content-Type": "application/json; charset=utf-8",
    "Host": "api5-normal-sinfonlineb.fqnovel.com",
}

DETAIL_BIZ_PARAM = {
    "detail_page_version": 0,
    "disable_digg_stat": False,
    "image_shrink_datas_str": (
        "W3siaW1hZ2VfdHlwZSI6MywiaW1hZ2Vfd2lkdGgiOjkwMCwic2hyaW5rX3R5cGUiOjN9LHsiaW1hZ2VfdHlwZSI6NCwiaW1hZ2Vfd2lkdGgiOjcyLCJzaHJpbmtfdHlwZSI6NH1d\n"
    ),
    "need_all_video_definition": False,
    "need_mp4_align": False,
    "screen_width_px": "900",
    "source": 7,
    "use_os_player": False,
    "use_server_dns": False,
}

MODEL_BIZ_PARAM = {
    "detail_page_version": 0,
    "device_level": 3,
    "disable_digg_stat": False,
    "need_all_video_definition": True,
    "need_mp4_align": False,
    "use_os_player": False,
    "use_server_dns": False,
    "video_platform": 1024,
}

_TIMEOUT = aiohttp.ClientTimeout(total=25)


# ====================================================================
# API 调用封装
# ====================================================================
class ApiError(RuntimeError):
    pass


async def api_call(api_path: str, body: dict, retries: int = 3) -> dict:
    """POST 官方接口,带 _rticket 时间戳与指数退避重试。

    原 JS 用 responseType=arraybuffer + 自解析,以区分「HTTP 200 但 0 字节」
    这类网关丢请求的情况;aiohttp 直接读字节做同样判断。
    """
    params = {**COMMON_QUERY, "_rticket": str(int(time.time() * 1000))}
    for i in range(retries):
        detail: dict = {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(API + api_path, params=params, json=body,
                                        headers=HEADERS, timeout=_TIMEOUT) as r:
                    detail["status"] = r.status
                    detail["logid"] = r.headers.get("x-tt-logid")
                    buf = await r.read()
                    detail["bytes"] = len(buf)
                    if r.status != 200:
                        raise ApiError(f"HTTP {r.status}")
                    if len(buf) == 0:
                        # 服务端 200 但无内容:网关在业务处理前就丢掉了请求
                        raise ApiError(
                            "接口返回空响应(HTTP 200,0 字节)"
                            + (f" logid={detail['logid']}" if detail.get("logid") else "")
                        )
                    text = buf.decode("utf-8")
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        raise ApiError(
                            f"响应不是合法 JSON(HTTP 200,{len(buf)} 字节): {text[:100]}"
                        )
        except Exception as e:
            if i == retries - 1:
                raise e
            await asyncio.sleep(2000 * (i + 1) / 1000)


# ====================================================================
# 官网网页版数据源
# ====================================================================
def normalize_video_url(raw: str) -> str:
    """MP4 直链:去掉 HTML 转义并剥掉 Range 头,让 CDN 回整段。"""
    url = (
        str(raw or "")
        .replace("\\u002F", "/")
        .replace("\\u0026", "&")
        .replace("&amp;", "&")
    )
    url = re.sub(r"([?&])Range=[^&]*", r"\1", url, flags=re.I)
    return re.sub(r"[?&]$", "", url)


def pick_json_string(text: str, key: str) -> str:
    """从响应体里安全地取出某个字符串字段。"""
    m = re.search(r'"' + re.escape(key) + r'"\s*:\s*"([^"]*)"', text)
    return m.group(1).replace("\\u002F", "/").replace("\\u0026", "&") if m else ""


async def fetch_site_html(url: str) -> str:
    """拉取官网页面 HTML。"""
    headers = {
        "User-Agent": WEB_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": WEB_REFERER,
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=30),
                               allow_redirects=True) as r:
            text = await r.text(errors="replace")
    return text


async def fetch_episode_list_from_web(series_id: str) -> dict:
    """官网兜底:从 player 页内嵌 JSON 取完整分集列表。

    vid_list 按下标即集数顺序(下标 i -> 第 i+1 集)。
    """
    html = await fetch_site_html(f"{SITE_ORIGIN}/player/{quote(str(series_id))}")
    m = re.search(r'"vid_list"\s*:\s*\[([^\]]*)\]', html)
    if not m:
        raise ApiError("官网页面未找到分集数据(vid_list)")
    vids = [s.strip().strip('"') for s in m.group(1).split(",")]
    vids = [v for v in vids if re.fullmatch(r"\d+", v)]
    if not vids:
        raise ApiError("官网分集列表为空")

    series_title = pick_json_string(html, "series_name") or "未命名短剧"
    cover = pick_json_string(html, "series_cover")
    episodes = [
        {"vid": vid, "vid_index": i + 1, "title": "",
         "series_id": str(series_id), "series_title": series_title, "cover": cover}
        for i, vid in enumerate(vids)
    ]
    return {
        "series_id": str(series_id),
        "series_title": series_title,
        "cover": cover or (episodes[0] and episodes[0]["cover"]) or "",
        "total": len(episodes),
        "episodes": episodes,
        "source": "web",
    }


async def fetch_play_url_from_web(vid: str, sid: str | None = None) -> dict | None:
    """官网兜底:取单集可直接下载的 MP4 直链。

    官网页里内嵌的 main_url 是「已经可播」的地址,明文 MP4,无 CENC 加密,
    因此不需要 spade_a / 解密这一步。sid 已知时用 /player/{sid}/{vid};
    未知时退回 /player/_/{vid} 再自行解析。
    """
    candidates = []
    if sid:
        candidates.append(f"{SITE_ORIGIN}/player/{quote(str(sid))}/{quote(str(vid))}")
    candidates.append(f"{SITE_ORIGIN}/player/_/{quote(str(vid))}")

    last_err = None
    for url in candidates:
        try:
            html = await fetch_site_html(url)
            m = re.search(r'"main_url"\s*:\s*"([^"]+)"', html)
            if not m:
                m = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', html)
            if not m:
                continue
            video_url = normalize_video_url(m.group(1))
            if not re.match(r"^https?://", video_url, re.I):
                continue
            return {"url": video_url, "spadeA": None, "codec": "", "source": "web"}
        except Exception as e:  # noqa: BLE001
            last_err = e
    if last_err:
        logger.warning(f"[Web] 取播放直链失败: {last_err}")
    return None


# ====================================================================
# 分享链接 -> series_id
# ====================================================================
async def resolve_series_id(share_url: str) -> str:
    """分享链接 / series_id -> series_id。"""
    trimmed = str(share_url or "").strip()
    if re.fullmatch(r"\d+", trimmed):
        return trimmed

    headers = {
        "User-Agent": ("Mozilla/5.0 (Linux; Android 9; SM-N9860) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/88.0.4324.152 Mobile Safari/537.36"),
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(trimmed, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=25),
                               allow_redirects=True) as r:
            final_url = str(r.url)
            body_text = await r.text(errors="replace")

    m = re.search(r"video_series_id=(\d+)", final_url)
    if m:
        return m.group(1)

    m = re.search(r"schemeParams[^&]*", final_url)
    if m:
        raw = m.group(0)
        for _ in range(2):  # 原 JS decodeURIComponent 两次
            try:
                raw = __import__("urllib.parse", fromlist=["unquote"]).unquote(raw)
            except Exception:  # noqa: BLE001
                break
        jm = re.search(r'"video_id"\s*:\s*"(\d+)"', raw)
        if jm:
            return jm.group(1)

    m = (re.search(r"video_series_id=(\d+)", body_text)
         or re.search(r'"video_id"\s*:\s*"(\d+)"', body_text)
         or re.search(r'"series_id"\s*:\s*"(\d+)"', body_text))
    if m:
        return m.group(1)

    raise ApiError(f"无法从链接解析 series_id: {final_url}")


# ====================================================================
# 分集 / 播放直链
# ====================================================================
async def fetch_episode_list(series_id: str) -> dict:
    """获取全集剧集列表(官方 App 接口,失败自动降级官网)。"""
    body = {
        "biz_param": DETAIL_BIZ_PARAM,
        "dr_scene": "preload",
        "series_id": str(series_id),
    }
    try:
        j = await api_call("/novel/player/multi_video_detail/preload/v1", body)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[Hongguo] detail API 不可用,改用官网数据源: {e}")
        try:
            web_data = await fetch_episode_list_from_web(series_id)
            logger.info(f"[Hongguo] 官网数据源成功:《{web_data['series_title']}》共 {web_data['total']} 集")
            return web_data
        except Exception as web_err:  # noqa: BLE001
            raise ApiError(
                f"获取分集失败:官方接口不可用({e}),官网兜底也失败({web_err})"
            )
    if not j or j.get("code") != 0:
        raise ApiError(f"detail API 失败: {json.dumps(j, ensure_ascii=False)[:200]}")
    d = j.get("data") or {}
    sid = next(iter(d.keys()), None)
    if not sid:
        raise ApiError("未获取到剧集数据")
    vd = (d.get(sid) or {}).get("video_data") or {}
    vl = vd.get("video_list") or []
    eps = [
        {
            "vid": str(item.get("vid", "")),
            "vid_index": item.get("vid_index") or 0,
            "title": item.get("title") or "",
            "series_id": str(item.get("series_id") or sid),
            "series_title": vd.get("series_title") or "",
            "cover": vd.get("series_cover") or vd.get("cover_url") or item.get("cover_url") or "",
        }
        for item in vl
    ]
    eps.sort(key=lambda e: e["vid_index"])
    return {
        "series_id": str(sid),
        "series_title": vd.get("series_title") or "未命名短剧",
        "cover": (vd.get("series_cover") or vd.get("cover_url")
                  or (eps[0] and eps[0]["cover"]) or ""),
        "total": len(eps),
        "episodes": eps,
    }


def stream_score(v: dict) -> tuple[int, int, int]:
    """单条视频流的清晰度评分,返回 (defNum, pixels, bitrate),越大越清晰。"""
    meta = v.get("video_meta") or {}
    def_str = str(meta.get("definition") or "")
    m = re.search(r"(\d+)\s*p", def_str, re.I)
    if m:
        def_num = int(m.group(1))
    else:
        mapping = {"4k": 2160, "2k": 1440, "fhd": 1080, "fullhd": 1080,
                   "hd": 720, "sd": 480, "ld": 360}
        def_num = mapping.get(def_str.lower(), 0)
    w = int(meta.get("vwidth") or 0)
    h = int(meta.get("vheight") or 0)
    bitrate = int(meta.get("bitrate") or meta.get("real_bitrate") or 0)
    return def_num, w * h, bitrate


def _codec_rank(codec: str) -> int:
    if codec in ("h265", "h264", "h265_hvc1", "hevc", "hvc1", "avc1"):
        return 0
    if codec == "bytevc1":
        return 1
    return 2


def parse_model_video(video_model: str) -> tuple[str | None, str | None, str | None]:
    """解析单个 video_model JSON。

    选流优先级:清晰度标签 > 像素 > 编码格式 > 码率(取最高分辨率)。
    """
    if not isinstance(video_model, str):
        return None, None, None
    try:
        vmj = json.loads(video_model)
    except json.JSONDecodeError:
        return None, None, None
    vl = vmj.get("video_list") or []
    best = None
    best_score = None
    for v in vl:
        if not v.get("main_url"):
            continue
        codec = (v.get("video_meta") or {}).get("codec_type") or ""
        ei = v.get("encrypt_info") or {}
        def_num, pixels, bitrate = stream_score(v)
        codec_rank = _codec_rank(codec)
        score = (def_num, pixels, -codec_rank, bitrate)
        if best_score is None or score > best_score:
            best_score = score
            best = (v.get("main_url"), ei.get("spade_a") or None, codec)
    return best or (None, None, None)


async def fetch_play_url_single(vid: str, sid: str | None = None) -> dict:
    """获取单集播放直链与 spade_a 加密 key(官方 App 接口,失败降级官网)。"""
    body = {
        "biz_param": MODEL_BIZ_PARAM,
        "dr_scene": "preload",
        "mixed_video_id_map": {"1004": [vid]},
    }
    try:
        j = await api_call("/novel/player/multi_video_model/preload/v1", body)
        item = ((j.get("data") or {}).get(vid) or {})
        url, spade_a, codec = parse_model_video(item.get("video_model"))
        if url:
            return {"url": url, "spadeA": spade_a, "codec": codec, "source": "api"}
    except Exception:  # noqa: BLE001
        pass
    # 官方 App 接口不可用时,改用官网内嵌的 MP4 直链(明文,无需解密)
    try:
        web = await fetch_play_url_from_web(vid, sid)
        if web and web.get("url"):
            return web
    except Exception:  # noqa: BLE001
        pass
    return {"url": None, "spadeA": None, "codec": None}
