"""중단 가능한 전체 인덱싱의 선택적 체크포인트 엔진.

기본 인덱싱 경로와 저장 데이터를 바꾸지 않으며, 명시적으로 선택한 새 작업만
이 패키지를 사용합니다. 완성 인덱스는 기존 Chroma/BM25 규약을 그대로 따릅니다.
"""

from .engine import ResumableIndexer, resume_status
from .errors import ResumeError

__all__ = ["ResumableIndexer", "ResumeError", "resume_status"]
