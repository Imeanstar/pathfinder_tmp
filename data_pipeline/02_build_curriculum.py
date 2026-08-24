"""
소프트웨어및컴퓨터공학전공(2025학번) 교육과정·졸업요건 데이터를 빌드한다.

출처: data_pipeline/yoram_official_extract.md (공식 요람 PDF 발췌, 2026-08-20).
이 스크립트는 PDF를 매번 다시 파싱하지 않는다 — 검증이 끝난 값을 코드에 직접
옮겨 적었다(1회성 변환). 값이 바뀌면 yoram_official_extract.md와 이 파일을
함께 갱신할 것.

실행: python3 data_pipeline/02_build_curriculum.py
출력: data/courses.json, data/graduation_requirements.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# 전공필수 10개 — 학점 합산이 아니라 "전부 이수했는가"로 판정한다 (audit.py Task 3-2 참고)
REQUIRED_MAJOR_COURSES = [
    {"name": "컴퓨터프로그래밍및실습", "credit": 4, "offered_terms_main": ["1-1"], "offered_terms_sub": ["1-2"]},
    {"name": "이산수학", "credit": 3, "offered_terms_main": ["2-1"], "offered_terms_sub": ["1-2"]},
    {"name": "인공지능입문", "credit": 3, "offered_terms_main": ["2-1"], "offered_terms_sub": ["2-2"]},
    {"name": "객체지향프로그래밍및실습", "credit": 4, "offered_terms_main": ["2-1"], "offered_terms_sub": ["2-2"]},
    {"name": "자료구조", "credit": 3, "offered_terms_main": ["2-1"], "offered_terms_sub": ["2-2"]},
    {"name": "컴퓨터구조", "credit": 3, "offered_terms_main": ["2-1"], "offered_terms_sub": ["2-2"]},
    {"name": "알고리즘", "credit": 3, "offered_terms_main": ["2-2"], "offered_terms_sub": ["3-1"]},
    {"name": "컴퓨터네트워크", "credit": 3, "offered_terms_main": ["2-2"], "offered_terms_sub": ["3-1"]},
    {"name": "운영체제", "credit": 3, "offered_terms_main": ["3-1"], "offered_terms_sub": ["3-2"]},
    {"name": "시스템프로그래밍", "credit": 3, "offered_terms_main": ["2-2"], "offered_terms_sub": ["3-1"]},
]
assert sum(c["credit"] for c in REQUIRED_MAJOR_COURSES) == 32

# 전공선택 전체 목록 — 학점은 합산 판정(현장실습 과목군은 audit.py에서 6학점 상한 적용)
ELECTIVE_MAJOR_COURSES = [
    {"name": "디지털회로", "credit": 3, "offered_terms_main": ["1-2", "2-1"], "offered_terms_sub": []},
    {"name": "네트워크소프트웨어", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": []},
    {"name": "컴퓨터통신", "credit": 3, "offered_terms_main": ["3-1"], "offered_terms_sub": ["3-2"]},
    {"name": "데이터베이스", "credit": 3, "offered_terms_main": ["3-1"], "offered_terms_sub": ["3-2"]},
    {"name": "정보보호", "credit": 3, "offered_terms_main": ["3-1"], "offered_terms_sub": ["3-2"]},
    {"name": "오픈소스SW입문", "credit": 3, "offered_terms_main": ["3-1"], "offered_terms_sub": ["3-2"]},
    {"name": "기계학습", "credit": 3, "offered_terms_main": ["3-1"], "offered_terms_sub": ["3-2"]},
    {"name": "컴파일러", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": ["3-1"]},
    {"name": "데이터마이닝", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": ["4-1"]},
    {"name": "IT전문영어", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": ["3-1"]},
    {"name": "IT집중교육1", "credit": 6, "offered_terms_main": ["3-2"], "offered_terms_sub": []},
    {"name": "IT집중교육2", "credit": 6, "offered_terms_main": ["3-2"], "offered_terms_sub": []},
    {"name": "자기주도프로젝트", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": ["3-1"]},
    {"name": "계산이론", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": []},
    {"name": "지능형사물인터넷", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": []},
    {"name": "소프트웨어공학", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": ["3-1"]},
    {"name": "디지털포렌식", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": []},
    {"name": "웹시스템설계", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": []},
    {"name": "임베디드소프트웨어", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": []},
    {"name": "현대암호이론및응용", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": []},
    {"name": "실전코딩1", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": ["3-1"]},
    {"name": "실전코딩2", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": ["3-1"]},
    {"name": "블록체인과IoT", "credit": 3, "offered_terms_main": ["3-2"], "offered_terms_sub": []},
    {"name": "AI집중교육1", "credit": 6, "offered_terms_main": ["3-2"], "offered_terms_sub": []},
    {"name": "AI집중교육2", "credit": 6, "offered_terms_main": ["3-2"], "offered_terms_sub": []},
    {"name": "모델링시뮬레이션", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": []},
    {"name": "컴퓨터비젼", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": ["4-2"]},
    {"name": "SW창업론", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": []},
    {"name": "모바일네트워크", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": []},
    {"name": "컴퓨터그래픽스", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": []},
    {"name": "자기주도연구1", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": []},
    {"name": "분산시스템", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": ["4-2"]},
    {"name": "인공지능컴퓨터시스템", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": []},
    {"name": "AI임베디드시스템", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": []},
    {"name": "AIoT실시간서비스설계", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": []},
    {"name": "AI통신네트워크", "credit": 3, "offered_terms_main": ["4-2"], "offered_terms_sub": []},
    {"name": "분산병렬컴퓨팅", "credit": 3, "offered_terms_main": ["4-2"], "offered_terms_sub": []},
    {"name": "SW캡스톤디자인", "credit": 6, "offered_terms_main": ["4-2"], "offered_terms_sub": ["4-1"]},
    {"name": "SW산업세미나", "credit": 1, "offered_terms_main": ["4-2"], "offered_terms_sub": []},
    {"name": "고급컴퓨터구조", "credit": 3, "offered_terms_main": ["4-2"], "offered_terms_sub": []},
    {"name": "인간과컴퓨터상호작용", "credit": 3, "offered_terms_main": ["4-2"], "offered_terms_sub": []},
    {"name": "인공지능", "credit": 3, "offered_terms_main": ["4-2"], "offered_terms_sub": ["4-1"]},
    {"name": "자기주도연구2", "credit": 3, "offered_terms_main": ["4-2"], "offered_terms_sub": ["4-1"]},
    {"name": "SW현장실습1", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": []},
    {"name": "SW현장실습2", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": []},
    {"name": "SW현장실습3", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": []},
    {"name": "SW현장실습4", "credit": 3, "offered_terms_main": ["4-2"], "offered_terms_sub": []},
    {"name": "SW현장실습5", "credit": 3, "offered_terms_main": ["4-2"], "offered_terms_sub": []},
    {"name": "SW현장실습6", "credit": 3, "offered_terms_main": ["4-2"], "offered_terms_sub": []},
    {"name": "창업실습1", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": ["4-2"]},
    {"name": "창업실습2", "credit": 3, "offered_terms_main": ["4-2"], "offered_terms_sub": ["4-1"]},
    {"name": "창업현장실습1", "credit": 3, "offered_terms_main": ["4-1"], "offered_terms_sub": ["4-2"]},
    {"name": "창업현장실습2", "credit": 3, "offered_terms_main": ["4-2"], "offered_terms_sub": ["4-1"]},
]

# 선수과목표 (yoram_official_extract.md 4장) — 과목명 -> 선수과목명 리스트
PREREQ_MAP = {
    "객체지향프로그래밍및실습": ["컴퓨터프로그래밍및실습"],
    "시스템프로그래밍": ["컴퓨터프로그래밍및실습"],
    "알고리즘": ["자료구조"],
    "운영체제": ["컴퓨터프로그래밍및실습"],
    "자료구조": ["컴퓨터프로그래밍및실습"],
    "IT전문영어": ["영어"],
    "IT집중교육1": ["객체지향프로그래밍및실습"],
    "IT집중교육2": ["객체지향프로그래밍및실습"],
    "계산이론": ["이산수학"],
    "고급컴퓨터구조": ["컴퓨터구조"],
    "기계학습": ["자료구조"],
    "네트워크소프트웨어": ["컴퓨터네트워크"],
    "데이터마이닝": ["자료구조"],
    "데이터베이스": ["자료구조"],
    "디지털포렌식": ["컴퓨터프로그래밍및실습"],
    "모델링시뮬레이션": ["자료구조"],
    "모바일네트워크": ["컴퓨터네트워크"],
    "분산시스템": ["컴퓨터프로그래밍및실습"],
    "블록체인과IoT": ["컴퓨터프로그래밍및실습"],
    "소프트웨어공학": ["객체지향프로그래밍및실습"],
    "오픈소스SW입문": ["컴퓨터프로그래밍및실습"],
    "웹시스템설계": ["객체지향프로그래밍및실습"],
    "인간과컴퓨터상호작용": ["알고리즘"],
    "인공지능": ["자료구조"],
    "임베디드소프트웨어": ["컴퓨터프로그래밍및실습"],
    "자기주도프로젝트": ["객체지향프로그래밍및실습"],
    "정보보호": ["자료구조"],
    "지능형사물인터넷": ["운영체제"],
    "컴파일러": ["자료구조"],
    "컴퓨터구조": ["컴퓨터프로그래밍및실습"],
    "컴퓨터그래픽스": ["자료구조"],
    "컴퓨터비젼": ["자료구조"],
}

GRADUATION_REQUIREMENTS = {
    "2025": {
        "total_credit": 128,
        "min_gpa": 2.0,
        "required_major_courses": [
            {"name": c["name"], "credit": c["credit"]} for c in REQUIRED_MAJOR_COURSES
        ],
        "elective_major_credit": {
            "심화과정": 32,
            "일반과정": 10,
            "복수과정": 10,
        },
        "elective_credit_cap_groups": {
            "현장실습군": {
                "courses": [
                    "SW현장실습1", "SW현장실습2", "SW현장실습3",
                    "SW현장실습4", "SW현장실습5", "SW현장실습6",
                    "창업실습1", "창업실습2",
                    "창업현장실습1", "창업현장실습2",
                ],
                "max_credit": 6,
            }
        },
        "requires_double_major_or_minor": ["일반과정", "복수과정"],
        "industry_project_certification": {
            "심화과정": {"min_courses": 2},
            "일반과정": {"min_courses": 1},
            "복수과정": {"min_courses": 1},
            "course_groups": {
                "집중교육과목군": ["IT집중교육1", "IT집중교육2", "AI집중교육1", "AI집중교육2"],
                "자기주도프로젝트과목군": ["자기주도프로젝트"],
                "현장실습과목군": [f"SW현장실습{i}" for i in range(1, 7)],
                "창업실습과목군": ["창업실습1", "창업실습2"],
                "캡스톤디자인과목군": ["SW캡스톤디자인"],
                "자기주도연구과목군": ["자기주도연구1", "자기주도연구2"],
            },
        },
        "programming_competency_certification": {
            "applies_to": ["심화과정"],
            "topcit_min_score": 190,
            "exemptions": [
                "APC 대회 참가 및 1문제 이상 정답",
                "SW 관련 전국대회 입상(2개년 이상 개최, 참가 100명 이상)",
            ],
        },
        "language_requirement": {
            "TOEIC": 730, "TEPS": 605, "TOEFL_PBT": 534, "TOEFL_CBT": 200,
            "TOEFL_iBT": 72, "GTELP_Lv2": 67, "GTELP_Lv3": 89,
            "TOEIC_Speaking": "IM1", "OPIc": "IL",
        },
    }
}


def build_courses():
    # 2026-08-21 추가: 요람은 "이 학기에 듣는 걸 강력 추천"(●)과 "이때 들어도 무방"
    # (〈●〉)을 구분해서 표시하는데, 예전엔 이 둘을 offered_terms 하나로 합쳐버려서
    # "언제 들어도 그만"인 것처럼 취급했다(로드맵 배치 근거가 불투명하다는 지적,
    # 사용자가 준 요람 표 캡처로 재대조). recommended_terms/optional_terms로 분리해
    # 내보내되, 기존 코드(prereq/개설학기 체크)가 의존하는 offered_terms는 그대로
    # main+sub 합집합으로 유지해 하위 호환을 깨지 않는다.
    courses = []
    for c in REQUIRED_MAJOR_COURSES:
        courses.append({
            "name": c["name"],
            "credit": c["credit"],
            "category": "전공필수",
            "prereq": PREREQ_MAP.get(c["name"], []),
            "offered_terms": c["offered_terms_main"] + c["offered_terms_sub"],
            "recommended_terms": c["offered_terms_main"],
            "optional_terms": c["offered_terms_sub"],
            "competency_tags": [],  # Task 2-4에서 채움 (역량 온톨로지 확정 후)
        })
    for c in ELECTIVE_MAJOR_COURSES:
        courses.append({
            "name": c["name"],
            "credit": c["credit"],
            "category": "전공선택",
            "prereq": PREREQ_MAP.get(c["name"], []),
            "offered_terms": c["offered_terms_main"] + c["offered_terms_sub"],
            "recommended_terms": c["offered_terms_main"],
            "optional_terms": c["offered_terms_sub"],
            "competency_tags": [],
        })
    return courses


def main():
    DATA_DIR.mkdir(exist_ok=True)
    courses = build_courses()

    with open(DATA_DIR / "courses.json", "w", encoding="utf-8") as f:
        json.dump(courses, f, ensure_ascii=False, indent=2)

    with open(DATA_DIR / "graduation_requirements.json", "w", encoding="utf-8") as f:
        json.dump(GRADUATION_REQUIREMENTS, f, ensure_ascii=False, indent=2)

    print(f"data/courses.json: {len(courses)}개 과목 "
          f"(전공필수 {len(REQUIRED_MAJOR_COURSES)}, 전공선택 {len(ELECTIVE_MAJOR_COURSES)})")
    print("data/graduation_requirements.json: 2025학번 항목 작성 완료")


if __name__ == "__main__":
    main()
