// 지금 이슈 설정.
// 로그인(여러 기기에서 관심사 함께 쌓기)을 켜려면, Firebase 콘솔 → 프로젝트 설정 → '내 앱'의
// 웹 앱 설정값(firebaseConfig)을 아래 firebase 자리에 붙여 넣는다. (README.md 의 '로그인 켜기' 참고)
// 이 값들은 비밀번호가 아니라 '어느 프로젝트인지' 알려 주는 공개 식별자라서 공개 저장소에 올려도 된다.
// 실제 접근 통제는 Firestore 보안 규칙(본인 문서만 읽고 쓰기)이 맡는다.
window.HOTISSUE_CONFIG = {
  firebase: null
  // firebase: { apiKey: "…", authDomain: "….firebaseapp.com", projectId: "…", appId: "…" }
};
