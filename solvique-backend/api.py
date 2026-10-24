"""Solvique — Enterprise AI Analytics & Intelligence Platform FastAPI backend."""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

load_dotenv()

from src.conversation_store import close_db, init_db
from src.logging_config import get_logger
from src.schemas.api_models import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
    ReportSection,
    VisualizeRequest,
    VisualizeResponse,
)
from src.services.chat_service import handle_chat
from src.services.conversation_service import (
    handle_delete_conversation,
    handle_get_conversation,
    handle_list_conversations,
)
from src.services.report_service import (
    create_report_docx,
    get_report_asset_bytes,
    get_report_preview_sections,
)
from src.services.visualization_service import handle_visualize

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Solvique API server starting up.")
    yield
    close_db()
    logger.info("Solvique API server shutting down.")


app = FastAPI(title="Solvique API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "solvique-backend", "version": "2.0.0"}


@app.get("/")
def root():
    return {
        "service": "Solvique API",
        "version": "2.0.0",
        "docs_url": "/docs",
        "status": "online",
    }


@app.post("/api/chat", response_model=list[ChatResponse])
def chat(req: ChatRequest):
    return handle_chat(req)


@app.get("/api/conversations", response_model=list[ConversationSummary])
def get_conversations():
    return handle_list_conversations()


@app.get("/api/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(conv_id: str):
    return handle_get_conversation(conv_id)


@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: str):
    return handle_delete_conversation(conv_id)


@app.get("/api/conversations/{conversation_id}/report.docx")
def get_report_docx(conversation_id: str):
    return Response(
         content=create_report_docx(conversation_id),
         media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         headers={
             "Content-Disposition": f'attachment; filename="{conversation_id}-report.docx"'
         },
    )


@app.get("/api/conversations/{conversation_id}/report/preview", response_model=list[ReportSection])
def get_report_preview(conversation_id: str):
    return get_report_preview_sections(conversation_id)


@app.get("/api/report-assets/{asset_id}")
def get_report_asset_file(asset_id: str):
    return Response(get_report_asset_bytes(asset_id), media_type="image/png")


@app.post("/api/visualize", response_model=VisualizeResponse)
def visualize(req: VisualizeRequest):
    return handle_visualize(req)

