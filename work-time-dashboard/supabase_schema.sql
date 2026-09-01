-- ==============================================================================
-- 카카오톡 작업/지원 보고 관리 시스템 Supabase 테이블 & 뷰 스키마
-- Supabase 대시보드의 [SQL Editor]에 복사하여 붙여넣고 [Run]을 실행하세요.
-- ==============================================================================

-- 1. 작업 로그 테이블 생성
CREATE TABLE IF NOT EXISTS public.work_logs (
    id BIGSERIAL PRIMARY KEY,
    msg_hash TEXT UNIQUE NOT NULL,                       -- 중복 방지용 고유 해시
    log_type VARCHAR(50) DEFAULT '작업',                 -- 작업 / 지원 / 점검 / 장애대응 등
    worker_name VARCHAR(100) NOT NULL,                   -- 담당자 이름 (예: 김시우)
    worker_company VARCHAR(100) DEFAULT '',              -- 소속 회사 (예: 상상인)
    worker_title VARCHAR(50) DEFAULT '',                 -- 직급 (예: 사원)
    worker_team VARCHAR(100) DEFAULT '',                 -- 팀명 (예: 기술 1팀)
    client_name VARCHAR(150) NOT NULL,                   -- 고객사명 (예: KDB생명)
    task_description TEXT NOT NULL,                      -- 상세 작업 내용
    estimated_minutes INTEGER DEFAULT 0,                 -- 예정 소요 시간(분)
    actual_minutes INTEGER DEFAULT 0,                    -- 실제 소요 시간(분)
    start_time TIMESTAMPTZ NOT NULL,                     -- 시작/보고 일시
    end_time TIMESTAMPTZ,                                -- 완료 일시
    status VARCHAR(30) DEFAULT 'COMPLETED',              -- COMPLETED(완료) / PENDING(진행중)
    is_night_work BOOLEAN DEFAULT FALSE,                 -- 야간 작업 여부 (22시~06시)
    is_weekend_work BOOLEAN DEFAULT FALSE,               -- 주말 작업 여부 (토/일)
    raw_start_message TEXT,                              -- 원본 시작 보고 메시지
    raw_end_message TEXT,                                -- 원본 완료 보고 메시지
    created_at TIMESTAMPTZ DEFAULT NOW(),                -- DB 등록 일시
    updated_at TIMESTAMPTZ DEFAULT NOW()                 -- DB 수정 일시
);

-- 2. 검색 최적화를 위한 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_work_logs_start_time ON public.work_logs (start_time);
CREATE INDEX IF NOT EXISTS idx_work_logs_worker_name ON public.work_logs (worker_name);
CREATE INDEX IF NOT EXISTS idx_work_logs_client_name ON public.work_logs (client_name);
CREATE INDEX IF NOT EXISTS idx_work_logs_status ON public.work_logs (status);

-- 3. Row Level Security (RLS) 활성화 및 전체 읽기/쓰기 허용 정책 (내부 대시보드 및 수집기 연동용)
ALTER TABLE public.work_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all access to work_logs for anon and authenticated"
ON public.work_logs
FOR ALL
TO anon, authenticated
USING (true)
WITH CHECK (true);

-- 4. 월별 팀원별 집계 뷰 (선택 사항)
CREATE OR REPLACE VIEW public.vw_monthly_worker_stats AS
SELECT 
    TO_CHAR(start_time, 'YYYY-MM') AS work_month,
    worker_name,
    worker_company,
    worker_team,
    COUNT(*) AS total_tasks,
    SUM(actual_minutes) AS total_actual_minutes,
    ROUND(SUM(actual_minutes)::numeric / 60, 1) AS total_actual_hours,
    SUM(estimated_minutes) AS total_estimated_minutes,
    ROUND(SUM(estimated_minutes)::numeric / 60, 1) AS total_estimated_hours,
    COUNT(CASE WHEN is_night_work = TRUE THEN 1 END) AS night_tasks,
    COUNT(CASE WHEN is_weekend_work = TRUE THEN 1 END) AS weekend_tasks
FROM public.work_logs
GROUP BY TO_CHAR(start_time, 'YYYY-MM'), worker_name, worker_company, worker_team;

-- 5. 월별 고객사별 집계 뷰 (선택 사항)
CREATE OR REPLACE VIEW public.vw_monthly_client_stats AS
SELECT 
    TO_CHAR(start_time, 'YYYY-MM') AS work_month,
    client_name,
    COUNT(*) AS total_tasks,
    SUM(actual_minutes) AS total_actual_minutes,
    ROUND(SUM(actual_minutes)::numeric / 60, 1) AS total_actual_hours
FROM public.work_logs
GROUP BY TO_CHAR(start_time, 'YYYY-MM'), client_name;

-- 6. 팀원 소속 관리 테이블 (기술 1/2/3팀, PI팀)
CREATE TABLE IF NOT EXISTS public.team_members (
    worker_name VARCHAR(100) PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.team_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all access to team_members for anon and authenticated"
ON public.team_members
FOR ALL
TO anon, authenticated
USING (true)
WITH CHECK (true);

-- 7. 초과 근무 보상 휴가 관리 테이블 (대휴, 반차 등 지급 현황)
CREATE TABLE IF NOT EXISTS public.reward_leave_logs (
    worker_name VARCHAR(100) NOT NULL,
    week_label VARCHAR(100) NOT NULL,
    leave_hours NUMERIC DEFAULT 0,
    note TEXT DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (worker_name, week_label)
);

ALTER TABLE public.reward_leave_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all access to reward_leave_logs for anon and authenticated"
ON public.reward_leave_logs
FOR ALL
TO anon, authenticated
USING (true)
WITH CHECK (true);

