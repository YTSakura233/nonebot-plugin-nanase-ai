"""Single runtime configuration, initialized by the NoneBot startup hook."""
from ..config import Config

SETTINGS = Config()
LLM_DEADLINE_SECONDS = 90.0
ENABLE_TOOLS = False
MAX_AGENT_STEPS = 10
CASUAL_MAX_AGENT_STEPS = 3
CASUAL_DEADLINE_SECONDS = 20.0
CASUAL_TOOL_NAMES = ['web_search', 'web_fetch']


def init(settings: Config) -> None:
    global SETTINGS, LLM_DEADLINE_SECONDS, ENABLE_TOOLS, MAX_AGENT_STEPS
    global CASUAL_MAX_AGENT_STEPS, CASUAL_DEADLINE_SECONDS, CASUAL_TOOL_NAMES
    SETTINGS = settings
    LLM_DEADLINE_SECONDS = settings.soruto_llm_deadline_seconds
    ENABLE_TOOLS = settings.soruto_enable_tools
    MAX_AGENT_STEPS = settings.soruto_max_agent_steps
    CASUAL_MAX_AGENT_STEPS = settings.soruto_casual_max_agent_steps
    CASUAL_DEADLINE_SECONDS = min(settings.soruto_casual_deadline_seconds, LLM_DEADLINE_SECONDS)
    CASUAL_TOOL_NAMES = sorted(settings.soruto_casual_tool_names)
