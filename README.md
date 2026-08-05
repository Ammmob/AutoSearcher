# AutoSearcher

AutoSearcher 是一个面向 Windows 和 Microsoft Edge 的可扩展网页自动搜索工具。它从多个热点数据源收集话题，完成去重和每日缓存，然后以接近普通用户的输入、停留与滚动节奏逐条执行网页搜索。

项目只负责“话题获取 → 浏览器搜索 → 结果页浏览”，不包含账号、积分或登录逻辑。

## 功能特性

- 聚合百度、腾讯和头条热点数据源
- 每个数据源独立容错，一个来源失败不会中断其他来源
- 当日首次成功获取后写入本地缓存，后续启动直接复用
- 所有在线来源均无结果时，自动使用本地保险话题
- 支持启动新的 Edge，或接管开启了远程调试的 Edge
- 使用已有 Edge 用户目录，保留登录状态和用户环境
- 模拟鼠标定位、逐字输入、随机停留和分段滚动
- 支持配置检查、单独调试数据源和完整搜索三种命令
- 提供无需安装 Python 的 Windows 便携 ZIP 构建

## 运行环境

### 使用便携版

- Windows 10/11 x64
- Microsoft Edge

目标机器不需要安装 Python 或项目依赖。首次缺少匹配的 EdgeDriver 时，Selenium Manager 可能需要联网下载。

### 从源码运行

- Python 3.11 或更高版本
- Microsoft Edge

## 快速开始

### 便携版

解压 `AutoSearcher-portable-win-x64.zip` 后，目录中包含程序、配置和保险话题数据：

```text
AutoSearcher/
├─ AutoSearcher.exe
├─ run.cmd
├─ check.cmd
├─ config/
│  └─ config.yaml
└─ data/
   └─ fallback_topics.txt
```

建议先运行：

```powershell
.\check.cmd
```

确认配置有效后运行：

```powershell
.\run.cmd
```

也可以直接执行 `AutoSearcher.exe`。未提供命令时默认执行 `run`。

### 源码安装

克隆或下载源码后，在项目目录执行：

```powershell
cd AutoSearcher
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
auto-searcher check
```

项目使用标准的 `src` 布局。开发环境应先执行可编辑安装，不依赖项目根目录偶然出现在 Python 模块搜索路径中。

## 命令行

```text
auto-searcher [选项] [{run,check,topics}]
```

| 命令 | 作用 |
| --- | --- |
| `run` | 获取话题并执行完整搜索；这是默认命令 |
| `check` | 检查配置和 Selenium 运行资源，并显示解析后的目录 |
| `topics` | 只获取并显示话题，不启动浏览器 |

常用选项：

| 选项 | 作用 |
| --- | --- |
| `--config PATH` | 指定 YAML 配置文件 |
| `--verbose` | 输出调试日志 |
| `--source NAME` | `topics` 命令只调试一个数据源 |
| `--limit N` | 限制 `topics` 显示的条数，默认 20 |

示例：

```powershell
# 使用默认配置执行搜索
auto-searcher

# 检查指定配置
auto-searcher --config config/config.yaml check

# 查看聚合后的话题
auto-searcher topics --limit 20

# 绕过缓存，单独调试百度数据源
auto-searcher topics --source baidu --limit 10
```

可用数据源名称为 `baidu`、`tencent` 和 `toutiao`。

## 配置

默认配置位于 `config/config.yaml`：

```yaml
browser:
  type: edge
  page_timeout_seconds: 20

search:
  url: https://www.bing.com
  count: 3
  interval_seconds: [3, 5]
  typing_delay_seconds: [0.08, 0.20]
  scroll_count: [3, 6]
  scroll_pause_seconds: [1.5, 3]

sources:
  enabled:
    - baidu
    - tencent
    - toutiao
  request_timeout_seconds: 10
  fallback_file: ../data/fallback_topics.txt
```

### 浏览器配置

| 字段 | 说明 |
| --- | --- |
| `type` | 浏览器类型，目前仅支持 `edge` |
| `user_data_dir` | Edge 用户数据目录；省略时自动使用当前用户的默认目录 |
| `profile_name` | 可选；省略时自动读取最近使用的 Edge 配置，也可指定 `Default` 或 `Profile 1` |
| `debugger_address` | 可选；省略时自动发现 Edge 当前调试端口，设为 `null` 时跳过接管，也可显式指定地址 |
| `page_timeout_seconds` | 页面加载和元素等待超时 |

省略 `user_data_dir` 时自动解析为：

```text
%LOCALAPPDATA%\Microsoft\Edge\User Data
```

省略 `profile_name` 时，程序读取用户数据目录下的 `Local State`，使用
Edge 最近使用的配置文件；无法读取时回退到 `Default`。显式填写配置名称
会覆盖自动识别结果。

路径字段支持绝对路径、环境变量，以及相对于配置文件所在目录的路径。

### 搜索配置

| 字段 | 说明 |
| --- | --- |
| `url` | 搜索引擎首页地址 |
| `count` | 本次执行的搜索次数 |
| `interval_seconds` | 两次搜索之间的随机等待范围 |
| `typing_delay_seconds` | 每次键盘输入之间的随机延迟范围 |
| `scroll_count` | 结果页分段滚动次数范围 |
| `scroll_pause_seconds` | 每次滚动后的随机停留范围 |

当前搜索交互通过语义属性 `name="q"` 定位搜索框，并根据 `/search` 判断结果页。更换搜索引擎时可能需要实现对应的页面适配。

### 数据源配置

| 字段 | 说明 |
| --- | --- |
| `enabled` | 启用的数据源列表及执行顺序 |
| `request_timeout_seconds` | 单个数据源的 HTTP 请求超时 |
| `cache_dir` | 可选的缓存目录；省略时使用系统默认目录 |
| `fallback_file` | 所有在线来源无结果时使用的本地话题文件 |

默认缓存位置：

```text
%LOCALAPPDATA%\AutoSearcher\cache\sources\<source>.json
```

缓存按数据源分别保存，并且只在生成当天有效。缓存不存在、日期过期、内容损坏或上次获取为空时，会重新请求对应数据源。`topics --source ...` 用于实时调试，因此会绕过缓存和保险话题。

保险文件采用一行一个话题的纯文本格式，空行和以 `#` 开头的注释会被忽略。只要任意在线来源返回有效结果，本次运行就不会混入保险话题。

## Edge 会话模式

### 启动新浏览器

没有检测到可接管的浏览器时，程序使用配置的用户目录和配置文件启动
Edge。端口 `9222` 空闲时优先使用该端口；如果已被占用，则通过
`--remote-debugging-port=0` 让 Edge 选择其他空闲端口。程序
拥有该浏览器实例，并会在任务结束时将其关闭。

需要跳过自动检测、始终启动新浏览器时，可以明确配置：

```yaml
browser:
  debugger_address: null
```

同一个 Edge 用户数据目录不能同时被两个浏览器进程占用。使用默认用户目录时，请先关闭正在运行的普通 Edge，否则新实例可能无法启动。

### 接管现有浏览器

省略 `debugger_address` 时，程序检查当前由 `msedge.exe` 持有的 TCP 监听端口，
并通过 `/json/version` 确认真正的 Edge 调试服务，不会预先猜测固定端口。
也可以显式配置固定地址。

- 找到 Edge：接管现有会话，新建一个标签页执行搜索，结束时只关闭该标签页。
- 未找到 Edge：使用配置的用户目录启动新 Edge；自动模式优先使用 `9222`，被占用时随机选择空闲端口，显式配置模式使用指定端口。
- 地址对应其他浏览器：停止运行并报告类型不匹配。

普通方式打开的 Edge 没有远程调试端口，不能在运行后直接接管。需要接管时，应在启动 Edge 时显式启用远程调试，例如：

```powershell
& "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="D:\Temp\EdgeDebugProfile"
```

然后配置：

```yaml
browser:
  user_data_dir: D:\Temp\EdgeDebugProfile
  debugger_address: 127.0.0.1:9222
```

显式配置的 `debugger_address` 是程序启动时优先尝试的接管地址。该地址没有
浏览器时，程序会启动由 EdgeDriver 管理的新实例，并继续使用配置的固定端口。

当前自动接管仍使用 Edge 131 支持的传统 HTTP 调试接口；Edge 151 的新版
WebSocket 接管不在本次实现范围内。

## 项目结构

```text
AutoSearcher/
├─ src/
│  └─ auto_searcher/
│     ├─ __main__.py          命令行入口和对象组装
│     ├─ auto_searcher.py     搜索流程协调器
│     ├─ topic_gather.py      话题聚合、容错和去重
│     ├─ browsers/            浏览器抽象、Edge 实现和搜索交互
│     ├─ schemas/             配置与搜索数据结构
│     ├─ sources/             数据源抽象、缓存装饰器和平台实现
│     └─ utils/               配置读取与路径解析
├─ tests/                     单元测试
├─ config/                    默认配置
├─ data/                      保险话题
├─ packaging/                 PyInstaller 配置和便携版文件
├─ scripts/                   构建脚本
└─ pyproject.toml             项目与依赖配置
```

核心依赖方向：

```text
CLI
 ├─ TopicGather ── Source ── CachedSource
 └─ AutoSearcher ── Browser ── SearchBrowser ── EdgeBrowser
```

- `AutoSearcher` 只协调搜索流程，通过 `Browser` 接口使用浏览器。
- `TopicGather` 只负责聚合、容错、去重和保险话题切换。
- `Source`、`HttpSource` 和 `CachedSource` 分别承担来源协议、HTTP 模板流程和缓存能力。
- `SearchInteraction` 封装页面输入与浏览动作，可脱离真实浏览器进行测试。
- `schemas` 只保存数据结构，不包含业务流程。

## 扩展数据源

JSON HTTP 数据源可以继承 `HttpSource`，只实现来源名称、接口地址和响应解析：

```python
from collections.abc import Sequence
from typing import Any

from auto_searcher.sources import HttpSource


class ExampleSource(HttpSource):
    url = "https://example.com/api/topics"

    @property
    def name(self) -> str:
        return "example"

    def parse(self, data: Any) -> Sequence[str]:
        return [item["title"] for item in data["items"]]
```

随后需要：

1. 在 `sources/__init__.py` 导出新类。
2. 在 `__main__.py` 的数据源构造映射中注册名称。
3. 将名称加入 `config.yaml` 的 `sources.enabled`。
4. 为解析逻辑增加不访问网络的单元测试。

非 HTTP 或非 JSON 来源可以直接实现 `Source.fetch()`。

## 测试

安装开发版本后运行：

```powershell
python -m unittest discover -s tests -v
```

测试使用假的浏览器和内存数据源，不会打开 Edge，也不会访问外部热点接口。

## 构建便携 ZIP

在 Windows x64 环境双击项目根目录下的 `build.cmd`，或者在终端运行：

```bat
build.cmd
```

需要直接调用底层 PowerShell 脚本时使用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_portable.ps1
```

构建脚本会：

1. 创建或复用隔离的 `.build-venv`。
2. 安装构建依赖并以 `src` 布局安装项目。
3. 使用 PyInstaller 生成 `onedir` 程序。
4. 复制默认配置、保险话题、命令脚本和 README。
5. 运行打包后的 `check` 命令验证运行资源。
6. 生成便携压缩包。

输出文件：

```text
dist\AutoSearcher-portable-win-x64.zip
```

## 注意事项

- 自动化页面结构可能随搜索引擎更新而变化。
- 热点接口属于外部服务，可能发生限流、字段调整或暂时不可用。
- 搜索节奏和页面交互用于还原常规操作流程，不保证绕过网站的自动化检测。
- 请遵守目标网站的服务条款、访问频率限制以及所在地适用法律。
