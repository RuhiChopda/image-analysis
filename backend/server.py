from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Body
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import io
import json
import asyncio

from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from chromadb.config import Settings
from emergentintegrations.llm.chat import LlmChat, UserMessage
from sentence_transformers import SentenceTransformer

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# ChromaDB setup
chroma_client = chromadb.PersistentClient(
    path="/app/backend/chroma_data",
    settings=Settings(anonymized_telemetry=False)
)
collection = chroma_client.get_or_create_collection(
    name="student_documents",
    metadata={"hnsw:space": "cosine"}
)

# Local embedding model (fallback due to network constraints)
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

# LLM setup
LLM_API_KEY = os.environ.get('EMERGENT_LLM_KEY')

app = FastAPI()
api_router = APIRouter(prefix="/api")

# Models
class Document(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    file_type: str
    chunk_count: int
    upload_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: str
    content: str
    sources: Optional[List[str]] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class QueryRequest(BaseModel):
    query: str
    session_id: str

class FAQItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str
    answer: str
    category: str

# Helper functions
async def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings using local sentence-transformers model"""
    try:
        # Use local model to avoid network issues
        embeddings = embedding_model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
    except Exception as e:
        logging.error(f"Error generating embeddings: {e}")
        raise

def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF bytes"""
    try:
        pdf_file = io.BytesIO(file_content)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        logging.error(f"Error extracting PDF text: {e}")
        raise

def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[str]:
    """Split text into chunks"""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    chunks = text_splitter.split_text(text)
    return chunks

# Routes
@api_router.get("/")
async def root():
    return {"message": "Student Study Assistant API"}

@api_router.post("/upload-document", response_model=Document)
async def upload_document(file: UploadFile = File(...)):
    """Upload and process a PDF document"""
    try:
        if not file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
        # Read file content
        content = await file.read()
        
        # Extract text
        text = extract_text_from_pdf(content)
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="No text found in PDF")
        
        # Chunk text
        chunks = chunk_text(text)
        
        # Generate embeddings
        embeddings = await generate_embeddings(chunks)
        
        # Store in ChromaDB
        doc_id = str(uuid.uuid4())
        chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        
        collection.add(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=[{"filename": file.filename, "doc_id": doc_id, "chunk_index": i} for i in range(len(chunks))]
        )
        
        # Save document metadata to MongoDB
        doc = Document(
            id=doc_id,
            filename=file.filename,
            file_type="pdf",
            chunk_count=len(chunks)
        )
        doc_dict = doc.model_dump()
        doc_dict['upload_date'] = doc_dict['upload_date'].isoformat()
        await db.documents.insert_one(doc_dict)
        
        return doc
    except Exception as e:
        logging.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/documents", response_model=List[Document])
async def get_documents():
    """Get all uploaded documents"""
    try:
        docs = await db.documents.find({}, {"_id": 0}).to_list(1000)
        for doc in docs:
            if isinstance(doc['upload_date'], str):
                doc['upload_date'] = datetime.fromisoformat(doc['upload_date'])
        return docs
    except Exception as e:
        logging.error(f"Error fetching documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and its chunks"""
    try:
        # Delete from ChromaDB
        results = collection.get(where={"doc_id": doc_id})
        if results['ids']:
            collection.delete(ids=results['ids'])
        
        # Delete from MongoDB
        await db.documents.delete_one({"id": doc_id})
        
        return {"message": "Document deleted successfully"}
    except Exception as e:
        logging.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/query")
async def query_documents(request: QueryRequest):
    """Query documents using RAG"""
    try:
        # Generate query embedding
        query_embedding = (await generate_embeddings([request.query]))[0]
        
        # Search ChromaDB
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=5
        )
        
        # Check if we have any results
        if not results['documents'] or not results['documents'][0]:
            # Check FAQs as fallback
            faqs = await db.faqs.find({}, {"_id": 0}).to_list(100)
            if faqs:
                faq_context = "\n\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in faqs])
                context = f"Based on frequently asked questions:\n\n{faq_context}"
                sources = ["FAQ Database"]
            else:
                context = "No relevant documents found in the knowledge base."
                sources = []
        else:
            retrieved_chunks = results['documents'][0]
            metadatas = results['metadatas'][0]
            sources = list(set([meta['filename'] for meta in metadatas]))
            
            # Check for FAQs as additional context
            faqs = await db.faqs.find({}, {"_id": 0}).to_list(100)
            faq_context = ""
            if faqs:
                faq_context = "\n\nAdditional FAQs:\n" + "\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in faqs[:3]])
            
            context = "\n\n".join(retrieved_chunks) + faq_context
        
        # Generate response using LLM
        chat = LlmChat(
            api_key=LLM_API_KEY,
            session_id=request.session_id,
            system_message="You are a helpful student study assistant. Use the provided context to answer questions accurately. If the context doesn't contain the answer, say so politely and offer general guidance based on the question topic."
        ).with_model("openai", "gpt-4o")
        
        user_message = UserMessage(
            text=f"Context:\n{context}\n\nQuestion: {request.query}\n\nProvide a clear, helpful answer based on the context above."
        )
        
        response_text = await chat.send_message(user_message)
        
        # Save messages to MongoDB
        user_msg = ChatMessage(
            session_id=request.session_id,
            role="user",
            content=request.query
        )
        assistant_msg = ChatMessage(
            session_id=request.session_id,
            role="assistant",
            content=response_text,
            sources=sources
        )
        
        user_dict = user_msg.model_dump()
        user_dict['timestamp'] = user_dict['timestamp'].isoformat()
        assistant_dict = assistant_msg.model_dump()
        assistant_dict['timestamp'] = assistant_dict['timestamp'].isoformat()
        
        await db.chat_messages.insert_one(user_dict)
        await db.chat_messages.insert_one(assistant_dict)
        
        return {
            "response": response_text,
            "sources": sources
        }
    except Exception as e:
        logging.error(f"Error querying documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/chat-history/{session_id}", response_model=List[ChatMessage])
async def get_chat_history(session_id: str):
    """Get chat history for a session"""
    try:
        messages = await db.chat_messages.find(
            {"session_id": session_id},
            {"_id": 0}
        ).sort("timestamp", 1).to_list(1000)
        
        for msg in messages:
            if isinstance(msg['timestamp'], str):
                msg['timestamp'] = datetime.fromisoformat(msg['timestamp'])
        return messages
    except Exception as e:
        logging.error(f"Error fetching chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/faqs/seed")
async def seed_faqs():
    """Seed initial FAQ data (BONUS FEATURE)"""
    try:
        existing = await db.faqs.count_documents({})
        if existing > 0:
            return {"message": "FAQs already seeded"}
        
        faqs = [
            FAQItem(question="What is RAG?", answer="RAG (Retrieval Augmented Generation) is a technique that enhances LLM responses by retrieving relevant information from a knowledge base before generating answers.", category="Technical"),
            FAQItem(question="How do I study effectively?", answer="Effective studying involves active recall, spaced repetition, understanding concepts rather than memorizing, and taking regular breaks.", category="Study Tips"),
            FAQItem(question="What are embeddings?", answer="Embeddings are numerical representations of text that capture semantic meaning, allowing computers to understand and compare text similarity.", category="Technical"),
            FAQItem(question="How can I improve retention?", answer="Improve retention by teaching others, using mnemonics, creating visual aids, and reviewing material multiple times over several days.", category="Study Tips"),
            FAQItem(question="What is vector search?", answer="Vector search is a method of finding similar items by comparing their vector embeddings in high-dimensional space using distance metrics.", category="Technical"),
        ]
        
        faq_dicts = [faq.model_dump() for faq in faqs]
        await db.faqs.insert_many(faq_dicts)
        
        return {"message": f"Seeded {len(faqs)} FAQs successfully"}
    except Exception as e:
        logging.error(f"Error seeding FAQs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/faqs", response_model=List[FAQItem])
async def get_faqs():
    """Get all FAQs (BONUS FEATURE - External data source)"""
    try:
        faqs = await db.faqs.find({}, {"_id": 0}).to_list(1000)
        return faqs
    except Exception as e:
        logging.error(f"Error fetching FAQs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/stats")
async def get_stats():
    """Get system statistics"""
    try:
        doc_count = await db.documents.count_documents({})
        chunk_count = collection.count()
        faq_count = await db.faqs.count_documents({})
        
        return {
            "documents": doc_count,
            "chunks": chunk_count,
            "faqs": faq_count
        }
    except Exception as e:
        logging.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()