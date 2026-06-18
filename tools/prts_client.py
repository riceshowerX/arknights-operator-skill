#!/usr/bin/env python3
"""
PRTS Wiki API 客户端 —— 统一的 API 调用、速率限制和错误处理

将原本分散在 story_extractor.py、phase_inferrer.py、game_data_parser.py
中的 PRTS API 调用逻辑集中管理，确保：
- 全局速率限制（所有调用共享同一个计时器，线程安全）
- 指数退避重试（对超时和 5xx 错误自动重试）
- 统一的错误处理和日志格式

用法：
    from prts_client import prts_api_get, fetch_page_categories, fetch_page_wikitext
"""

import json
import logging
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

# 支持从 tools 目录内和从项目根目录两种导入方式
try:
    from constants import (
        PRTS_API_URL,
        PRTS_USER_AGENT,
        PRTS_REQUEST_TIMEOUT,
        PRTS_REQUEST_INTERVAL,
    )
except ImportError:
    from tools.constants import (
        PRTS_API_URL,
        PRTS_USER_AGENT,
        PRTS_REQUEST_TIMEOUT,
        PRTS_REQUEST_INTERVAL,
    )

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 全局速率限制（线程安全）
# ──────────────────────────────────────────────

_rate_lock = threading.Lock()
_last_request_time: float = 0.0

# 重试配置
_MAX_RETRIES = 5  # PRTS Wiki 不稳定，增加重试次数
_RETRY_BASE_DELAY = 0.5  # 秒，指数退避基数（0.5s, 1s, 2s, 4s, 8s）


def _rate_limit() -> None:
    """确保请求间隔 >= PRTS_REQUEST_INTERVAL（线程安全）"""
    global _last_request_time
    with _rate_lock:
        elapsed = time.time() - _last_request_time
        if elapsed < PRTS_REQUEST_INTERVAL:
            time.sleep(PRTS_REQUEST_INTERVAL - elapsed)
        _last_request_time = time.time()


def _is_retryable_error(exc: Exception) -> bool:
    """判断异常是否可重试"""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500  # 5xx 可重试，4xx 不可
    if isinstance(exc, (urllib.error.URLError, TimeoutError, OSError)):
        return True
    return False


# ──────────────────────────────────────────────
# 核心 API 调用
# ──────────────────────────────────────────────


def prts_api_get(params: dict, timeout: int = PRTS_REQUEST_TIMEOUT) -> dict:
    """调用 PRTS MediaWiki API（含速率限制、重试和统一错误处理）

    对超时和 5xx 错误自动指数退避重试（最多 3 次）。

    Args:
        params: API 参数 dict（format=json 会自动添加）
        timeout: 请求超时秒数

    Returns:
        API 响应 JSON dict，失败时返回空 dict
    """
    params = dict(params)
    params["format"] = "json"
    url = f"{PRTS_API_URL}?{urllib.parse.urlencode(params)}"

    last_error: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        _rate_limit()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": PRTS_USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1 and _is_retryable_error(e):
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.info("PRTS API 请求失败 (尝试 %d/%d): %s，%0.1f 秒后重试",
                            attempt + 1, _MAX_RETRIES, e, delay)
                time.sleep(delay)
                continue
            # 不可重试或已达最大次数
            break

    logger.warning("PRTS API 请求最终失败: %s | params=%s", last_error, params)
    return {}


def fetch_page_wikitext(page_title: str, follow_redirects: bool = True) -> str:
    """获取 PRTS 页面的 wikitext 内容

    Args:
        page_title: 页面标题
        follow_redirects: 是否跟随重定向

    Returns:
        wikitext 字符串，失败时返回空字符串
    """
    data = prts_api_get({
        "action": "parse",
        "page": page_title,
        "prop": "wikitext",
        "redirects": "true" if follow_redirects else "",
    })
    return data.get("parse", {}).get("wikitext", {}).get("*", "")


def fetch_page_categories(page_title: str) -> list[str]:
    """获取 PRTS 页面的分类标签

    Args:
        page_title: 页面标题

    Returns:
        分类标签列表（已去掉 "分类:" 前缀）
    """
    data = prts_api_get({
        "action": "query",
        "titles": page_title,
        "prop": "categories",
        "cllimit": "50",
    })
    categories: list[str] = []
    for page in data.get("query", {}).get("pages", {}).values():
        for cat in page.get("categories", []):
            title: str = cat.get("title", "")
            if title.startswith("分类:"):
                title = title[3:]
            categories.append(title)
    return categories


def fetch_page_revisions(page_title: str) -> str:
    """获取 PRTS 页面的最新修订 wikitext

    Args:
        page_title: 页面标题

    Returns:
        wikitext 字符串，失败时返回空字符串
    """
    data = prts_api_get({
        "action": "query",
        "titles": page_title,
        "prop": "revisions",
        "rvprop": "content",
        "rvlimit": "1",
    })
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return ""
    page = next(iter(pages.values()))
    revisions = page.get("revisions", [])
    if not revisions:
        return ""
    return revisions[0].get("*", "")


def fetch_activity_info(page_title: str) -> dict:
    """从 PRTS 活动页面提取 {{活动信息}} 模板数据

    Args:
        page_title: 活动页面标题

    Returns:
        活动信息 dict
    """
    wikitext = fetch_page_revisions(page_title)
    if not wikitext:
        return {}

    info: dict = {}
    in_template = False
    depth = 0
    for line in wikitext.split("\n"):
        if "活动信息" in line and "{{" in line:
            in_template = True
            depth = line.count("{{") - line.count("}}")
        if in_template:
            for segment in line.split("|"):
                if "=" in segment:
                    key, _, value = segment.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if key and value and not key.startswith("{"):
                        info[key] = value
            depth += line.count("{{") - line.count("}}")
            if depth <= 0:
                break

    return info


# ──────────────────────────────────────────────
# 便捷函数：带速率限制的 urlopen
# ──────────────────────────────────────────────


def rate_limited_urlopen(req: urllib.request.Request, timeout: int = PRTS_REQUEST_TIMEOUT):
    """带速率限制和重试的 urlopen 调用（兼容旧接口）

    对超时和 5xx 错误自动指数退避重试。
    返回响应对象，调用方负责读取和关闭。
    """
    last_error: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        _rate_limit()
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except Exception as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1 and _is_retryable_error(e):
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.info("urlopen 失败 (尝试 %d/%d): %s，%0.1f 秒后重试",
                            attempt + 1, _MAX_RETRIES, e, delay)
                time.sleep(delay)
                continue
            break

    raise last_error  # type: ignore[misc]
