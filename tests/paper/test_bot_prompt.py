import hashlib
import json

from alpha_agent.paper.bot_models import BotConfig, BotDecision
from alpha_agent.paper.bot_prompt import PROMPT_VERSION, SYSTEM, build_decision_messages


def test_prompt_extraction_preserves_approved_policy_and_wire_text():
    # Frozen from main 61a5494 before extracting the pure prompt builder.
    assert hashlib.sha256(SYSTEM.encode()).hexdigest() == "098d1bc80350ae939d265dbefbc9cca27eb23c7f1636f054d22932f9e310fcce"
    assert PROMPT_VERSION == "bot-system-v2-20261113-fact-discipline"
    config = BotConfig(provider="kimi", model="kimi-for-coding")
    context = {"context_id": "fixture", "quotes": {}, "text": "示例"}
    messages = build_decision_messages(config, context, llm_calls=1)
    assert [m.role for m in messages] == ["system", "user"]
    assert messages[0].content == SYSTEM.format(schema=json.dumps(
        BotDecision.model_json_schema(), ensure_ascii=False, default=str, allow_nan=False,
    ))
    assert json.loads(messages[1].content) == {
        "strategy": config.model_dump(), "context": context, "remaining_research_rounds": 1,
    }
    assert config.provider == "kimi" and context == {"context_id": "fixture", "quotes": {}, "text": "示例"}


def test_replay_has_no_extra_research_allowance():
    messages = build_decision_messages(BotConfig(), {}, llm_calls=3)
    assert json.loads(messages[1].content)["remaining_research_rounds"] == 0
