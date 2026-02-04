import os
import json
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import secrets
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi import Request
from sqlalchemy.orm import Session
from typing import List, Optional
from sqlalchemy.orm import joinedload
import models, schemas
from database import engine, SessionLocal
from pydantic import BaseModel

security = HTTPBasic()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

templates = Jinja2Templates(directory="templates")

models.Base.metadata.create_all(bind=engine)

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = ADMIN_USERNAME.encode("utf8")
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )

    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = ADMIN_PASSWORD.encode("utf8")
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )

    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Incorrect username or password',
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username





class StatusUpdate(BaseModel):
    room_id: int
    status: str
    status_note: str = ""


class ConnectionManager:
    def __init__(self):
        # Используем set (множество) вместо списка, это быстрее и исключает дубликаты
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        # Делаем копию сета для итерации, чтобы избежать ошибок при изменении размера
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                # Если отправить не удалось — сокет мертв, удаляем
                self.disconnect(connection)

manager = ConnectionManager()


class DoctorCreate(BaseModel):
    full_name: str
    specialization: str


class RoomCreate(BaseModel):
    number: str
    doctor_id: Optional[int] = None


class RoomUpdate(BaseModel):
    number: Optional[str] = None
    doctor_id: Optional[int] = None


class TickerUpdate(BaseModel):
    text: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def read_tablo(request: Request):
    return templates.TemplateResponse("tablo.html", {"request": request})

@app.websocket("/ws/tablo")
async def websocket_endpoint(websocket: WebSocket):
    # 1. Сначала ВСЕГДА принимаем соединение
    await websocket.accept()

    # 2. Только после accept добавляем в список рассылки
    manager.active_connections.add(websocket)
    print(f"DEBUG: Экран подключен. Всего экранов: {len(manager.active_connections)}")

    try:
        while True:
            # 3. Слушаем сообщения от клиента (телевизора)
            # Это «бесконечный цикл», который держит соединение открытым
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        print("DEBUG: Экран отключился (WebSocketDisconnect)")
        manager.disconnect(websocket)
    except Exception as e:
        print(f"DEBUG: Непредвиденная ошибка WS: {e}")
        manager.disconnect(websocket)


@app.get("/api/get-display")
def get_display(db: Session = Depends(get_db)):
    rooms = db.query(models.Room).options(joinedload(models.Room.doctor)).all()
    ticker = db.query(models.Content).filter(models.Content.type == "ticker").first()

    rooms_data = []
    for r in rooms:
        # Для отладки: выведет в терминал, видит ли Python врача
        print(f"Room {r.number}: Doctor object is {r.doctor}")

        rooms_data.append({
            "id": r.id,
            "number": r.number,
            "status": r.status,
            "status_note": r.status_note or "",
            # Проверяем объект doctor, который подтянулся через relationship
            "doctor_name": r.doctor.full_name if r.doctor else "Врач не назначен",
            "specialization": r.doctor.specialization if r.doctor else ""
        })
    print('Sending to browser: ', rooms_data[0])

    return {
        "rooms": rooms_data,
        "ticker": ticker.text if ticker else "Добро пожаловать!"
    }


@app.patch("/api/update-status")
async def update_status(data: schemas.StatusUpdate, db: Session = Depends(get_db), username: str = Depends(get_current_username)):
    room = db.query(models.Room).filter(models.Room.id == data.room_id).first()
    if room:
        room.status = data.status
        room.status_note = data.status_note
        if data.doctor_id:
            room.current_doctor_id = data.doctor_id
        db.commit()

        await manager.broadcast({
            "type": "STATUS_CHANGED",
            "room_id": room.id,
            "status": room.status,
            "note": room.status_note,
            "room_number": room.number
        })
    return {"status": "ok"}


@app.get("/api/doctors")
def get_doctors(db: Session = Depends(get_db)):
    return db.query(models.Doctor).all()



@app.post("/api/doctors")
async def add_doctor(data: DoctorCreate, db: Session = Depends(get_db), user: str = Depends(get_current_username)):
    new_doc = models.Doctor(full_name=data.full_name, specialization=data.specialization)
    db.add(new_doc)
    db.commit()
    return {"status": "success"}


@app.post("/api/rooms")
async def add_room(data: RoomCreate, db: Session = Depends(get_db), user: str = Depends(get_current_username)):
    new_room = models.Room(number=data.number, current_doctor_id=data.doctor_id, status="break")
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    await manager.broadcast({"type": "STATUS_CHANGED", "room_id": new_room.id})
    return {"status": "success"}


@app.delete("/api/rooms/{room_id}")
async def delete_room(room_id: int, db: Session = Depends(get_db), user: str = Depends(get_current_username)):
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room: return {"error": "Кабинет не найден"}
    db.delete(room)
    db.commit()
    await manager.broadcast({"type": "STATUS_CHANGED", "room_id": room_id})
    return {"status": "deleted"}


@app.patch("/api/rooms/{room_id}/details")
async def update_room_details(room_id: int, data: RoomUpdate, db: Session = Depends(get_db), user: str = Depends(get_current_username)):
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room: return {"error": "Кабинет не найден"}
    if data.number: room.number = data.number
    if data.doctor_id is not None:
        room.current_doctor_id = data.doctor_id if data.doctor_id != 0 else None
    db.commit()
    await manager.broadcast({"type": "STATUS_CHANGED", "room_id": room_id})
    return {"status": "updated"}


@app.patch("/api/update-ticker")
async def update_ticker(data: TickerUpdate, db: Session = Depends(get_db), user: str = Depends(get_current_username)):
    ticker = db.query(models.Content).filter(models.Content.type == "ticker").first()
    if not ticker:
        ticker = models.Content(type="ticker", text=data.text)
        db.add(ticker)
    else:
        ticker.text = data.text
    db.commit()
    await manager.broadcast({"type": "TICKER_CHANGED", "text": data.text})
    return {"status": "success"}



@app.get("/admin", response_class=HTMLResponse)
async def read_admin(request: Request, username: str = Depends(get_current_username)):
    return templates.TemplateResponse("admin.html", {"request": request})
