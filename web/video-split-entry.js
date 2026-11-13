// 이전 주소도 공통 메뉴 안의 영상 나누기로 연결한다.
const url=new URL('./',location.href);
url.search=location.search;
url.hash='split';
location.replace(url.href);
