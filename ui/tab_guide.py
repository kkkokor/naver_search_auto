from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
from PyQt6.QtCore import Qt

class UserGuideWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet("background-color: white; padding: 20px; font-family: 'Malgun Gothic'; font-size: 14px;")
        
        # HTML 형식의 사용 설명서
        html_content = """
        <h1 style="color: #03c75a;">📌 네이버 광고 관리 솔루션 사용 가이드</h1>
        <hr style="border: 1px solid #ddd;">
        
        <h2 style="color: #007bff;">🚀 1. 자동 입찰 (Auto Bidder)</h2>
        <p><b>목표 순위 유지 자동화 시스템</b></p>
        <p>
        네이버 검색광고의 입찰가를 수동으로 조정하는 것은 번거롭습니다. 
        이 기능은 목표로 삼은 순위를 자동으로 유지하면서, 
        필요에 따라 입찰가를 올리거나 내려줍니다.
        </p>
        <h4>💡 사용 방법:</h4>
        <ol>
            <li><b>캠페인/그룹 선택:</b> 좌측 트리에서 입찰가 조정을 원하는 광고그룹을 체크합니다.</li>
            <li><b>설정 입력:</b> 우측 '공통 설정 값' 영역에서:
                <ul>
                    <li><b>목표 순위:</b> 유지하고 싶은 순위 (예: 3위)</li>
                    <li><b>최대 입찰가:</b> 절대 넘지 않을 최대 금액 (예: 20,000원)</li>
                    <li><b>입찰 단위:</b> 한 번에 조정할 가격 (예: 500원)</li>
                    <li><b>탐색 한도:</b> 노출이 적어 순위 데이터가 부족할 때 시도해볼 입찰가 최대 한도 (예: 5,000원)</li>
                    <li><b>신뢰 노출:</b> 최소 몇 번의 노출 후 순위를 신뢰할지 (예: 20회 이상)</li>
                </ul>
            </li>
            <li><b>저장:</b> "▼ 설정 적용하여 대기열 추가" 버튼을 누릅니다.</li>
            <li><b>실행:</b> "🚀 입찰 시작" 버튼을 눌러 자동 입찰을 시작합니다.</li>
        </ol>
        <p style="background-color: #f0f8ff; padding: 10px; border-left: 4px solid #007bff;">
        💡 <b>팁:</b> "무한반복" 옵션을 켜면 설정한 대기 시간마다 계속 순위를 확인하고 입찰가를 조정합니다.
        </p>
        <h4>⭐ 일괄 입찰가 설정:</h4>
        <p>
        모든 키워드를 같은 금액으로 통일하고 싶다면 <b>섹션 4 '일괄 입찰가 설정'</b>을 사용하세요.
        캠페인을 선택하고 원하는 입찰가를 입력 후 "✓ 일괄 설정 실행"을 누르면 
        해당 캠페인의 모든 키워드가 한 번에 설정됩니다.
        </p>
        <br>
        
        <h2 style="color: #007bff;">🎨 2. 광고 소재 관리 (Creative)</h2>
        <p><b>광고 문구와 이미지 한 곳에서 관리하기</b></p>
        <p>
        좋은 광고 소재를 만들었다면, 이를 여러 광고그룹에 복사하여 사용하는 것이 효율적입니다.
        이 기능은 소재 생성, 조회, 그리고 일괄 복사를 간편하게 해줍니다.
        </p>
        <h4>💡 사용 방법:</h4>
        <ol>
            <li><b>소재 작성:</b> 네이버 센터에서 광고 소재를 먼저 만듭니다.</li>
            <li><b>분석 시작:</b> "새로고침 / 분석 시작" 버튼을 눌러 현재 소재들을 불러옵니다.</li>
            <li><b>소재 선택:</b> 복사하고 싶은 소재를 선택합니다.</li>
            <li><b>대상 선택:</b> 체크박스에서 소재를 복사할 광고그룹을 선택합니다.</li>
            <li><b>복사 실행:</b> "선택한 그룹에 복사하기" 버튼을 눌러 일괄 등록합니다.</li>
        </ol>
        <p style="background-color: #fff3cd; padding: 10px; border-left: 4px solid #ff9800;">
        ⚠️ <b>주의:</b> 소재 복사는 네이버 API 정책에 따라 느릴 수 있습니다. 여유 있게 기다려주세요.
        </p>
        <br>
        
        <h2 style="color: #007bff;">🔗 3. 확장 소재 (Ad Extensions)</h2>
        <p><b>한 그룹의 확장소재를 다른 그룹들에 쉽게 복제하기</b></p>
        <p>
        네이버 광고에 추가 정보(전화번호, 위치, 서브링크 등)를 붙일 수 있습니다.
        이러한 확장 소재는 클릭률을 높이는 데 매우 효과적입니다.
        이미 잘 만들어진 확장 소재가 있다면, 다른 수십~수백 개의 그룹에 일괄 복사할 수 있습니다.
        </p>
        <h4>💡 사용 방법:</h4>
        <ol>
            <li><b>캠페인 선택:</b> 분석할 캠페인을 선택합니다.</li>
            <li><b>분석 시작:</b> "새로고침 / 분석 시작" 버튼으로 현재 확장 소재를 조회합니다.</li>
            <li><b>탭으로 필터링:</b> 필요한 확장 소재 유형을 선택합니다.
                <ul>
                    <li><b>전화번호(PHONE):</b> 고객이 클릭하면 바로 전화 연결</li>
                    <li><b>서브링크(SUB_LINKS):</b> "예약하기", "가격 보기" 등 추가 링크</li>
                    <li><b>헤드라인/설명(HEADLINE/DESCRIPTION):</b> 광고 제목과 설명 추가</li>
                    <li><b>이미지(IMAGE):</b> 이미지를 함께 표시</li>
                </ul>
            </li>
            <li><b>복사할 확장소재 선택:</b> 화면에 표시된 카드 중 복사하고 싶은 확장소재를 찾습니다.</li>
            <li><b>대상 그룹 선택:</b> 해당 카드 하단에서 복사할 광고그룹들을 체크합니다.</li>
            <li><b>복사 실행:</b> "선택한 그룹에 복사하기" 버튼을 눌러 일괄 등록합니다.</li>
        </ol>
        <p style="background-color: #f0f8ff; padding: 10px; border-left: 4px solid #007bff;">
        💡 <b>팁:</b> 확장 소재가 많을수록 광고 품질이 높아져 입찰가를 낮춰도 순위 유지가 가능합니다!
        </p>
        <p style="background-color: #fff3cd; padding: 10px; border-left: 4px solid #ff9800;">
        ⚠️ <b>주의:</b> 확장소재 복사는 네이버 API 정책에 따라 느릴 수 있습니다. 여유 있게 기다려주세요.
        </p>
        <br>
        
        <h2 style="color: #007bff;">✨ 4. 키워드 확장 (Keyword Expansion)</h2>
        <p><b>광고그룹명 매핑을 통한 대량 키워드 자동 생성</b></p>
        <p>
        광고그룹명에 지역 정보가 포함되어 있다면, 이를 자동으로 인식하여 
        원하는 키워드와 조합해 수백 개의 키워드를 생성할 수 있습니다.
        </p>
        <h4>📋 그룹명 매핑 방식:</h4>
        <p>
        광고그룹명을 다음과 같은 형식으로 작성하면 자동으로 지역을 추출합니다:<br>
        <b>예시:</b> <code>서울강남구그룹(강남,역삼,서초)</code><br>
        → 괄호 안의 <b>강남, 역삼, 서초</b>가 <b>A 키워드</b>(지역)로 자동 인식됩니다.
        </p>
        <h4>💡 사용 방법:</h4>
        <ol>
            <li><b>광고그룹 선택:</b> 좌측에서 키워드를 추가할 광고그룹을 선택합니다.</li>
            <li><b>A 키워드 확인:</b> 그룹명에서 자동 추출된 지역 키워드를 확인합니다.
                <ul>
                    <li>그룹명: <b>서울강남구그룹(강남,역삼,서초)</b></li>
                    <li>추출된 A 키워드: <b>강남, 역삼, 서초</b></li>
                </ul>
            </li>
            <li><b>B 키워드 입력:</b> 우측 입력란에 조합할 키워드를 입력합니다.
                <ul>
                    <li>콤마(,) 또는 줄바꿈으로 구분</li>
                    <li>예: <code>마케팅,온라인광고,바이럴마케팅</code></li>
                </ul>
            </li>
            <li><b>조합 방식 선택:</b>
                <ul>
                    <li><b>A+B 조합:</b> "강남 마케팅", "역삼 온라인광고", "서초 바이럴마케팅" 형태</li>
                    <li><b>B+A 조합:</b> "마케팅 강남", "온라인광고 역삼", "바이럴마케팅 서초" 형태</li>
                    <li><b>B 키워드만:</b> "마케팅", "온라인광고", "바이럴마케팅" (지역 제외)</li>
                </ul>
            </li>
            <li><b>실행:</b> "🔍 키워드 분석 및 등록" 버튼을 눌러 자동 생성 및 등록합니다.</li>
        </ol>
        <p style="background-color: #f0f8ff; padding: 10px; border-left: 4px solid #007bff;">
        💡 <b>예시:</b> A 키워드 3개(강남,역삼,서초) × B 키워드 3개(마케팅,온라인광고,바이럴) = 최대 9개 키워드 자동 생성!<br>
        A+B 조합 시: "강남 마케팅", "강남 온라인광고", "강남 바이럴", "역삼 마케팅", "역삼 온라인광고"...
        </p>
        <p style="background-color: #fff3cd; padding: 10px; border-left: 4px solid #ff9800;">
        ⚠️ <b>주의:</b> 그룹명에 괄호가 없으면 A 키워드를 추출할 수 없습니다. 반드시 <code>그룹명(지역1,지역2)</code> 형식으로 작성하세요.
        </p>
        <br>
        
        <hr style="border: 1px solid #ddd;">
        <h2 style="color: #28a745;">📞 문의 및 기술 지원</h2>
        <p>문의사항이나 기술적 문제가 있으시면 아래로 연락 바랍니다.</p>
        <p style="background-color: #f0f8ff; padding: 15px; border-left: 4px solid #28a745; border-radius: 4px;">
        <b>🏢 ID Company</b><br>
        담당자: 최지용<br>
        📞 전화: <b>010-8839-8387</b><br>
        ⏰ 업무 시간: 평일 09:00 ~ 18:00
        </p>
        
        <hr style="border: 1px solid #ddd;">
        <p style="color: #999; font-size: 12px; text-align: center;">
        본 솔루션은 네이버 검색광고 API를 기반으로 개발되었습니다.<br>
        버전: 1.0 | 마지막 업데이트: 2026년 1월
        </p>
        """
        
        self.browser.setHtml(html_content)
        layout.addWidget(self.browser)