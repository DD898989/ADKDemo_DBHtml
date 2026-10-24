# MyADK - 資料庫智慧分析與視覺化報告系統

基於 Google GenAI **Agent Development Kit (ADK)** 與 **Gemini 2.5 Pro** 的多 Agent 協同資料庫分析系統。
由第一階段的**「資料庫連線專家」**率先接收連線資訊並測試通道，隨後由探索 Agent 分析 Schema、關聯與數據樣貌，再由業務專家迭代推導業務邏輯並驗證，最終生成美觀現代的 Tailwind CSS 單頁 HTML 分析報告。

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

### 3. 啟動前端介面

```bash
streamlit run app.py
```

啟動後於瀏覽器開啟 `http://localhost:8501`。

---

## 介面功能特色

1. **資料庫連線專家表單**：
   - 側邊欄提供專門表單輸入 `dbtype`（PostgreSQL、MySQL、SQL Server、Oracle、SQLite 等）、`IP/Host`、`Port`、`Username`、`Password` 與 `Database`。
   - 附帶「測試資料庫連線」按鈕可立即測試網路通道通訊。
2. **即時 Agent 執行監控**：
   - 即時標記各 Agent 身分（`DBConnectionExpertAgent`、`SchemaAgent`、`RelationAgent`、`SamplerAgent`、`SystemLogicWriterAgent`、`SQLValidationAgent`、`HTMLReportAgent`）。
3. **成果展示**：
   - **互動 HTML 報告預覽**：直接渲染 Tailwind CSS 網頁。
   - **HTML 原始碼與下載**：一鍵下載單頁 HTML 報告檔案 (`database_report.html`)。
