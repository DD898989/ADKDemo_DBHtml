import os
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()

from adk_db_html_analyzer_py import run_db_pipeline_stream, test_db_connection_tool

st.set_page_config(
    page_title="MyADK - 資料庫智慧分析 Agent",
    page_icon="🤖",
    layout="wide"
)

# 視覺樣式
st.markdown("""
<style>
    .main-title { font-size: 2rem; font-weight: 700; color: #0F172A; }
    .sub-title { color: #475569; font-size: 1rem; margin-bottom: 1.2rem; }
    .agent-pill {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
        background-color: #EEF2FF;
        color: #4F46E5;
        border: 1px solid #C7D2FE;
        margin-bottom: 0.3rem;
    }
    .stDownloadButton > button { background-color: #10B981 !important; color: white !important; border: none !important; }
</style>
""", unsafe_allow_html=True)

# 狀態管理
if "final_html" not in st.session_state:
    st.session_state["final_html"] = None
if "logs" not in st.session_state:
    st.session_state["logs"] = []

# 各 Agent 圖示對照表
AGENT_ICONS = {
    "DBConnectionExpertAgent": "🔌",
    "SchemaAgent": "📋",
    "RelationAgent": "🔗",
    "SamplerAgent": "🔬",
    "SystemLogicWriterAgent": "✍️",
    "SQLValidationAgent": "🛡️",
    "HTMLReportAgent": "🌐",
    "ParallelDBExplorer": "⚡",
    "IterativeValidationLoop": "🔄",
    "CompleteDBToHTMLPipeline": "🚀"
}

# 預設 Port 對照表
DEFAULT_PORTS = {
    "PostgreSQL": 5432,
    "MySQL": 3306,
    "SQL Server": 1433,
    "Oracle": 1521,
    "MariaDB": 3306,
    "SQLite": 0,
    "其他": 5432
}

# ==========================================
# 側邊欄：API Key 與 資料庫連線參數表單
# ==========================================
with st.sidebar:
    st.title("⚙️ 連線與配置")

    # 1. API Key
    st.subheader("1. Gemini API 金鑰")
    current_key = os.getenv("GOOGLE_API_KEY", "")
    api_key_input = st.text_input(
        "GOOGLE_API_KEY",
        value=current_key,
        type="password",
        placeholder="請輸入 API Key",
        help="如本機 .env 已設定會自動讀取。"
    )
    if api_key_input:
        os.environ["GOOGLE_API_KEY"] = api_key_input
        st.success("API Key 已就緒", icon="🔑")
    else:
        st.warning("請先輸入有效的 GOOGLE_API_KEY。")

    st.markdown("---")

    # 2. 資料庫連線專家參數
    st.subheader("2. 資料庫連線參數")

    dbtype = st.selectbox(
        "資料庫類型 (dbtype)",
        ["PostgreSQL", "MySQL", "SQL Server", "Oracle", "MariaDB", "SQLite", "其他"],
        index=0
    )

    if dbtype == "SQLite":
        col_file, _ = st.columns([3, 1])
        host = ""
        port = 0
        username = ""
        password = ""
        database = st.text_input("SQLite 檔案路徑或名稱 (database)", value="mydb.sqlite")
    else:
        col_host, col_port = st.columns([2, 1])
        host = col_host.text_input("主機位址 (IP / Host)", value="localhost")
        default_port = DEFAULT_PORTS.get(dbtype, 5432)
        port = col_port.number_input("埠號 (Port)", value=default_port, min_value=1, max_value=65535)

        col_user, col_pwd = st.columns(2)
        username = col_user.text_input("帳號 (Username)", value="postgres" if dbtype == "PostgreSQL" else "root")
        password = col_pwd.text_input("密碼 (Password)", type="password")
        database = st.text_input("資料庫名稱 (Database)", value="my_database")

    # 側邊欄提供快速連線測試按鈕
    if st.button("⚡ 測試資料庫連線", use_container_width=True):
        diag_msg = test_db_connection_tool(
            dbtype=dbtype,
            host=host,
            port=port,
            username=username,
            password=password,
            database=database
        )
        if "【連線成功】" in diag_msg:
            st.success(diag_msg)
        else:
            st.info(diag_msg)

    # 額外結構補充 (選填)
    with st.expander("📝 補充資料庫結構/DDL (選填)"):
        extra_db_info = st.text_area(
            "補充說明",
            placeholder="若有現成 Table 清單或 DDL 可貼在此處...",
            height=100
        )

    st.markdown("---")
    st.subheader("3. Pipeline 執行流程")
    st.markdown("""
    - 🔌 **DBConnectionExpertAgent**：驗證連線參數並測試連線
    - 📋 **SchemaAgent**：讀取表格結構與欄位
    - 🔗 **RelationAgent**：分析外鍵與關聯
    - 🔬 **SamplerAgent**：數據抽樣與實體意義
    - ✍️ **SystemLogicWriterAgent**：推導業務模組與流程
    - 🛡️ **SQLValidationAgent**：驗證業務邏輯假設
    - 🌐 **HTMLReportAgent**：生成 Tailwind CSS 報告
    """)

# ==========================================
# 主畫面
# ==========================================
st.markdown('<div class="main-title">🤖 MyADK 資料庫智慧分析 Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">由「資料庫連線專家」率先驗證連線，協同多 Agent 探索架構並推導業務邏輯，最終產出美觀現代的 Tailwind CSS 單頁 HTML 報告。</div>', unsafe_allow_html=True)

# 指令輸入區
default_prompt = "請連線專家先檢驗目標資料庫通道，隨後由探索 Agent 分析所有表格結構、推導核心業務流程與關聯架構，最後生成排版美觀、具備 Tailwind CSS 的單頁 HTML 報告。"
user_prompt = st.text_area("📝 分析任務指示：", value=default_prompt, height=80)

col_run, _ = st.columns([1, 4])
with col_run:
    start_clicked = st.button("🚀 開始執行 Pipeline 分析", type="primary", use_container_width=True)

if start_clicked:
    if not os.getenv("GOOGLE_API_KEY"):
        st.error("❌ 請先在左側填入有效的 GOOGLE_API_KEY！")
    else:
        st.session_state["final_html"] = None
        st.session_state["logs"] = []

        conn_dict = {
            "dbtype": dbtype,
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "database": database
        }

        status_box = st.status("🔄 Agent Pipeline 協同作業中...", expanded=True)
        log_view = status_box.empty()

        try:
            for agent_name, text, html_candidate in run_db_pipeline_stream(
                user_prompt=user_prompt,
                connection_params=conn_dict,
                extra_db_info=extra_db_info if 'extra_db_info' in locals() else ""
            ):
                if text:
                    icon = AGENT_ICONS.get(agent_name, "🤖")
                    st.session_state["logs"].append({
                        "agent": agent_name,
                        "icon": icon,
                        "text": text
                    })
                    latest = st.session_state["logs"][-4:]
                    log_view.markdown("\n\n".join([f"**{item.get('icon', '🤖')} [{item['agent']}]**\n{item['text']}" for item in latest]))
                if html_candidate:
                    st.session_state["final_html"] = html_candidate

            status_box.update(label="🎉 分析完成！", state="complete", expanded=False)
            st.rerun()
        except Exception as e:
            status_box.update(label="❌ 執行失敗", state="error", expanded=True)
            st.error(f"錯誤：{e}")

# 結果分頁
tab_report, tab_source, tab_logs = st.tabs(["🌐 HTML 報告預覽", "💻 HTML 原始碼", "📋 完整 Agent 歷程"])

with tab_report:
    if st.session_state["final_html"]:
        st.success("報告生成完畢！")
        components.html(st.session_state["final_html"], height=850, scrolling=True)
    else:
        st.info("尚未執行分析。請在左側填寫資料庫連線參數後點擊「開始執行 Pipeline 分析」。")

with tab_source:
    if st.session_state["final_html"]:
        st.download_button(
            "📥 下載報告 (database_report.html)",
            data=st.session_state["final_html"],
            file_name="database_report.html",
            mime="text/html"
        )
        st.code(st.session_state["final_html"], language="html")
    else:
        st.caption("暫無原始碼。")

with tab_logs:
    if st.session_state["logs"]:
        for log in st.session_state["logs"]:
            with st.chat_message("assistant", avatar=log.get("icon", "🤖")):
                st.markdown(f'<span class="agent-pill">{log.get("icon", "🤖")} {log["agent"]}</span>', unsafe_allow_html=True)
                st.markdown(log["text"])
    else:
        st.caption("暫無日誌。")
