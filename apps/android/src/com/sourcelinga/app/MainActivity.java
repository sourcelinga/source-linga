package com.sourcelinga.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Insets;
import android.graphics.Outline;
import android.net.Uri;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.tts.TextToSpeech;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.HapticFeedbackConstants;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewOutlineProvider;
import android.view.WindowInsets;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * Source Linga for Android. The AI runs on your Mac; this app finds the Mac on your Wi-Fi (Bonjour),
 * pairs with the 6-digit code the Mac shows, then shows the chat app the Mac serves, with native
 * copy, share, read-aloud, haptics and "share to Source Linga" from any app.
 */
public class MainActivity extends Activity {
    private static final String SERVICE = "_sourcelinga._tcp";

    private SharedPreferences prefs;
    private WebView web;
    private View setup, offline, loading, pickStep, codeStep, busy;
    private LinearLayout found;
    private TextView searching, error, pairWith, offlineWhy;
    private EditText address, code;
    private final Handler main = new Handler(Looper.getMainLooper());

    private String pairBase;          // the Mac we're pairing with
    private String pendingText;       // text shared from another app, handed to the chat once it loads
    private boolean pageOk;
    private TextToSpeech tts;
    private NsdManager nsd;
    private NsdManager.DiscoveryListener discovery;
    private WifiManager.MulticastLock multicast;
    private final List<String> foundNames = new ArrayList<>();

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(R.layout.main);
        prefs = getSharedPreferences("sourcelinga", MODE_PRIVATE);

        web = findViewById(R.id.web);
        setup = findViewById(R.id.setup);
        offline = findViewById(R.id.offline);
        loading = findViewById(R.id.loading);
        pickStep = findViewById(R.id.pickStep);
        codeStep = findViewById(R.id.codeStep);
        busy = findViewById(R.id.busy);
        found = findViewById(R.id.found);
        searching = findViewById(R.id.searching);
        error = findViewById(R.id.error);
        pairWith = findViewById(R.id.pairWith);
        offlineWhy = findViewById(R.id.offlineWhy);
        address = findViewById(R.id.address);
        code = findViewById(R.id.code);

        fitSystemBars(findViewById(R.id.root));
        for (int id : new int[]{R.id.logo1, R.id.logo2}) roundCorners(findViewById(id));
        setupWebView();
        wireSetup();
        ((Button) findViewById(R.id.retry)).setOnClickListener(v -> loadChat());
        ((Button) findViewById(R.id.changeMac)).setOnClickListener(v -> showSetup(null));

        takeIntent(getIntent());
        if (base() == null || key() == null) showSetup(null);
        else loadChat();
    }

    // ------------------------------------------------------------------ layout

    /** Android 15 draws apps edge to edge; keep content clear of the status bar, navigation bar and keyboard. */
    private void fitSystemBars(View root) {
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                Insets ime = insets.getInsets(WindowInsets.Type.ime());
                v.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, ime.bottom));
            } else {
                v.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                        insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            }
            return insets;
        });
    }

    private static void roundCorners(View v) {
        v.setOutlineProvider(new ViewOutlineProvider() {
            @Override public void getOutline(View view, Outline o) {
                o.setRoundRect(0, 0, view.getWidth(), view.getHeight(), view.getWidth() * 0.24f);
            }
        });
        v.setClipToOutline(true);
    }

    private void show(View which) {
        for (View v : new View[]{setup, offline}) v.setVisibility(v == which ? View.VISIBLE : View.GONE);
        web.setVisibility(which == web ? View.VISIBLE : View.INVISIBLE);
        loading.setVisibility(View.GONE);
    }

    // ------------------------------------------------------------------ the chat (served by the Mac)

    private void setupWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setTextZoom(100);
        s.setUserAgentString(s.getUserAgentString() + " SourceLingaAndroid/1.1");
        web.setBackgroundColor(getColor(R.color.bg));
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.addJavascriptInterface(new Bridge(), "SLNative");
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                String b = base();
                if (b != null && u.toString().startsWith(b)) {
                    if ("/pair".equals(u.getPath())) {  // the Mac no longer knows this phone's key
                        prefs.edit().remove("key").apply();
                        showSetup("Your Mac asked to pair again (its key was changed).");
                        return true;
                    }
                    return false;
                }
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) { }
                return true;
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                pageOk = true;
                if (url != null && url.endsWith("/pair")) {
                    prefs.edit().remove("key").apply();
                    showSetup("Your Mac asked to pair again (its key was changed).");
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (pageOk && url != null && url.contains("/app")) show(web);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) {
                    pageOk = false;
                    offlineWhy.setText("Make sure the Mac (" + host(base()) + ") is awake, Source Linga is running, "
                            + "and this phone is on the same Wi-Fi.");
                    show(offline);
                }
            }
        });
    }

    private void loadChat() {
        String b = base(), k = key();
        if (b == null || k == null) { showSetup(null); return; }
        loading.setVisibility(View.VISIBLE);
        offline.setVisibility(View.GONE);
        CookieManager cm = CookieManager.getInstance();
        cm.setAcceptCookie(true);
        cm.setCookie(b, "sl_key=" + k + "; Path=/; Max-Age=31536000");
        cm.flush();
        web.loadUrl(b + "/app");
    }

    /** Called by the web app (window.SLNative) for things a browser page can't do well on Android. */
    private class Bridge {
        @JavascriptInterface public void copy(String text) {
            main.post(() -> {
                ClipboardManager cb = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                cb.setPrimaryClip(ClipData.newPlainText("Source Linga", text));
            });
        }

        @JavascriptInterface public void share(String text) {
            main.post(() -> {
                Intent send = new Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text);
                startActivity(Intent.createChooser(send, "Share"));
            });
        }

        @JavascriptInterface public void speak(String text) {
            main.post(() -> {
                if (tts != null && tts.isSpeaking()) { tts.stop(); return; }
                if (tts == null) {
                    tts = new TextToSpeech(MainActivity.this, st -> {
                        if (st == TextToSpeech.SUCCESS) tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "sl");
                    });
                } else tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "sl");
            });
        }

        @JavascriptInterface public void haptic() {
            main.post(() -> web.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP));
        }

        @JavascriptInterface public void settings() { main.post(MainActivity.this::showSettings); }

        @JavascriptInterface public String pendingText() {
            String t = pendingText;
            pendingText = null;
            return t == null ? "" : t;
        }
    }

    private void showSettings() {
        new AlertDialog.Builder(this)
                .setTitle("Source Linga")
                .setMessage("Connected to " + prefs.getString("name", "your Mac") + "\n" + base()
                        + "\n\nThe AI and your chats stay on that Mac.")
                .setPositiveButton("Reload", (d, w) -> loadChat())
                .setNeutralButton("Change Mac", (d, w) -> {
                    prefs.edit().remove("key").remove("base").apply();
                    showSetup(null);
                })
                .setNegativeButton("Close", null)
                .show();
    }

    // ------------------------------------------------------------------ sharing into the app

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        takeIntent(intent);
        if (web.getVisibility() == View.VISIBLE) deliverPending();
    }

    private void takeIntent(Intent i) {
        if (i == null) return;
        String t = null;
        if (Intent.ACTION_SEND.equals(i.getAction())) t = i.getStringExtra(Intent.EXTRA_TEXT);
        else if (Build.VERSION.SDK_INT >= 23 && Intent.ACTION_PROCESS_TEXT.equals(i.getAction())) {
            CharSequence cs = i.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT);
            t = cs == null ? null : cs.toString();
        } else if ("com.sourcelinga.app.NEW_CHAT".equals(i.getAction())) {
            if (web.getVisibility() == View.VISIBLE) web.evaluateJavascript("window.slNew&&slNew()", null);
            return;
        }
        if (t != null && !t.trim().isEmpty()) pendingText = t;
    }

    private void deliverPending() {
        if (pendingText == null) return;
        String js = "window.slShare&&slShare(" + JSONObject.quote(pendingText) + ")";
        pendingText = null;
        web.evaluateJavascript(js, null);
    }

    // ------------------------------------------------------------------ first run: find and pair

    private void wireSetup() {
        findViewById(R.id.next).setOnClickListener(v -> useAddress());
        address.setOnEditorActionListener((v, id, e) -> {
            if (id == EditorInfo.IME_ACTION_GO) { useAddress(); return true; }
            return false;
        });
        findViewById(R.id.pair).setOnClickListener(v -> pair());
        findViewById(R.id.back).setOnClickListener(v -> showSetup(null));
        code.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int b, int c) { }
            public void onTextChanged(CharSequence s, int a, int b, int c) { }
            public void afterTextChanged(Editable s) { if (s.length() == 6) pair(); }
        });
    }

    private void showSetup(String message) {
        show(setup);
        pickStep.setVisibility(View.VISIBLE);
        codeStep.setVisibility(View.GONE);
        busy.setVisibility(View.GONE);
        error.setText(message == null ? "" : message);
        code.setText("");
        pairBase = null;
        startDiscovery();
    }

    private void startDiscovery() {
        stopDiscovery();
        found.removeAllViews();
        foundNames.clear();
        searching.setVisibility(View.VISIBLE);
        try {
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            multicast = wm.createMulticastLock("sourcelinga");
            multicast.setReferenceCounted(false);
            multicast.acquire();
        } catch (Exception ignored) { }
        nsd = (NsdManager) getSystemService(Context.NSD_SERVICE);
        discovery = new NsdManager.DiscoveryListener() {
            public void onDiscoveryStarted(String t) { }
            public void onDiscoveryStopped(String t) { }
            public void onStartDiscoveryFailed(String t, int e) { }
            public void onStopDiscoveryFailed(String t, int e) { }
            public void onServiceLost(NsdServiceInfo s) { }
            public void onServiceFound(NsdServiceInfo s) { resolve(s); }
        };
        try { nsd.discoverServices(SERVICE, NsdManager.PROTOCOL_DNS_SD, discovery); } catch (Exception ignored) { }
    }

    @SuppressWarnings("deprecation")
    private void resolve(NsdServiceInfo s) {
        try {
            nsd.resolveService(s, new NsdManager.ResolveListener() {
                public void onResolveFailed(NsdServiceInfo i, int e) { }
                public void onServiceResolved(NsdServiceInfo i) {
                    InetAddress addr = i.getHost();
                    if (Build.VERSION.SDK_INT >= 34) {
                        for (InetAddress a : i.getHostAddresses()) if (a instanceof Inet4Address) { addr = a; break; }
                    }
                    if (addr == null) return;
                    String h = addr.getHostAddress();
                    if (h.contains(":")) h = "[" + h.replaceAll("%.*$", "") + "]";
                    String url = "http://" + h + ":" + i.getPort();
                    String name = i.getServiceName().replace("Source Linga on ", "");
                    main.post(() -> addFound(name, url));
                }
            });
        } catch (Exception ignored) { }
    }

    private void addFound(String name, String url) {
        if (foundNames.contains(name) || setup.getVisibility() != View.VISIBLE) return;
        foundNames.add(name);
        searching.setVisibility(View.GONE);
        TextView row = new TextView(this);
        row.setText("💻   " + name);
        row.setTextSize(17);
        row.setTextColor(getColor(R.color.ink));
        row.setBackgroundResource(R.drawable.row);
        int p = dp(16);
        row.setPadding(p, p, p, p);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(8);
        row.setOnClickListener(v -> chooseMac(url, name));
        found.addView(row, lp);
    }

    private void useAddress() {
        String t = address.getText().toString().trim();
        if (t.isEmpty()) return;
        if (!t.contains("://")) t = "http://" + t;
        Uri u = Uri.parse(t);
        if (u.getHost() == null) { error.setText("That doesn't look like an address."); return; }
        String url = "http://" + (u.getHost().contains(":") ? "[" + u.getHost() + "]" : u.getHost()) + ":"
                + (u.getPort() > 0 ? u.getPort() : 8777);
        setBusy(true);
        new Thread(() -> {
            try {
                JSONObject info = new JSONObject(http(url + "/api/info", null, null));
                String name = info.optString("computer", u.getHost());
                main.post(() -> { setBusy(false); chooseMac(url, name); });
            } catch (Exception e) {
                main.post(() -> {
                    setBusy(false);
                    error.setText("No Source Linga at that address. Is the Mac awake, on this Wi-Fi, with device access on?");
                });
            }
        }).start();
    }

    private void chooseMac(String url, String name) {
        pairBase = url;
        prefs.edit().putString("name", name).apply();
        pickStep.setVisibility(View.GONE);
        codeStep.setVisibility(View.VISIBLE);
        pairWith.setText("Pair with " + name);
        error.setText("");
        code.requestFocus();
        InputMethodManager imm = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
        main.postDelayed(() -> imm.showSoftInput(code, InputMethodManager.SHOW_IMPLICIT), 150);
    }

    private void pair() {
        String c = code.getText().toString().trim();
        if (pairBase == null || c.length() != 6 || busy.getVisibility() == View.VISIBLE) return;
        setBusy(true);
        error.setText("");
        String target = pairBase;
        new Thread(() -> {
            try {
                JSONObject body = new JSONObject().put("code", c).put("app", true);
                JSONObject r = new JSONObject(http(target + "/pair", body.toString(), null));
                String key = r.getString("key");
                prefs.edit().putString("base", target).putString("key", key)
                        .putString("name", r.optString("computer", "your Mac")).apply();
                main.post(() -> {
                    setBusy(false);
                    stopDiscovery();
                    InputMethodManager imm = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
                    imm.hideSoftInputFromWindow(code.getWindowToken(), 0);
                    loadChat();
                });
            } catch (Exception e) {
                String msg = e.getMessage() == null ? "Could not pair." : e.getMessage();
                main.post(() -> { setBusy(false); code.setText(""); error.setText(msg); });
            }
        }).start();
    }

    private void setBusy(boolean b) { busy.setVisibility(b ? View.VISIBLE : View.GONE); }

    /** Small blocking HTTP helper (runs on a background thread). Throws with the server's error message. */
    private static String http(String url, String json, String key) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(6000);
        c.setReadTimeout(15000);
        if (key != null) c.setRequestProperty("Authorization", "Bearer " + key);
        if (json != null) {
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            try (OutputStream o = c.getOutputStream()) { o.write(json.getBytes(StandardCharsets.UTF_8)); }
        }
        int status = c.getResponseCode();
        InputStream in = status < 400 ? c.getInputStream() : c.getErrorStream();
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        if (in != null) {
            byte[] b = new byte[8192];
            for (int n; (n = in.read(b)) > 0; ) buf.write(b, 0, n);
            in.close();
        }
        String text = buf.toString("UTF-8");
        if (status >= 400) {
            String err = "Error " + status;
            try { err = new JSONObject(text).optString("error", err); } catch (Exception ignored) { }
            throw new Exception(err.substring(0, 1).toUpperCase(Locale.ROOT) + err.substring(1));
        }
        return text;
    }

    private void stopDiscovery() {
        try { if (nsd != null && discovery != null) nsd.stopServiceDiscovery(discovery); } catch (Exception ignored) { }
        discovery = null;
        try { if (multicast != null) multicast.release(); } catch (Exception ignored) { }
    }

    // ------------------------------------------------------------------ lifecycle

    @Override
    public void onBackPressed() {
        if (setup.getVisibility() == View.VISIBLE && codeStep.getVisibility() == View.VISIBLE) { showSetup(null); return; }
        if (web.getVisibility() == View.VISIBLE && web.canGoBack()) { web.goBack(); return; }
        super.onBackPressed();
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
        if (offline.getVisibility() == View.VISIBLE) loadChat();  // came back to the app: try again
        if (web.getVisibility() == View.VISIBLE) main.postDelayed(this::deliverPending, 300);
    }

    @Override
    protected void onPause() {
        web.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        stopDiscovery();
        if (tts != null) tts.shutdown();
        super.onDestroy();
    }

    private String base() { return prefs.getString("base", null); }
    private String key() { return prefs.getString("key", null); }
    private static String host(String url) { return url == null ? "" : Uri.parse(url).getHost(); }
    private int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }
}
