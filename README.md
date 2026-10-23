# Apple Music 点歌（AstrBot 插件）

[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.16-blue)](https://astrbot.app)
[![platform](https://img.shields.io/badge/platform-aiocqhttp%20(OneBot%20v11)-green)]()
[![license](https://img.shields.io/badge/license-MIT-lightgrey)](./LICENSE)

给 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 用的 `/点歌` 指令：从 **Apple Music 官方目录**搜索，并以 **QQ 语音消息**发回 30 秒试听。

```
/点歌 皇后大道東
/点歌 Lemon 米津玄師
/am 首都              # 别名
/apple 晴天 周杰伦     # 别名
```

返回两条消息：先 **文字 + 专辑封面**（歌名 / 歌手 / 专辑 / 原曲时长），再 **一条语音**（试听片段）。

<img src="./logo.png" width="120" alt="logo">

---

## ⚠️ 先读这段：为什么只有 30 秒

**Apple Music 的完整曲目受 DRM（FairPlay）保护，任何第三方都无法获取音频本体。**
所以本插件发的是 Apple 官方 `previewUrl`——**约 30 秒的官方试听片段**，不是整首歌。

想要"整首歌"只能走别的音源（网易云 / QQ 音乐 / yt-dlp 等），那与"接入 Apple Music"是两回事，
合规风险也不同。本插件刻意只做 Apple 官方目录能做到的事。

---

## 工作原理

| 环节 | 做法 |
| --- | --- |
| 搜索 | `https://itunes.apple.com/search` —— Apple 公开目录接口，**无需鉴权、无需 Apple Music 订阅、无需开发者账号** |
| 取音频 | 搜索结果里的 `previewUrl`（m4a / AAC，约 30 秒） |
| 发送 | 构造 OneBot `record` 段，`file` 直接填该 URL；**SnowLuma / NapCat 会自动下载并转成 QQ 语音** |

### 关于区域

⚠️ **中国区店面（`country=CN`）的搜索接口返回空结果**，所以默认用 `US`，
并自动回退 `US → JP → HK → TW → GB → SG`，直到命中带试听片段的曲目。
中文歌名（简繁皆可）在 US / JP 店面通常都能搜到。

---

## 安装

1. 把本仓库放进 AstrBot 的插件目录：

```bash
cd <AstrBot>/data/plugins
git clone https://github.com/<你的用户名>/astrbot_plugin_apple_music.git
# 或者直接下载 zip 解压成 astrbot_plugin_apple_music/ 目录
```

2. 重启 AstrBot，或在 WebUI「插件管理」里启用。

3. 确认日志出现：

```
Loading plugin astrbot_plugin_apple_music ...
Plugin astrbot_plugin_apple_music (v1.0.0) by mashiro: ...
```

## 配置

放好后在 WebUI 插件配置页可改，或编辑 `data/config/astrbot_plugin_apple_music_config.json`：

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `region` | `US` | 首选店面，**不要填 CN**（接口返回空） |
| `limit` | `5` | 每次搜索候选数，取第一个带试听片段的 |
| `send_artwork` | `true` | 是否附带专辑封面 |
| `send_voice` | `true` | 是否发送语音（关掉则只发文字+封面） |

## 平台支持

| 平台 | 支持 | 说明 |
| --- | --- | --- |
| `aiocqhttp`（OneBot v11 / NapCat / SnowLuma） | ✅ | 用 `record` 段发语音 |
| `qq_official` | ❌ | 官方机器人的语音格式不同，未适配 |
| 其它（telegram / lark 等） | ❌ | 未适配 |

## 常见问题

**`/点歌` 没反应，或者回复「点歌超时」**
说明有别的点歌插件先接管了这个指令。检查是否装了 `astrbot_plugin_music`
（它注册了 `点歌` 以及网易点歌 / QQ点歌 / 酷狗点歌等 12 个别名）。
两个办法：停用它，或者用本插件的 `/am`、`/apple` 别名。

**能搜到但收不到语音**
先确认协议端能发语音：用 OneBot 的 `send_private_msg` 发一条
`{"type":"record","data":{"file":"<任意 m4a 直链>"}}`，能收到就说明协议端没问题。
SnowLuma 日志里应出现 `| 发送：[语音]`。

**中文歌搜不到**
换店面试试（`region` 改成 `HK` 或 `TW`）；也可以"歌名 + 歌手"一起搜。
少数冷门曲目确实不在 Apple 目录里。

**会不会很吃带宽**
试听片段约 1 MB/首，且由协议端下载，AstrBot 侧只发一个 URL。

## 开发

```bash
# 在容器里直接验证搜索逻辑（不用触发 QQ 消息）
docker exec -i astrbot python3 - <<'PY'
import asyncio, importlib.util
spec = importlib.util.spec_from_file_location(
    "am", "/AstrBot/data/plugins/astrbot_plugin_apple_music/main.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p = mod.AppleMusicPlugin(None, {"region": "US"})
print(asyncio.run(p._search_itunes("Lemon")))
PY
```

## 许可

[MIT](./LICENSE)

Apple Music 是 Apple Inc. 的商标。本项目与 Apple 无隶属关系，
仅调用其公开的 iTunes Search 目录接口。
