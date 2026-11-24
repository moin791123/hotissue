# 지금 이슈

여러 언론사가 **지금 동시에 쓰고 있는** 이슈만 순위로 보여 주는 개인용 실시간 핫이슈 보드.
한 줄 순위 → 누르면 관련 뉴스 → 열어 본 기사로 관심사를 배워 비슷한 이슈를 조금 더 위로.

## 두 가지로 돈다

| | 내 PC판 | 클라우드판 |
|---|---|---|
| 여는 곳 | `http://localhost:8787` (이 PC) | `https://<계정>.github.io/<저장소>/` (어느 기기든) |
| 갱신 | 속보 피드 1분, 나머지 3분 | GitHub Actions 5분 주기 (GitHub 사정으로 몇 분 더 늦어질 수 있음) |
| 돌리는 것 | `server.py` (PC가 켜져 있어야 함) | `.github/workflows/collect.yml` → `build.py` |
| 화면 | `web/` — 양쪽이 똑같은 파일을 쓴다 | |

관심사는 브라우저가 직접 계산·보관한다. 로그인을 켜면 구글 계정에 저장돼 여러 기기에서 같이 쌓인다.

## 내 PC판

- `핫이슈 실행.bat` — 켜고 브라우저 열기 (이미 켜져 있으면 브라우저만 연다)
- `핫이슈 끄기.bat` — 백그라운드로 도는 서버 끄기
- 윈도우 시작프로그램에 등록돼 있으면 PC를 켤 때 창 없이 자동으로 켜진다. 기록은 `data/server.log`.

## 클라우드판 동작

1. 5분마다 GitHub Actions 가 `build.py` 를 실행한다.
2. 직전 실행이 남긴 `state.json.gz`(기사 묶음·이슈 id·순위 기록)를 Pages 에서 받아 이어서 계산한다.
3. 언론사 RSS 를 받아 이슈를 묶고 순위를 매긴 뒤, `data/issues.json` 과 이슈별 `data/i/<id>.json` 을 만들어 Pages 로 배포한다.

저장소에 60일 동안 변화가 없으면 GitHub 이 일정 실행을 자동으로 멈춘다. Actions 탭에서 다시 켜면 된다.

## 로그인 켜기 (여러 기기에서 관심사 같이 쌓기)

구글 계정 로그인과 저장은 Firebase(무료 Spark 요금제)를 쓴다. 한 번만 하면 된다.

1. <https://console.firebase.google.com> → **프로젝트 추가** (애널리틱스는 꺼도 된다).
2. **빌드 → Authentication → 시작하기 → 로그인 방법 → Google** 사용 설정.
3. **Authentication → 설정 → 승인된 도메인**에 `<계정>.github.io` 추가. (`localhost` 는 기본으로 들어 있다)
4. **빌드 → Firestore Database → 데이터베이스 만들기** (위치는 `asia-northeast3` 서울, 프로덕션 모드).
5. Firestore **규칙** 탭에 아래를 붙여 넣고 게시 — 로그인한 본인만 자기 문서를 읽고 쓴다.

   ```
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       match /profiles/{uid} {
         allow read, write: if request.auth != null && request.auth.uid == uid;
       }
     }
   }
   ```

6. **프로젝트 설정(톱니바퀴) → 일반 → 내 앱 → 웹 앱 추가(`</>`)** 후 나오는 `firebaseConfig` 값을
   `web/config.js` 의 `firebase:` 자리에 넣고 저장소에 올린다.
   이 값은 비밀번호가 아니라 공개 식별자다. 접근 통제는 5번의 규칙이 맡는다.

그러면 화면 오른쪽 위에 **로그인** 버튼이 생긴다. 로그인 전에 그 기기에 쌓인 관심사는 로그인할 때 계정 것과 합쳐진다.
카카오톡 같은 앱 안 브라우저에서는 구글 로그인 창이 막히므로 크롬·사파리에서 연다.

## 순위 성격 바꾸기

`engine.py` 맨 위 조정값:

- `CAT_WEIGHT`, `CAT_CAP` — 분야 비중과 종합 순위에 들어올 수 있는 몫 (정치·연예 2개, 스포츠 1개)
- `HALF_LIFE_MIN` — 기사의 뜨거움이 절반으로 식는 시간(분)
- `URGENT` — 분야와 상관없이 앞세우는 안보·재난 낱말
- `BLAND`, `STOP` — 이슈 이름·관심사에서 빼는 밋밋한 말

언론사 목록은 `sources.py`.
