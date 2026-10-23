"""Apple Music 点歌插件。

原理：
  - Apple Music 的完整曲目受 DRM 保护，第三方无法获取音频本体；
  - Apple 官方 iTunes 目录接口（itunes.apple.com/search，无需鉴权）会返回
    每首歌的 previewUrl —— 官方 30 秒试听片段；
  - 把该 URL 交给 OneBot 的 record 段，SnowLuma/NapCat 会自动下载并转成
    QQ 语音消息。

命令：/点歌 歌名 [歌手]   （别名 /song /music）
"""

import urllib.parse

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain, Record
from astrbot.api.star import Context, Star, register

ITUNES_SEARCH = "https://itunes.apple.com/search"

# 命令别名（都会被识别，前缀 / 可有可无）
COMMAND_WORDS = ("点歌", "song", "music", "听歌")

# 店面回退顺序：CN 店面搜索接口返回空结果，所以不放进来
FALLBACK_REGIONS = ("US", "JP", "HK", "TW", "GB", "SG")


@register(
    "apple_music",
    "mashiro",
    "Apple Music 点歌：搜索官方目录并以语音消息发送 30 秒试听片段",
    "1.0.0",
)
class AppleMusicPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context, config)
        cfg = config or {}
        self.region = str(cfg.get("region") or "US").strip().upper()
        try:
            self.limit = max(1, min(25, int(cfg.get("limit", 5))))
        except (TypeError, ValueError):
            self.limit = 5
        self.send_artwork = bool(cfg.get("send_artwork", True))
        self.send_voice = bool(cfg.get("send_voice", True))
        self.duration_note = str(cfg.get("max_duration_note") or "30 秒试听")
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------ 工具
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20),
                headers={"User-Agent": "Mozilla/5.0 (AstrBot AppleMusic Plugin)"},
            )
        return self._session

    @staticmethod
    def _strip_command(text: str) -> str:
        """去掉开头的命令词与前后空白/常见分隔符。"""
        s = (text or "").strip()
        if s.startswith("/"):
            s = s[1:]
        lowered = s.lower()
        for word in COMMAND_WORDS:
            if lowered.startswith(word):
                s = s[len(word):]
                break
        return s.strip(" \t:：,，、-—")

    async def _search_itunes(self, keyword: str) -> tuple[dict | None, str]:
        """依次尝试多个店面，返回 (第一个带试听片段的曲目, 命中店面)。"""
        session = await self._get_session()
        regions = []
        for r in (self.region, *FALLBACK_REGIONS):
            if r and r not in regions:
                regions.append(r)

        for region in regions:
            params = {
                "term": keyword,
                "media": "music",
                "entity": "song",
                "limit": str(self.limit),
                "country": region,
            }
            url = f"{ITUNES_SEARCH}?{urllib.parse.urlencode(params)}"
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.debug("[apple_music] search %s -> HTTP %s", region, resp.status)
                        continue
                    data = await resp.json(content_type=None)
            except Exception as exc:  # 网络问题：换下一个店面
                logger.debug("[apple_music] search %s failed: %r", region, exc)
                continue

            for track in data.get("results") or []:
                if track.get("previewUrl"):
                    return track, region
        return None, ""

    @staticmethod
    def _fmt_duration(ms) -> str:
        try:
            total = int(ms) // 1000
        except (TypeError, ValueError):
            return "?"
        return f"{total // 60}:{total % 60:02d}"

    @staticmethod
    def _big_artwork(url: str) -> str:
        if not url:
            return ""
        return url.replace("100x100bb", "300x300bb").replace("100x100", "300x300")

    # ------------------------------------------------------------------ 主流程
    async def _handle(self, event: AstrMessageEvent):
        keyword = self._strip_command(event.message_str)
        logger.info(
            "[apple_music] 收到点歌请求 keyword=%r 会话=%s",
            keyword, event.unified_msg_origin,
        )
        if not keyword:
            yield event.plain_result(
                "用法：/点歌 歌名 歌手\n例如：/点歌 Lemon 米津玄師"
            )
            return

        # 交给本插件处理后，阻止大模型再回复一遍
        event.stop_event()

        try:
            track, region = await self._search_itunes(keyword)
        except Exception as exc:
            logger.error("[apple_music] 搜索异常: %r", exc, exc_info=True)
            yield event.plain_result("搜索出错了，稍后再试。")
            return

        logger.info(
            "[apple_music] 搜索 %r -> %s (region=%s)",
            keyword, (track or {}).get("trackName") or "(未命中)", region or "-",
        )

        if not track:
            yield event.plain_result(
                f"Apple Music 里没搜到「{keyword}」。\n换个写法试试，比如加上歌手名。"
            )
            return

        name = (track.get("trackName") or "").strip()
        artist = (track.get("artistName") or "").strip()
        album = (track.get("collectionName") or "").strip()
        preview = track.get("previewUrl") or ""
        artwork = self._big_artwork(track.get("artworkUrl100") or "")
        duration = self._fmt_duration(track.get("trackTimeMillis"))

        lines = [f"🎵 {name}" + (f" — {artist}" if artist else "")]
        if album:
            lines.append(f"💽 {album}")
        lines.append(f"⏱ 原曲 {duration} · 发送 {self.duration_note}")
        if region and region != self.region:
            lines.append(f"🌍 命中店面 {region}")

        chain = [Plain("\n".join(lines))]
        if self.send_artwork and artwork:
            chain.append(Image.fromURL(artwork))
        if self.send_voice and preview:
            # SnowLuma/NapCat 会自动把该音频转成 QQ 语音
            chain.append(Record.fromURL(preview, text=f"{name} - {artist}"))

        yield event.chain_result(chain)

    @filter.command("点歌")
    async def cmd_song(self, event: AstrMessageEvent):
        async for result in self._handle(event):
            yield result

    @filter.command("song")
    async def cmd_song_en(self, event: AstrMessageEvent):
        async for result in self._handle(event):
            yield result

    @filter.command("music")
    async def cmd_music(self, event: AstrMessageEvent):
        async for result in self._handle(event):
            yield result

    # 别名：不会和其他点歌插件冲突，万一「点歌」被抢就用这几个
    @filter.command("am")
    async def cmd_am(self, event: AstrMessageEvent):
        async for result in self._handle(event):
            yield result

    @filter.command("apple")
    async def cmd_apple(self, event: AstrMessageEvent):
        async for result in self._handle(event):
            yield result

    async def terminate(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
