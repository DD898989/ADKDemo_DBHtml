# MyADK - 資料庫智慧分析與視覺化報告系統

基於 Google GenAI **Agent Development Kit (ADK)** 與 **Gemini 2.5 Pro** 的多 Agent 協同資料庫分析系統。
由第一階段的**「資料庫連線專家」**率先接收連線資訊並測試通道，隨後由探索 Agent 分析 Schema、關聯與數據樣貌，再由業務專家迭代推導業務邏輯並驗證，最終生成美觀現代的 Tailwind CSS 單頁 HTML 分析報告。

本專案符合 Google ADK 官方規範，同時支援 **官方視覺化 ADK Web UI**（提供互動式拓撲 Workflow 圖與節點詳情）以及 **客製化 Streamlit 儀表板**（提供完整連線表單與 HTML 報告即時預覽）。

---

## 🏗️ 系統架構 (Agent Pipeline)

本系統採用 `SequentialAgent` 依序串接四個主要階段：

```
[SequentialAgent: CompleteDBToHTMLPipeline]
   │
   ├── 0. 階段零：連線專家 (DBConnectionExpertAgent)
   │     └── 接收 dbtype, host/ip, port, username, password, database
   │         調用 test_db_connection_tool 驗證連線通道
   │
   ├── 1. 階段一：平行探索 (ParallelDBExplorer)
   │     ├── SchemaAgent: 讀取資料表名稱、欄位與資料型態 (get_schema_tool)
   │     ├── RelationAgent: 分析資料表主鍵 (PK) 與外鍵 (FK) 關聯性 (get_relations_tool)
   │     └── SamplerAgent: 對核心表格抽樣少量資料 (get_sample_data_tool)
   │
   ├── 2. 階段二：迭代驗證 (IterativeValidationLoop)
   │     ├── SystemLogicWriterAgent: 根據探索結果推導系統業務功能與架構
   │     └── SQLValidationAgent: 編寫並執行唯讀 SQL 驗證邏輯假設 (run_read_only_sql_tool)
   │                             驗證通過則呼叫 exit_loop 結束迭代
   │
   └── 3. 階段三：報告生成 (HTMLReportAgent)
         └── 將綜合推導結果包裝為單一、內建 Tailwind CSS 的美觀互動 HTML 報告
```

---

## 📁 專案目錄結構

```text
MyADK/
├── db_analyzer_agent/           # 符合 Google ADK 規範的 Agent 模組
│   ├── __init__.py              # 匯出 agent 模組
│   └── agent.py                 # 定義 Tools、Pipeline 與 root_agent 進入點
├── adk_db_html_analyzer_py.py   # 向後相容層 (轉發 db_analyzer_agent.agent)
├── app.py                       # Streamlit 前端應用程式
├── RUN.bat                      # 啟動 Streamlit 介面
├── RUN_ADK_WEB.bat              # 啟動 Google ADK 官方 Web UI
├── requirements.txt             # 專案相依套件清單
└── README.md
```

---

## 🚀 快速開始

### 1. 安裝相依套件

```bash
pip install -r requirements.txt
```

### 2. 設定 Gemini API 金鑰

於 `.env` 中設定（或直接在網頁側邊欄輸入）：
```env
GOOGLE_API_KEY="您的_GEMINI_API_KEY"
```

---

## 🖥️ 兩種運行模式

### 模式 A：Google ADK 官方 Web UI (推薦用於架構觀察與節點除錯)

提供互動式 **Workflow 拓撲圖** 與 **節點檢查器 (Node Inspector)**：

```bash
adk web .
```
或雙擊執行 `RUN_ADK_WEB.bat`。

* 開啟瀏覽器訪問：`http://localhost:8000`
* **特色**：
  - 完整展示 SequentialAgent、ParallelDBExplorer (平行分支)、IterativeValidationLoop (迴圈) 之 Workflow 圖。
  - 點擊任何 Agent 或 Tool 節點，可在右側檢視 Prompt (Instruction)、模型 (Model)、綁定工具 (Tools) 與執行 Trace。

---

### 模式 B：Streamlit 業務儀表板 (推薦用於終端用戶與產出報告)

提供直覺的資料庫連線參數表單與單頁 HTML 報告渲染：

```bash
streamlit run app.py
```
或雙擊執行 `RUN.bat`。

* 開啟瀏覽器訪問：`http://localhost:8501`
* **特色**：
  - **資料庫連線專家表單**：側邊欄快速配置 PostgreSQL、MySQL、SQL Server、Oracle、SQLite 等連線參數，並提供連線測試按鈕。
  - **即時串流監控**：即時查看各 Agent 執行動態。
  - **HTML 報告預覽與下載**：直接在頁面上預覽 Tailwind CSS 報告並一鍵下載 `database_report.html`。
