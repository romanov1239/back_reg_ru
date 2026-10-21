from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.sql import func
from fastapi import Cookie, Response, Depends
from itsdangerous import URLSafeSerializer, BadSignature
from rag_router import router as rag_router


# --- Настройки БД ---
DATABASE_URL = "postgresql://appuser:strong_password@127.0.0.1:5432/appdb"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# --- Модели ---
class ItemModel(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")


class VisitorModel(Base):
    __tablename__ = "visitors"
    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String(45), unique=True, index=True, nullable=False)
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


Base.metadata.create_all(bind=engine)


# --- Схемы ---
class ItemCreate(BaseModel):
    name: str
    description: str = ""

class ItemUpdate(BaseModel):
    name: str
    description: str = ""

class ItemResponse(BaseModel):
    id: int
    name: str
    description: str
    class Config:
        from_attributes = True


# --- FastAPI ---
app = FastAPI()
app.include_router(rag_router)

# --- Простая авторизация по никнейму ---
SECRET_KEY = "QDC_0dAM-HbaF_jNK8I_8PtKI30UwDakSSq-SleBwUG0zPkd6UJJeqhds6Q5ORpMfxk"
serializer = URLSafeSerializer(SECRET_KEY, salt="nickname")


def get_current_nick(nick_cookie: str | None = Cookie(default=None)) -> str | None:
    if not nick_cookie:
        return None
    try:
        return serializer.loads(nick_cookie)
    except BadSignature:
        return None


class LoginData(BaseModel):
    nickname: str


@app.post("/login")
def login(data: LoginData, response: Response):
    nickname = data.nickname.strip()
    if not nickname or len(nickname) > 30:
        raise HTTPException(status_code=400, detail="Ник должен быть от 1 до 30 символов")
    token = serializer.dumps(nickname)
    response.set_cookie(
        key="nick_cookie",
        value=token,
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
    )
    return {"nickname": nickname}


@app.post("/logout")
def logout(response: Response):
    response.delete_cookie("nick_cookie")
    return {"message": "Вы вышли"}


@app.get("/me")
def me(nick: str | None = Depends(get_current_nick)):
    return {"nickname": nick}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_client_ip(request: Request) -> str:
    """Реальный IP клиента с учётом nginx-прокси."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


# --- Страницы ---
@app.get("/snake")
async def snake_page():
    return FileResponse("static/snake.html")


# --- CRUD ---
@app.post("/items/", response_model=ItemResponse)
def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    db_item = ItemModel(**item.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@app.get("/items/", response_model=list[ItemResponse])
def read_items(db: Session = Depends(get_db)):
    return db.query(ItemModel).all()

@app.get("/items/{item_id}", response_model=ItemResponse)
def read_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(ItemModel).filter(ItemModel.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.put("/items/{item_id}", response_model=ItemResponse)
def update_item(item_id: int, item: ItemUpdate, db: Session = Depends(get_db)):
    db_item = db.query(ItemModel).filter(ItemModel.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    db_item.name = item.name
    db_item.description = item.description
    db.commit()
    db.refresh(db_item)
    return db_item

@app.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    db_item = db.query(ItemModel).filter(ItemModel.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(db_item)
    db.commit()
    return {"message": "Item deleted"}


# --- Счётчик посещений ---
@app.post("/visit")
def register_visit(request: Request, db: Session = Depends(get_db)):
    ip = get_client_ip(request)

    # не считаем локальные заходы (твои тесты через curl)
    if ip in ("127.0.0.1", "::1", "localhost", "unknown"):
        total = db.query(VisitorModel).count()
        return {"new": False, "total": total, "skipped": True}

    visitor = db.query(VisitorModel).filter(VisitorModel.ip == ip).first()
    if visitor:
        visitor.last_seen = func.now()
        db.commit()
        return {"new": False, "total": db.query(VisitorModel).count()}
    else:
        db.add(VisitorModel(ip=ip))
        db.commit()
        return {"new": True, "total": db.query(VisitorModel).count()}


@app.get("/visits/count")
def visits_count(db: Session = Depends(get_db)):
    return {"total": db.query(VisitorModel).count()}


# --- Раздача фронтенда ---
# Создайте папку static и положите туда index.html
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")