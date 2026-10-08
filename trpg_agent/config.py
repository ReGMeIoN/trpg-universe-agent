# -*- coding: utf-8 -*-
"""配置中心: 单文件 config.yaml -> pydantic 模型。

设计要点
- 所有可调项都在这里; 代码里不允许出现硬编码路径/模型名。
- 切库只改 workspace.root 一行。
- 密钥只从环境变量读(api_key_env), 不落配置文件。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CONFIG_NAME = "config.yaml"


class Cfg(BaseModel):
    model_config = ConfigDict(extra="allow", protected_namespaces=())


class WorkspaceCfg(Cfg):
    """一个 Workspace = 一个宇宙库(含 素材/数据/产出/.trpg)。"""

    root: str = "."
    # 生产库路径: 与 root 相同且未开 allow_production_write 时, store --apply 会被拒绝
    production_root: str = ""
    data_dir: str = "数据"
    output_dir: str = "产出"
    material_dir: str = "素材"
    work_dir: str = ".trpg"
    backup_keep: int = 10
    allow_production_write: bool = False


class DateGroupRange(Cfg):
    """一个日期区间 -> 一个团名(用于"一次导出含多个团"的拆团)。"""

    start: str  # YYYY-MM-DD (含)
    end: str  # YYYY-MM-DD (含)
    group: str


class DateGroupRule(Cfg):
    """把某个导出按日期区间拆成多个团。

    例: 卧槽是伪人群_三团合集_*.json 含三个团, 按日期区间拆开。
    区间外的消息不会被丢弃: 默认写进 <来源名>_未归类_聊天记录纯文本.txt 并告警,
    也可用 unmatched_group 显式指定归属。
    """

    source_glob: str
    ranges: list[DateGroupRange] = Field(default_factory=list)
    unmatched_group: str | None = None


class IngestCfg(Cfg):
    exclude_globs: list[str] = Field(
        default_factory=lambda: [
            "_scripts/**",
            "_whisper_models/**",
            "qq-chat-exporter/**",
            "QQDecrypt/**",
            "nt_msg_db_util/**",
            "napcat/**",
            "NapCat*/**",
            "_headless_profile*/**",
            "_test/**",
            "segments/**",
            "提炼/**",
            "*提炼*.md",
            "*_段*.md",
            "*_state.txt",
            "*.bak_*",
            "*.log",
            "*.err",
            "napcat_*",
            "_test.*",
            "*.py",
            "*.ps1",
            "*.mjs",
            "*.zip",
        ]
    )
    hash_algo: str = "sha256"
    # 已知团名(群名即团名): 文件名/目录名里出现即归属该团(最长匹配优先)
    known_groups: list[str] = Field(default_factory=list)
    # 目录名/文件前缀 -> 规范团名(处理简称、合集、拼写差异)
    group_aliases: dict[str, str] = Field(default_factory=dict)
    # 目录约定外的团名识别规则(优先级最高): [{glob: "xxx*", group: "团名"}]
    group_rules: list[dict] = Field(default_factory=list)
    # 按日期区间拆团的规则(一次导出含多个团)
    date_group_rules: list[DateGroupRule] = Field(default_factory=list)
    # 已被人为废弃的派生产物(如手工转出的整份纯文本已被拆团取代): 标记 superseded, 不参与切段
    supersede_globs: list[str] = Field(default_factory=list)
    normalized_dir: str = "normalized"
    audio_exts: list[str] = Field(
        default_factory=lambda: [".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".wma", ".opus"]
    )
    text_exts: list[str] = Field(default_factory=lambda: [".txt", ".md"])
    doc_exts: list[str] = Field(default_factory=lambda: [".docx"])
    legacy_doc_exts: list[str] = Field(default_factory=lambda: [".doc", ".xls", ".ppt"])
    image_exts: list[str] = Field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]
    )
    json_exts: list[str] = Field(default_factory=lambda: [".json"])
    # 只报不改
    dry_run: bool = False


class LLMProviderCfg(Cfg):
    type: Literal["openai", "ollama"] = "openai"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:14b"
    api_key_env: str | None = None
    temperature: float = 0.2
    max_tokens: int = 8000
    timeout_s: int = 600
    num_parallel: int = 1  # Ollama 本地默认单并发
    # ⚠️ Ollama 会按显存给出很小的默认上下文(实测 4096), 不显式设置会静默截断长段文本
    num_ctx: int = 32768
    #: 结构化输出模式: json_object(多数端点可用) / json_schema(部分不支持) / none
    json_mode: Literal["json_object", "json_schema", "none"] = "json_object"

    @property
    def api_key(self) -> str | None:
        """密钥只从环境变量读；本机(Windows)另加一层注册表兜底。

        为什么需要兜底：DSH 的 pwsh 每次都是全新进程，必须显式设 `$env:TRPG_LLM_KEY`；
        而当沙箱后端不可用时 pwsh 会落在 ConstrainedLanguage，连
        `[Environment]::GetEnvironmentVariable(...)` 都被禁 —— 于是所有云端步骤直接失败。
        用户级环境变量在注册表 HKCU\\Environment 里，读它不需要任何特殊权限。
        """
        if not self.api_key_env:
            return None
        val = os.environ.get(self.api_key_env)
        if val:
            return val
        if os.name == "nt":
            try:
                import winreg

                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                    raw, _ = winreg.QueryValueEx(key, self.api_key_env)
                if isinstance(raw, str) and raw:
                    os.environ[self.api_key_env] = raw  # 缓存进本进程, 后续不再读注册表
                    return raw
            except (OSError, ImportError, ValueError):
                pass
        return None


class LLMCfg(Cfg):
    default: str = "local"
    providers: dict[str, LLMProviderCfg] = Field(
        default_factory=lambda: {
            "local": LLMProviderCfg(type="ollama", base_url="http://127.0.0.1:11434", model="qwen2.5:14b"),
        }
    )
    # 分档路由: 逻辑名 -> provider 名
    routes: dict[str, str] = Field(
        default_factory=lambda: {"extract": "local", "segment_title": "local", "filter": "local"}
    )

    def provider_for(self, route: str) -> LLMProviderCfg:
        name = self.routes.get(route, self.default)
        if name not in self.providers:
            raise KeyError(f"llm.routes.{route} 指向未定义的 provider: {name!r} (已定义: {list(self.providers)})")
        return self.providers[name]


class EmbeddingCfg(Cfg):
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "nomic-embed-text"


class VadCfg(Cfg):
    min_silence_ms: int = 600
    speech_pad_ms: int = 400
    gap_break_s: int = 60


class BatchCfg(Cfg):
    max_speech_s: int = 780
    max_span_s: int = 1800


class AsrCfg(Cfg):
    engine: str = "faster_whisper"
    model_path: str = ""
    device: str = "cpu"
    compute_type: str = "int8"
    cpu_threads: int = 8
    language: str = "zh"
    initial_prompt: str = "以下是普通话的跑团游戏对话记录，包含主持人与玩家的角色扮演发言。"
    beam_size: int = 5
    # 批式推理(faster-whisper BatchedInferencePipeline): 本机实测**不可用** —
    #   clip_timestamps 每个 clip 只取前 30 秒(源码 transcribe.py:438), 而 VAD 语音块常有
    #   >30s 的连续说话段 -> 直接丢内容; 且实测更慢(0.409x vs 0.372x)并诱发幻觉
    #   ("感谢观看,请不吝点赞…")。保留开关以便将来换卡/换版本再试, 默认关。
    batched: bool = False
    batch_size: int = 8
    # 跨窗口文本条件: 长音频+噪声+音乐时容易诱发复读/幻觉, 关掉更稳(也略快)
    condition_on_previous_text: bool = True
    # 窗口化流式解码: 每 window_s 秒一个窗口(30 分钟窗口约 115MB 内存), 避免整段 STFT 的 OOM
    window_s: int = 1800
    seek_on_resume: bool = True  # 续跑时 seek 到断点窗口, 省去重新解码
    vad: VadCfg = Field(default_factory=VadCfg)
    batch: BatchCfg = Field(default_factory=BatchCfg)
    smoke_seconds: int = 0  # >0 只转开头 N 秒(冒烟)
    resume: bool = True
    # 质量自检: 提示词泄漏(音乐/噪声段每 30 秒复读 initial_prompt)与复读幻觉
    filter_prompt_leak: bool = True
    filter_repeats: bool = True
    leak_similarity: float = 0.8
    out_dir: str = "素材"
    out_suffix: str = "_转写"
    state_every: int = 50  # 每 N 段写一次 state


class SegmentCfg(Cfg):
    strategy: Literal["time_window", "date", "line_chunk"] = "time_window"
    window_s: int = 3770
    max_lines: int = 40000
    # date 策略: 连续日期合并到累计行数超过此值(0 = 一天一段, 不合并)
    date_merge_max_lines: int = 3600
    out_dir: str = "素材/segments"
    inputs: list[str] = Field(default_factory=lambda: ["transcript", "qq_text", "raw_text"])
    keep_unparsed: bool = False


class ExtractCfg(Cfg):
    template: str = "templates/extract_template.md"
    consolidate_template: str = "templates/consolidate_template.md"
    out_dir: str = "extracts"
    concurrency: int = 1          # Ollama 本地默认单并发; 云端可调到 4-8
    model_route: str = "extract"  # llm.routes 里的逻辑名
    roster_scope: Literal["group_plus_cross", "all_names", "none"] = "group_plus_cross"
    max_segment_chars: int = 200000   # 单段输入上限(超出会报错, 提示调小切段窗口)
    skip_if_exists: bool = True
    retry: int = 2
    consolidation_max_output_tokens: int = 8000


class ReviewCfg(Cfg):
    require_confirm: bool = True
    pending_file: str = "pending/待确认.md"
    decisions_dir: str = "review"


class StoreCfg(Cfg):
    strictness: Literal["strict", "lenient"] = "strict"
    backup: bool = True
    write_report: bool = True
    report_dir: str = "reports"
    # 团名 -> id 前缀 显式映射(算法推不出来, 必须人工约定)
    id_prefix_map: dict[str, str] = Field(default_factory=dict)
    id_prefix_fallback: Literal["pinyin", "seq", "error"] = "pinyin"
    dangling_ref: Literal["warn", "error", "ignore"] = "warn"
    normalization_file: str = "canon/naming.json"


class VisualizeCfg(Cfg):
    net_enabled: bool = True
    net_engine: Literal["legacy_svg", "echarts"] = "legacy_svg"
    pl_wall: bool = True
    chronicle: bool = True
    jack_dossier: bool = True
    jack_ids: list[str] = Field(default_factory=lambda: ["cross_jieke"])


class ExportCfg(Cfg):
    kb_pack: bool = True
    out_dir: str = "astrbot知识库导入"
    push_rag: bool = False
    # 只覆盖本工具生成过的文件; 遇到手工文件默认跳过(设 true 才覆盖)
    overwrite_unmanaged: bool = False


class JobsCfg(Cfg):
    backend: Literal["detached", "inline"] = "detached"
    log_level: str = "INFO"
    on_finish: Literal["none", "shutdown", "notify"] = "none"


class Config(Cfg):
    version: int = 1
    workspace: WorkspaceCfg = Field(default_factory=WorkspaceCfg)
    ingest: IngestCfg = Field(default_factory=IngestCfg)
    llm: LLMCfg = Field(default_factory=LLMCfg)
    embedding: EmbeddingCfg = Field(default_factory=EmbeddingCfg)
    asr: AsrCfg = Field(default_factory=AsrCfg)
    segment: SegmentCfg = Field(default_factory=SegmentCfg)
    extract: ExtractCfg = Field(default_factory=ExtractCfg)
    review: ReviewCfg = Field(default_factory=ReviewCfg)
    store: StoreCfg = Field(default_factory=StoreCfg)
    visualize: VisualizeCfg = Field(default_factory=VisualizeCfg)
    export: ExportCfg = Field(default_factory=ExportCfg)
    jobs: JobsCfg = Field(default_factory=JobsCfg)


def find_config(explicit: str | Path | None = None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise FileNotFoundError(f"配置文件不存在: {p}")
        return p
    env = os.environ.get("TRPG_CONFIG")
    if env and Path(env).is_file():
        return Path(env)
    here = Path.cwd() / DEFAULT_CONFIG_NAME
    if here.is_file():
        return here
    pkg = Path(__file__).resolve().parent.parent / DEFAULT_CONFIG_NAME
    if pkg.is_file():
        return pkg
    raise FileNotFoundError(
        f"未找到 {DEFAULT_CONFIG_NAME}; 用 --config 指定, 或先在项目根目录创建配置文件。"
    )


def load_config(explicit: str | Path | None = None, ws_override: str | Path | None = None) -> Config:
    path = find_config(explicit)
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = Config(**raw)
    if ws_override:
        cfg.workspace.root = str(ws_override)
    return cfg


def dump_effective_config(cfg: Config) -> str:
    return yaml.safe_dump(cfg.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
