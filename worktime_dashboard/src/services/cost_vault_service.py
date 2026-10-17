import os
import sys
import time
import base64
import json
import sqlite3
from typing import Optional, Tuple, Dict, Any
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..config import config

VERIFIER_PLAINTEXT = "COST_VAULT_VERIFY_TOKEN_v1"
PBKDF2_ITERATIONS = 600_000  # OWASP 2024 권장 군사 표준
MAX_VAULT_ATTEMPTS = 5
VAULT_LOCKOUT_SECONDS = 180  # 5회 연속 실패 시 3분 잠금


class CostVaultService:
    """
    🔐 비용 데이터 제로-트러스트(Zero-Knowledge) 보안 금고 서비스
    
    핵심 원리:
    1. 비밀번호 및 복호화 키는 서버 디스크, .env, DB 어디에도 저장하지 않습니다.
    2. 관리자가 입력한 마스터 비밀번호로 RAM(휘발성 메모리)에서만 즉석으로 AES-256 키를 유도(PBKDF2 600,000회)합니다.
    3. 세션 종료 또는 잠금 클릭 시 메모리에서 키가 영구 증발하여 서버/DB가 털려도 복호화가 불가능합니다.
    """

    _fallback_cipher: Optional[Fernet] = None  # 비 Streamlit 환경(단위 테스트 등)용 메모리 캐시
    _failed_attempts: int = 0
    _lockout_until: float = 0.0

    @classmethod
    def derive_key(cls, password: str, salt: bytes) -> bytes:
        """비밀번호와 솔트로부터 32바이트 AES-256 Fernet 호환 URL-safe base64 키 유도"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        raw_key = kdf.derive(password.encode("utf-8"))
        return base64.urlsafe_b64encode(raw_key)

    # -------------------------------------------------------------
    # 1. 금고 메타데이터 (솔트 및 검증 토큰) 로컬/클라우드 I/O
    # -------------------------------------------------------------
    @classmethod
    def _ensure_local_vault_table(cls):
        """로컬 SQLite 금고 설정 테이블 보장"""
        db_path = config.LOCAL_DB_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cost_vault_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        conn.commit()
        conn.close()

    @classmethod
    def get_vault_meta(cls) -> Dict[str, str]:
        """
        저장된 솔트와 검증 토큰 반환
        반환: {'salt_hex': str, 'verifier_cipher': str} 또는 {}
        """
        meta = {}
        # 1. Supabase 시도 (worktime_hourly_rates의 특수 레코드 활용)
        try:
            from ..database.supabase_client import db_manager
            if db_manager.use_supabase and db_manager.supabase:
                res = db_manager.supabase.table("worktime_hourly_rates").select("job_title").eq("hourly_rate", -99999).execute()
                if res.data:
                    for row in res.data:
                        jt = str(row.get("job_title", ""))
                        if jt.startswith("__VAULT_META__:"):
                            payload_json = jt[len("__VAULT_META__:"):]
                            meta = json.loads(payload_json)
                            if "salt_hex" in meta and "verifier_cipher" in meta:
                                return meta
        except Exception:
            pass

        # 2. 로컬 SQLite 조회
        try:
            cls._ensure_local_vault_table()
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM cost_vault_config")
            for k, v in cursor.fetchall():
                meta[str(k)] = str(v)
            conn.close()
            if "salt_hex" in meta and "verifier_cipher" in meta:
                return meta
        except Exception as e:
            print(f"[CostVault] 로컬 메타 조회 오류: {e}")

        return meta

    @classmethod
    def save_vault_meta(cls, salt_hex: str, verifier_cipher: str) -> bool:
        """솔트와 검증 토큰을 로컬 및 클라우드에 영구 보존"""
        # 1. 로컬 SQLite 저장
        try:
            cls._ensure_local_vault_table()
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO cost_vault_config (key, value) VALUES ('salt_hex', ?)", (salt_hex,))
            cursor.execute("INSERT OR REPLACE INTO cost_vault_config (key, value) VALUES ('verifier_cipher', ?)", (verifier_cipher,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[CostVault] 로컬 메타 저장 실패: {e}")
            return False

        # 2. Supabase 저장 시도 (특수 식별자 -99999 활용)
        try:
            from ..database.supabase_client import db_manager
            if db_manager.use_supabase and db_manager.supabase:
                payload_str = json.dumps({"salt_hex": salt_hex, "verifier_cipher": verifier_cipher})
                record_key = f"__VAULT_META__:{payload_str}"
                # 기존 메타 삭제 후 삽입
                db_manager.supabase.table("worktime_hourly_rates").delete().eq("hourly_rate", -99999).execute()
                db_manager.supabase.table("worktime_hourly_rates").insert({"job_title": record_key, "hourly_rate": -99999}).execute()
        except Exception as e:
            print(f"[CostVault] Supabase 메타 저장 알림 (로컬 저장 완료): {e}")

        return True

    @classmethod
    def is_vault_initialized(cls) -> bool:
        """금고 마스터 비밀번호가 한 번이라도 설정되었는지 확인"""
        meta = cls.get_vault_meta()
        return bool(meta.get("salt_hex") and meta.get("verifier_cipher"))

    # -------------------------------------------------------------
    # 2. 인메모리(RAM) 세션 생명주기 관리
    # -------------------------------------------------------------
    @classmethod
    def _is_streamlit_context(cls) -> bool:
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            return get_script_run_ctx() is not None
        except Exception:
            return False

    @classmethod
    def _get_cipher(cls) -> Optional[Fernet]:
        """현재 세션 RAM에 상주하는 Fernet 암호화 객체 반환 (세션 간 완벽 격리)"""
        if cls._is_streamlit_context():
            import streamlit as st
            return st.session_state.get("_cost_vault_cipher", None)
        return cls._fallback_cipher

    @classmethod
    def _set_cipher(cls, cipher: Optional[Fernet]):
        """세션 RAM에 Fernet 암호화 객체 보관 또는 소멸 (세션 간 완벽 격리)"""
        if cls._is_streamlit_context():
            import streamlit as st
            if cipher is not None:
                st.session_state["_cost_vault_cipher"] = cipher
                st.session_state["_cost_vault_unlocked"] = True
            else:
                st.session_state.pop("_cost_vault_cipher", None)
                st.session_state["_cost_vault_unlocked"] = False
        else:
            cls._fallback_cipher = cipher

    @classmethod
    def _get_lockout_state(cls) -> Tuple[int, float]:
        """세션별 실패 횟수 및 잠금 해제 시각 조회 (세션 간 완벽 격리)"""
        if cls._is_streamlit_context():
            import streamlit as st
            failed = st.session_state.get("_vault_failed_attempts", 0)
            lockout = st.session_state.get("_vault_lockout_until", 0.0)
            return failed, lockout
        return cls._failed_attempts, cls._lockout_until

    @classmethod
    def _set_lockout_state(cls, failed: int, lockout: float):
        """세션별 실패 횟수 및 잠금 해제 시각 저장 (세션 간 완벽 격리)"""
        if cls._is_streamlit_context():
            import streamlit as st
            st.session_state["_vault_failed_attempts"] = failed
            st.session_state["_vault_lockout_until"] = lockout
        else:
            cls._failed_attempts = failed
            cls._lockout_until = lockout

    @classmethod
    def is_unlocked(cls) -> bool:
        """현재 금고가 열려있는(RAM에 복호화 키가 존재하는) 상태인지 여부"""
        return cls._get_cipher() is not None

    @classmethod
    def lock(cls):
        """금고 즉시 잠금 (RAM에서 키 영구 소멸 및 단가/보정 캐시 초기화)"""
        cls._set_cipher(None)
        try:
            from ..database.supabase_client import db_manager
            db_manager.clear_cost_cache()
        except Exception:
            pass

    @classmethod
    def setup_initial_vault(cls, password: str) -> Tuple[bool, str]:
        """
        최초 비밀번호 설정 (16바이트 솔트 생성 -> 검증 토큰 암호화 -> DB 저장 -> 즉시 언락)
        """
        if cls.is_vault_initialized():
            return False, "이미 금고 마스터 비밀번호가 설정되어 있습니다. 재설정하려면 금고 초기화를 먼저 진행하세요."

        clean_pw = password.strip()
        if len(clean_pw) < 4:
            return False, "비밀번호는 최소 4자리 이상이어야 합니다."

        salt = os.urandom(16)
        salt_hex = salt.hex()
        key = cls.derive_key(clean_pw, salt)
        cipher = Fernet(key)

        # 검증 토큰 암호화
        enc_verifier = f"ENC:{cipher.encrypt(VERIFIER_PLAINTEXT.encode()).decode()}"

        success = cls.save_vault_meta(salt_hex, enc_verifier)
        if not success:
            return False, "금고 메타데이터 DB 저장에 실패했습니다."

        # 세션 RAM에 일회성 키 탑재
        cls._set_cipher(cipher)
        
        # 기존 평문 데이터 즉시 일괄 암호화 마이그레이션 실행
        cls.migrate_legacy_data_to_encrypted()
        try:
            from ..database.supabase_client import db_manager
            db_manager.clear_cost_cache()
        except Exception:
            pass
        return True, "비용 보안 마스터 비밀번호가 설정되고 기존 데이터가 안전하게 일괄 암호화되었습니다."

    @classmethod
    def reset_vault(cls) -> bool:
        """금고 설정 완전 초기화 (비밀번호 분실 또는 재설정 시)"""
        cls.lock()
        cls._set_lockout_state(0, 0.0)
        success = True
        # 1. 로컬 SQLite 초기화
        try:
            cls._ensure_local_vault_table()
            conn = sqlite3.connect(str(config.LOCAL_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cost_vault_config")

            # 구 암호문 정리 및 기본 표준 단가 복원
            default_rates = [("수석", 80000), ("과장", 60000), ("대리", 50000), ("사원", 35000)]
            for jt, rate in default_rates:
                cursor.execute("""
                    INSERT INTO hourly_rates (job_title, hourly_rate, updated_at)
                    VALUES (?, ?, datetime('now', 'localtime'))
                    ON CONFLICT(job_title) DO UPDATE SET
                        hourly_rate=excluded.hourly_rate,
                        updated_at=excluded.updated_at
                """, (jt, rate))

            # 이전 키로 암호화된 보정 내역 정리
            cursor.execute("DELETE FROM adjusted_work_logs WHERE note LIKE 'ENC_ADJ:%'")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[CostVault] 로컬 금고 초기화 오류: {e}")
            success = False

        # 2. Supabase 초기화
        try:
            from ..database.supabase_client import db_manager
            if db_manager.use_supabase and db_manager.supabase:
                # 메타데이터(-99999) 및 암호화 단가 페이로드(-99998) 삭제
                db_manager.supabase.table("worktime_hourly_rates").delete().in_("hourly_rate", [-99999, -99998]).execute()

                # 기본 표준 단가 복원 (0원 마스킹 해제)
                default_payloads = [
                    {"job_title": "수석", "hourly_rate": 80000},
                    {"job_title": "과장", "hourly_rate": 60000},
                    {"job_title": "대리", "hourly_rate": 50000},
                    {"job_title": "사원", "hourly_rate": 35000}
                ]
                db_manager.supabase.table("worktime_hourly_rates").upsert(default_payloads).execute()

                # 이전 암호화된 보정 장표 삭제
                db_manager.supabase.table("worktime_adjusted_work_logs").delete().like("note", "ENC_ADJ:%").execute()
        except Exception as e:
            print(f"[CostVault] Supabase 금고 초기화 오류: {e}")

        return success

    @classmethod
    def migrate_legacy_data_to_encrypted(cls) -> int:
        """기존 평문 단가 및 보정 데이터를 안전하게 일괄 암호화하여 DB 덮어쓰기"""
        migrated_count = 0
        try:
            from ..database.supabase_client import db_manager
            # 1. 단가 암호화 덮어쓰기
            current_rates = db_manager.get_hourly_rates()
            if current_rates:
                db_manager.save_hourly_rates(current_rates)
                migrated_count += len(current_rates)

            # 2. 시간 보정 장표 암호화 덮어쓰기
            current_records = db_manager.get_adjusted_records_map()
            if current_records:
                batch_list = []
                for mh, rec in current_records.items():
                    batch_list.append({
                        "msg_hash": mh,
                        "adjusted_hours": rec.get("adjusted_hours", 0.0),
                        "original_hours": rec.get("original_hours", 0.0),
                        "note": rec.get("note", "")
                    })
                if batch_list:
                    db_manager.batch_save_adjusted_work_logs(batch_list)
                    migrated_count += len(batch_list)
        except Exception as e:
            print(f"[CostVault] 데이터 암호화 마이그레이션 오류: {e}")
        return migrated_count

    @classmethod
    def unlock(cls, password: str) -> Tuple[bool, str]:
        """
        비밀번호 검증 및 금고 잠금 해제 (일치 시 RAM에 키 탑재, 5회 연속 실패 시 3분 잠금)
        """
        now_ts = time.time()
        failed_attempts, lockout_until = cls._get_lockout_state()
        if lockout_until > now_ts:
            rem_sec = int(lockout_until - now_ts) + 1
            return False, f"비밀번호 5회 연속 오류로 인해 잠겼습니다. {rem_sec}초 후에 다시 시도해주세요."

        clean_pw = password.strip()
        if not clean_pw:
            return False, "비밀번호를 입력해 주세요."

        meta = cls.get_vault_meta()
        if not meta or not meta.get("salt_hex") or not meta.get("verifier_cipher"):
            return False, "금고가 아직 초기화되지 않았습니다. 신규 비밀번호를 설정해 주세요."

        try:
            salt = bytes.fromhex(meta["salt_hex"])
            key = cls.derive_key(clean_pw, salt)
            cipher = Fernet(key)

            # 검증 토큰 복호화 시도
            verifier_token = meta["verifier_cipher"]
            if verifier_token.startswith("ENC:"):
                verifier_token = verifier_token[4:]

            decrypted = cipher.decrypt(verifier_token.encode()).decode()
            if decrypted == VERIFIER_PLAINTEXT:
                cls._set_lockout_state(0, 0.0)
                cls._set_cipher(cipher)
                try:
                    db_manager.clear_cost_cache()
                except Exception:
                    pass
                return True, "비용 보안 금고가 정상적으로 잠금 해제되었습니다."
            else:
                failed_attempts += 1
                if failed_attempts >= MAX_VAULT_ATTEMPTS:
                    cls._set_lockout_state(failed_attempts, time.time() + VAULT_LOCKOUT_SECONDS)
                    return False, f"비밀번호가 {MAX_VAULT_ATTEMPTS}회 연속 불일치하여 3분간 잠금 처리되었습니다."
                cls._set_lockout_state(failed_attempts, lockout_until)
                return False, f"비밀번호가 일치하지 않습니다. (실패 {failed_attempts}/{MAX_VAULT_ATTEMPTS})"
        except InvalidToken:
            failed_attempts += 1
            if failed_attempts >= MAX_VAULT_ATTEMPTS:
                cls._set_lockout_state(failed_attempts, time.time() + VAULT_LOCKOUT_SECONDS)
                return False, f"비밀번호가 {MAX_VAULT_ATTEMPTS}회 연속 불일치하여 3분간 잠금 처리되었습니다."
            cls._set_lockout_state(failed_attempts, lockout_until)
            return False, f"비밀번호가 일치하지 않습니다. (실패 {failed_attempts}/{MAX_VAULT_ATTEMPTS})"
        except Exception as e:
            return False, f"인증 처리 중 오류 발생: {e}"

    # -------------------------------------------------------------
    # 3. 데이터 암호화 / 복호화 헬퍼
    # -------------------------------------------------------------
    @classmethod
    def encrypt_str(cls, plaintext: str) -> str:
        """
        문자열 암호화 -> 'ENC:gAAAAAB...' 포맷 반환
        금고가 잠겨있으면 원본 그대로 반환(암호화 불가 알림)
        """
        cipher = cls._get_cipher()
        if cipher is None:
            raise PermissionError("비용 보안 금고가 잠겨 있어 암호화를 수행할 수 없습니다.")
        token = cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return f"ENC:{token}"

    @classmethod
    def decrypt_str(cls, ciphertext: str, fallback: str = "") -> str:
        """
        'ENC:...' 암호문 복호화 -> 원본 문자열 반환
        기존 평문 데이터는 그대로 반환
        금고가 잠겨있거나 복호화 실패 시 fallback 반환
        """
        if not ciphertext or not isinstance(ciphertext, str):
            return fallback

        # 평문인 경우 그대로 반환 (하위 호환)
        if not ciphertext.startswith("ENC:"):
            return ciphertext

        cipher = cls._get_cipher()
        if cipher is None:
            return fallback

        try:
            raw_token = ciphertext[4:]
            return cipher.decrypt(raw_token.encode("utf-8")).decode("utf-8")
        except Exception:
            return fallback

    @classmethod
    def encrypt_int(cls, val: int) -> str:
        """정수형 금액 암호화"""
        return cls.encrypt_str(str(int(val)))

    @classmethod
    def decrypt_int(cls, ciphertext: Any, fallback: int = 0) -> int:
        """암호문 복호화 후 int 반환"""
        if isinstance(ciphertext, (int, float)):
            return int(ciphertext)
        dec = cls.decrypt_str(str(ciphertext), fallback="")
        if dec:
            try:
                return int(float(dec))
            except ValueError:
                pass
        return fallback

    @classmethod
    def encrypt_float(cls, val: float) -> str:
        """부동소수점 시간 암호화"""
        return cls.encrypt_str(str(float(val)))

    @classmethod
    def decrypt_float(cls, ciphertext: Any, fallback: float = 0.0) -> float:
        """암호문 복호화 후 float 반환"""
        if isinstance(ciphertext, (int, float)):
            return float(ciphertext)
        dec = cls.decrypt_str(str(ciphertext), fallback="")
        if dec:
            try:
                return float(dec)
            except ValueError:
                pass
        return fallback
