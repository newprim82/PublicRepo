import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

@dataclass
class RawKakaoMessage:
    raw_text: str
    sender_profile: str
    timestamp: datetime
    content: str
    body_content: str = ""
    reply_target_sender: Optional[str] = None
    reply_target_content: Optional[str] = None

@dataclass
class WorkerInfo:
    full_profile: str
    name: str
    company: str = ""
    title: str = ""
    team: str = ""

@dataclass
class ParsedTaskStart:
    log_type: str
    worker_name: str
    client_name: str
    task_description: str
    estimated_minutes: int
    raw_message: str
    timestamp: datetime
    worker_info: WorkerInfo
    task_group_id: str = ""
    is_direct_completed: bool = False
    direct_actual_minutes: int = 0

@dataclass
class ParsedTaskEnd:
    actual_minutes: int
    raw_message: str
    timestamp: datetime
    worker_info: WorkerInfo
    reply_target_content: Optional[str] = None
    worker_specific_minutes: Dict[str, int] = field(default_factory=dict)
    is_explicit_time: bool = True


def parse_duration_to_minutes(text: str) -> int:
    """
    시간 및 일수(Day) 표현식에서 총 분(minutes)을 계산
    ★ 기준: 1day = 9시간 (540분) ★
    """
    if not text:
        return 0
    text = text.strip()
    
    range_match = re.search(r'(\d{1,2}):(\d{2})\s*[~-]\s*(\d{1,2}):(\d{2})', text)
    if range_match:
        sh, sm = int(range_match.group(1)), int(range_match.group(2))
        eh, em = int(range_match.group(3)), int(range_match.group(4))
        diff = (eh * 60 + em) - (sh * 60 + sm)
        if diff < 0:
            diff += 24 * 60
        if diff > 0:
            return diff

    total_minutes = 0

    # 일수(Day) 매칭: 1day = 9시간 = 540분
    day_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:days?|d(?![a-zA-Z])|D|일)', text)
    if day_match:
        days = float(day_match.group(1))
        total_minutes += int(days * 9 * 60)

    float_hour_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:시간|h|H|hours?)', text)
    if float_hour_match:
        hours = float(float_hour_match.group(1))
        total_minutes += int(hours * 60)
        
    minute_match = re.search(r'(\d+)\s*(?:분|m|M|mins?)', text)
    if minute_match:
        total_minutes += int(minute_match.group(1))
        
    if total_minutes == 0:
        num_match = re.search(r'(\d+)(?:\s*예정|\s*소요|\s*완료|\Z)', text)
        if num_match:
            val = int(num_match.group(1))
            if 1 <= val <= 24:
                total_minutes = val * 60
            else:
                total_minutes = val
                
    return total_minutes


def parse_worker_profile(profile_str: str, fallback_name: str = "") -> WorkerInfo:
    if not profile_str:
        return WorkerInfo(full_profile="", name=fallback_name or "미상")
    
    profile_str = profile_str.strip()
    team = ""
    
    if "/" in profile_str:
        parts = [p.strip() for p in profile_str.split("/") if p.strip()]
        user_part = parts[0]
        if len(parts) > 1:
            team = " / ".join(parts[1:])
    else:
        user_part = profile_str
        
    tokens = user_part.split()
    company = ""
    name = fallback_name or ""
    title = ""
    
    known_titles = ["사원", "주임", "대리", "과장", "차장", "부장", "팀장", "이사", "상무", "대표", "엔지니어", "매니저", "선임", "책임", "수석"]
    
    if len(tokens) == 1:
        name = tokens[0]
    elif len(tokens) == 2:
        if tokens[1] in known_titles:
            name = tokens[0]
            title = tokens[1]
        else:
            company = tokens[0]
            name = tokens[1]
    elif len(tokens) >= 3:
        company = tokens[0]
        name = tokens[1]
        title = " ".join(tokens[2:])
        
    if not name and fallback_name:
        name = fallback_name
        
    return WorkerInfo(
        full_profile=profile_str,
        name=name or user_part,
        company=company,
        title=title,
        team=team
    )


def extract_individual_workers(name_field_str: str, sender_info: WorkerInfo) -> List[WorkerInfo]:
    if not name_field_str:
        return [sender_info]

    cleaned = name_field_str.strip()
    cleaned = re.sub(r'\(.*?\)', ' ', cleaned)
    cleaned = re.sub(r'\[.*?\]', ' ', cleaned)
    
    known_titles = {"사원", "주임", "대리", "과장", "차장", "부장", "팀장", "이사", "상무", "대표", "엔지니어", "매니저", "선임", "책임", "수석", "팀원"}
    known_stopwords = {"외", "등", "및", "dell", "bgf", "상상인", "sk", "kt", "lg", "cisco", "협력사", "담당"}

    cleaned = re.sub(r'[,/&+\-_\\|]+', ' ', cleaned)
    
    raw_tokens = cleaned.split()
    individual_names: List[str] = []

    for token in raw_tokens:
        token = token.strip()
        if not token:
            continue
            
        lower_token = token.lower()
        if lower_token in known_stopwords:
            continue
            
        if len(token) <= 2 and token in known_titles:
            continue
            
        if re.match(r'^외\s*\d+명?$', token):
            continue
            
        for title in known_titles:
            if token.endswith(title) and len(token) > len(title) and len(token) >= 4:
                token = token[:-len(title)].strip()
                break
                
        if len(token) >= 2:
            if token not in individual_names:
                individual_names.append(token)

    if not individual_names:
        individual_names = [sender_info.name or cleaned]

    workers: List[WorkerInfo] = []
    for uname in individual_names:
        workers.append(WorkerInfo(
            full_profile=f"{sender_info.company} {uname} / {sender_info.team}".strip(),
            name=uname,
            company=sender_info.company,
            title="",
            team=sender_info.team
        ))
        
    return workers


class KakaoMessageParser:
    DATE_HEADER_PATTERNS = [
        re.compile(r'^-+\s*(\d{4})[년./\-]\s*(\d{1,2})[월./\-]\s*(\d{1,2})일?.*-+$'),
        re.compile(r'^(\d{4})[년./\-]\s*(\d{1,2})[월./\-]\s*(\d{1,2})일?\s+[월화수목금토일]요일$')
    ]
    
    MSG_WIN_PATTERN = re.compile(
        r'^\[(?P<sender>[^\]]+)\]\s*\[(?:(?P<ampm>오전|오후)\s*)?(?P<hour>\d{1,2}):(?P<minute>\d{2})\]\s*(?P<content>.*)$'
    )
    
    MSG_MOB_PATTERN = re.compile(
        r'^(?P<year>\d{4})[년./\-]\s*(?P<month>\d{1,2})[월./\-]\s*(?P<day>\d{1,2})일?\s+(?:(?P<ampm>오전|오후)\s*)?(?P<hour>\d{1,2}):(?P<minute>\d{2}),?\s*(?P<sender>[^:]+)\s*:\s*(?P<content>.*)$'
    )

    START_PATTERNS = [
        re.compile(r'^(?:\[(?P<b_type>[^\]]+)\]\s*)?(?P<type>[^/\n\r]+?)\s*/\s*(?P<name>[^/\n\r]+?)\s*/\s*(?P<client>[^/\n\r]+?)\s*/\s*(?P<task>[^/\n\r]+?)\s*/\s*(?P<est>[^\n\r]+)$', re.MULTILINE),
        re.compile(r'^\[(?P<type>[^\]]+)\]\s*(?P<name>[^/\n\r]+?)\s*/\s*(?P<client>[^/\n\r]+?)\s*/\s*(?P<task>[^/\n\r]+?)\s*/\s*(?P<est>[^\n\r]+)$', re.MULTILINE),
    ]

    END_WITH_TIME_PATTERNS = [
        re.compile(r'(?P<time>(?:\d+(?:\.\d+)?\s*(?:days?|d|D|일)\s*)?(?:\d+(?:\.\d+)?\s*(?:시간|h|H|hours?)\s*)?(?:\d+\s*(?:분|m|M|mins?)\s*)?)\s*(?:소요\s*)?(?:작업\s*)?(?:지원\s*)?완료', re.IGNORECASE),
        re.compile(r'(?:작업\s*|지원\s*)?완료\s*[\/:,\(\[\s]+\s*(?P<time>(?:\d+(?:\.\d+)?\s*(?:days?|d|D|일)\s*)?(?:\d+(?:\.\d+)?\s*(?:시간|h|H|hours?)\s*)?(?:\d+\s*(?:분|m|M|mins?)\s*)?)', re.IGNORECASE),
        re.compile(r'(?P<time>(?:\d+(?:\.\d+)?\s*(?:days?|d|D|일)\s*)?(?:\d+(?:\.\d+)?\s*(?:시간|h|H)\s*)?(?:\d+\s*(?:분|m|M)\s*)?)\s*소요', re.IGNORECASE),
    ]
    
    SIMPLE_END_PATTERN = re.compile(r'^(?:작업\s*|지원\s*)?완료(?:\s*했습니다|\s*합니다|\Z|\!|\.)', re.IGNORECASE)

    @classmethod
    def parse_raw_text_to_messages(cls, full_text: str) -> List[RawKakaoMessage]:
        messages: List[RawKakaoMessage] = []
        lines = full_text.splitlines()
        
        current_date: Optional[datetime] = None
        current_sender: str = ""
        current_timestamp: Optional[datetime] = None
        current_content_lines: List[str] = []
        last_msg_time: Optional[datetime] = None

        def finalize_current_msg():
            nonlocal current_sender, current_timestamp, current_content_lines, last_msg_time
            if current_sender and current_timestamp and current_content_lines:
                full_raw = "\n".join(current_content_lines).strip()
                
                reply_sender = None
                reply_content = None
                body_content = full_raw
                
                reply_match = re.search(r'^(.*?)에게\s*답장\s*\n([\s\S]*?)(?=\n[^\n]+완료|\n\d|\Z)', full_raw)
                if reply_match:
                    reply_sender = reply_match.group(1).strip()
                    reply_content = reply_match.group(2).strip()
                    body_content = full_raw[reply_match.end():].strip()
                    if not body_content:
                        body_content = full_raw
                
                messages.append(RawKakaoMessage(
                    raw_text=full_raw,
                    sender_profile=current_sender,
                    timestamp=current_timestamp,
                    content=full_raw,
                    body_content=body_content,
                    reply_target_sender=reply_sender,
                    reply_target_content=reply_content
                ))
                last_msg_time = current_timestamp
            current_content_lines = []

        now = datetime.now()
        
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
                
            matched_date = False
            for d_pattern in cls.DATE_HEADER_PATTERNS:
                d_match = d_pattern.match(line_str)
                if d_match:
                    finalize_current_msg()
                    y, m, d = int(d_match.group(1)), int(d_match.group(2)), int(d_match.group(3))
                    current_date = datetime(y, m, d)
                    matched_date = True
                    break
            if matched_date:
                continue
                
            msg_win_match = cls.MSG_WIN_PATTERN.match(line_str)
            if msg_win_match:
                finalize_current_msg()
                current_sender = msg_win_match.group("sender").strip()
                ampm = msg_win_match.group("ampm")
                h = int(msg_win_match.group("hour"))
                m = int(msg_win_match.group("minute"))
                if ampm == "오후" and h < 12:
                    h += 12
                elif ampm == "오전" and h == 12:
                    h = 0
                
                base_d = current_date or datetime(now.year, now.month, now.day)
                temp_time = base_d.replace(hour=h, minute=m, second=0, microsecond=0)
                
                if last_msg_time and last_msg_time.date() == temp_time.date():
                    if last_msg_time.hour >= 18 and temp_time.hour < 10:
                        temp_time += timedelta(days=1)
                        current_date = temp_time.replace(hour=0, minute=0, second=0)

                current_timestamp = temp_time
                content = msg_win_match.group("content")
                if content:
                    current_content_lines.append(content)
                continue
                
            msg_mob_match = cls.MSG_MOB_PATTERN.match(line_str)
            if msg_mob_match:
                finalize_current_msg()
                y = int(msg_mob_match.group("year"))
                mon = int(msg_mob_match.group("month"))
                d = int(msg_mob_match.group("day"))
                ampm = msg_mob_match.group("ampm")
                h = int(msg_mob_match.group("hour"))
                m = int(msg_mob_match.group("minute"))
                if ampm == "오후" and h < 12:
                    h += 12
                elif ampm == "오전" and h == 12:
                    h = 0
                    
                current_timestamp = datetime(y, mon, d, h, m, 0)
                current_sender = msg_mob_match.group("sender").strip()
                content = msg_mob_match.group("content")
                if content:
                    current_content_lines.append(content)
                continue
                
            if current_sender:
                current_content_lines.append(line)
                
        finalize_current_msg()
        return messages

    @classmethod
    def parse_task_starts(cls, msg: RawKakaoMessage) -> List[ParsedTaskStart]:
        target_text = msg.body_content if msg.body_content else msg.content
        
        # 순수 완료 보고(슬래시 없는 형태)인 경우 시작 보고 파싱 제외
        if cls.parse_task_end(msg) and not any("/" in line for line in target_text.splitlines()):
            return []

        match = None
        for pat in cls.START_PATTERNS:
            match = pat.search(target_text)
            if match:
                break
            for line in target_text.splitlines():
                sub_match = pat.search(line.strip())
                if sub_match:
                    match = sub_match
                    break
            if match:
                break
                    
        if not match:
            return []
            
        group_dict = match.groupdict()
        log_type = (group_dict.get("b_type") or group_dict.get("type", "작업")).strip()
        raw_name_field = group_dict.get("name", "").strip()
        client_name = group_dict.get("client", "").strip()
        task_desc = group_dict.get("task", "").strip()
        est_str = group_dict.get("est", "").strip()
        
        is_direct_completed = ("완료" in est_str) or ("소요" in est_str)
        direct_actual_minutes = parse_duration_to_minutes(est_str) if is_direct_completed else 0
        est_minutes = parse_duration_to_minutes(est_str)
        
        sender_worker_info = parse_worker_profile(msg.sender_profile)
        individual_workers = extract_individual_workers(raw_name_field, sender_worker_info)
        group_id = f"{client_name}_{msg.timestamp.strftime('%Y%m%d%H%M')}_{task_desc[:15]}"
        
        task_starts = []
        for worker in individual_workers:
            task_starts.append(ParsedTaskStart(
                log_type=log_type,
                worker_name=worker.name,
                client_name=client_name,
                task_description=task_desc,
                estimated_minutes=est_minutes,
                raw_message=msg.raw_text,
                timestamp=msg.timestamp,
                worker_info=worker,
                task_group_id=group_id,
                is_direct_completed=is_direct_completed,
                direct_actual_minutes=direct_actual_minutes
            ))
            
        return task_starts

    @classmethod
    def parse_task_end(cls, msg: RawKakaoMessage) -> Optional[ParsedTaskEnd]:
        target_text = msg.body_content.strip() if msg.body_content else msg.content.strip()
        
        # 다중 작업자별 완료 시간 파싱 (예: "전종필, 김시우 / 4 days 완료\n김시우 / 1 days 완료")
        worker_specific = {}
        for line in target_text.splitlines():
            line = line.strip()
            if "/" in line:
                parts = [p.strip() for p in line.split("/") if p.strip()]
                if len(parts) >= 2:
                    names_part = parts[0]
                    time_part = parts[1]
                    mins = parse_duration_to_minutes(time_part)
                    if mins > 0:
                        # 이름 분리
                        temp_sender = parse_worker_profile(msg.sender_profile)
                        for w in extract_individual_workers(names_part, temp_sender):
                            worker_specific[w.name] = mins
                            
        for pat in cls.END_WITH_TIME_PATTERNS:
            match = pat.search(target_text)
            if match:
                time_str = match.group("time") if "time" in match.groupdict() else match.group(0)
                minutes = parse_duration_to_minutes(time_str)
                if minutes > 0 or worker_specific:
                    worker_info = parse_worker_profile(msg.sender_profile)
                    return ParsedTaskEnd(
                        actual_minutes=minutes,
                        raw_message=msg.raw_text,
                        timestamp=msg.timestamp,
                        worker_info=worker_info,
                        reply_target_content=msg.reply_target_content,
                        worker_specific_minutes=worker_specific,
                        is_explicit_time=True
                    )
                    
        if cls.SIMPLE_END_PATTERN.search(target_text) or target_text in ["완료", "작업완료", "지원완료", "완료했습니다", "완료요"]:
            worker_info = parse_worker_profile(msg.sender_profile)
            return ParsedTaskEnd(
                actual_minutes=0,
                raw_message=msg.raw_text,
                timestamp=msg.timestamp,
                worker_info=worker_info,
                reply_target_content=msg.reply_target_content,
                worker_specific_minutes=worker_specific,
                is_explicit_time=False
            )

        return None
