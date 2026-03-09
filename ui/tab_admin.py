import sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QTableWidgetItem, QHeaderView, QPushButton, QFrame, 
    QMessageBox, QSplitter, QGroupBox, QMenu, QComboBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QBrush

from api.api_client import api

class AdminDashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
        # 5초마다 데이터 갱신
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)
        # 탭이 열릴 때 start 하도록 설정할 수도 있음

    def showEvent(self, event):
        self.refresh_data()
        self.timer.start(5000) # 5초 주기

    def hideEvent(self, event):
        self.timer.stop()

    def init_ui(self):
        layout = QHBoxLayout(self)
        
        # [좌측] 실시간 접속 현황
        left_box = QGroupBox("📡 실시간 클라이언트 모니터링")
        left_layout = QVBoxLayout(left_box)
        
        self.live_table = QTableWidget()
        self.live_table.setColumnCount(4)
        self.live_table.setHorizontalHeaderLabels(["유저명", "상태 (Activity)", "최근 접속", "라이센스"])
        self.live_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        left_layout.addWidget(self.live_table)
        
        # [우측] 회원 관리 및 승인
        right_box = QGroupBox("👥 회원 승인 관리")
        right_layout = QVBoxLayout(right_box)
        
        self.user_table = QTableWidget()
        self.user_table.setColumnCount(4)
        self.user_table.setHorizontalHeaderLabels(["ID", "이름", "권한", "관리"])
        self.user_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        right_layout.addWidget(self.user_table)
        
        btn_refresh = QPushButton("수동 새로고침")
        btn_refresh.clicked.connect(self.refresh_data)
        right_layout.addWidget(btn_refresh)
        
        # 스플리터
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_box)
        splitter.addWidget(right_box)
        splitter.setSizes([600, 400])
        
        layout.addWidget(splitter)

    def refresh_data(self):
        # 1. 라이브 상태 조회
        live_data = api.get_admin_live_status()
        self.update_live_table(live_data)
        
        # 2. 전체 유저 조회
        all_users = api.get_all_users()
        self.update_user_table(all_users)

    def update_live_table(self, data):
        self.live_table.setRowCount(len(data))
        for i, row in enumerate(data):
            # username
            self.live_table.setItem(i, 0, QTableWidgetItem(f"{row['username']} ({row['name']})"))
            
            # status (Online/Offline 색상 구분)
            status_item = QTableWidgetItem(row['status'])
            if row['is_online']:
                status_item.setForeground(QBrush(QColor("green")))
                status_item.setText(f"🟢 {row['status']}")
            else:
                status_item.setForeground(QBrush(QColor("gray")))
                status_item.setText(f"⚫ {row['status']}")
            self.live_table.setItem(i, 1, status_item)
            
            # time
            self.live_table.setItem(i, 2, QTableWidgetItem(row['last_seen']))
            
            # license
            expiry = row.get('expiry') or "만료됨"
            self.live_table.setItem(i, 3, QTableWidgetItem(str(expiry).split('T')[0]))

    def update_user_table(self, users):
        self.user_table.setRowCount(len(users))
        for i, u in enumerate(users):
            self.user_table.setItem(i, 0, QTableWidgetItem(u['username']))
            self.user_table.setItem(i, 1, QTableWidgetItem(u['name']))
            
            role = "관리자" if u['is_superuser'] else ("유료회원" if u['is_paid'] else "대기회원")
            self.user_table.setItem(i, 2, QTableWidgetItem(role))
            
            # [수정] 모든 회원에 대해 액션 버튼 제공 (대기회원 + 기존 유료회원)
            btn_container = QWidget()
            btn_layout = QHBoxLayout(btn_container)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            
            action_btn = QPushButton("⚙️ 관리")
            action_btn.setStyleSheet("background-color: #007bff; color: white; border-radius: 4px; padding: 5px;")
            action_btn.setFixedWidth(80)
            action_btn.clicked.connect(lambda _, uid=u['id'], idx=i: self.show_action_menu(uid, u, idx))
            btn_layout.addWidget(action_btn)
            btn_layout.addStretch()
            
            self.user_table.setCellWidget(i, 3, btn_container)

    def approve_user(self, user_id):
        if QMessageBox.question(self, "승인", "해당 회원의 사용을 승인하시겠습니까?") == QMessageBox.StandardButton.Yes:
            if api.approve_user(user_id):
                QMessageBox.information(self, "성공", "승인되었습니다.")
                self.refresh_data()
            else:
                QMessageBox.critical(self, "실패", "승인 실패")

    def show_action_menu(self, user_id, user_data, row_idx):
        """회원에 대한 관리 액션 메뉴 표시"""
        menu = QMenu(self)
        
        # [옵션 1] 승인 (대기회원 전용)
        if not user_data['is_paid'] and not user_data['is_superuser']:
            action_approve = menu.addAction("✅ 1개월 승인")
            action_approve.triggered.connect(lambda: self.action_approve(user_id))
        
        # [옵션 2] 연장 (유료회원 전용)
        if user_data['is_paid'] and not user_data['is_superuser']:
            action_extend = menu.addAction("🔄 사용기간 연장 (1개월)")
            action_extend.triggered.connect(lambda: self.action_extend(user_id))
        
        # [옵션 3] 사용정지 (모든 비관리자)
        if not user_data['is_superuser']:
            action_suspend = menu.addAction("⛔ 사용정지")
            action_suspend.triggered.connect(lambda: self.action_suspend(user_id))
        
        # [옵션 4] 복구 (사용정지된 회원만 - is_suspended 상태 확인)
        if not user_data['is_superuser'] and user_data.get('is_suspended'):
            action_resume = menu.addAction("🟢 사용 복구")
            action_resume.triggered.connect(lambda: self.action_resume(user_id))
        
        # 메뉴 표시 (마우스 위치)
        menu.exec()

    def action_approve(self, user_id):
        """회원 승인 (1개월)"""
        if QMessageBox.question(self, "확인", "해당 회원을 1개월간 승인하시겠습니까?") == QMessageBox.StandardButton.Yes:
            if api.approve_user(user_id, days=30):
                QMessageBox.information(self, "성공", "회원이 승인되었습니다. (1개월)")
                self.refresh_data()
            else:
                QMessageBox.critical(self, "실패", "승인 실패")

    def action_extend(self, user_id):
        """회원 사용기간 연장 (1개월)"""
        if QMessageBox.question(self, "확인", "해당 회원의 사용기간을 1개월간 연장하시겠습니까?") == QMessageBox.StandardButton.Yes:
            if api.extend_user_license(user_id, days=30):
                QMessageBox.information(self, "성공", "사용기간이 연장되었습니다. (1개월)")
                self.refresh_data()
            else:
                QMessageBox.critical(self, "실패", "연장 실패")

    def action_suspend(self, user_id):
        """회원 사용정지"""
        if QMessageBox.question(self, "확인", "해당 회원을 사용정지하시겠습니까?\n(복구는 나중에 가능)") == QMessageBox.StandardButton.Yes:
            if api.suspend_user(user_id):
                QMessageBox.information(self, "성공", "회원이 사용정지되었습니다.")
                self.refresh_data()
            else:
                QMessageBox.critical(self, "실패", "사용정지 실패")

    def action_resume(self, user_id):
        """사용정지된 회원 복구"""
        if QMessageBox.question(self, "확인", "해당 회원을 사용 복구하시겠습니까?") == QMessageBox.StandardButton.Yes:
            if api.resume_user(user_id):
                QMessageBox.information(self, "성공", "회원이 복구되었습니다.")
                self.refresh_data()
            else:
                QMessageBox.critical(self, "실패", "복구 실패")