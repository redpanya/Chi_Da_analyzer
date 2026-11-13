# 로컬 디자인 구성요소

- Web Awesome Core **3.14.0**, Copyright 2025–2026 Fonticons, Inc. [MIT 원문](LICENSE.md).
- Lit 및 Lit HTML: Copyright 2017–2022 Google LLC. 배포 모듈의 BSD-3-Clause 주석을 그대로 유지했다. [BSD 원문](LICENSE-LIT.txt).
- Web Awesome 내부 시스템 아이콘은 **Font Awesome Free**의 SVG다. Copyright 2025–2026 Fonticons, Inc. SVG 주석과 원래 모양을 보존했다. 아이콘 CC-BY-4.0, 일반 코드 MIT. 폰트 파일은 동봉하지 않는다. [고지 원문](LICENSE-FONTAWESOME.txt), [공식 아이콘 라이선스](https://fontawesome.com/license/free).

`manifest.json`에 공식 npm tarball URL·SHA-256 및 각 동봉 파일 해시가 있다. npm tarball의 SHA-512를 레지스트리 메타데이터와 대조한 뒤 버튼·배지의 의존 파일만 추출했다. npm 설치 스크립트는 실행하지 않았다. Pro 구성, 전체 로더, 원격 CDN, 원격 글꼴은 사용하지 않는다.

앱 `design-system.js`는 기본 아이콘 resolver의 경로를 같은 로컬 서버 경로로 지정한다. 버튼 내부의 시스템 아이콘은 번들에 이미 있다. 새로운 일반 아이콘을 사용할 때에는 로컬 SVG와 고지를 추가해야 하며 없는 파일을 원격으로 대체하지 않는다.
