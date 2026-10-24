# 📊 Solvique — AI Analytics & Decision Intelligence
### *An AI-powered workspace for turning business questions into data-backed decisions*

[![Live Application](https://img.shields.io/badge/Demo-Live%20Application-brightgreen?style=for-the-badge&logo=googlecloud)](https://solvique-frontend-65499697760.asia-south1.run.app/)
[![Angular 19](https://img.shields.io/badge/Frontend-Angular%2019-DD0031?style=for-the-badge&logo=angular)](https://angular.dev/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![BigQuery](https://img.shields.io/badge/Data-BigQuery-4285F4?style=for-the-badge&logo=googlebigquery)](https://cloud.google.com/bigquery)

---

## 🌐 Live Application & Video Walkthrough

> ### 🚀 **[Open the Solvique application](https://solvique-frontend-65499697760.asia-south1.run.app/)**

### 🎬 System Overview & Demo Walkthrough

<!-- Add a screen recording link or place a recording such as assets/solvique-overview.mp4 in the repository. -->

> 📹 **[Add the Solvique overview recording link here](YOUR_SCREEN_RECORDING_URL)**

---

## 🎯 1. Project Goal & Business Value

### The Challenge

Business data is often difficult to explore without SQL skills, specialist tools, or support from an analytics team. Relevant context may also live in documents, while forecasts and findings are produced in separate workflows. This makes it harder for teams to move from a business question to a clear, shareable decision.

### The Solution

Solvique brings conversational analytics, document search, predictive modeling, interactive data exploration, and report creation into one workspace. Users can ask a question in natural language, inspect the resulting analysis, and share key findings through an executive-ready report.

---

## 🏛️ 2. Key System Capabilities

- **Conversational analytics**: Ask business questions in natural language and receive answers grounded in analytical results.
- **BigQuery data exploration**: Generate and execute SQL queries against connected business data.
- **Forecasting and machine learning**: Request forecasts and classification insights using available models.
- **Document search**: Retrieve relevant context from reference documents using retrieval-augmented generation (RAG).
- **Interactive Data Studio**: Inspect result tables, explore charts, refine visualizations, and export data.
- **Executive reporting**: Preview analysis as a structured report with summaries, tables, and visualizations; export it as a Word document.
- **Conversation history**: Revisit and continue previous analyses.

---

## 🧭 3. Product Workspaces

| Workspace | Purpose |
| :--- | :--- |
| **Assistant** | Start an analysis, query business data, ask for a forecast, or search reference documents. |
| **Data Studio** | Explore returned datasets through tables and interactive visualizations, then export results. |
| **Report Center** | Review findings in a report layout and export the analysis for sharing. |

---

## ⚙️ 4. Application Architecture

```text
┌─────────────────────────────────────┐
│       Angular 19 Web Application    │
│ Assistant · Data Studio · Reports   │
└──────────────────┬──────────────────┘
                   │ REST API
                   ▼
┌─────────────────────────────────────┐
│          FastAPI Backend            │
│ AI workflows · analytics · reports  │
└─────────┬──────────┬──────────┬─────┘
          │          │          │
          ▼          ▼          ▼
      BigQuery   ML models   Document search
                             & reporting tools
```

The Angular frontend provides the application experience and communicates with the FastAPI backend over a REST API. The backend coordinates query generation and execution, AI workflows, model inference, document retrieval, visualization, and report generation.

---

## 📂 5. Repository Structure

```text
solvique/
├── solvique-frontend/             # Angular web application
│   └── src/app/
│       ├── core/                  # Shared application services
│       ├── features/chat/         # Assistant, Data Studio, and Report Center
│       └── shared/                # Shared interfaces and components
│
├── solvique-backend/              # FastAPI analytics API
│   ├── api.py                     # API application and routes
│   ├── graph.py                   # AI workflow orchestration
│   └── src/
│       ├── ml_tool_utils/         # Forecasting and model inference
│       ├── rag_tool_utils/        # Document retrieval utilities
│       ├── reporting/             # Report generation
│       ├── services/              # Application services
│       ├── sql_tool_utils/        # SQL and data query utilities
│       ├── tools/                 # AI workflow tools
│       └── visualization_tool/    # Interactive chart generation
│
└── README.md                      # Project overview
```

---

## 👨‍💻 6. Project Summary

- **Product**: AI-powered analytics and decision intelligence workspace
- **Frontend**: Angular 19
- **Backend**: FastAPI and Python
- **Data analytics**: BigQuery
- **AI capabilities**: Natural-language workflows, document retrieval, and machine-learning inference
- **Application**: [solvique-frontend-65499697760.asia-south1.run.app](https://solvique-frontend-65499697760.asia-south1.run.app/)
