## Q1
- 유형: 1
- 질문: version_callback 함수는 무엇을 하나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 71~84줄
- 한 줄 요약: --version이 주어지면 버전을 출력하고 종료한다
- 비고: FastAPI Cloud CLI 버전 출력은 import 가능할 때만 수행됨

## Q2
- 유형: 1
- 질문: callback 함수는 무엇을 하나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 87~106줄
- 한 줄 요약: verbose 값에 따라 로그 레벨을 정하고 setup_logging을 호출한다
- 비고: CLI 전역 콜백으로 동작

## Q3
- 유형: 1
- 질문: _get_module_tree 함수는 무엇을 하나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 109~127줄
- 한 줄 요약: 모듈 경로 목록을 Rich Tree로 렌더링 가능한 구조로 만든다
- 비고: 디렉터리 경로면 __init__.py 노드도 추가

## Q4
- 유형: 1
- 질문: _run 함수는 무엇을 하나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 130~300줄
- 한 줄 요약: import 대상을 해석하고 uvicorn.run으로 서버를 실행하는 핵심 실행 루틴
- 비고: 설정 로딩, 자동 탐지, 로그 출력, 에러 처리까지 포함

## Q5
- 유형: 1
- 질문: FastAPIConfig 클래스의 역할은 무엇인가요?
- 정답 위치:
  - src/fastapi_cli/config.py 10~42줄
- 한 줄 요약: entrypoint 관련 설정을 모델로 표현하고 검증한다
- 비고: resolve 메서드에서 최종 model_validate 수행

## Q6
- 유형: 1
- 질문: _read_pyproject_toml 메서드는 무엇을 하나요?
- 정답 위치:
  - src/fastapi_cli/config.py 15~35줄
- 한 줄 요약: 현재 디렉터리 pyproject.toml의 tool.fastapi 설정을 읽는다
- 비고: 파일/파서가 없으면 빈 dict 반환

## Q7
- 유형: 1
- 질문: resolve 메서드는 무엇을 하나요?
- 정답 위치:
  - src/fastapi_cli/config.py 37~42줄
- 한 줄 요약: pyproject 값과 CLI 인자를 합쳐 FastAPIConfig를 구성한다
- 비고: from_pyproject 플래그 계산 로직 포함

## Q8
- 유형: 1
- 질문: get_default_path 함수는 무엇을 하나요?
- 정답 위치:
  - src/fastapi_cli/discover.py 18~36줄
- 한 줄 요약: 기본 후보 파일을 순서대로 찾아 첫 매치를 반환한다
- 비고: 찾지 못하면 FastAPICLIException 발생

## Q9
- 유형: 1
- 질문: ModuleData 클래스는 어떤 정보를 담나요?
- 정답 위치:
  - src/fastapi_cli/discover.py 39~42줄
- 한 줄 요약: module import 문자열, sys.path 추가 경로, 경로 체인을 담는다
- 비고: dataclass로 선언됨

## Q10
- 유형: 1
- 질문: get_module_data_from_path 함수는 무엇을 하나요?
- 정답 위치:
  - src/fastapi_cli/discover.py 45~65줄
- 한 줄 요약: 경로를 패키지 문맥으로 해석해 ModuleData를 계산한다
- 비고: 상위 디렉터리의 __init__.py 존재를 따라가며 경계 결정

## Q11
- 유형: 1
- 질문: get_app_name 함수는 어떤 기준으로 앱 이름을 결정하나요?
- 정답 위치:
  - src/fastapi_cli/discover.py 68~116줄
- 한 줄 요약: 명시 이름 검증 후, 없으면 app/api 우선 및 첫 FastAPI 객체를 탐색한다
- 비고: 실패 시 --app 사용을 유도하는 예외 메시지 출력

## Q12
- 유형: 1
- 질문: get_import_data 함수는 무엇을 하나요?
- 정답 위치:
  - src/fastapi_cli/discover.py 128~153줄
- 한 줄 요약: 경로/앱 정보를 바탕으로 import_string과 출처 메타데이터를 만든다
- 비고: path가 없으면 auto-discovery 경로 사용

## Q13
- 유형: 1
- 질문: get_import_data_from_import_string 함수는 무엇을 하나요?
- 정답 위치:
  - src/fastapi_cli/discover.py 156~182줄
- 한 줄 요약: module:app 문자열을 검증해 ImportData로 변환한다
- 비고: 현재 작업 디렉터리를 sys.path 앞에 추가

## Q14
- 유형: 1
- 질문: setup_logging 함수는 무엇을 하나요?
- 정답 위치:
  - src/fastapi_cli/logging.py 7~20줄
- 한 줄 요약: fastapi_cli 로거에 RichHandler를 설정하고 레벨/전파를 조정한다
- 비고: terminal_width가 있으면 Console 너비를 지정

## Q15
- 유형: 1
- 질문: should_use_rich_logs 함수는 무엇을 기준으로 True/False를 반환하나요?
- 정답 위치:
  - src/fastapi_cli/utils/cli.py 17~19줄
- 한 줄 요약: stdout이 TTY인지(isatty) 여부로 rich 로그 사용 여부를 결정한다
- 비고: 환경 의존 동작 판단 함수

## Q16
- 유형: 2
- 질문: CLI 명령 실행은 어디서 시작되나요?
- 정답 위치:
  - src/fastapi_cli/__main__.py 1~3줄
  - src/fastapi_cli/cli.py 538~539줄
- 한 줄 요약: __main__.py가 main()을 호출하고, cli.main()이 app()을 실행한다
- 비고: 실제 Typer 진입점은 cli.py의 app()

## Q17
- 유형: 2
- 질문: fastapi dev 실행 흐름은 어디서 시작해서 어디에서 실제 서버 실행으로 이어지나요?
- 정답 위치:
  - README.md 26~31줄
  - src/fastapi_cli/cli.py 303~420줄
  - src/fastapi_cli/cli.py 130~300줄
- 한 줄 요약: dev 명령이 _run으로 위임되고 _run 내부 uvicorn.run으로 서버를 띄운다
- 비고: 문서 설명과 구현 흐름을 함께 봐야 정확함

## Q18
- 유형: 2
- 질문: fastapi run 실행 흐름은 어디서 시작해서 어디에서 서버를 띄우나요?
- 정답 위치:
  - README.md 83~85줄
  - src/fastapi_cli/cli.py 422~536줄
  - src/fastapi_cli/cli.py 130~300줄
- 한 줄 요약: run 명령이 _run으로 위임되고 실제 실행은 uvicorn.run에서 시작된다
- 비고: production 모드 설명은 README에 있고 구현은 cli.py에 있음

## Q19
- 유형: 2
- 질문: --version 옵션 처리는 어디서 시작되나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 87~96줄
  - src/fastapi_cli/cli.py 71~84줄
- 한 줄 요약: callback 옵션 선언에서 version_callback으로 연결되고, 콜백에서 출력 후 종료한다
- 비고: 옵션 선언과 실행 함수가 분리되어 있음

## Q20
- 유형: 2
- 질문: 로그 초기화는 어디서 시작되나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 103~106줄
  - src/fastapi_cli/logging.py 7~20줄
- 한 줄 요약: CLI callback이 setup_logging을 호출하고 실제 로거 설정은 logging.py에서 수행된다
- 비고: 시작점과 실제 설정 지점이 다른 파일에 있음

## Q21
- 유형: 2
- 질문: 개발 모드에서 FASTAPI_ENV 설정은 어디서 시작되나요?
- 정답 위치:
  - README.md 79~81줄
  - src/fastapi_cli/cli.py 402~402줄
- 한 줄 요약: README 설명대로 dev 실행 전 환경값을 설정하며, 코드는 os.environ.setdefault로 시작한다
- 비고: run은 FASTAPI_ENV를 그대로 둔다는 설명도 README에 있음

## Q22
- 유형: 2
- 질문: entrypoint 설정(pyproject.toml 또는 --entrypoint)의 반영은 어디서 시작되나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 167~188줄
  - src/fastapi_cli/config.py 37~45줄
  - src/fastapi_cli/config.py 15~35줄
- 한 줄 요약: _run에서 resolve로 설정을 확정하고 entrypoint가 있으면 import string 경로로 분기한다
- 비고: 설정 로딩과 실행 분기를 모두 확인해야 함

## Q23
- 유형: 2
- 질문: path 또는 --app 기반 import string 생성은 어디서 시작되나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 181~183줄
  - src/fastapi_cli/discover.py 128~153줄
  - src/fastapi_cli/discover.py 68~116줄
- 한 줄 요약: _run이 get_import_data를 호출하고 discover.py에서 app 이름/모듈 문자열을 조합한다
- 비고: path/app 옵션이 있을 때의 우선 경로

## Q24
- 유형: 2
- 질문: 기본 파일(main.py/app.py/api.py) 자동 탐색은 어디서 시작되나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 187~188줄
  - src/fastapi_cli/discover.py 132~134줄
  - src/fastapi_cli/discover.py 18~36줄
- 한 줄 요약: 기본 분기에서 get_import_data()가 get_default_path()를 호출해 후보 파일을 탐색한다
- 비고: 경로 미지정 시에만 발동

## Q25
- 유형: 2
- 질문: FastAPI 앱 객체 이름(app/api 우선, 그 외 fallback) 탐지는 어디서 시작되나요?
- 정답 위치:
  - README.md 65~65줄
  - src/fastapi_cli/discover.py 143~143줄
  - src/fastapi_cli/discover.py 68~116줄
- 한 줄 요약: get_import_data가 get_app_name으로 위임하고, get_app_name이 app/api 우선 탐색 후 fallback한다
- 비고: 문서의 "자동 감지" 설명과 코드 구현을 대조 가능

## Q26
- 유형: 2
- 질문: module:app 형식 검증은 어디서 시작되나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 184~186줄
  - src/fastapi_cli/discover.py 156~165줄
- 한 줄 요약: _run의 entrypoint 분기에서 get_import_data_from_import_string으로 들어가 형식 오류를 검사한다
- 비고: 잘못된 형식이면 FastAPICLIException 발생

## Q27
- 유형: 2
- 질문: verbose 모드에서 모듈 트리 출력은 어디서 시작되나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 197~211줄
  - src/fastapi_cli/cli.py 109~127줄
- 한 줄 요약: _run의 verbose 분기에서 _get_module_tree를 호출해 트리를 출력한다
- 비고: module_paths가 있는 경우에만 트리 출력

## Q28
- 유형: 2
- 질문: auto-discovery일 때 pyproject entrypoint 설정 안내 출력은 어디서 시작되나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 199줄
  - src/fastapi_cli/cli.py 246~262줄
- 한 줄 요약: auto-discovery 판정 후 pyproject.toml entrypoint 예시를 안내한다
- 비고: 기본 출력 경로에서 노출되는 가이드

## Q29
- 유형: 2
- 질문: Uvicorn에 Rich 로그 포맷을 적용하는 흐름은 어디서 시작되나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 280~281줄
  - src/fastapi_cli/utils/cli.py 146~186줄
  - src/fastapi_cli/utils/cli.py 130~143줄
- 한 줄 요약: _run이 rich 로그 사용 여부를 판단해 log_config를 넣고, 해당 config는 CustomFormatter를 사용한다
- 비고: 실행 분기와 포맷 정의가 다른 파일에 분리됨

## Q30
- 유형: 2
- 질문: fastapi cloud/new 같은 확장 서브커맨드 등록은 어디서 시작되나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 51~58줄
  - src/fastapi_cli/cli.py 61~68줄
- 한 줄 요약: 모듈 import 시 try 블록에서 각 CLI를 불러 app.add_typer로 등록한다
- 비고: 패키지가 없으면 ImportError를 무시하고 기본 명령만 유지

## Q31
- 유형: 3
- 질문: 이 프로젝트는 전체적으로 무엇을 하는 도구인가요?
- 정답 위치:
  - README.md 18~24줄
- 한 줄 요약: FastAPI 앱을 커맨드라인에서 실행하고 관리하는 CLI 도구다
- 비고: 프로젝트 목적은 README 도입부와 Description에 명시됨

## Q32
- 유형: 3
- 질문: 프로젝트를 실행할 때 기본적으로 어떤 명령(dev/run)을 사용하나요?
- 정답 위치:
  - README.md 26~27줄
  - README.md 67~67줄
  - README.md 85~85줄
- 한 줄 요약: 개발은 fastapi dev, 운영은 fastapi run을 사용한다
- 비고: dev/run의 역할이 README에 분리 설명되어 있음

## Q33
- 유형: 3
- 질문: 이 프로젝트를 사용하려면 Python 버전과 설치 방식은 무엇인가요?
- 정답 위치:
  - pyproject.toml 8~8줄
  - README.md 24~24줄
- 한 줄 요약: Python 3.10+가 필요하고 FastAPI 설치 시 fastapi-cli가 포함되어 fastapi 명령을 제공한다
- 비고: 버전 요건과 설치 방식 근거가 서로 다른 파일에 있음

## Q34
- 유형: 3
- 질문: 핵심 런타임 의존성은 어디에 정의돼 있고 무엇인가요?
- 정답 위치:
  - pyproject.toml 33~37줄
- 한 줄 요약: pyproject dependencies에 typer, uvicorn[standard], rich-toolkit, tomli 조건부 의존성이 정의돼 있다
- 비고: 질문은 설정 파일 직접 검색 능력을 평가함

## Q35
- 유형: 3
- 질문: 새 기능을 추가할 때 주로 어느 폴더를 보면 되나요?
- 정답 위치:
  - pyproject.toml 84~84줄
  - pyproject.toml 101~106줄
  - pyproject.toml 88~91줄
- 한 줄 요약: 구현은 src/fastapi_cli 중심, 검증은 tests를 함께 본다
- 비고: 버전 경로/coverage source/build include를 종합해야 함

## Q36
- 유형: 3
- 질문: 문서·저장소·이슈 트래커 링크는 어디서 확인하나요?
- 정답 위치:
  - pyproject.toml 52~57줄
- 한 줄 요약: project.urls 섹션에서 Documentation/Repository/Issues 링크를 확인할 수 있다
- 비고: 운영·협업 관점의 메타정보 탐색 질문

## Q37
- 유형: 3
- 질문: 추가 기능(예: cloud/new 관련 명령)을 쓰려면 어떤 옵션 의존성을 봐야 하나요?
- 정답 위치:
  - pyproject.toml 40~49줄
  - src/fastapi_cli/cli.py 51~59줄
  - src/fastapi_cli/cli.py 61~68줄
- 한 줄 요약: optional-dependencies에서 fastapi-cloud-cli/fastapi-new를 확인하고, cli.py에서 실제 서브커맨드 등록을 본다
- 비고: 의존성 정의와 실행 연결 지점을 모두 요구하는 다문서 문제

## Q38
- 유형: 3
- 질문: 이 프로젝트의 라이선스는 어디서 확인할 수 있나요?
- 정답 위치:
  - README.md 93~95줄
  - pyproject.toml 10~10줄
- 한 줄 요약: README와 pyproject 모두 MIT 라이선스를 명시한다
- 비고: 문서와 메타데이터의 일치 여부를 확인하는 질문

## Q39
- 유형: 4
- 질문: pyproject.toml 설정이 잘못됐다는 에러가 나면 어디를 봐야 하나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 168~177줄
  - src/fastapi_cli/config.py 37~45줄
- 한 줄 요약: _run에서 ValidationError를 잡아 에러를 출력하고, config.resolve의 model_validate가 검증을 수행한다
- 비고: 설정 검증 발생 위치와 에러 표시 위치가 다름

## Q40
- 유형: 4
- 질문: --entrypoint를 path 또는 --app과 같이 써서 실패하면 어디서 검사하나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 159~165줄
- 한 줄 요약: _run 초반 충돌 검사에서 에러 메시지를 출력하고 종료한다
- 비고: 사용자 입력 조합 오류를 즉시 차단하는 방어 로직

## Q41
- 유형: 4
- 질문: 지정한 파일 경로가 없다는 에러는 어디서 발생하고 어디서 사용자에게 보여주나요?
- 정답 위치:
  - src/fastapi_cli/discover.py 139~140줄
  - src/fastapi_cli/cli.py 189~192줄
- 한 줄 요약: discover에서 Path does not exist를 raise하고, _run이 받아서 [error]로 출력한다
- 비고: raise 지점과 핸들링 지점을 모두 봐야 함

## Q42
- 유형: 4
- 질문: 기본 실행 파일을 찾지 못했다는 에러는 어디서 발생하나요?
- 정답 위치:
  - src/fastapi_cli/discover.py 18~36줄
- 한 줄 요약: get_default_path가 후보 파일을 찾지 못하면 FastAPICLIException을 발생시킨다
- 비고: 경로 미지정(auto-discovery) 상황에서 주로 나타남

## Q43
- 유형: 4
- 질문: --app으로 준 이름을 못 찾거나 FastAPI 앱이 아닐 때는 어디를 봐야 하나요?
- 정답 위치:
  - src/fastapi_cli/discover.py 84~93줄
- 한 줄 요약: get_app_name이 이름 존재 여부와 FastAPI 타입 여부를 각각 검증한다
- 비고: 두 케이스의 에러 메시지가 다름

## Q44
- 유형: 4
- 질문: FastAPI 앱 자체를 모듈에서 찾지 못했다는 에러는 어디서 발생하나요?
- 정답 위치:
  - src/fastapi_cli/discover.py 95~103줄
- 한 줄 요약: app/api 우선 탐색과 전체 탐색 이후에도 실패하면 최종 예외를 발생시킨다
- 비고: 자동 탐색 로직을 이해해야 원인 파악이 쉬움

## Q45
- 유형: 4
- 질문: entrypoint import string 형식이 잘못됐다는 에러는 어디서 검사하나요?
- 정답 위치:
  - src/fastapi_cli/discover.py 156~165줄
- 한 줄 요약: get_import_data_from_import_string에서 partition 후 module/app 비어 있음을 검사한다
- 비고: module.submodule:app_name 형식 요구

## Q46
- 유형: 4
- 질문: Uvicorn을 import하지 못했다는 에러는 어디서 발생하나요?
- 정답 위치:
  - src/fastapi_cli/cli.py 44~46줄
  - src/fastapi_cli/cli.py 271~274줄
- 한 줄 요약: 모듈 import 실패 시 uvicorn=None으로 두고, _run에서 None 검사 후 예외를 raise한다
- 비고: import 시점과 실행 시점 검사가 분리되어 있음

## Q47
- 유형: 5
- 질문: 이 프로젝트에서 사용자 로그인은 어떻게 처리하나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에서 확인할 수 없습니다.
- 비고: login, jwt, oauth 로 검색했으나 결과 없음

## Q48
- 유형: 5
- 질문: JWT 토큰 발급과 검증 로직은 어디에 있나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에 해당 내용이 없습니다.
- 비고: jwt, token, sign 로 검색했으나 결과 없음

## Q49
- 유형: 5
- 질문: OAuth2 인증 플로우는 어떤 파일에서 구성하나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에서 확인할 수 없습니다.
- 비고: oauth, oauth2, authorization code 로 검색했으나 결과 없음

## Q50
- 유형: 5
- 질문: 역할 기반 권한(RBAC) 정책은 어디에서 정의하나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에 해당 내용이 없습니다.
- 비고: rbac, role, permission 로 검색했으나 결과 없음

## Q51
- 유형: 5
- 질문: 결제 처리 로직은 어느 모듈에서 시작되나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에서 확인할 수 없습니다.
- 비고: payment, invoice, refund 로 검색했으나 결과 없음

## Q52
- 유형: 5
- 질문: 데이터베이스 연결 설정은 어떤 파일에서 관리하나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에 해당 내용이 없습니다.
- 비고: database, postgres, mysql, sqlite 로 검색했으나 결과 없음

## Q53
- 유형: 5
- 질문: 스키마 마이그레이션(Alembic) 절차는 어디에 문서화되어 있나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에서 확인할 수 없습니다.
- 비고: alembic, migration, revision 로 검색했으나 결과 없음

## Q54
- 유형: 5
- 질문: 요청/응답 캐시(예: Redis) 전략은 어디에 구현돼 있나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에 해당 내용이 없습니다.
- 비고: redis, cache, memcached 로 검색했으나 결과 없음

## Q55
- 유형: 5
- 질문: S3나 GCS로 파일 업로드하는 기능은 어디서 제공하나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에서 확인할 수 없습니다.
- 비고: s3, gcs, upload 로 검색했으나 결과 없음

## Q56
- 유형: 5
- 질문: WebSocket 엔드포인트 초기화 코드는 어디에 있나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에 해당 내용이 없습니다.
- 비고: websocket, ws, endpoint 로 검색했으나 결과 없음

## Q57
- 유형: 5
- 질문: 요청 Rate Limit(스로틀링) 정책은 어디에서 설정하나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에서 확인할 수 없습니다.
- 비고: rate limit, throttle, limiter 로 검색했으나 결과 없음

## Q58
- 유형: 5
- 질문: 다국어(i18n) 또는 로컬라이제이션 리소스는 어디에 있나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에 해당 내용이 없습니다.
- 비고: i18n, localization, locale 로 검색했으나 결과 없음

## Q59
- 유형: 5
- 질문: OpenTelemetry 트레이싱 설정은 어디에서 활성화하나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에서 확인할 수 없습니다.
- 비고: opentelemetry, tracing, otel 로 검색했으나 결과 없음

## Q60
- 유형: 5
- 질문: Prometheus 메트릭 수집 엔드포인트는 어디에 노출하나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에 해당 내용이 없습니다.
- 비고: prometheus, metrics, /metrics 로 검색했으나 결과 없음

## Q61
- 유형: 5
- 질문: 멀티테넌시(tenant 분리) 설계는 어떤 문서에 정리돼 있나요?
- 정답 위치:
  - 문서에 해당 내용 없음 (README.md, pyproject.toml, src/fastapi_cli, tests, scripts 검색)
- 한 줄 요약: 문서에서 확인할 수 없습니다.
- 비고: tenant, multitenant, workspace isolation 로 검색했으나 결과 없음
