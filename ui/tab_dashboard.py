import time
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QDateEdit,
    QMessageBox, QSplitter, QProgressBar, QComboBox, QTabWidget, QFrame,
    QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate
from PyQt6.QtGui import QColor, QBrush, QFont

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

from api.api_client import api

# 한글 폰트 설정
try:
    plt.rcParams['font.family'] = 'Malgun Gothic'
    plt.rcParams['axes.unicode_minus'] = False
except:
    pass

# -------------------------------------------------------------------------
# [대시보드 데이터 로더] 전체 캠페인 리스트 조회
# -------------------------------------------------------------------------
class DashboardLoader(QThread):
    data_signal = pyqtSignal(list)
    status_signal = pyqtSignal(str)
    
    def __init__(self, selected_campaign_ids, since, until):
        super().__init__()
        self.selected_campaign_ids = selected_campaign_ids
        self.since = since
        self.until = until

    def run(self):
        try:
            if not self.selected_campaign_ids:
                self.status_signal.emit("캠페인을 선택해주세요")
                self.data_signal.emit([])
                return
            
            result = []
            
            # 선택된 캠페인들만 조회
            for camp_id in self.selected_campaign_ids:
                self.status_signal.emit(f"조회 중: {camp_id}")
                
                # 캠페인 통계
                camp_stats_map = api.get_stats([camp_id], since=self.since, until=self.until)
                camp_stats = camp_stats_map.get(camp_id, {})
                
                # 광고그룹 조회
                groups = api.get_adgroups(camp_id)
                
                # 그룹 통계 일괄 조회
                group_ids = [g['nccAdgroupId'] for g in groups]
                group_stats_map = {}
                if group_ids:
                    group_stats_map = api.get_stats(group_ids, since=self.since, until=self.until)
                
                # 그룹 데이터 구성
                group_data_list = []
                for group in groups:
                    gid = group['nccAdgroupId']
                    gname = group['name']
                    
                    group_data_list.append({
                        'id': gid,
                        'name': gname,
                        'stats': group_stats_map.get(gid, {})
                    })
                
                result.append({
                    'id': camp_id,
                    'stats': camp_stats,
                    'groups': group_data_list
                })
                
                time.sleep(0.2)
            
            self.data_signal.emit(result)
        except Exception as e:
            self.status_signal.emit(f"오류: {str(e)}")
            self.data_signal.emit([])

# -------------------------------------------------------------------------
# [메인 대시보드 UI]
# -------------------------------------------------------------------------
class DashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.loader = None
        self.campaign_data = []
        self.all_campaigns = []  # 전체 캠페인 리스트
        self.init_ui()
        self.load_campaign_list()  # 초기 캠페인 리스트 로드
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # [상단] 기간 선택 카드
        top_card = QFrame()
        top_card.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
                padding: 15px;
            }
        """)
        top_layout = QHBoxLayout(top_card)
        
        # 타이틀
        title_label = QLabel("📊 통계 조회")
        title_label.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        top_layout.addWidget(title_label)
        top_layout.addSpacing(20)
        
        # 기본값: 어제
        yesterday = QDate.currentDate().addDays(-1)
        
        self.date_from = QDateEdit()
        self.date_from.setDate(yesterday)
        self.date_from.setCalendarPopup(True)
        self.date_from.setStyleSheet("""
            QDateEdit {
                padding: 8px 12px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                background: white;
                min-width: 120px;
            }
            QDateEdit:focus {
                border: 2px solid #0d6efd;
            }
        """)
        
        self.date_to = QDateEdit()
        self.date_to.setDate(yesterday)
        self.date_to.setCalendarPopup(True)
        self.date_to.setStyleSheet(self.date_from.styleSheet())
        
        top_layout.addWidget(QLabel("시작:"))
        top_layout.addWidget(self.date_from)
        top_layout.addWidget(QLabel("~"))
        top_layout.addWidget(self.date_to)
        top_layout.addSpacing(10)
        
        # 빠른 선택 버튼
        btn_style = """
            QPushButton {
                padding: 8px 16px;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                background: white;
                color: #495057;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #f8f9fa;
                border-color: #0d6efd;
                color: #0d6efd;
            }
            QPushButton:pressed {
                background: #e7f1ff;
            }
        """
        
        btn_yesterday = QPushButton("어제")
        btn_yesterday.clicked.connect(self.select_yesterday)
        btn_yesterday.setStyleSheet(btn_style)
        
        btn_this_week = QPushButton("이번 주")
        btn_this_week.clicked.connect(self.select_this_week)
        btn_this_week.setStyleSheet(btn_style)
        
        btn_this_month = QPushButton("이번 달")
        btn_this_month.clicked.connect(self.select_this_month)
        btn_this_month.setStyleSheet(btn_style)
        
        top_layout.addWidget(btn_yesterday)
        top_layout.addWidget(btn_this_week)
        top_layout.addWidget(btn_this_month)
        top_layout.addSpacing(10)
        
        btn_refresh = QPushButton("🔄 조회")
        btn_refresh.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0d6efd, stop:1 #0b5ed7);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0b5ed7, stop:1 #0a58ca);
            }
            QPushButton:pressed {
                background: #0a58ca;
            }
        """)
        btn_refresh.clicked.connect(self.load_data)
        top_layout.addWidget(btn_refresh)
        
        top_layout.addStretch()
        
        layout.addWidget(top_card)
        
        # [캠페인 선택] 카드
        campaign_card = QFrame()
        campaign_card.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
                padding: 15px;
            }
        """)
        campaign_layout = QVBoxLayout(campaign_card)
        
        campaign_title = QLabel("📂 캠페인 선택")
        campaign_title.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        campaign_layout.addWidget(campaign_title)
        
        # 전체 선택/해제 버튼
        select_buttons_layout = QHBoxLayout()
        btn_select_all = QPushButton("전체 선택")
        btn_select_all.clicked.connect(self.select_all_campaigns)
        btn_select_all.setStyleSheet(btn_style)
        
        btn_deselect_all = QPushButton("전체 해제")
        btn_deselect_all.clicked.connect(self.deselect_all_campaigns)
        btn_deselect_all.setStyleSheet(btn_style)
        
        select_buttons_layout.addWidget(btn_select_all)
        select_buttons_layout.addWidget(btn_deselect_all)
        select_buttons_layout.addStretch()
        campaign_layout.addLayout(select_buttons_layout)
        
        # 캠페인 리스트 (체크박스)
        self.campaign_list = QListWidget()
        self.campaign_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background: #fafafa;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background: #e7f1ff;
            }
            QListWidget::item:selected {
                background: #0d6efd;
                color: white;
            }
        """)
        self.campaign_list.setMaximumHeight(200)
        campaign_layout.addWidget(self.campaign_list)
        
        layout.addWidget(campaign_card)
        
        # [메인] 좌측 트리 + 우측 통계
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 좌측: 캠페인/그룹 트리 (모던한 카드)
        left_card = QFrame()
        left_card.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
            }
        """)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(15, 15, 15, 15)
        
        tree_title = QLabel("📁 캠페인 구조")
        tree_title.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        left_layout.addWidget(tree_title)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("캠페인 / 광고그룹")
        self.tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background: #fafafa;
                padding: 5px;
            }
            QTreeWidget::item {
                padding: 8px;
                border-radius: 4px;
            }
            QTreeWidget::item:selected {
                background: #e7f1ff;
                color: #0d6efd;
            }
            QTreeWidget::item:hover {
                background: #f0f0f0;
            }
        """)
        left_layout.addWidget(self.tree)
        
        # 우측: 통계 탭 (테이블 + 차트만, 비교차트 제거)
        right_card = QFrame()
        right_card.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
            }
        """)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(15, 15, 15, 15)
        
        stats_title = QLabel("📊 통계 상세")
        stats_title.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        right_layout.addWidget(stats_title)
        
        # 탭 위젯
        self.tab_view = QTabWidget()
        self.tab_view.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background: white;
            }
            QTabBar::tab {
                padding: 10px 20px;
                margin-right: 5px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                background: #f8f9fa;
                color: #6c757d;
            }
            QTabBar::tab:selected {
                background: white;
                color: #0d6efd;
                font-weight: bold;
                border-bottom: 2px solid #0d6efd;
            }
            QTabBar::tab:hover {
                background: #e9ecef;
            }
        """)
        
        # [탭1] 테이블 뷰
        self.table_stats = QTableWidget()
        self.table_stats.setColumnCount(2)
        self.table_stats.setHorizontalHeaderLabels(["항목", "수치"])
        self.table_stats.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_stats.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_stats.setStyleSheet("""
            QTableWidget {
                border: none;
                background: white;
                gridline-color: #f0f0f0;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background: #f8f9fa;
                padding: 10px;
                border: none;
                border-bottom: 2px solid #dee2e6;
                font-weight: bold;
                color: #495057;
            }
        """)
        self.tab_view.addTab(self.table_stats, "📊 테이블")
        
        # [탭2] 차트 뷰 (선택된 캠페인/그룹만)
        self.chart_widget = QWidget()
        chart_layout = QVBoxLayout(self.chart_widget)
        chart_layout.setContentsMargins(10, 10, 10, 10)
        self.figure = Figure(figsize=(8, 6), facecolor='white')
        self.canvas = FigureCanvas(self.figure)
        chart_layout.addWidget(self.canvas)
        self.tab_view.addTab(self.chart_widget, "📈 차트")
        
        right_layout.addWidget(self.tab_view)
        
        splitter.addWidget(left_card)
        splitter.addWidget(right_card)
        splitter.setSizes([300, 500])
        
        layout.addWidget(splitter)
        
        # 상태 바 (모던한 스타일)
        status_bar = QFrame()
        status_bar.setStyleSheet("""
            QFrame {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        status_layout = QHBoxLayout(status_bar)
        self.lbl_status = QLabel("✨ 기간을 선택하고 조회 버튼을 눌러주세요")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #6c757d; font-size: 12px;")
        status_layout.addWidget(self.lbl_status)
        layout.addWidget(status_bar)

    def load_campaign_list(self):
        """초기 캠페인 리스트 로드"""
        try:
            # 전체 캠페인 조회
            res = api.call_naver("/ncc/campaigns")
            if not res:
                self.lbl_status.setText("캠페인 조회 실패")
                return
            
            self.all_campaigns = []
            for camp in res:
                if camp.get('userLock') or camp.get('delFlag'):
                    continue
                
                self.all_campaigns.append({
                    'id': camp['nccCampaignId'],
                    'name': camp['name']
                })
            
            # 리스트 위젯에 추가 (체크박스)
            self.campaign_list.clear()
            for camp in self.all_campaigns:
                item = QListWidgetItem(camp['name'])
                item.setData(Qt.ItemDataRole.UserRole, camp['id'])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)  # 기본 체크
                self.campaign_list.addItem(item)
            
            self.lbl_status.setText(f"✨ {len(self.all_campaigns)}개 캠페인 로드 완료. 기간을 선택하고 조회하세요.")
                
        except Exception as e:
            print(f"캠페인 리스트 로드 오류: {e}")
            self.lbl_status.setText(f"캠페인 로드 오류: {e}")
    
    def select_all_campaigns(self):
        """전체 캠페인 선택"""
        for i in range(self.campaign_list.count()):
            item = self.campaign_list.item(i)
            item.setCheckState(Qt.CheckState.Checked)
    
    def deselect_all_campaigns(self):
        """전체 캠페인 선택 해제"""
        for i in range(self.campaign_list.count()):
            item = self.campaign_list.item(i)
            item.setCheckState(Qt.CheckState.Unchecked)

    def load_data(self):
        """선택한 캠페인과 기간으로 데이터 조회"""
        # 체크된 캠페인 ID 수집
        selected_ids = []
        for i in range(self.campaign_list.count()):
            item = self.campaign_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                campaign_id = item.data(Qt.ItemDataRole.UserRole)
                selected_ids.append(campaign_id)
        
        if not selected_ids:
            self.lbl_status.setText("캠페인을 선택해주세요")
            return
        
        since = self.date_from.date().toString(Qt.DateFormat.ISODate)
        until = self.date_to.date().toString(Qt.DateFormat.ISODate)
        
        self.lbl_status.setText("조회 중...")
        self.tree.clear()
        self.table_stats.setRowCount(0)
        
        self.loader = DashboardLoader(selected_ids, since, until)
        self.loader.data_signal.connect(self.on_data_loaded)
        self.loader.status_signal.connect(self.lbl_status.setText)
        self.loader.start()

    def on_data_loaded(self, data):
        """조회된 데이터로 트리 구성"""
        self.campaign_data = data
        self.tree.clear()
        
        if not data:
            self.lbl_status.setText("데이터 없음")
            return
        
        # 캠페인별로 트리 아이템 생성
        for camp in data:
            camp_item = QTreeWidgetItem(self.tree)
            camp_item.setText(0, camp['name'])
            camp_item.setData(0, Qt.ItemDataRole.UserRole, ('campaign', camp['id']))
            camp_item.setFont(0, QFont("Malgun Gothic", 10, QFont.Weight.Bold))
            
            # 캠페인 통계 요약
            stats = camp['stats']
            imp = stats.get('impCnt', 0)
            clk = stats.get('clkCnt', 0)
            cost = stats.get('salesAmt', 0)
            summary = f"노출:{imp} | 클릭:{clk} | 비용:{cost:,.0f}원"
            camp_item.setText(0, f"{camp['name']} ({summary})")
            
            # 광고그룹
            for group in camp['groups']:
                group_item = QTreeWidgetItem(camp_item)
                group_item.setText(0, group['name'])
                group_item.setData(0, Qt.ItemDataRole.UserRole, ('group', group['id']))
                
                # 그룹 통계 요약
                g_stats = group['stats']
                g_imp = g_stats.get('impCnt', 0)
                g_clk = g_stats.get('clkCnt', 0)
                g_cost = g_stats.get('salesAmt', 0)
                g_summary = f"노출:{g_imp} | 클릭:{g_clk} | 비용:{g_cost:,.0f}원"
                group_item.setText(0, f"{group['name']} ({g_summary})")
        
        self.tree.expandAll()
        self.lbl_status.setText(f"조회 완료 ({len(data)}개 캠페인)")

    def on_tree_selection_changed(self):
        """트리 선택 변경 시 상세 통계 표시"""
        selected = self.tree.selectedItems()
        if not selected:
            self.table_stats.setRowCount(0)
            return
        
        item = selected[0]
        item_type, item_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        # 데이터에서 찾기
        stats = None
        name = ""
        
        for camp in self.campaign_data:
            if item_type == 'campaign' and camp['id'] == item_id:
                stats = camp['stats']
                name = camp['name']
                break
            elif item_type == 'group':
                for group in camp['groups']:
                    if group['id'] == item_id:
                        stats = group['stats']
                        name = group['name']
                        break
        
        if stats is None:
            return
        
        # 테이블에 통계 표시
        self.display_stats(name, stats)
        
        # 차트 업데이트
        self.display_chart(name, stats)

    def display_stats(self, name, stats):
        """통계를 테이블에 표시"""
        self.table_stats.setRowCount(0)
        
        # 주요 통계 추출
        imp = stats.get('impCnt', 0)
        clk = stats.get('clkCnt', 0)
        cost = stats.get('salesAmt', 0)
        conv = stats.get('convCnt', 0)  # 전환수
        
        # 계산된 지표
        ctr = (clk / imp * 100) if imp > 0 else 0
        cpc = (cost / clk) if clk > 0 else 0
        cvr = (conv / clk * 100) if clk > 0 else 0
        cpa = (cost / conv) if conv > 0 else 0
        
        # 테이블 데이터
        data = [
            ("📌 대상", name),
            ("", ""),  # 구분선
            ("📊 주요 지표", ""),
            ("노출수", f"{imp:,}"),
            ("클릭수", f"{clk:,}"),
            ("총비용", f"{cost:,.0f}원"),
            ("전환수", f"{conv:,}"),
            ("", ""),  # 구분선
            ("📈 효율 지표", ""),
            ("클릭률 (CTR)", f"{ctr:.2f}%"),
            ("평균 클릭비용 (CPC)", f"{cpc:,.0f}원"),
            ("전환율 (CVR)", f"{cvr:.2f}%"),
            ("전환당비용 (CPA)", f"{cpa:,.0f}원"),
        ]
        
        self.table_stats.setRowCount(len(data))
        
        for row, (label, value) in enumerate(data):
            # 라벨
            label_item = QTableWidgetItem(label)
            if label == "":
                label_item.setBackground(QBrush(QColor("#f8f9fa")))
            elif label.startswith("📌") or label.startswith("📊") or label.startswith("📈"):
                label_item.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
                label_item.setBackground(QBrush(QColor("#e7f1ff")))
                label_item.setForeground(QBrush(QColor("#0d6efd")))
            
            self.table_stats.setItem(row, 0, label_item)
            
            # 값
            value_item = QTableWidgetItem(value)
            if label == "":
                value_item.setBackground(QBrush(QColor("#f8f9fa")))
            elif label.startswith("📌") or label.startswith("📊") or label.startswith("📈"):
                value_item.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
                value_item.setBackground(QBrush(QColor("#e7f1ff")))
                value_item.setForeground(QBrush(QColor("#0d6efd")))
            else:
                # 일반 값 스타일
                value_item.setFont(QFont("Malgun Gothic", 10))
                if any(x in label for x in ["클릭", "비용"]):
                    value_item.setForeground(QBrush(QColor("#198754")))
            
            self.table_stats.setItem(row, 1, value_item)

    # [기간 선택 함수들]
    def select_yesterday(self):
        yesterday = QDate.currentDate().addDays(-1)
        self.date_from.setDate(yesterday)
        self.date_to.setDate(yesterday)
        self.load_data()

    def select_this_week(self):
        today = QDate.currentDate()
        start = today.addDays(-(today.dayOfWeek() - 1))
        self.date_from.setDate(start)
        self.date_to.setDate(today)
        self.load_data()

    def select_this_month(self):
        today = QDate.currentDate()
        start = QDate(today.year(), today.month(), 1)
        self.date_from.setDate(start)
        self.date_to.setDate(today)
        self.load_data()

    # [차트 시각화 함수]
    def display_chart(self, name, stats):
        """선택된 항목의 차트 표시"""
        self.figure.clear()
        
        # 데이터 추출
        imp = stats.get('impCnt', 0)
        clk = stats.get('clkCnt', 0)
        cost = stats.get('salesAmt', 0)
        conv = stats.get('convCnt', 0)
        
        ctr = (clk / imp * 100) if imp > 0 else 0
        cpc = (cost / clk) if clk > 0 else 0
        cvr = (conv / clk * 100) if clk > 0 else 0
        cpa = (cost / conv) if conv > 0 else 0
        
        # 2x2 서브플롯
        ax1 = self.figure.add_subplot(2, 2, 1)
        ax2 = self.figure.add_subplot(2, 2, 2)
        ax3 = self.figure.add_subplot(2, 2, 3)
        ax4 = self.figure.add_subplot(2, 2, 4)
        
        # [1] 주요 지표 막대 그래프 (전환수 포함)
        metrics = ['노출수', '클릭수', '전환수', '비용(천원)']
        values = [imp, clk, conv, cost/1000]
        colors = ['#0d6efd', '#198754', '#dc3545', '#ffc107']
        
        bars = ax1.bar(metrics, values, color=colors, alpha=0.85, edgecolor='white', linewidth=2)
        ax1.set_title(f'{name[:20]}...' if len(name) > 20 else name, 
                     fontweight='bold', fontsize=11, pad=10)
        ax1.set_ylabel('수치', fontsize=9)
        ax1.tick_params(axis='x', rotation=15, labelsize=9)
        ax1.grid(axis='y', alpha=0.3, linestyle='--')
        for bar, v in zip(bars, values):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{v:,.0f}', ha='center', va='bottom', fontsize=8, fontweight='bold')
        
        # [2] CTR & CVR 비율 비교
        ax2.bar(['CTR', 'CVR'], [ctr, cvr], color=['#17a2b8', '#28a745'], alpha=0.85, edgecolor='white', linewidth=2)
        ax2.set_title('클릭률 & 전환율', fontweight='bold', fontsize=11, pad=10)
        ax2.set_ylabel('%', fontsize=9)
        ax2.grid(axis='y', alpha=0.3, linestyle='--')
        for i, (label, val) in enumerate([('CTR', ctr), ('CVR', cvr)]):
            ax2.text(i, val, f'{val:.2f}%', ha='center', va='bottom', fontsize=9, fontweight='bold')
        
        # [3] CPC & CPA 비용 비교
        ax3.bar(['CPC', 'CPA'], [cpc, cpa], color=['#fd7e14', '#dc3545'], alpha=0.85, edgecolor='white', linewidth=2)
        ax3.set_title('평균 클릭비용 & 전환당비용', fontweight='bold', fontsize=11, pad=10)
        ax3.set_ylabel('원', fontsize=9)
        ax3.grid(axis='y', alpha=0.3, linestyle='--')
        for i, (label, val) in enumerate([('CPC', cpc), ('CPA', cpa)]):
            ax3.text(i, val, f'{val:,.0f}', ha='center', va='bottom', fontsize=8, fontweight='bold')
        
        # [4] 전환 퍼널 도넛 차트
        if imp > 0 and clk > 0 and conv > 0:
            # 노출 → 클릭 → 전환 퍼널
            sizes = [conv, clk-conv, imp-clk]
            labels = ['전환', '클릭(미전환)', '노출만']
            colors_pie = ['#dc3545', '#ffc107', '#e9ecef']
            explode = (0.08, 0.03, 0)
            
            wedges, texts, autotexts = ax4.pie(sizes, labels=labels, 
                   autopct='%1.1f%%', colors=colors_pie, startangle=90,
                   explode=explode, shadow=False, textprops={'fontsize': 8})
            
            # 도넛 효과
            centre_circle = plt.Circle((0,0), 0.70, fc='white')
            ax4.add_artist(centre_circle)
            
            ax4.set_title('전환 퍼널', fontweight='bold', fontsize=11, pad=10)
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
                autotext.set_fontsize(8)
        elif imp > 0 and clk > 0:
            # 전환 없을 때는 클릭만 표시
            sizes = [clk, imp-clk]
            labels = ['클릭', '노출만']
            colors_pie = ['#28a745', '#e9ecef']
            explode = (0.05, 0)
            
            wedges, texts, autotexts = ax4.pie(sizes, labels=labels, 
                   autopct='%1.1f%%', colors=colors_pie, startangle=90,
                   explode=explode, shadow=False, textprops={'fontsize': 9})
            
            centre_circle = plt.Circle((0,0), 0.70, fc='white')
            ax4.add_artist(centre_circle)
            
            ax4.set_title('노출 대비 클릭', fontweight='bold', fontsize=11, pad=10)
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
        else:
            ax4.text(0.5, 0.5, '📊\n데이터 없음', ha='center', va='center', 
                    transform=ax4.transAxes, fontsize=12, color='#999')
            ax4.set_title('전환 퍼널', fontweight='bold', fontsize=11, pad=10)
            ax4.axis('off')
        
        self.figure.tight_layout(pad=2.0)
        self.canvas.draw()
