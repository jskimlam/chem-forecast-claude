package com.jskimlam.chemforecast; // 앱 패키지

import android.app.Activity;               // 기본 화면 클래스
import android.content.ContentResolver;    // 사진 저장소 접근용
import android.content.ContentValues;      // 저장할 사진 정보 담는 그릇
import android.content.Intent;             // 다른 앱(브라우저·공유) 호출용
import android.content.res.Configuration;  // 화면 크기 변화 감지용
import android.graphics.Color;             // 색상 지정용
import android.net.Uri;                    // 주소 처리용
import android.os.Bundle;                  // 화면 상태 저장용
import android.provider.MediaStore;        // 사진 앱(갤러리) 저장소
import android.util.Base64;                // base64 글자를 이미지 데이터로 되돌리는 용도
import android.view.KeyEvent;              // 뒤로가기 키 처리용
import android.view.Window;                // 상태바 색 지정용
import android.webkit.JavascriptInterface; // 웹페이지에서 부를 수 있는 앱 기능 표시
import android.webkit.WebResourceError;    // 웹 오류 정보
import android.webkit.WebResourceRequest;  // 웹 요청 정보
import android.webkit.WebSettings;         // 웹뷰 설정
import android.webkit.WebView;             // 웹페이지를 보여주는 뷰
import android.webkit.WebViewClient;       // 웹 이동·오류 처리용

import java.io.OutputStream;               // 파일 쓰기용

/** 대시보드(GitHub Pages)를 앱 안에서 보여주는 껍데기 화면입니다. 캡처 이미지 저장·공유 기능을 웹페이지에 제공합니다. */
public class MainActivity extends Activity {

    // 대시보드 주소: 주소가 바뀌면 이 한 줄만 고치면 됩니다.
    private static final String HOME_URL = "https://jskimlam.github.io/chem-forecast-claude/";

    // 앱 안에서 열어도 되는 사이트 주소(그 외 주소는 기본 브라우저로 보냄)
    private static final String HOME_HOST = "jskimlam.github.io";

    private WebView webView; // 웹페이지를 보여줄 뷰

    @Override
    protected void onCreate(Bundle savedInstanceState) { // 화면이 처음 만들어질 때
        super.onCreate(savedInstanceState); // 기본 동작 실행

        Window window = getWindow(); // 창 가져오기
        window.setStatusBarColor(Color.parseColor("#5B5BF0")); // 상태바를 앱 대표색으로

        webView = new WebView(this); // 웹뷰 생성
        setContentView(webView);     // 화면 전체를 웹뷰로 채움

        WebSettings settings = webView.getSettings(); // 웹뷰 설정 가져오기
        settings.setJavaScriptEnabled(true);          // 차트 그리기에 자바스크립트 필요
        settings.setDomStorageEnabled(true);          // 페이지 내부 저장소 허용
        settings.setCacheMode(WebSettings.LOAD_DEFAULT); // 기본 캐시 방식 사용
        settings.setSupportZoom(false);               // 확대 제스처 끔(화면 고정)

        // 웹페이지에서 window.LamApp.saveImage / shareImage 로 부를 수 있게 연결(우리 사이트 안에서만 열리므로 안전)
        webView.addJavascriptInterface(new Bridge(), "LamApp");

        webView.setWebViewClient(new WebViewClient() { // 페이지 이동·오류 처리
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) { // 링크를 눌렀을 때
                Uri uri = request.getUrl(); // 이동할 주소
                if (HOME_HOST.equals(uri.getHost())) { // 우리 사이트면
                    return false; // 앱 안에서 그대로 연다
                }
                startActivity(new Intent(Intent.ACTION_VIEW, uri)); // 외부 주소는 기본 브라우저로 연다
                return true; // 앱 안에서는 열지 않음
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) { // 불러오기 실패
                if (request.isForMainFrame()) { // 메인 페이지가 실패했을 때만
                    String html = "<html><body style='font-family:sans-serif;padding:32px;text-align:center'>"
                            + "<h3>페이지를 불러오지 못했습니다</h3>"
                            + "<p>인터넷 연결을 확인한 뒤 앱을 다시 열어 주세요.</p></body></html>"; // 한글 안내문
                    view.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null); // 안내문 표시
                }
            }
        });

        if (savedInstanceState != null) { // 화면 회전 등으로 다시 만들어졌다면
            webView.restoreState(savedInstanceState); // 보던 상태 복원
        } else {
            webView.loadUrl(HOME_URL); // 처음에는 대시보드 열기
        }
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) { // 폴드 접기·펼치기, 회전 등으로 화면 크기가 바뀔 때
        super.onConfigurationChanged(newConfig); // 기본 동작 실행(앱을 다시 시작하지 않음, 웹페이지가 알아서 크기에 맞춰 다시 그림)
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) { // 상태 저장 시점
        super.onSaveInstanceState(outState); // 기본 동작 실행
        webView.saveState(outState);         // 웹뷰 상태 저장
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) { // 키를 눌렀을 때
        if (keyCode == KeyEvent.KEYCODE_BACK && webView.canGoBack()) { // 뒤로가기이고 이전 페이지가 있으면
            webView.goBack(); // 앱 종료 대신 이전 페이지로
            return true;      // 처리 완료
        }
        return super.onKeyDown(keyCode, event); // 그 외에는 기본 동작
    }

    /** PNG(base64)를 사진 앱의 Pictures/LAMfcst 폴더에 저장하고 주소를 돌려줍니다. 실패하면 null. */
    private Uri savePng(String base64, String name) {
        try {
            byte[] data = Base64.decode(base64, Base64.DEFAULT); // 글자를 이미지 데이터로 되돌림
            ContentResolver cr = getContentResolver();            // 저장소 접근 도구
            ContentValues v = new ContentValues();                // 저장할 사진 정보
            v.put(MediaStore.Images.Media.DISPLAY_NAME, name);    // 파일 이름
            v.put(MediaStore.Images.Media.MIME_TYPE, "image/png"); // 파일 종류
            v.put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/LAMfcst"); // 저장 폴더
            v.put(MediaStore.Images.Media.IS_PENDING, 1);         // 쓰는 동안 갤러리에 숨김
            Uri uri = cr.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, v); // 빈 파일 만들기
            if (uri == null) return null;                         // 만들지 못함
            try (OutputStream os = cr.openOutputStream(uri)) {    // 파일 열기
                if (os == null) return null;                      // 열지 못함
                os.write(data);                                   // 이미지 데이터 쓰기
            }
            v.clear();                                            // 정보 비우기
            v.put(MediaStore.Images.Media.IS_PENDING, 0);         // 쓰기 완료 표시
            cr.update(uri, v, null, null);                        // 갤러리에 보이게 함
            return uri;                                           // 저장된 주소
        } catch (Exception e) {
            return null; // 어떤 오류든 실패로 처리(웹페이지가 한글 안내문을 보여줌)
        }
    }

    /** 웹페이지에서 부르는 앱 기능 모음 */
    public class Bridge {
        /** 이미지를 저장하고 결과 글자를 돌려줍니다("저장됨" 또는 "오류: ..."). */
        @JavascriptInterface
        public String saveImage(String base64, String name) {
            Uri uri = savePng(base64, name); // 사진 저장
            return uri == null ? "오류: 저장 실패" : "저장됨"; // 결과 글자
        }

        /** 이미지를 저장한 뒤 안드로이드 공유 창을 엽니다. */
        @JavascriptInterface
        public void shareImage(final String base64, final String name) {
            final Uri uri = savePng(base64, name); // 사진 저장(공유할 파일 주소가 필요)
            if (uri == null) return; // 저장 실패면 중단
            runOnUiThread(new Runnable() { // 화면 스레드에서 공유 창 열기
                @Override
                public void run() {
                    Intent send = new Intent(Intent.ACTION_SEND);       // 공유 요청
                    send.setType("image/png");                           // 이미지 종류
                    send.putExtra(Intent.EXTRA_STREAM, uri);             // 공유할 파일
                    send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION); // 받는 앱에 읽기 권한 부여
                    startActivity(Intent.createChooser(send, "공유")); // 공유 대상 선택 창
                }
            });
        }
    }
}
