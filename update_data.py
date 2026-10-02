import os
import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import time

# =========================================================================
# 프로그램 명칭: KRA전국 승부예상AI_V6.8 (탑웨이트 챔피언 보정 & TOP3 적중 극대화)
# =========================================================================
VERSION = "KRA전국 승부예상AI_V6.8"
API_KEY = os.environ.get("KRA_API_KEY", "")
URL = "http://apis.data.go.kr/B551015/racedetailresult/getracedetailresult"

KST = timezone(timedelta(hours=9))

MEET_CONFIG = [
    ("1", "서울"),
    ("4", "영천"),
    ("2", "제주"),
    ("3", "부산경남")
]

JOCKEY_RATES = {
    # 서울 기수
    "문세영": 33.2, "김용근": 24.5, "빅투아르": 25.1, "유승완": 21.0,
    "송재철": 19.5, "이혁": 19.2, "임다빈": 18.5, "장추열": 18.0,
    "임기원": 17.5, "이동하": 16.0, "조인권": 21.4, "마이아": 22.0,
    # 부경/영천 기수
    "서승운": 31.5, "최시대": 26.8, "다나카": 25.4, "다비드": 24.2,
    "유현명": 23.8, "정도윤": 22.5, "김혜선": 20.8, "김동영": 17.8,
    "이성재": 16.5, "송경윤": 15.2, "전진구": 14.8, "김어수": 14.5, "손경민": 14.0,
    # 제주 기수
    "전현준": 26.5, "한영민": 24.2, "임재광": 21.8, "양민재": 19.5,
    "원유일": 18.2, "박재희": 17.5, "곽용남": 16.8, "김한남": 16.0,
    "강수한": 15.5, "이동준": 15.0, "안득수": 20.5, "정명일": 19.0
}

TRAINER_RATES = {
    # 서울 조교사
    "서홍수": 24.5, "송문길": 21.5, "배휴준": 20.8, "정호익": 19.5,
    "최용건": 19.0, "박재우": 17.2, "이강서": 16.8, "전승규": 16.0, "서인석": 15.0,
    # 부경/영천 조교사
    "김영관": 28.0, "라이스": 25.2, "민장기": 22.1, "구영준": 18.5,
    "김도현": 18.2, "안우성": 18.0, "임성실": 17.5, "백광열": 18.8, "강은석": 15.5,
    # 제주 조교사
    "심도연": 23.5, "김태준": 21.0, "강대은": 20.5, "김길홍": 18.5,
    "윤덕상": 17.8, "김대연": 17.2, "이준호": 16.5, "문성호": 15.8, "고성동": 22.0
}

def parse_time_seconds(time_str):
    try:
        t = str(time_str).strip().replace("'", "").replace('"', '')
        if not t: return None
        if ":" in t:
            parts = t.split(":")
            return float(parts[0]) * 60 + float(parts[1])
        if t.count(".") == 2:
            parts = t.split(".")
            return float(parts[0]) * 60 + float(f"{parts[1]}.{parts[2]}")
        val = float(t)
        if val > 20.0: return val
    except:
        pass
    return None

def fetch_meet_data(meet_code, meet_name, date_str):
    params = {
        "serviceKey": API_KEY,
        "pageNo": "1",
        "numOfRows": "150",
        "meet": meet_code,
        "rc_date": date_str
    }
    full_url = f"{URL}?{urllib.parse.urlencode(params)}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "*/*"
    }

    try:
        req = urllib.request.Request(full_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        if not items:
            return []

        print(f"[{meet_name}] 마사회 데이터 수신: {len(items)}개 출전마")

        races = {}
        for it in items:
            def gv(tag_list):
                for t in tag_list:
                    n = it.find(t)
                    if n is not None and n.text and n.text.strip():
                        return n.text.strip()
                    for child in it:
                        if child.tag.lower() == t.lower():
                            if child.text and child.text.strip():
                                return child.text.strip()
                return ""

            raw_rc_no = gv(["rcNo", "rc_no"]) or "1"
            rc_no = str(int(raw_rc_no)) if raw_rc_no.isdigit() else raw_rc_no

            raw_gate = gv(["chulNo", "chul_no", "gateNo", "hrNo"]) or "0"
            gate = str(int(raw_gate)) if raw_gate.isdigit() else raw_gate
            name = gv(["hrName", "hr_name"]) or "경주마"
            jockey = gv(["jkName", "jk_name"]) or "기수"
            trainer = gv(["trName", "tr_name"]) or "조교사"
            weight = gv(["wgBudam", "wg_budam"]) or "55.0"
            track = gv(["track", "track_state", "trackCond", "weather"]) or "양호"

            rc_time = gv(["rcTime", "rc_time", "record", "rcRecord", "ordTime"]) or ""
            past_time = gv(["bestRecord", "bestRcTime", "recentRecord", "recentRcTime", "preRcTime"]) or ""
            g1f_time = gv(["g1f", "g1f_time", "g1fTime", "g1fRecord", "g_1f"]) or ""
            win_odds = gv(["winOdds", "win_odds", "win_rate", "odds"]) or "0"
            pre_ord = gv(["preOrd", "pre_ord", "recentOrd", "preRcOrd"]) or ""

            gear_info = gv(["gear", "janggu", "hrequip", "equip", "blinker", "equipName"]) or ""
            training_info = gv(["training", "jogyo", "trackwork", "trainType", "trainRider"]) or ""
            combo_info = gv(["combo", "dongban", "jkHrRecord", "jockeyCombo"]) or ""
            
            rc_cnt = gv(["rcCnt", "rc_cnt", "totRcCnt"]) or "0"
            ord1_cnt = gv(["ord1Cnt", "ord1_cnt", "totOrd1Cnt"]) or "0"
            ord2_cnt = gv(["ord2Cnt", "ord2_cnt", "totOrd2Cnt"]) or "0"

            s1f_rank = gv(["g1p", "s1f", "g1pRank", "ord1p"]) or "99"
            is_front = True if s1f_rank in ["1", "2", "01", "02"] else False

            # 착순 정확 추출
            ord_no = "-"
            direct_ord = gv(["ordNo", "ord_no", "ord", "rc_ord", "rcOrd", "rank", "rankNo", "chaksun"])
            if direct_ord and direct_ord.isdigit() and int(direct_ord) > 0:
                ord_no = str(int(direct_ord))
            else:
                for child in it:
                    tag_low = child.tag.lower()
                    if any(ex in tag_low for ex in ["cnt", "s1f", "g1p", "g2p", "g3p", "g4p", "pass", "time"]):
                        continue
                    if any(k in tag_low for k in ["ord", "rank", "plc", "place", "chak"]):
                        txt = child.text.strip() if child.text else ""
                        if txt.isdigit() and int(txt) > 0:
                            ord_no = str(int(txt))
                            break

            key = f"{meet_name}_{rc_no}"
            if key not in races:
                races[key] = {
                    "meet_code": meet_code,
                    "meet_name": meet_name,
                    "race_no": rc_no,
                    "race_date": date_str,
                    "distance": "1400",
                    "track": track,
                    "version": VERSION,
                    "horses": []
                }

            already_exists = any(h["gate"] == gate or h["name"] == name for h in races[key]["horses"])
            if already_exists:
                continue

            races[key]["horses"].append({
                "gate": gate,
                "name": name,
                "jockey": jockey,
                "trainer": trainer,
                "weight": weight,
                "track": track,
                "rc_time": rc_time,
                "past_time": past_time,
                "g1f_time": g1f_time,
                "win_odds": win_odds,
                "pre_ord": pre_ord,
                "gear_info": gear_info,
                "training_info": training_info,
                "combo_info": combo_info,
                "rc_cnt": rc_cnt,
                "ord1_cnt": ord1_cnt,
                "ord2_cnt": ord2_cnt,
                "is_front": is_front,
                "actual_ord": ord_no
            })

        for r in races.values():
            meet = r["meet_name"]
            r_no = str(int(r["race_no"])) if str(r["race_no"]).isdigit() else str(r["race_no"])

            if meet == "제주":
                actual_dist = "900" if r_no in ["1", "2", "3"] else ("1000" if r_no in ["4", "5"] else "1110")
            elif meet == "부산경남":
                actual_dist = "1200" if r_no in ["1", "2", "3"] else ("1400" if r_no in ["4", "5", "6"] else "1800")
            else:
                actual_dist = "1200" if r_no in ["1", "6"] else ("1400" if r_no in ["2", "8"] else "1800")

            r["distance"] = actual_dist
            dist = int(actual_dist)

            has_finished = any(h["actual_ord"].isdigit() and int(h["actual_ord"]) > 0 for h in r["horses"]) or \
                           any(parse_time_seconds(h.get("rc_time", "")) is not None for h in r["horses"])

            # 🎯 [핵심 1] 해당 경주 출전마들의 최고 부담중량(Top Weight) 산출!
            all_weights = []
            for h in r["horses"]:
                try:
                    all_weights.append(float(re.sub(r'[^0-9.]', '', str(h["weight"]))))
                except:
                    all_weights.append(55.0)
            max_race_weight = max(all_weights) if all_weights else 55.0

            # 스피드 잠재력 계산
            for h in r["horses"]:
                jk_r = JOCKEY_RATES.get(h["jockey"], 12.0)
                tr_r = TRAINER_RATES.get(h["trainer"], 14.0)
                g_val = int(h["gate"]) if str(h["gate"]).isdigit() else 5
                try:
                    w_val = float(re.sub(r'[^0-9.]', '', str(h["weight"])))
                except:
                    w_val = 55.0
                
                gate_power = 6.0 if g_val <= 3 else (4.0 if g_val <= 7 else 0.0)
                weight_power = (55.0 - w_val) * 1.5
                front_power = 10.0 if h["is_front"] else 0.0
                h["speed_power"] = jk_r * 0.8 + tr_r * 0.4 + gate_power + weight_power + front_power

            sorted_by_speed = sorted(r["horses"], key=lambda x: x["speed_power"], reverse=True)
            top_speed_gate = str(sorted_by_speed[0]["gate"]).strip() if sorted_by_speed else ""
            second_speed_gate = str(sorted_by_speed[1]["gate"]).strip() if len(sorted_by_speed) > 1 else ""

            for h in r["horses"]:
                h["distance"] = str(dist)
                score = 30.0
                tags = []
                g = int(h["gate"]) if str(h["gate"]).isdigit() else 5
                this_gate = str(h["gate"]).strip()

                # 1. 기수 & 조교사 복승률
                jk_rate = JOCKEY_RATES.get(h["jockey"], 12.0)
                score += (jk_rate * 0.8)
                if jk_rate >= 24.0:
                    tags.append("특급 기수 🏇")
                elif jk_rate >= 19.0:
                    tags.append("상위 기수")

                tr_rate = TRAINER_RATES.get(h["trainer"], 14.0)
                score += (tr_rate * 0.5)
                if tr_rate >= 20.0:
                    tags.append("우수 마방 🏆")

                # 2. 거리별 게이트 가중치 (외곽 감점 완전 배제)
                if dist <= 1300:
                    score += 6.0 if g <= 3 else (4.0 if g <= 7 else 0.0)
                    if g <= 3:
                        tags.append("단거리 황금게이트 ⚡")
                elif dist >= 1700:
                    score += 5.0 if g <= 4 else (3.0 if g <= 8 else 0.0)
                else:
                    score += 5.0 if g <= 4 else (3.0 if g <= 8 else 0.0)

                # 3. 🎯 [핵심 2: 제주 6R 교훈 완벽 반영] 부담중량의 역설 밸런스 패치!
                try:
                    clean_w = float(re.sub(r'[^0-9.]', '', str(h["weight"])))
                    
                    # (A) 경량마 (51~52.5kg): 가벼운 등짐 혜택
                    if clean_w <= 52.5:
                        score += (55.0 - clean_w) * 2.0
                        tags.append(f"경량 부중({clean_w}kg) ⚡")
                    # (B) 헤비급 챔피언 (57.5kg 이상 및 당일 최고 중량마): 체급 최강자 인정!
                    elif clean_w >= 57.5 and clean_w == max_race_weight:
                        # 과도한 감점을 없애고, 핸디캐퍼가 인정한 최강마 보너스 부여!
                        score += 5.0
                        tags.append("체급 최강자(탑웨이트) 🏋️")
                    else:
                        # 일반 중량마 완만한 감점 (최대 -3~4점 이내로 억제)
                        score -= max(0.0, (clean_w - 55.0) * 0.8)
                except:
                    pass

                # 4. 스피드 뱃지
                if has_finished:
                    sec = parse_time_seconds(h.get("rc_time", ""))
                    if sec:
                        base_time = {
                            800: 52.0, 900: 59.0, 1000: 65.5, 1110: 73.0, 1200: 74.8, 1400: 88.5
                        }.get(dist, dist * 0.063 + 0.5)
                        diff = base_time - sec
                        if diff >= 1.0:
                            score += 10.0
                            tags.append(f"스피드 지수 최상({round(sec,1)}초) 🏎️")
                        elif diff >= 0.0:
                            score += 5.0
                            tags.append("기록 우수")
                else:
                    past_sec = parse_time_seconds(h.get("past_time", ""))
                    if past_sec:
                        score += 10.0
                        tags.append(f"과거 스피드 최상({round(past_sec,1)}초) 🏎️")
                    elif this_gate == top_speed_gate:
                        score += 10.0
                        tags.append("과거 스피드 최상 🏎️")
                    elif this_gate == second_speed_gate:
                        score += 5.0
                        tags.append("스피드 우수 🏎️")

                # 5. 전적
                if not has_finished:
                    tot_rc = int(re.sub(r'[^0-9]', '', str(h.get("rc_cnt", "0"))) or 0)
                    ord1_cnt = int(re.sub(r'[^0-9]', '', str(h.get("ord1_cnt", "0"))) or 0)
                    ord2_cnt = int(re.sub(r'[^0-9]', '', str(h.get("ord2_cnt", "0"))) or 0)
                    if tot_rc >= 3:
                        quinella_rate = round(((ord1_cnt + ord2_cnt) / tot_rc) * 100, 1)
                        if quinella_rate >= 40.0:
                            score += 8.0
                            tags.append(f"통산 복승률 최상({quinella_rate}%) 🏎️")
                        elif quinella_rate >= 25.0:
                            score += 4.0
                            tags.append(f"검증된 입상마({quinella_rate}%)")

                # 6. 마구 변경
                g_str = str(h.get("gear_info", "")).strip()
                if any(k in g_str for k in ["눈가면(신규)", "블링커(신규)", "신규눈가면"]):
                    score += 6.0
                    tags.append("눈가면 첫 착용 🤿")

                # 7. 조교 강도
                t_str = str(h.get("training_info", "")).strip()
                if any(k in t_str for k in ["습보", "강훈련"]):
                    score += 7.0
                    tags.append("새벽 습보 강훈련 🏋️")
                if h["jockey"] and h["jockey"] in t_str:
                    score += 5.0
                    tags.append("기수 직접 전담조교 🚴")

                # 8. 찰떡 콤비
                c_str = str(h.get("combo_info", "")).strip()
                if any(k in c_str for k in ["1승", "2승", "우승"]):
                    score += 6.0
                    tags.append("찰떡 콤비(우승 경험) 🤝")

                # 9. 선행력
                if h["is_front"]:
                    score += 6.0
                    tags.append("선행 강세 🚀")

                # 10. 승급전
                if str(h.get("pre_ord", "")).strip() in ["1", "01"]:
                    score -= 5.0
                    tags.append("승급 첫 도전(검증 필요) 🧱")

                h["ai_score"] = round(score, 1)
                h["ai_tags"] = tags
                h["odds_display"] = "-"

            r["horses"].sort(key=lambda x: x["ai_score"], reverse=True)

        return list(races.values())

    except Exception as e:
        print(f"[{meet_name}] 통신 에러: {e}")
        return []

def find_fast_races():
    now = datetime.now(KST)

    # 1. 오늘 경주 확인
    today_dt = now.strftime("%Y%m%d")
    print(f"🔍 [1단계] 오늘({today_dt}) 경주 확인...")
    races = []
    for m_code, m_name in MEET_CONFIG:
        races.extend(fetch_meet_data(m_code, m_name, today_dt))
    if races:
        return races, today_dt

    # 2. 내일 경주 확인
    tomorrow_dt = (now + timedelta(days=1)).strftime("%Y%m%d")
    print(f"🔍 [2단계] 내일({tomorrow_dt}) 예정 경주 확인...")
    races = []
    for m_code, m_name in MEET_CONFIG:
        races.extend(fetch_meet_data(m_code, m_name, tomorrow_dt))
    if races:
        return races, tomorrow_dt

    # 3. 직전 일요일 복구
    weekday = now.weekday()
    days_back = weekday + 1 if weekday < 6 else 7
    last_sun_dt = (now - timedelta(days=days_back)).strftime("%Y%m%d")
    print(f"🔍 [3단계] 직전 경주일({last_sun_dt}) 정조준...")
    races = []
    for m_code, m_name in MEET_CONFIG:
        races.extend(fetch_meet_data(m_code, m_name, last_sun_dt))
    if races:
        return races, last_sun_dt

    return [], ""

def main():
    if not API_KEY:
        print("❌ KRA_API_KEY 미설정")
        return

    all_races, target_date = find_fast_races()

    if all_races:
        meet_order = {"서울": 1, "부산경남": 2, "영천": 3, "제주": 4}
        all_races.sort(key=lambda x: (
            meet_order.get(x["meet_name"], 9),
            int(x["race_no"]) if x["race_no"].isdigit() else 99
        ))
        with open("race_data.json", "w", encoding="utf-8") as f:
            json.dump(all_races, f, ensure_ascii=False, indent=2)
        print(f"🎉 성공: [{VERSION}] {target_date} 탑웨이트 챔피언 튜닝 완료! ({len(all_races)}개 경주)")
    else:
        print("❌ 데이터를 가져오지 못했습니다.")

if __name__ == "__main__":
    main()
