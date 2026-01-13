# server.py (Refactored for Client-Server Architecture)
import sys
import os
import time
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, Session, relationship, declarative_base
from passlib.context import CryptContext
from jose import JWTError, jwt

# [설정]
SECRET_KEY = "YOUR_SECRET_KEY_PLEASE_CHANGE_THIS"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24시간

SQLALCHEMY_DATABASE_URL = "sqlite:///./app.db"

# [데이터베이스 설정]
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -------------------------------------------------------------------
# [Models] DB 스키마 정의
# -------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    name = Column(String)
    phone = Column(String)
    
    # [API Key 저장소] 클라이언트가 로그인 시 이 키를 받아감
    naver_access_key = Column(String, nullable=True)
    naver_secret_key = Column(String, nullable=True)
    naver_customer_id = Column(String, nullable=True)
    
    # [라이센스 관리]
    is_active = Column(Boolean, default=True)
    is_paid = Column(Boolean, default=False)     # 관리자 승인 여부
    is_superuser = Column(Boolean, default=False)
    subscription_expiry = Column(DateTime, nullable=True) # 만료일

    # 관계 설정
    logs = relationship("ActivityLog", back_populates="user")

class ActivityLog(Base):
    """클라이언트 상태 모니터링용 하트비트 로그"""
    __tablename__ = "activity_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    timestamp = Column(DateTime, default=datetime.now)
    client_ip = Column(String)
    status_message = Column(String) # 예: "자동입찰 수행 중 (캠페인A)"
    is_online = Column(Boolean, default=True)

    user = relationship("User", back_populates="logs")

Base.metadata.create_all(bind=engine)

# -------------------------------------------------------------------
# [Security] 보안 및 인증 로직
# -------------------------------------------------------------------
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    phone: str

class UserUpdateKeys(BaseModel):
    naver_access_key: str
    naver_secret_key: str
    naver_customer_id: str

class UserOut(BaseModel):
    id: int
    username: str
    name: str
    is_active: bool
    is_paid: bool
    is_superuser: bool
    subscription_expiry: Optional[datetime] = None
    
    # 클라이언트로 키 전송 (보안 주의: HTTPS 필수)
    naver_access_key: Optional[str] = None
    naver_secret_key: Optional[str] = None
    naver_customer_id: Optional[str] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class HeartbeatItem(BaseModel):
    status: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="자격 증명을 검증할 수 없습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception

    # [라이센스 만료 체크]
    if user.is_paid and not user.is_superuser:
        if user.subscription_expiry and user.subscription_expiry < datetime.now():
            print(f"🚫 [만료] {user.username}님의 이용 기간 종료")
            user.is_paid = False 
            db.commit()
    
    return user

def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="비활성화된 사용자입니다.")
    if not current_user.is_paid and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="이용 승인 대기 중이거나 만료되었습니다.")
    return current_user

# -------------------------------------------------------------------
# [API] FastAPI 엔드포인트
# -------------------------------------------------------------------
app = FastAPI(title="Naver Ad Manager Pro Server", description="Auth & License Control Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. 회원가입/로그인
@app.post("/auth/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")
    
    is_first = db.query(User).count() == 0
    new_user = User(
        username=user.username,
        hashed_password=get_password_hash(user.password),
        name=user.name,
        phone=user.phone,
        is_paid=False,
        is_superuser=is_first
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/auth/token", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 일치하지 않습니다.")
    
    access_token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": access_token, "token_type": "bearer"}

# 2. 내 정보 및 키 관리 (클라이언트 동기화용)
@app.get("/users/me", response_model=UserOut)
def read_users_me(current_user: User = Depends(get_current_user)):
    # 클라이언트가 이 정보를 호출하여 Naver API Key를 획득함
    return current_user

@app.put("/users/me/keys")
def update_api_keys(keys: UserUpdateKeys, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.naver_access_key = keys.naver_access_key.strip()
    current_user.naver_secret_key = keys.naver_secret_key.strip()
    current_user.naver_customer_id = str(keys.naver_customer_id).strip()
    db.commit()
    return {"status": "success", "message": "API 키가 서버에 안전하게 저장되었습니다."}

# 3. [관제] 클라이언트 하트비트 (30초마다 호출됨)
@app.post("/api/monitor/heartbeat")
def client_heartbeat(item: HeartbeatItem, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    # 기존 로그가 있다면 업데이트, 없으면 생성 (또는 매번 생성하여 이력 남기기 - 여기선 최신 상태 업데이트 방식 사용)
    # 단순화를 위해 매번 로그를 쌓되, 관리자 조회 시 최신것만 가져오도록 설계하거나
    # 여기서는 '최신 상태' 테이블을 따로 두지 않고 로그를 계속 쌓습니다.
    log = ActivityLog(
        user_id=current_user.id,
        status_message=item.status,
        client_ip="Unknown", # 실제 환경에선 request.client.host 사용
        is_online=True
    )
    db.add(log)
    db.commit()
    return {"status": "alive"}

# 4. [관리자] 라이센스 및 모니터링
@app.get("/admin/users", response_model=List[UserOut])
def get_all_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")
    return db.query(User).all()

@app.put("/admin/approve/{user_id}")
def approve_user(user_id: int, months: int = 1, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_paid = True
    # 기존 만료일이 남아있으면 거기서 연장, 아니면 현재부터 연장
    now = datetime.now()
    if user.subscription_expiry and user.subscription_expiry > now:
        base_date = user.subscription_expiry
    else:
        base_date = now
    
    user.subscription_expiry = base_date + timedelta(days=30 * months)
    db.commit()
    return {"status": "success", "message": f"{user.name}님 승인 완료 ({months}개월)", "expiry": user.subscription_expiry}

@app.get("/admin/monitor/live")
def get_live_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")
    
    # 최근 2분 이내에 하트비트를 보낸 유저만 조회
    limit_time = datetime.now() - timedelta(minutes=2)
    
    # Subquery나 Join을 통해 유저별 최신 로그만 가져오는 로직이 필요하나,
    # 간단하게 구현하기 위해 전체 활성 유저의 최신 로그를 조회
    active_users = []
    users = db.query(User).filter(User.is_active == True).all()
    
    for u in users:
        last_log = db.query(ActivityLog).filter(ActivityLog.user_id == u.id).order_by(ActivityLog.timestamp.desc()).first()
        is_online = False
        status_msg = "Offline"
        last_seen = "-"
        
        if last_log and last_log.timestamp > limit_time:
            is_online = True
            status_msg = last_log.status_message
            last_seen = last_log.timestamp.strftime("%H:%M:%S")
            
        active_users.append({
            "username": u.username,
            "name": u.name,
            "is_online": is_online,
            "status": status_msg,
            "last_seen": last_seen,
            "expiry": u.subscription_expiry
        })
        
    return active_users

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)