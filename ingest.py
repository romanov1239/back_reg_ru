import os
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
DB_DIR = "chroma_db"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150


def load_documents():
    docs = []
    for path in DATA_DIR.rglob("*"):
        if path.suffix.lower() == ".pdf":
            reader = PdfReader(str(path))
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
        elif path.suffix.lower() in {".txt", ".md"}:
            text = path.read_text(encoding="utf-8")
        else:
            continue
        docs.append({"source": path.name, "text": text})
    return docs


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    chunks, start = [], 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return [c.strip() for c in chunks if c.strip()]


def main():
    docs = load_documents()
    if not docs:
        print("Положи файлы в data/ и запусти снова.")
        return

    client = chromadb.PersistentClient(path=DB_DIR)
    # эмбеддинги через OpenAI
    ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=os.getenv("OPENAI_API_KEY"),
        model_name="text-embedding-3-small",
    )

    # пересоздаём коллекцию
    try:
        client.delete_collection("docs")
    except Exception:
        pass
    collection = client.create_collection("docs", embedding_function=ef)

    ids, texts, metas = [], [], []
    for doc in docs:
        for i, chunk in enumerate(chunk_text(doc["text"])):
            ids.append(f"{doc['source']}::{i}")
            texts.append(chunk)
            metas.append({"source": doc["source"], "chunk": i})

    collection.add(ids=ids, documents=texts, metadatas=metas)
    print(f"Проиндексировано {len(texts)} чанков из {len(docs)} файлов.")


if __name__ == "__main__":
    main()
