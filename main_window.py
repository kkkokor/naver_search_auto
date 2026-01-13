import sys
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QMessageBox, QDialog, 
    QStackedWidget, QListWidget, QFrame, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor

# 모듈 불러오기
from api_client import api
from tab_autobidder import AutoBidderWidget
from tab_creative import CreativeManagerWidget
from tab_extension import ExtensionManagerWidget
from tab_keyword import KeywordExpanderWidget
from tab_admin import AdminDashboardWidget
from tab_settings import SettingsWidget
from tab_guide import UserGuideWidget

# [한글 깨짐 방지]
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding='utf-8')

DEFAULT_FONT = "font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;"

STYLESHEET = """
QMainWindow { background-color: #f4f7fc; }
QWidget { font-family: 'Pretendard', 'Malgun Gothic', sans-serif; font-size: 14px; color: #333; }
QListWidget { background-color: #ffffff; border: none; min-width: 240px; }
QListWidget::item { height: 55px; padding-left: 20px; color: #6c757d; border-left: 5px solid transparent; margin-bottom: 5px; }
QListWidget::item:hover { background-color: #f8f9fa; color: #0d6efd; }
QListWidget::item:selected { background-color: #e7f1ff; color: #0d6efd; border-left: 5px solid #0d6efd; font-weight: bold; }
QStackedWidget { background-color: transparent; }
QFrame#ContentFrame, QDialog { background-color: #ffffff; border-radius: 12px; border: 1px solid #eef2f6; }
QLineEdit { background-color: #fbfbfb; border: 1px solid #dee2e6; border-radius: 8px; padding: 12px; }
QLineEdit:focus { border: 1px solid #0d6efd; background-color: #ffffff; }
QPushButton { background-color: #0d6efd; color: white; border: none; border-radius: 8px; padding: 10px 20px; font-weight: bold; }
QPushButton:hover { background-color: #0b5ed7; margin-top: 1px; }
QPushButton#LinkButton { background-color: transparent; color: #6c757d; text-align: right; }
QPushButton#LinkButton:hover { color: #0d6efd; text-decoration: underline; }
QLabel#TitleLabel { font-size: 24px; font-weight: bold; color: #212529; margin-bottom: 10px; }
"""

# -------------------------------------------------------------------------
# [회원가입 창]
# -------------------------------------------------------------------------
class RegisterDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("회원가입")
        self.setFixedSize(400, 500)
        self.setStyleSheet(STYLESHEET)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(15)
        
        title = QLabel("계정 생성")
        title.setObjectName("TitleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        self.in_id = QLineEdit(); self.in_id.setPlaceholderText("아이디")
        self.in_pw = QLineEdit(); self.in_pw.setPlaceholderText("비밀번호"); self.in_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_name = QLineEdit(); self.in_name.setPlaceholderText("이름 (실명)")
        self.in_phone = QLineEdit(); self.in_phone.setPlaceholderText("전화번호")
        
        layout.addWidget(self.in_id); layout.addWidget(self.in_pw)
        layout.addWidget(self.in_name); layout.addWidget(self.in_phone)
        
        layout.addSpacing(20)
        btn_reg = QPushButton("가입하기")
        btn_reg.clicked.connect(self.try_register)
        layout.addWidget(btn_reg)
        self.setLayout(layout)
        
    def try_register(self):
        uid, upw = self.in_id.text().strip(), self.in_pw.text().strip()
        uname, uphone = self.in_name.text().strip(), self.in_phone.text().strip()
        if not all([uid, upw, uname, uphone]): return QMessageBox.warning(self, "오류", "모두 입력해주세요.")
            
        try:
            resp = requests.post(f"{api.server_url}/auth/register", json={"username": uid, "password": upw, "name": uname, "phone": uphone}, timeout=5)
            if resp.status_code == 200:
                QMessageBox.information(self, "성공", "가입되었습니다. 로그인해주세요.")
                self.accept()
            elif resp.status_code == 400: QMessageBox.warning(self, "실패", "이미 존재하는 아이디입니다.")
            else: QMessageBox.critical(self, "오류", f"서버 응답: {resp.text}")
        except Exception as e: QMessageBox.critical(self, "오류", str(e))

# -------------------------------------------------------------------------
# [로그인 창]
# -------------------------------------------------------------------------
class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("로그인")
        self.setFixedSize(400, 450)
        self.setStyleSheet(STYLESHEET)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(15)
        
        title = QLabel("Naver Ad Pro")
        title.setObjectName("TitleLabel")
        title.setStyleSheet("color: #03c75a; font-size: 32px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        self.in_id = QLineEdit(); self.in_id.setPlaceholderText("아이디")
        self.in_pw = QLineEdit(); self.in_pw.setPlaceholderText("비밀번호"); self.in_pw.setEchoMode(QLineEdit.EchoMode.Password)
        
        layout.addWidget(self.in_id); layout.addWidget(self.in_pw)
        layout.addSpacing(10)
        
        self.btn_login = QPushButton("로그인")
        self.btn_login.clicked.connect(self.handle_login)
        layout.addWidget(self.btn_login)
        
        self.btn_reg = QPushButton("계정이 없으신가요? 회원가입")
        self.btn_reg.setObjectName("LinkButton")
        self.btn_reg.clicked.connect(lambda: RegisterDialog().exec())
        layout.addWidget(self.btn_reg)
        self.setLayout(layout)

    def handle_login(self):
        uid, upw = self.in_id.text().strip(), self.in_pw.text().strip()
        if not uid or not upw: return
        
        self.btn_login.setText("접속 중..."); self.btn_login.setEnabled(False)
        QApplication.processEvents()
        
        if api.login(uid, upw):
            if api.fetch_user_info(): self.accept()
            else: QMessageBox.critical(self, "오류", "정보 로드 실패"); self.btn_login.setEnabled(True)
        else:
            QMessageBox.critical(self, "실패", "로그인 실패 (아이디/비번 확인 또는 승인 대기)"); self.btn_login.setEnabled(True); self.btn_login.setText("로그인")

# -------------------------------------------------------------------------
# [API 키 설정 창]
# -------------------------------------------------------------------------
class ApiKeyDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("API 키 설정")
        self.setFixedSize(450, 400)
        self.setStyleSheet(STYLESHEET)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(30,30,30,30)
        layout.addWidget(QLabel("네이버 검색광고 API 키 입력", objectName="TitleLabel"))
        
        self.ak = QLineEdit(); self.ak.setPlaceholderText("Access License Key")
        self.sk = QLineEdit(); self.sk.setPlaceholderText("Secret Key")
        self.cid = QLineEdit(); self.cid.setPlaceholderText("Customer ID")
        
        layout.addWidget(QLabel("Access Key")); layout.addWidget(self.ak)
        layout.addWidget(QLabel("Secret Key")); layout.addWidget(self.sk)
        layout.addWidget(QLabel("Customer ID")); layout.addWidget(self.cid)
        
        btn = QPushButton("저장 및 연동")
        btn.clicked.connect(self.save)
        layout.addWidget(btn)
        self.setLayout(layout)
        
    def save(self):
        ak, sk, cid = self.ak.text().strip(), self.sk.text().strip(), self.cid.text().strip()
        if not all([ak, sk, cid]): return
        
        api.naver_api_key = ak; api.naver_secret_key = sk; api.naver_customer_id = cid
        try:
            res = requests.put(f"{api.server_url}/users/me/keys", json={"naver_access_key": ak, "naver_secret_key": sk, "naver_customer_id": cid}, headers={"Authorization": f"Bearer {api.server_token}"})
            if res.status_code == 200: QMessageBox.information(self, "성공", "저장되었습니다."); self.accept()
            else: QMessageBox.warning(self, "실패", "서버 저장 실패")
        except Exception as e: QMessageBox.critical(self, "오류", str(e))

# -------------------------------------------------------------------------
# [메인 윈도우]
# -------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Naver Ad Manager Pro")
        self.resize(1280, 850)
        self.setStyleSheet(STYLESHEET)
        
        # 하트비트
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.send_heartbeat)
        self.timer.start(30000)
        
        self.init_ui()

    def init_ui(self):
        container = QWidget(); self.setCentralWidget(container)
        layout = QHBoxLayout(container); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        
        # 사이드바
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(260)
        
        is_admin = getattr(api, 'is_superuser', False)
        
        # [메뉴 목록]
        first_menu_name = "📊  대시보드 (Admin)" if is_admin else "📖  사용 가이드"
        items = [
            first_menu_name,              # 0
            "🚀  자동 입찰 (Auto Bid)",    # 1
            "🎨  소재 관리 (Creatives)",   # 2
            "🔗  확장 소재 (Extensions)",  # 3
            "✨  키워드 확장 (Expansion)", # 4
            "⚙️  설정 (Settings)"          # 5
        ]
        self.sidebar.addItems(items)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self.change_tab)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15); shadow.setColor(QColor(0,0,0,30)); shadow.setOffset(2,0)
        self.sidebar.setGraphicsEffect(shadow)
        self.sidebar.raise_()
        layout.addWidget(self.sidebar)
        
        # 컨텐츠
        content = QWidget(); vbox = QVBoxLayout(content); vbox.setContentsMargins(30,30,30,30); vbox.setSpacing(20)
        
        # 헤더
        hbox = QHBoxLayout()
        self.title = QLabel("관리자 대시보드"); self.title.setObjectName("TitleLabel")
        hbox.addWidget(self.title); hbox.addStretch()
        
        user_txt = f"👑 관리자 ({api.naver_customer_id})" if getattr(api, 'is_superuser', False) else f"👤 {api.naver_customer_id}"
        hbox.addWidget(QLabel(user_txt))
        vbox.addLayout(hbox)
        
        # [페이지 스택 구성] - 순서가 사이드바 인덱스와 1:1로 매칭되어야 함
        self.pages = QStackedWidget()
        
        # [0] 첫 번째 탭: 권한에 따라 분기
        if is_admin:
            self.pages.addWidget(AdminDashboardWidget())
        else:
            self.pages.addWidget(UserGuideWidget())
            
        # [1~5] 나머지 탭들
        self.pages.addWidget(AutoBidderWidget())          # 1: 자동입찰
        self.pages.addWidget(CreativeManagerWidget())     # 2: 소재관리
        self.pages.addWidget(ExtensionManagerWidget())    # 3: 확장소재
        self.pages.addWidget(KeywordExpanderWidget())     # 4: 키워드확장
        self.pages.addWidget(SettingsWidget())            # 5: 설정
        
        frame = QFrame(); frame.setObjectName("ContentFrame")
        fl = QVBoxLayout(frame); fl.setContentsMargins(20,20,20,20); fl.addWidget(self.pages)
        
        f_shadow = QGraphicsDropShadowEffect()
        f_shadow.setBlurRadius(10); f_shadow.setColor(QColor(0,0,0,10)); f_shadow.setOffset(0,2)
        frame.setGraphicsEffect(f_shadow)
        
        vbox.addWidget(frame)
        layout.addWidget(content)

    def change_tab(self, idx):
        self.pages.setCurrentIndex(idx)
        first_title = "관리자 대시보드" if getattr(api, 'is_superuser', False) else "사용 가이드"
        titles = [first_title, "자동 입찰", "소재 관리", "확장 소재", "키워드 확장", "설정"]
        if 0 <= idx < len(titles): self.title.setText(titles[idx])

    def send_heartbeat(self):
        try: api.send_heartbeat("Active")
        except: pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Malgun Gothic", 10))
    
    if LoginDialog().exec() == QDialog.DialogCode.Accepted:
        # 일반 유저도 API 키 없으면 설정 탭에서 입력하도록 유도 (강제 종료 X)
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)