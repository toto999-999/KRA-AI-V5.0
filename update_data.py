import os
import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import time

# =========================================================================
# 프로그램 명칭: KRA전국 승부예상AI_V5.8 (제주 전산 통합 & 중복 방지 완성본)
# =========================================================================
VERSION = "KRA전국 승부예상AI_V5.8"
API_KEY = os.environ.get("KRA_API_KEY", "")
URL = "http://apis.data.go.kr/B551015/racedetailresult/getracedetailresult"

KST = timezone(timedelta(hours=9))

MEET_CONFIG = [
    ("1", "서울"),
    ("4", "영천"),
    ("2", "제주"),
    ("3", "부산경남")
]

# 🎯 전국 4대 경마장(서울/부경/영천/제주) 통합 기수 복승률 DB (%)
JOCKEY_RATES = {
    # 서울 기수
    "문세영": 33.2, "김용근": 24.5, "빅투아르": 25.1, "유승완": 21.0,
    "송재철": 19.5, "이혁": 19.2, "임다빈": 18.5, "장추열": 18.0,
    "임기원": 17.5, "이동하": 16.0, "조인권": 21.4, "마이아": 22.0,
    # 부경/영천 기수
    "서승운": 31.5, "최시대": 26.8, "다나카": 25.4, "다비드": 24.2,
    "유현명": 23.8, "정도윤": 22.5, "김혜선": 20.8, "김동영": 17.8,
    "이성재": 16.5, "송경윤": 15.2, "전진구": 14.8, "김어수": 14.5, "손경민": 14.0,
    # 🌴 제주 기수 (신규 대거 보강!)
    "전현준": 26.5, "한영민": 24.2, "임재광": 21.8, "양민재": 19.5,
    "원유일": 18.2, "박재희": 17.5, "곽용남": 16.8, "김한남": 16.0,
    "강수한": 15.5, "이동준": 15.0, "안득수": 20.5, "정명일": 19.0
}

# 🎯 전국 4대 경마장 통합 조교사 복승률 DB (%)
TRAINER_RATES = {
    # 서울 조교사
    "서홍수": 24.5, "송문길": 21.5, "배휴준": 20.8, "정호익": 19.5,
    "최용건": 19.0, "박재우": 17.2, "이강서": 16.8, "전승규": 16.0, "서인석": 15.0,
    # 부경/영천 조교사
    "김영관": 28.0, "라이스": 25.2, "민장기": 22.1, "구영준": 18.5,
    "김도현": 18.2, "안우성": 18.0, "임성실": 17.5, "백광열": 18.8, "강은석": 15.5,
    # 🌴 제주 조교사 (신규 대거 보강!)
    "심도연": 23.5, "김태준": 21.0, "강대은": 20.5, "김길홍": 18.5,
    "윤덕상": 17.8, "김대연": 17.2, "이준호": 16.5, "문성호": 15.8, "고성동": 22.0
}

def fetch_live_chulma_distances():
    dist_map = {}
    meets = [("1", "서울"), ("3", "부산경남"), ("2", "제주")]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*"
    }

    for m_code, m_name in meets:
        try:
            url = f"https://race.kra.co.kr/chulmainfo/ChulmaDetailInfoList.do?Act=02&Sub=1&meet={m_code}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as res:
                html = res.read().decode('euc-kr', errors='ignore')

            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
            for row in rows:
                dist_match = re.search(r'(\d{3,4})\s*M', row, re.IGNORECASE)
                if dist_match:
                    dist_val = dist_match.group(1)
                    target_meet = m_name
                    if "영천" in row: target_meet = "영천"
                    elif "부경" in row or "부산" in row: target_meet = "부산경남"
                    elif "제주" in row: target_meet = "제주"
                    elif "서울" in row: target_meet = "서울"

                    tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                    for td in tds:
                        clean_td = re.sub(r'<.*?>', '', td).strip()
                        if clean_td.isdigit() and 1 <= int(clean_td) <= 16:
                            rc_no = str(int(clean_td))
                            dist_map[(target_meet, rc_no)] = dist_val
                            break
        except Exception:
            continue
    return dist_map

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

def calculate_speed_rating_v58(h, dist, is_post_race=False, meet_name="서울"):
    bonus = 0.0
    tags = []
    
    # 1. [경기 후] 오늘의 실제 완주시간 채점
    if is_post_race:
        sec = parse_time_seconds(h["rc_time"])
        if sec:
            base_time = {
                800: 52.0, 900: 59.0, 1000: 65.5, 1110: 73.0, 1200: 74.8, 1400: 88.5
            }.get(dist, dist * 0.063 + 0.5)
            diff = base_time - sec
            if diff >= 1.0:
                bonus += 10.0
                tags.append(f"스피드 지수 최상({round(sec,1)}초) 🏎️")
            elif diff >= 0.0:
                bonus += 5.0
                tags.append("기록 우수")
            elif diff <= -2.0:
                bonus -= 4.0
        return bonus, tags

    # 2. [경기 전] 출마표의 전적(승률/복승률) 및 레이팅 기반 사전 스피드/능력 분석!
    tot_rc = int(re.sub(r'[^0-9]', '', str(h.get("rc_cnt", "0"))) or 0)
    ord1_cnt = int(re.sub(r'[^0-9]', '', str(h.get("ord1_cnt", "0"))) or 0)
    ord2_cnt = int(re.sub(r'[^0-9]', '', str(h.get("ord2_cnt", "0"))) or 0)

    if tot_rc >= 3:
        quinella_rate = round(((ord1_cnt + ord2_cnt) / tot_rc) * 100, 1)
        if quinella_rate >= 40.0:
            bonus += 12.0
            tags.append(f"통산 복승률 최상({quinella_rate}%) 🏎️")
        elif quinella_rate >= 25.0:
            bonus += 6.0
            tags.append(f"검증된 입상마({quinella_rate}%)")
    else:
        tags.append("신예마 🌟")

    past_sec = parse_time_seconds(h.get("past_time", ""))
    if past_sec:
        tags.append(f"과거 기록({round(past_sec,1)}초)")

    return bonus, tags

def fetch_meet_data(meet_code, meet_name, date_str, live_distances):
    params = {
        "serviceKey": API_KEY,
        "pageNo": "1",
        "numOfRows": "150",
        "meet": meet_code,
        "rc_date": date_str
    }
    full_url = f"{URL}?{urllib.parse.urlencode(params)}"
    print(f"[{meet_name}] 데이터 확인 요청: {date_str}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "*/*"
    }

    try:
        req = urllib.request.Request(full_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        if not items:
            return []

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

            rc_time = gv(["rcTime", "rc_time", "record", "rcRecord", "raceRcd", "ordTime"]) or ""
            past_time = gv(["bestRecord", "bestRcTime", "recentRecord", "recentRcTime", "preRcTime"]) or ""
            rating = gv(["rating", "rat", "hr_rating"]) or ""
            g1f_time = gv(["g1f", "g1f_time", "g1fTime", "g1fRecord", "g_1f"]) or ""
            win_odds = gv(["winOdds", "win_odds", "win_rate", "odds"]) or "0"
            pre_ord = gv(["preOrd", "pre_ord", "recentOrd", "preRcOrd"]) or ""
            
            rc_cnt = gv(["rcCnt", "rc_cnt", "totRcCnt", "tot_rc_cnt"]) or "0"
            ord1_cnt = gv(["ord1Cnt", "ord1_cnt", "totOrd1Cnt"]) or "0"
            ord2_cnt = gv(["ord2Cnt", "ord2_cnt", "totOrd2Cnt"]) or "0"

            s1f_rank = gv(["g1p", "s1f", "g1pRank", "ord1p", "s1fRank"]) or "99"
            is_front = True if s1f_rank in ["1", "2", "01", "02"] else False

            # 착순 판별 (0 또는 공백은 경기 전으로 처리)
            ord_no = "-"
            for child in it:
                tag_low = child.tag.lower()
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

            # 🎯 [중복 마필 원천 차단 필터]
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
                "rating": rating,
                "g1f_time": g1f_time,
                "win_odds": win_odds,
                "pre_ord": pre_ord,
                "rc_cnt": rc_cnt,
                "ord1_cnt": ord1_cnt,
                "ord2_cnt": ord2_cnt,
                "is_front": is_front,
                "actual_ord": ord_no
            })

        for r in races.values():
            meet = r["meet_name"]
            r_no = str(int(r["race_no"])) if str(r["race_no"]).isdigit() else str(r["race_no"])

            if (meet, r_no) in live_distances:
                actual_dist = live_distances[(meet, r_no)]
            elif meet == "제주":
                actual_dist = "900" if r_no in ["1", "2", "3"] else ("1000" if r_no in ["4", "5"] else "1110")
            else:
                actual_dist = "1400"

            r["distance"] = actual_dist
            dist = int(actual_dist)

            has_finished = any(h["actual_ord"].isdigit() and int(h["actual_ord"]) > 0 for h in r["horses"])

            for h in r["horses"]:
                h["distance"] = str(dist)
                score = 30.0
                tags = []
                g = int(h["gate"]) if str(h["gate"]).isdigit() else 5

                # 1. 통합 기수 & 조교사 복승률 (제주도 포함!)
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

                # 2. 거리별 게이트
                if dist <= 1300:
                    score += 15.0 if g <= 3 else 7.0 if g <= 7 else -4.0
                    if g <= 3:
                        tags.append("단거리 황금게이트 ⚡")
                elif dist >= 1700:
                    score += 8.0 if g <= 4 else 5.0 if g <= 8 else 2.0
                else:
                    score += 10.0 if g <= 4 else 6.0 if g <= 8 else 1.0

                # 3. 부담중량
                try:
                    clean_w = float(re.sub(r'[^0-9.]', '', str(h["weight"])))
                    w_factor = 3.5 if dist >= 1700 else 2.5
                    score += (55.0 - clean_w) * w_factor
                    if clean_w <= 52.5:
                        tags.append(f"경량 부중({clean_w}kg) ⚡")
                except:
                    pass

                # 4. 스피드/능력 분석 (사전 복승률 & 사후 주파기록)
                s_bonus, s_tags = calculate_speed_rating_v58(h, dist, is_post_race=has_finished, meet_name=meet)
                score += s_bonus
                tags.extend(s_tags)

                # 5. 단독 선행
                if h["is_front"]:
                    score += 8.0
                    tags.append("선행 강세 🚀")

                h["ai_score"] = round(score, 1)
                h["ai_tags"] = tags

            r["horses"].sort(key=lambda x: x["ai_score"], reverse=True)

        return list(races.values())

    except Exception as e:
        print(f"[{meet_name}] 수신 에러: {e}")
        return []

def find_most_relevant_races(live_distances):
    now = datetime.now(KST)
    for offset in range(0, 5):
        target_dt = (now + timedelta(days=offset)).strftime("%Y%m%d")
        found = []
        for m_code, m_name in MEET_CONFIG:
            res = fetch_meet_data(m_code, m_name, target_dt, live_distances)
            found.extend(res)
            time.sleep(0.3)
        if found:
            return found, target_dt

    for offset in range(1, 10):
        past_dt = (now - timedelta(days=offset)).strftime("%Y%m%d")
        found = []
        for m_code, m_name in MEET_CONFIG:
            res = fetch_meet_data(m_code, m_name, past_dt, live_distances)
            found.extend(res)
            time.sleep(0.3)
        if found:
            return found, past_dt

    return [], ""

def main():
    if not API_KEY:
        print("❌ KRA_API_KEY 미설정")
        return

    live_distances = fetch_live_chulma_distances()
    all_races, target_date = find_most_relevant_races(live_distances)

    if all_races:
        meet_order = {"서울": 1, "부산경남": 2, "영천": 3, "제주": 4}
        all_races.sort(key=lambda x: (
            meet_order.get(x["meet_name"], 9),
            int(x["race_no"]) if x["race_no"].isdigit() else 99
        ))
        with open("race_data.json", "w", encoding="utf-8") as f:
            json.dump(all_races, f, ensure_ascii=False, indent=2)
        print(f"🎉 성공: [{VERSION}] {target_date} 데이터 갱신 완료!")
    else:
        print("데이터를 가져오지 못했습니다.")

if __name__ == "__main__":
    main()
