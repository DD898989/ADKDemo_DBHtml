import os
import re
import json
from urllib.parse import quote_plus
from typing import Generator, Tuple, Optional
from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = os.environ.get("GOOGLE_GENAI_MODEL", "gemini-2.5-pro")

from sqlalchemy import create_engine, inspect, text
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.loop_agent import LoopAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.tools.exit_loop_tool import exit_loop
from google.adk.runners import InMemoryRunner
from google.genai import types

# 全域連線引擎（連線成功後保存，供後續 Agent 真實讀取）
_ACTIVE_ENGINE = None


# ==========================================
# 資料庫連線字串組裝與真實身分驗證
# ==========================================
def build_db_url(
    dbtype: str,
    host: str,
    port: int,
    username: str = "",
    password: str = "",
    database: str = ""
) -> str:
    """根據資料庫類型與認證參數，組裝標準 SQLAlchemy 連線字串。"""
    clean_dbtype = (dbtype or "").strip().lower()
    u = quote_plus(str(username or "").strip())
    p = quote_plus(str(password or "").strip())
    h = (host or "localhost").strip()
    d = (database or "").strip()

    if "sqlite" in clean_dbtype:
        db_path = d or h
        return f"sqlite:///{db_path}" if db_path else "sqlite:///:memory:"

    auth = f"{u}:{p}@" if u else ""

    if "postgres" in clean_dbtype:
        pt = int(port or 5432)
        return f"postgresql+psycopg2://{auth}{h}:{pt}/{d}"

    if "mysql" in clean_dbtype or "mariadb" in clean_dbtype:
        pt = int(port or 3306)
        return f"mysql+pymysql://{auth}{h}:{pt}/{d}"

    if "oracle" in clean_dbtype:
        pt = int(port or 1521)
        return f"oracle+oracledb://{auth}{h}:{pt}/?service_name={d}"

    if "sqlserver" in clean_dbtype or "mssql" in clean_dbtype:
        pt = int(port or 1433)
        return f"mssql+pymssql://{auth}{h}:{pt}/{d}"

    return f"{clean_dbtype}://{auth}{h}:{port}/{d}"


def test_db_connection_tool(
    dbtype: str,
    host: str,
    port: int,
    username: str = "",
    password: str = "",
    database: str = ""
) -> str:
    """
    真實測試資料庫登入與認證狀態。
    發送認證協定握手並執行 SELECT 1 檢驗帳號、密碼與資料庫名稱是否正確。
    """
    global _ACTIVE_ENGINE

    clean_dbtype = (dbtype or "").strip()
    clean_host = (host or "localhost").strip()
    clean_db = (database or "").strip()

    # SQLite 特別檢驗
    if "sqlite" in clean_dbtype.lower():
        target_path = clean_db or clean_host
        if not target_path or not os.path.exists(target_path):
            _ACTIVE_ENGINE = None
            return f"【連線失敗】指定的 SQLite 資料庫檔案不存在：'{target_path or '(未指定)'}'"
        try:
            url = f"sqlite:///{target_path}"
            engine = create_engine(url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            _ACTIVE_ENGINE = engine
            return f"【連線成功】SQLite 資料庫檔案驗證通過，檔案已成功掛載：{target_path}"
        except Exception as e:
            _ACTIVE_ENGINE = None
            return f"【連線失敗】開啟 SQLite 資料庫出錯：{str(e)}"

    # 必須提供資料庫名稱
    if not clean_db:
        _ACTIVE_ENGINE = None
        return "【連線失敗】未提供「資料庫名稱 (database)」，請填寫要登入的具體資料庫。"

    try:
        url = build_db_url(clean_dbtype, clean_host, port, username, password, clean_db)
        connect_args = {}
        if "sqlite" not in clean_dbtype.lower():
            connect_args["connect_timeout"] = 4

        # 建立引擎並實際嘗試連線與驗證
        engine = create_engine(url, connect_args=connect_args)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            try:
                ver_row = conn.execute(text("SELECT version()")).fetchone()
                ver = str(ver_row[0]) if ver_row else "正常"
            except Exception:
                ver = "認證通過"

        _ACTIVE_ENGINE = engine
        return (
            f"【連線成功】真實資料庫認證通過！\n"
            f"- 資料庫類型: {clean_dbtype}\n"
            f"- 目標主機: {clean_host}:{port}\n"
            f"- 資料庫名稱: {clean_db}\n"
            f"- 登入帳號: {username}\n"
            f"- 伺服器回傳: {ver[:80]}"
        )
    except Exception as e:
        _ACTIVE_ENGINE = None
        err_msg = str(e).strip()
        # 提煉核心錯誤訊息避免冗長 traceback
        if "password authentication failed" in err_msg or "Access denied" in err_msg:
            return f"【連線失敗】密碼認證失敗！使用者 '{username}' 無法以此密碼登入目標資料庫。"
        elif "does not exist" in err_msg or "Unknown database" in err_msg:
            return f"【連線失敗】找不到資料庫！伺服器上不存在名稱為 '{clean_db}' 的資料庫。"
        elif "timed out" in err_msg or "timeout" in err_msg:
            return f"【連線失敗】連線逾時！無法連線至 {clean_host}:{port}，請確認主機位址與連接埠是否正確或有防火牆阻擋。"
        else:
            return f"【連線失敗】資料庫登入發生錯誤：\n{err_msg}"


def get_schema_tool() -> str:
    """負責讀取資料庫中所有表格名稱、欄位名稱與資料型態。"""
    global _ACTIVE_ENGINE
    if _ACTIVE_ENGINE is None:
        return "連線尚未建立或驗證未通過，無法讀取資料庫結構。"

    try:
        insp = inspect(_ACTIVE_ENGINE)
        tables = insp.get_table_names()
        if not tables:
            return "資料庫連線成功，但該資料庫中未發現任何資料表。"

        lines = []
        for t in tables[:25]:
            cols = insp.get_columns(t)
            pk_cols = set(insp.get_pk_constraint(t).get("constrained_columns", []))
            cols_desc = [
                f"{c['name']} ({c['type']}){' [PK]' if c['name'] in pk_cols else ''}"
                for c in cols
            ]
            lines.append(f"表格: {t}\n  欄位: {', '.join(cols_desc)}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"讀取資料庫 Schema 失敗：{e}"


def get_relations_tool() -> str:
    """負責分析資料表之間的主鍵（PK）與外鍵（FK）關聯性。"""
    global _ACTIVE_ENGINE
    if _ACTIVE_ENGINE is None:
        return "連線尚未建立，無法讀取外鍵關聯。"

    try:
        insp = inspect(_ACTIVE_ENGINE)
        tables = insp.get_table_names()
        relations = []
        for t in tables:
            fks = insp.get_foreign_keys(t)
            for fk in fks:
                ref_tbl = fk.get("referred_table")
                for col, ref_col in zip(fk.get("constrained_columns", []), fk.get("referred_columns", [])):
                    relations.append(f"{t}.{col} -> {ref_tbl}.{ref_col}")

        if not relations:
            return "該資料庫未建立實體 Foreign Key 鍵值限制，需依欄位命名慣例（如 xxx_id）推測關聯。"
        return "實體外鍵關聯清單：\n" + "\n".join(f"- {r}" for r in relations)
    except Exception as e:
        return f"讀取外鍵關聯失敗：{e}"


def get_sample_data_tool(table_name: str, limit: int = 5) -> str:
    """負責對指定表格進行少量資料抽樣，觀察真實資料樣貌。"""
    global _ACTIVE_ENGINE
    if _ACTIVE_ENGINE is None:
        return f"連線尚未建立，無法抽樣表格 {table_name}。"

    try:
        with _ACTIVE_ENGINE.connect() as conn:
            result = conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT {int(limit)}'))
            rows = result.fetchall()
            keys = list(result.keys())
            data = [dict(zip(keys, row)) for row in rows]
            return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return f"抽樣表格 {table_name} 失敗：{e}"


def run_read_only_sql_tool(query: str) -> str:
    """編寫並執行唯讀 SQL 來驗證業務邏輯假設。"""
    global _ACTIVE_ENGINE
    if _ACTIVE_ENGINE is None:
        return f"連線尚未建立，無法執行驗證 SQL: {query}"

    cleaned = query.strip()
    if not cleaned.upper().startswith("SELECT"):
        return "安全性限制：僅允許執行唯讀 SELECT 驗證查詢。"

    try:
        with _ACTIVE_ENGINE.connect() as conn:
            result = conn.execute(text(cleaned))
            rows = result.fetchmany(10)
            keys = list(result.keys())
            data = [dict(zip(keys, row)) for row in rows]
            return f"SQL 執行成功，取得 {len(data)} 筆資料：\n{json.dumps(data, ensure_ascii=False, indent=2, default=str)}"
    except Exception as e:
        return f"SQL 執行錯誤：{e}"


# ==========================================
# 階段零：DBConnectionExpertAgent (資料庫連線專家)
# ==========================================
connection_expert_agent = LlmAgent(
    name="DBConnectionExpertAgent",
    model=MODEL_NAME,
    description="負責接收連線參數並調用工具驗證資料庫通道狀態的專家。",
    instruction="""
    你是資深的資料庫連線與環境診斷專家 (DBConnectionExpertAgent)。
    【核心任務】：
    1. 接收使用者提供的連線參數（dbtype, host/ip, port, username, password, database 等）。
    2. 調用 `test_db_connection_tool` 工具進行真實資料庫認證與登入測試。
    3. 根據工具返回的診斷結果進行分析報告：
       - 若回傳「【連線成功】」，請清楚列出資料庫型態、目標主機、資料庫名稱與版本，並正式宣告通道已就緒，交棒給下一階段的探索 Agent。
       - 若回傳「【連線失敗】」，請明確指出失敗原因（例如帳號密碼錯誤、資料庫不存在、或伺服器逾時），提醒使用者需修正連線設定。
    4. 切勿憑空猜測連線成功，嚴格以工具實際回傳結果為準。
    """,
    tools=[test_db_connection_tool]
)

# ==========================================
# 階段一：ParallelAgent (平行資料庫探索)
# ==========================================
schema_agent = LlmAgent(
    name="SchemaAgent",
    model=MODEL_NAME,
    description="調用 get_schema_tool 讀取資料表名稱、欄位與資料型態。",
    instruction=(
        "你是負責分析資料庫架構的專家。請調用 `get_schema_tool` 工具讀取已連線資料庫的結構，"
        "整理並明確列出所有資料表名稱、欄位與資料型態。"
        "請自主完成結構分析並直接輸出分析結果，切勿反問使用者。"
    ),
    tools=[get_schema_tool]
)

relation_agent = LlmAgent(
    name="RelationAgent",
    model=MODEL_NAME,
    description="調用 get_relations_tool 分析外鍵與關聯性。",
    instruction=(
        "你是負責資料表關聯性分析的專家。請調用 `get_relations_tool` 工具獲取外鍵限制，"
        "並依據資料表與欄位名稱（例如 user_id, order_id 等），明確推導並列出資料表之間的關聯（如 1對多、多對多）。"
        "請直接輸出關聯分析報告，切勿反問使用者。"
    ),
    tools=[get_relations_tool]
)

sampler_agent = LlmAgent(
    name="SamplerAgent",
    model=MODEL_NAME,
    description="調用 get_sample_data_tool 抽樣真實資料並說明欄位意義。",
    instruction=(
        "你是資料抽樣與業務樣貌分析專家。請對核心表格調用 `get_sample_data_tool` 工具進行抽樣，"
        "說明各表格代表的實體資料樣貌與欄位意義。"
        "請直接輸出抽樣數據分析，切勿反問使用者。"
    ),
    tools=[get_sample_data_tool]
)

parallel_explore = ParallelAgent(
    name="ParallelDBExplorer",
    description="平行調度 SchemaAgent、RelationAgent 與 SamplerAgent 同步進行多維度探索。",
    sub_agents=[schema_agent, relation_agent, sampler_agent]
)

# ==========================================
# 階段二：LoopAgent (迭代推導與 SQL 驗證)
# ==========================================
writer_agent = LlmAgent(
    name="SystemLogicWriterAgent",
    model=MODEL_NAME,
    description="根據探索結果推導系統業務架構、模組與流程，提出假設。",
    instruction=(
        "根據探索階段收集到的資料庫結構與關聯，深入推導並撰寫該系統對應的業務模組架構、"
        "核心功能以及業務運作流程。請提出具體的業務邏輯假設供 SQL 驗證。"
    )
)

tester_agent = LlmAgent(
    name="SQLValidationAgent",
    model=MODEL_NAME,
    description="編寫唯讀 SQL 進行實體驗證，驗證通過則呼叫 exit_loop 結束迴圈。",
    instruction=(
        "根據 WriterAgent 提出的業務功能假設，編寫關鍵驗證 SQL 並調用 `run_read_only_sql_tool` 進行驗證。"
        "只要推論合乎資料庫邏輯架構，請呼叫 exit_loop 結束迴圈，以順利將成果傳遞給下一個階段；"
        "若有需微調之處請給出精簡建議。"
    ),
    tools=[run_read_only_sql_tool, exit_loop]
)

iterative_loop = LoopAgent(
    name="IterativeValidationLoop",
    description="由業務推導專家與 SQL 驗證專家進行迭代驗證，驗證完畢後退出迴圈。",
    sub_agents=[writer_agent, tester_agent],
    max_iterations=2
)

# ==========================================
# 階段三：HTML Report Agent (專門負責 HTML 輸出)
# ==========================================
html_report_agent = LlmAgent(
    name="HTMLReportAgent",
    model=MODEL_NAME,
    description="整合所有分析成果，生成現代 Tailwind CSS 單頁視覺化 HTML 報告。",
    instruction="""
    你是專業的網頁前端工程師與技術文案編輯。
    請接收前面所有 Agent 分析出來的「連線資訊、系統架構、資料表關聯與業務邏輯」，將其整合為一份【完整、單一檔案且視覺美觀】的 HTML 網頁。

    【輸出要求】：
    1. 使用 Tailwind CSS (CDN: https://cdn.tailwindcss.com) 進行排版與配色，設計需現代俐落、層次清晰。
    2. 頁面需包含以下區塊：
       - 頁首區：系統名稱、資料庫類型、目標伺服器與分析時間。
       - 核心業務模組：以 Grid / Card 呈現推導出的核心業務功能。
       - 資料庫實體關聯 (ER Summary)：視覺化整理資料表之間的關聯性。
       - 關鍵邏輯與 SQL 驗證：展示經過驗證的核心業務推論。
    3. 直接輸出完整的 HTML 程式碼片段（以 <!DOCTYPE html> 開頭至 </html> 結尾），不要包裹額外的說明或客套話。
    """
)

# ==========================================
# 最終 pipeline 串接 (SequentialAgent)
# ==========================================
db_analysis_pipeline = SequentialAgent(
    name="CompleteDBToHTMLPipeline",
    description="完整的資料庫分析 Pipeline：連線驗證 -> 平行結構探索 -> 迭代業務推導與驗證 -> 生成 HTML 報告。",
    sub_agents=[
        connection_expert_agent,  # 0. 連線專家：真實認證帳密與資料庫
        parallel_explore,         # 1. 平行探索：真實讀取 Schema, 外鍵與抽樣
        iterative_loop,           # 2. 業務推導與驗證：Writer + Tester (真實執行 SQL)
        html_report_agent         # 3. HTML 報告生成
    ]
)

# ADK CLI 規範的 root_agent 進入點
root_agent = db_analysis_pipeline


def extract_html(raw_text: str) -> str:
    """從文字中提取純 HTML 內容。"""
    pattern = r"```(?:html)?\s*(<!DOCTYPE html[\s\S]*?|<html>[\s\S]*?|<div[\s\S]*?)```"
    match = re.search(pattern, raw_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    doc_index = raw_text.find("<!DOCTYPE")
    if doc_index != -1:
        end_index = raw_text.rfind("</html>")
        if end_index != -1:
            return raw_text[doc_index : end_index + 7].strip()
        return raw_text[doc_index:].strip()

    html_index = raw_text.find("<html")
    if html_index != -1:
        end_index = raw_text.rfind("</html>")
        if end_index != -1:
            return raw_text[html_index : end_index + 7].strip()
        return raw_text[html_index:].strip()

    return raw_text.strip()


def run_db_pipeline_stream(
    user_prompt: str,
    connection_params: Optional[dict] = None,
    extra_db_info: str = ""
) -> Generator[Tuple[str, str, Optional[str]], None, None]:
    """執行分析 Pipeline 並即時串流事件。"""
    app_name = "DBAnalysisApp"
    runner = InMemoryRunner(app_name=app_name, agent=db_analysis_pipeline)
    session_id = f"session_{os.urandom(4).hex()}"
    runner.session_service.create_session_sync(
        app_name=app_name,
        user_id="web_user",
        session_id=session_id
    )

    conn_text = ""
    if connection_params:
        conn_text = (
            "【資料庫連線參數】：\n"
            f"- dbtype: {connection_params.get('dbtype', '')}\n"
            f"- host: {connection_params.get('host', '')}\n"
            f"- port: {connection_params.get('port', '')}\n"
            f"- username: {connection_params.get('username', '')}\n"
            f"- password: {connection_params.get('password', '')}\n"
            f"- database: {connection_params.get('database', '')}\n"
        )

    full_prompt = (
        f"{conn_text}\n"
        f"【額外架構或結構補充資訊】：\n{extra_db_info.strip()}\n\n"
        f"【分析任務指示】：\n{user_prompt}"
    )

    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=full_prompt)]
    )

    final_html = ""

    for event in runner.run(
        user_id="web_user",
        session_id=session_id,
        new_message=content
    ):
        agent_name = (
            getattr(event, "author", None)
            or getattr(event, "source", None)
            or "Agent"
        )

        text = ""
        if hasattr(event, "content") and event.content:
            parts = getattr(event.content, "parts", [])
            for p in parts:
                if hasattr(p, "text") and p.text:
                    text += p.text
                elif hasattr(p, "function_call") and p.function_call:
                    fc = p.function_call
                    text += f"🔧 [工具調用] {fc.name}({getattr(fc, 'args', '')})\n"
                elif hasattr(p, "function_response") and p.function_response:
                    fr = p.function_response
                    text += f"💡 [工具回應] {fr.name}: {getattr(fr, 'response', '')}\n"

        if not text and hasattr(event, "text") and event.text:
            text = str(event.text)

        if "HTMLReportAgent" in str(agent_name) and text:
            final_html += text

        yield (str(agent_name), text, extract_html(final_html) if final_html else None)
