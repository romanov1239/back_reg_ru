import os
from functools import lru_cache
from dotenv import load_dotenv
from openai import OpenAI
import chromadb
from chromadb.utils import embedding_functions

load_dotenv()

SYSTEM_PROMPT = """Ты — ассистент, отвечающий на вопросы строго по контексту.
Если ответа в контексте нет — скажи об этом честно.
В конце ответа указывай источники в формате [source]."""

EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"
DB_DIR = "chroma_db"
COLLECTION = "docs"


class RagUnavailable(Exception):
    """RAG временно недоступен (нет ключа / нет индекса)."""
    pass


def is_configured() -> bool:
    """Ключ задан и непустой."""
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def is_indexed() -> bool:
    """Индекс Chroma существует на диске."""
    return os.path.isdir(DB_DIR)


@lru_cache(maxsize=1)
def _llm():
    if not is_configured():
        raise RagUnavailable("OPENAI_API_KEY не задан в .env")
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@lru_cache(maxsize=1)
def _collection():
    if not is_configured():
        raise RagUnavailable("OPENAI_API_KEY не задан в .env")
    if not is_indexed():
        raise RagUnavailable("Индекс не построен. Запустите ingest.py")
    ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=os.getenv("OPENAI_API_KEY"),
        model_name=EMBED_MODEL,
    )
    client = chromadb.PersistentClient(path=DB_DIR)
    return client.get_collection(COLLECTION, embedding_function=ef)


def retrieve(question: str, k: int = 4):
    res = _collection().query(query_texts=[question], n_results=k)
    return list(zip(res["documents"][0], res["metadatas"][0]))


def answer(question: str) -> dict:
    chunks = retrieve(question)
    if not chunks:
        return {"answer": "В базе знаний нет документов.", "sources": []}

    context = "\n\n---\n\n".join(f"[{m['source']}]\n{doc}" for doc, m in chunks)

    response = _llm().chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Контекст:\n{context}\n\nВопрос: {question}"},
        ],
        temperature=0.2,
    )
    return {
        "answer": response.choices[0].message.content,
        "sources": list({m["source"] for _, m in chunks}),
    }