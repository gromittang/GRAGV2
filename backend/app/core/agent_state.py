"""
共享 Agent State 类型定义
所有 LangGraph Agent 的 State 至少包含 user_context 字段，
为后续 RBAC 接入预留。
"""
from typing import TypedDict, Optional, List, Dict, Any


class BaseAgentState(TypedDict, total=False):
    """所有 Agent 的基类 State，预埋 user_context"""
    user_context: Dict[str, Any]


class QueryAgentState(BaseAgentState, total=False):
    """NL2SQL Agent State"""
    question: str
    schema_context: str
    forced_tables: List[str]
    spec_context: str
    domain: str
    domain_confidence: float
    domain_tables: List[str]
    sql: str
    validation_result: Dict[str, Any]
    query_result: Dict[str, Any]
    insight: Dict[str, Any]
    error: Optional[str]
    success: bool
    tables_used: List[str]
    columns: List[str]
    total: int
    confidence: float
    explanation: str


class RAGAgentState(BaseAgentState, total=False):
    """RAG Agent State"""
    question: str
    messages: List[Dict[str, Any]]
    context: str              # 原始检索上下文（含 [IMG] 标签）
    cleaned_context: str      # 预处理后上下文
    img_refs: Dict            # 图片引用表 {idx: {url, label}}
    answer: str
    sources: List[Dict[str, Any]]
    has_documents: bool
    best_relevance_score: float   # 检索最高分（reranker score 或 vector score）
    score_source: str             # 分数来源："rerank" | "vector"
    is_rejected: bool             # 标记本次为拒绝回复
    tool_calls: List[Any]
    error: Optional[str]


class MCPAgentState(BaseAgentState, total=False):
    """MCP Data Copilot Agent State

    Phase 2: 三层路由模型 (Layer A 在 Gateway, Layer B/C 在 graph_mcp)
    - Layer A: Gateway._check_mcp_eligibility() → 设置 eligibility 字段
    - Layer B: tool_filter_node → 按 domain 缩小候选 Tool 集
    - Layer C: tool_select_node → LLM 选择 1 个 Tool + 填参数
    """
    # ── 输入 ──
    question: str
    session_id: str

    # ── Layer A 传递 ──
    domain_hint: str                            # DomainClassifier 分类结果
    candidate_tool_names: List[str]             # Layer B 输出的候选 Tool 名列表

    # ── Tool Registry（Layer B 填充）──
    tool_registry_raw: List[Dict[str, Any]]     # 原始 Tool 列表（来自 McpClientManager）
    mcp_manager: Any                            # McpClientManager 实例（McpExecutor 注入）

    # ── Layer C 输出 ──
    selected_tool: str                          # 被选中的 Tool 名称
    tool_arguments: Dict[str, Any]              # LLM 提取的 Tool 参数

    # ── MCP 调用结果 ──
    mcp_raw_result: Dict[str, Any]              # MCP Server 原始返回
    tool_calls: List[Dict[str, Any]]            # 调用的 Tool 记录

    # ── 查询结果（映射后）──
    columns: List[str]                          # 英文原始列名
    rows: List[List[Any]]                       # 数据行
    total: int

    # ── 控制 ──
    success: bool
    error: Optional[str]
    error_code: Optional[str]
    clarification_needed: bool
    clarification_question: Optional[str]

    # ── 回退记录 ──
    bypass_reason: str                          # 跳过的原因（供可观测）


class PMSolutionState(BaseAgentState, total=False):
    """PM Solution Studio Agent State"""
    # 会话元数据
    session_id: str
    knowledge_id: Optional[str]
    session_title: str

    # 阶段编排
    current_stage: str                    # "problem"|"analysis"|"detail"|"prd"
    stage_order: List[str]                # ["problem","analysis","detail","prd"]

    # 当前交互（interrupt 恢复后设置）
    user_input: str
    user_action: str                      # "continue"|"confirm"

    # 检索结果
    context: str
    sources: List[Dict[str, Any]]
    need_retrieve: bool

    # 生成结果
    answer: str
    structured_output: Dict[str, Any]

    # 跨阶段累积（随检查点持久化，同时同步到 SQLAlchemy）
    stage_outputs: Dict[str, Dict]        # {stage_type: {output_data, summary, confirmed_at}}
    stage_chats: Dict[str, List[Dict]]    # {stage_type: [{role, content, sources}, ...]}
    session_topic: str                    # Phase1 提取的核心主题

    # 控制
    error: Optional[str]
    is_completed: bool
