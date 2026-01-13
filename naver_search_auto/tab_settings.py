import sys
import requests
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QGroupBox, QMessageBox, QFormLayout
)
from PyQt6.QtCore import Qt
from api_client import api

class SettingsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 1. API 키 설정 그룹
        grp_key = QGroupBox("네이버 검색광고 API 키 설정")
        grp_key.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; margin-top: 10px; }")
        
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        
        self.in_ak = QLineEdit()
        self.in_ak.setPlaceholderText("Access License Key")
        self.in_ak.setText(api.naver_api_key or "") # 현재 키 로드
        
        self.in_sk = QLineEdit()
        self.in_sk.setPlaceholderText("Secret Key")
        self.in_sk.setEchoMode(QLineEdit.EchoMode.Password) # 비밀번호처럼 가리기
        self.in_sk.setText(api.naver_secret_key or "")
        
        self.in_cid = QLineEdit()
        self.in_cid.setPlaceholderText("Customer ID (숫자)")
        self.in_cid.setText(api.naver_customer_id or "")
        
        form_layout.addRow("Access Key:", self.in_ak)
        form_layout.addRow("Secret Key:", self.in_sk)
        form_layout.addRow("Customer ID:", self.in_cid)
        
        grp_key.setLayout(form_layout)
        layout.addWidget(grp_key)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        
        btn_save = QPushButton("API 키 저장 및 적용")
        btn_save.setStyleSheet("background-color: #0d6efd; color: white; padding: 10px; font-weight: bold;")
        btn_save.clicked.connect(self.save_keys)
        
        btn_test = QPushButton("연결 테스트")
        btn_test.setStyleSheet("background-color: #6c757d; color: white; padding: 10px;")
        btn_test.clicked.connect(self.test_connection)
        
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_test)
        
        layout.addLayout(btn_layout)
        
        # 안내 문구
        lbl_info = QLabel("※ 관리자는 이곳에서 API 키를 변경하여 다른 계정의 광고를 관리할 수 있습니다.\n※ 일반 유저는 키를 변경하면 서버에도 자동 동기화됩니다.")
        lbl_info.setStyleSheet("color: #666; margin-top: 20px;")
        layout.addWidget(lbl_info)
        
    def save_keys(self):
        ak = self.in_ak.text().strip()
        sk = self.in_sk.text().strip()
        cid = self.in_cid.text().strip()
        
        if not all([ak, sk, cid]):
            QMessageBox.warning(self, "경고", "모든 키 정보를 입력해주세요.")
            return
            
        # 1. 로컬 메모리에 즉시 적용 (이게 관리자가 바로 다른 계정 전환할 때 쓰임)
        api.naver_api_key = ak
        api.naver_secret_key = sk
        api.naver_customer_id = cid
        
        # 2. 서버에 저장 (내 정보 업데이트)
        try:
            headers = {"Authorization": f"Bearer {api.server_token}"}
            body = {
                "naver_access_key": ak,
                "naver_secret_key": sk,
                "naver_customer_id": cid
            }
            # api_client에 있는 server_url 사용
            resp = requests.put(f"{api.server_url}/users/me/keys", json=body, headers=headers, timeout=5)
            
            if resp.status_code == 200:
                QMessageBox.information(self, "성공", "API 키가 저장되고 적용되었습니다.\n이제 다른 탭에서 기능을 사용할 수 있습니다.")
            else:
                # 관리자가 임의로 키를 바꿀 땐 서버 저장이 필수는 아님 (자기 계정 키가 덮어씌워지니까)
                # 하지만 일단 경고는 띄움
                QMessageBox.warning(self, "서버 저장 실패", f"로컬에는 적용되었으나 서버 저장에 실패했습니다.\n({resp.text})")
                
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def test_connection(self):
        # API 키가 유효한지 캠페인 목록을 한번 불러와봄
        if not api.naver_api_key:
             QMessageBox.warning(self, "경고", "먼저 키를 저장해주세요.")
             return
             
        try:
            # api_client의 get_campaigns는 내부적으로 call_naver를 호출함
            camps = api.get_campaigns()
            if camps is not None:
                cnt = len(camps)
                QMessageBox.information(self, "연결 성공", f"정상적으로 연결되었습니다.\n현재 캠페인 수: {cnt}개")
            else:
                QMessageBox.critical(self, "연결 실패", "API 키가 틀렸거나 권한이 없습니다.\n(403 Forbidden 오류 등)")
        except Exception as e:
             QMessageBox.critical(self, "오류", str(e))