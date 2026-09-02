-- ==============================================================================
-- 🚀 기술본부 업무 관리 시스템 Supabase 테이블 그룹핑 스키마 (worktime_ 접두사)
-- Supabase 대시보드의 [SQL Editor]에 복사하여 붙여넣고 [Run]을 실행하세요.
-- ==============================================================================

-- [OPTION A: 기존 테이블이 있는 경우 -> 0.01초 만에 이름 변경 및 데이터 100% 보존]
ALTER TABLE IF EXISTS public.work_logs RENAME TO worktime_work_logs;
ALTER TABLE IF EXISTS public.team_members RENAME TO worktime_team_members;
ALTER TABLE IF EXISTS public.reward_leave_logs RENAME TO worktime_reward_leave_logs;

-- ==============================================================================
-- [OPTION B: 신규 생성 (테이블이 없을 때 자동 생성)]
-- ==============================================================================

-- 1. 작업 로그 테이블 (worktime_work_logs)
CREATE TABLE IF NOT EXISTS public.worktime_work_logs (
    id BIGSERIAL PRIMARY KEY,
    msg_hash TEXT UNIQUE NOT NULL,                       -- 중복 방지용 고유 해시
    log_type VARCHAR(50) DEFAULT '작업',                 -- 작업 / 지원 / 점검 / 장애대응 등
    worker_name VARCHAR(100) NOT NULL,                   -- 담당자 이름 (예: 김태현)
    worker_company VARCHAR(100) DEFAULT '',              -- 소속 회사 (예: 상상인)
    worker_title VARCHAR(50) DEFAULT '',                 -- 직급 (예: 사원)
    worker_team VARCHAR(100) DEFAULT '',                 -- 팀명 (예: 기술 1팀)
    client_name VARCHAR(150) NOT NULL,                   -- 고객사명 (예: 국도화학)
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

-- 검색 최적화 인덱스
CREATE INDEX IF NOT EXISTS idx_worktime_logs_start_time ON public.worktime_work_logs (start_time);
CREATE INDEX IF NOT EXISTS idx_worktime_logs_worker_name ON public.worktime_work_logs (worker_name);
CREATE INDEX IF NOT EXISTS idx_worktime_logs_client_name ON public.worktime_work_logs (client_name);
CREATE INDEX IF NOT EXISTS idx_worktime_logs_status ON public.worktime_work_logs (status);

-- RLS 활성화 및 권한 정책
ALTER TABLE public.worktime_work_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow all access to worktime_work_logs" ON public.worktime_work_logs;
CREATE POLICY "Allow all access to worktime_work_logs"
ON public.worktime_work_logs FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);


-- 2. 팀원 소속 관리 테이블 (worktime_team_members)
CREATE TABLE IF NOT EXISTS public.worktime_team_members (
    worker_name VARCHAR(100) PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL,
    job_title VARCHAR(50) DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.worktime_team_members ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow all access to worktime_team_members" ON public.worktime_team_members;
CREATE POLICY "Allow all access to worktime_team_members"
ON public.worktime_team_members FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);


-- 3. 보상 휴가 관리 테이블 (worktime_reward_leave_logs)
CREATE TABLE IF NOT EXISTS public.worktime_reward_leave_logs (
    worker_name VARCHAR(100) NOT NULL,
    week_label VARCHAR(100) NOT NULL,
    leave_hours NUMERIC DEFAULT 0,
    note TEXT DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (worker_name, week_label)
);

ALTER TABLE public.worktime_reward_leave_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow all access to worktime_reward_leave_logs" ON public.worktime_reward_leave_logs;
CREATE POLICY "Allow all access to worktime_reward_leave_logs"
ON public.worktime_reward_leave_logs FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
