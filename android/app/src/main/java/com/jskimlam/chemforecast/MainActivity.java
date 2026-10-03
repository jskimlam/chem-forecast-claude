package com.jskimlam.chemforecast; // 앱 패키지

import android.app.Activity;               // 기본 화면 클래스
import android.content.Intent;             // 다른 앱(브라우저) 호출용
import android.graphics.Color;             // 색상 지정용
import android.net.Uri;                    // 주소 처리용
import android.os.Bundle;                  // 화면 상태 저장용
import android.view.KeyEvent;              // 뒤로가기 키 처리용
import android.view.View;                  // 화면 요소 기본형
import android.view.Window;                // 상태바 색 지정용
import android.webkit.WebResourceError;    // 웹 오류 정보
import android.webkit.WebResourceRequest;  // 웹 요청 정보
import android.webkit.WebSettings;         // 웹뷰 설정
import android.webkit.WebView;             // 웹페이지를 보여주는 뷰
import android.webkit.WebViewClient;       // 웹 이동·오류 처리용

/** 대시보드(GitHub Pages)를 앱 안에서 보여주는 껍데기 화면입니다. */
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
}
