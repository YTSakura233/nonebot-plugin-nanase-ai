from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator


class MCPServer(BaseModel):
    transport: Literal['stdio', 'streamable_http', 'sse'] = 'streamable_http'
    url: str = ''
    command: str = ''
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    readonly_tools: list[str] = Field(default_factory=list)
    allowed_users: set[int] = Field(default_factory=set)
    allowed_groups: set[int] = Field(default_factory=set)

    @model_validator(mode='after')
    def validate_transport(self):
        if self.transport == 'stdio' and not self.command:
            raise ValueError('stdio MCP requires command')
        if self.transport != 'stdio' and not self.url.startswith(('https://', 'http://')):
            raise ValueError('remote MCP requires http(s) url')
        if not set(self.readonly_tools) <= set(self.allowed_tools):
            raise ValueError('readonly_tools must be a subset of allowed_tools')
        return self


class Config(BaseModel):
    soruto_deepseek_api_key: SecretStr = SecretStr('')
    soruto_db_host: str = 'localhost'
    soruto_db_port: int = Field(default=3306, ge=1, le=65535)
    soruto_db_user: str = ''
    soruto_db_password: SecretStr = SecretStr('')
    soruto_db_name: str = ''
    soruto_allowed_groups: set[int] = Field(default_factory=set)
    soruto_banned_users: set[int] = Field(default_factory=set)
    soruto_simple_models: list[str] = Field(default_factory=lambda: ['deepseek-flash'])
    soruto_complex_models: list[str] = Field(default_factory=lambda: ['deepseek-v4-pro'])
    soruto_vision_models: list[str] = Field(default_factory=lambda: ['deepseek-flash'])
    soruto_fallback_models: list[str] = Field(default_factory=list)
    soruto_llm_deadline_seconds: float = Field(default=90, ge=1, le=600)
    soruto_model_concurrency: int = Field(default=8, ge=1, le=64)
    soruto_max_tokens: int = Field(default=4096, ge=256, le=32768)
    soruto_enable_tools: bool = False
    soruto_max_agent_steps: int = Field(default=10, ge=1, le=30)
    soruto_max_tool_calls: int = Field(default=12, ge=1, le=50)
    soruto_tool_timeout_seconds: float = Field(default=15, ge=1, le=120)
    soruto_casual_max_agent_steps: int = Field(default=3, ge=2, le=4)
    soruto_casual_deadline_seconds: float = Field(default=20, ge=1, le=90)
    soruto_casual_tool_names: set[str] = Field(default_factory=lambda: {'web_search', 'web_fetch'})
    soruto_mcp_servers: dict[str, MCPServer] = Field(default_factory=dict)
    soruto_skills_dir: Path | None = None
    soruto_enabled_skills: set[str] = Field(default_factory=set)
    soruto_knowledge_dir: Path | None = None
    soruto_knowledge_collections: set[str] = Field(default_factory=set)
    soruto_knowledge_top_k: int = Field(default=4, ge=1, le=12)
    soruto_knowledge_query_expansion: bool = True
    soruto_reply_units: int = Field(default=1800, ge=200, le=3900)
    soruto_max_pending_turns: int = Field(default=64, ge=1, le=512)
    soruto_ignore_prefixes: tuple[str, ...] = ('/', 'mai.', 'SGWCMAID')
    soruto_enable_help_alias: bool = True

    @model_validator(mode='after')
    def validate_chains(self):
        for chain in (self.soruto_simple_models, self.soruto_complex_models, self.soruto_vision_models):
            if not chain or any(not item.strip() for item in chain):
                raise ValueError('model chains must not be empty')
        if 'deepseek-v4-pro' in self.soruto_vision_models:
            raise ValueError('deepseek-v4-pro does not support images')
        return self
