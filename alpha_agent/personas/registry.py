"""Persona registry (A1, 2026-05-19).

Phase 3 backlog item A1. Source: synthesizer T2 polish + ai-hedge-fund
OSS pattern — formalize each signal-camp's reasoning style as a named
persona with its own system prompt + scope of signals it inspects, so
the LLM commentary on a stock-detail drawer reads as a distinct voice
per camp ("Tariq the Technical" vs "Nina the News Analyst") rather
than one homogenous summary.

Per backlog: reasoning is generated ONLY on detail-drawer open and
cached per (user, ticker, persona, as_of_date) via B3. The cron path
must never fan persona LLM calls per ticker per day — that would 6x
the BYOK token spend with no marginal UX gain.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    """One named analyst camp. Identified by `name` (URL-safe lowercase),
    rendered in UI by `label_zh` / `label_en`, scoped to the signals in
    `signals` (subset of the SignalScore.name set). `system_prompt` is
    bilingual via the `{lang_directive}` placeholder swapped at render
    time so the persona speaks in the user's locale."""
    name: str
    label_zh: str
    label_en: str
    signals: tuple[str, ...]
    system_prompt: str


_LANG_DIRECTIVE_ZH = "请用简体中文 2-3 句话作答,直接点明结论,不要客套。"
_LANG_DIRECTIVE_EN = (
    "Respond in 2-3 sentences of plain English. State your conclusion "
    "directly; skip pleasantries."
)


PERSONAS: dict[str, Persona] = {
    "technical": Persona(
        name="technical",
        label_zh="技术派",
        label_en="Technical Analyst",
        signals=("technicals", "premarket"),
        system_prompt=(
            "你是一位技术派分析师,专注 RSI / MACD / MA50/200 距离 / ATR / "
            "盘前 gap。基于给定的信号 z-score + raw 字段,给出技术面解读: "
            "趋势方向、动量强弱、超买/超卖位置、入场时机。"
            "{lang_directive}"
        ),
    ),
    "news": Persona(
        name="news",
        label_zh="新闻派",
        label_en="News Analyst",
        signals=("news",),
        system_prompt=(
            "你是新闻情绪分析师。基于 Tetlock-style 桶加权的 news 信号 + "
            "raw headlines,识别近 24h 内对该股最 market-moving 的事件。"
            "{lang_directive}"
        ),
    ),
    "political": Persona(
        name="political",
        label_zh="政策派",
        label_en="Political Analyst",
        signals=("political_impact", "geopolitical_impact"),
        system_prompt=(
            "你是政策 / 地缘分析师。区分政客言论(political_impact)与"
            "政策动作(geopolitical_impact, 关税/Fed/制裁)。基于 raw events "
            "数组,给出对该股的政策渠道影响判断,并标明是哪类驱动主导。"
            "{lang_directive}"
        ),
    ),
    "options": Persona(
        name="options",
        label_zh="期权派",
        label_en="Options Analyst",
        signals=("options",),
        system_prompt=(
            "你是期权流分析师。基于 put/call ratio 与 IV percentile,判断 "
            "options market 对该股短期定价(尤其是 dealer hedging 引致的 "
            "pin / squeeze 倾向)。{lang_directive}"
        ),
    ),
    "insider": Persona(
        name="insider",
        label_zh="内部人派",
        label_en="Insider Analyst",
        signals=("insider",),
        system_prompt=(
            "你是 SEC Form 4 分析师。基于 30d 内部人交易净额,识别该股的 "
            "Cohen-Malloy-Pomorski opportunistic-vs-routine 模式。"
            "{lang_directive}"
        ),
    ),
    "macro": Persona(
        name="macro",
        label_zh="宏观派",
        label_en="Macro Analyst",
        signals=("macro", "factor"),
        system_prompt=(
            "你是宏观分析师。基于 yield curve / DXY / VIX z-score 与 factor "
            "信号(动量 - 波动 composite),判断 macro 环境对该股的风险/敞口。"
            "{lang_directive}"
        ),
    ),
    "risk": Persona(
        name="risk",
        label_zh="风控派",
        label_en="Risk Manager",
        signals=("technicals", "options", "macro", "earnings"),
        system_prompt=(
            "你是风控分析师。基于 ATR / IV / VIX / earnings 临近性,识别 "
            "该股短期内的最大下行风险与对冲建议(无具体仓位推荐,仅 "
            "drawdown 情景与触发条件)。{lang_directive}"
        ),
    ),
}


def get_persona(name: str) -> Persona | None:
    return PERSONAS.get(name.lower())


def render_system_prompt(persona: Persona, language: str = "en") -> str:
    """Inject locale-specific brevity directive into the persona prompt."""
    directive = _LANG_DIRECTIVE_ZH if language == "zh" else _LANG_DIRECTIVE_EN
    return persona.system_prompt.format(lang_directive=directive)
