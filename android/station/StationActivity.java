package com.aivuda.h16;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.view.ViewGroup;
import android.view.ViewParent;
import android.webkit.*;
import android.widget.*;
import org.json.JSONObject;
import java.io.*;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/** Hosts the bundled management panel at the selected server's origin so its API,
 * event streams, interactive installation and app UI routes use the desktop protocol. */
public class StationActivity extends Activity {
    private static final String ASSETS = "/_aivuda_h16/";
    // This reserved origin serves only bundled pages until the user chooses a server.
    private static final String SETUP_ORIGIN = "https://aivuda.invalid";
    private static final int REQUEST_PICK_FILE = 1;
    private static final int REQUEST_EXPORT_FILE = 2;
    private WebView web;
    private String origin;
    private String store;
    private ValueCallback<Uri[]> pendingFiles;
    private String pendingExportText;
    private boolean sslErrorShown;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        SharedPreferences prefs = getSharedPreferences("panel", MODE_PRIVATE);
        try { origin = address(prefs.getString("origin", "")); }
        catch (Exception invalidStoredAddress) { origin = ""; }
        // Preserve store address migrated from older station builds.
        store = prefs.getString("store", "");
        open();
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (Intent.ACTION_MAIN.equals(intent.getAction()) && intent.hasCategory(Intent.CATEGORY_LAUNCHER)) {
            open();
        }
    }

    private String pageOrigin() {
        return origin.isEmpty() ? SETUP_ORIGIN : origin;
    }

    private boolean isPageOrigin(Uri uri) {
        if (uri == null || uri.getScheme() == null || uri.getHost() == null) return false;
        String scheme = uri.getScheme().toLowerCase(Locale.ROOT);
        String host = uri.getHost().toLowerCase(Locale.ROOT);
        int port = uri.getPort();
        if (("http".equals(scheme) && port == 80) || ("https".equals(scheme) && port == 443)) port = -1;
        String normalized = port > 0 ? scheme + "://" + host + ":" + port : scheme + "://" + host;
        return pageOrigin().equals(normalized);
    }

    private String address(String text) throws Exception {
        String value = text.trim();
        URI uri = new URI(value.contains("://") ? value : "http://" + value);
        String scheme = uri.getScheme();
        if (!("http".equalsIgnoreCase(scheme) || "https".equalsIgnoreCase(scheme))
            || uri.getHost() == null || uri.getUserInfo() != null || uri.getPort() == 0
            || uri.getPort() > 65535 || "aivuda.invalid".equalsIgnoreCase(uri.getHost()))
            throw new IllegalArgumentException();
        int port = uri.getPort();
        if (("http".equalsIgnoreCase(scheme) && port == 80) || ("https".equalsIgnoreCase(scheme) && port == 443)) port = -1;
        return new URI(scheme.toLowerCase(java.util.Locale.ROOT), null,
            uri.getHost().toLowerCase(java.util.Locale.ROOT), port, null, null, null).toString();
    }

    private void configure() {
        EditText field = new EditText(this);
        field.setSingleLine();
        field.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        field.setText(origin);
        field.setSelectAllOnFocus(true);
        LinearLayout container = new LinearLayout(this);
        int padding = Math.round(20 * getResources().getDisplayMetrics().density);
        container.setPadding(padding, 0, padding, 0);
        container.addView(field, -1, -2);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle(R.string.endpoint).setView(container)
            .setNegativeButton(android.R.string.cancel, null).setPositiveButton(android.R.string.ok, null).create();
        dialog.setOnShowListener(v -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(button -> {
            try {
                String target = address(field.getText().toString());
                dialog.dismiss();
                if (!target.equals(origin)) {
                    origin = target;
                    getSharedPreferences("panel", MODE_PRIVATE).edit().putString("origin", origin).apply();
                    open();
                }
            } catch (Exception e) { field.setError(getString(R.string.invalid_server)); }
        }));
        dialog.show();
    }

    private void open() {
        releaseWebView();
        sslErrorShown = false;
        WebView.setWebContentsDebuggingEnabled(getPackageName().equals(android.provider.Settings.Global.getString(
            getContentResolver(), android.provider.Settings.Global.DEBUG_APP)));
        web = new WebView(this);
        if (getActionBar() != null) getActionBar().hide();
        setContentView(web);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setUseWideViewPort(true);
        settings.setTextZoom(100);
        web.addJavascriptInterface(new StationBridge(this), "h16Station");
        web.setWebChromeClient(new FileChooser(this));
        web.setDownloadListener((url, ua, disposition, mime, length) -> {
            Uri uri = Uri.parse(url);
            if (!"http".equals(uri.getScheme()) && !"https".equals(uri.getScheme())) return;
            DownloadManager.Request request = new DownloadManager.Request(uri);
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setTitle(URLUtil.guessFileName(url, disposition, mime));
            try { ((DownloadManager)getSystemService(DOWNLOAD_SERVICE)).enqueue(request); }
            catch (RuntimeException e) {
                new AlertDialog.Builder(this).setMessage(getString(R.string.error) + "\n" + e.getMessage())
                    .setPositiveButton(android.R.string.ok, null).show();
            }
        });
        web.setWebViewClient(new BundledPages(this));
        web.loadUrl(pageOrigin() + "/login");
    }

    private void startExportTextFile(String filename, String content) {
        if (web == null || !isPageOrigin(Uri.parse(web.getUrl() == null ? "" : web.getUrl()))) return;
        String safeName = filename == null ? "" : filename.trim().replace('\\', '/');
        int slash = safeName.lastIndexOf('/');
        if (slash >= 0) safeName = safeName.substring(slash + 1);
        if (safeName.isEmpty()) safeName = "aivudaos-config.json";
        pendingExportText = content == null ? "" : content;
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/json");
        intent.putExtra(Intent.EXTRA_TITLE, safeName);
        try {
            startActivityForResult(intent, REQUEST_EXPORT_FILE);
        } catch (ActivityNotFoundException e) {
            pendingExportText = null;
            new AlertDialog.Builder(this).setMessage(getString(R.string.export_unavailable))
                .setPositiveButton(android.R.string.ok, null).show();
        }
    }

    private static final class StationBridge {
        final StationActivity owner;
        StationBridge(StationActivity owner) { this.owner = owner; }

        @JavascriptInterface public void saveTextFile(String filename, String content) {
            owner.runOnUiThread(() -> owner.startExportTextFile(filename, content));
        }
    }

    private static final class FileChooser extends WebChromeClient {
        final StationActivity owner;
        FileChooser(StationActivity owner) { this.owner = owner; }
        @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
            if (owner.pendingFiles != null) owner.pendingFiles.onReceiveValue(null);
            owner.pendingFiles = callback;
            Intent intent = params.createIntent();
            String type = intent.getType();
            if (type == null || !type.contains("/") || type.contains(",")) {
                intent.setType("*/*");
            }
            try { owner.startActivityForResult(intent, REQUEST_PICK_FILE); }
            catch (ActivityNotFoundException e) {
                intent.setType("*/*");
                try { owner.startActivityForResult(intent, REQUEST_PICK_FILE); }
                catch (ActivityNotFoundException fallbackError) {
                    callback.onReceiveValue(null);
                    owner.pendingFiles = null;
                }
            }
            return true;
        }
    }

    private static final class BundledPages extends WebViewClient {
        final StationActivity owner;
        BundledPages(StationActivity owner) { this.owner = owner; }
        @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            if (!"aivuda-station".equals(request.getUrl().getScheme())) return false;
            Uri page = Uri.parse(view.getUrl() == null ? "" : view.getUrl());
            if (request.isForMainFrame() && "aivuda-station://server".equals(request.getUrl().toString())
                && "/login".equals(page.getPath()) && owner.isPageOrigin(page)) owner.configure();
            return true;
        }

        @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest req) {
            Uri uri = req.getUrl();
            if (!owner.isPageOrigin(uri) || !"GET".equals(req.getMethod())) return null;
            String path = uri.getPath();
            if (path == null) path = "";
            if (req.isForMainFrame() && (path.isEmpty() || "/".equals(path) || "/login".equals(path)
                || "/dashboard".equals(path) || path.startsWith("/dashboard/")))
                return owner.panelFile("index.html");
            if (path.startsWith(ASSETS)) return owner.panelFile(path.substring(ASSETS.length()));
            return null;
        }

        @Override public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
            handler.cancel();
            if (owner.sslErrorShown || owner.isFinishing()) return;
            Uri failedUri = error != null && error.getUrl() != null ? Uri.parse(error.getUrl()) : null;
            if (failedUri == null || owner.isPageOrigin(failedUri)) {
                owner.sslErrorShown = true;
                owner.runOnUiThread(() -> {
                    if (!owner.isFinishing()) {
                        new AlertDialog.Builder(owner).setTitle(R.string.error)
                            .setMessage(R.string.ssl_error)
                            .setPositiveButton(android.R.string.ok, null).show();
                    }
                });
            }
        }
    }

    private WebResourceResponse panelFile(String name) {
        if (name.contains("..")) return null;
        try {
            InputStream in = getAssets().open("panel/" + name);
            if ("index.html".equals(name)) {
                String html;
                try (InputStream input = in) {
                    html = Streams.readUtf8(input);
                }
                String locale = getResources().getConfiguration().getLocales().get(0).getLanguage().equals("zh") ? "zh-CN" : "en-US";
                String settings = "{server:" + JSONObject.quote(origin) + ",store:" + JSONObject.quote(store)
                    + ",locale:" + JSONObject.quote(locale) + "}";
                String bootstrap = "<script>window.h16Settings=" + settings.replace("<", "\\u003c") + ";</script>";
                in = new ByteArrayInputStream(html.replace("</head>", bootstrap + "</head>").getBytes(StandardCharsets.UTF_8));
            }
            String mime = name.endsWith(".js") ? "application/javascript" : name.endsWith(".css") ? "text/css" :
                name.endsWith(".html") ? "text/html" : java.net.URLConnection.guessContentTypeFromName(name);
            return new WebResourceResponse(mime, mime != null && (mime.startsWith("text") || mime.contains("javascript")) ? "UTF-8" : null, in);
        } catch (IOException e) { return null; }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == REQUEST_PICK_FILE && pendingFiles != null) {
            pendingFiles.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result, data));
            pendingFiles = null;
        } else if (request == REQUEST_EXPORT_FILE) {
            String content = pendingExportText;
            pendingExportText = null;
            if (result == RESULT_OK && data != null && data.getData() != null && content != null) {
                try (OutputStream out = getContentResolver().openOutputStream(data.getData())) {
                    if (out == null) throw new IOException("Unable to open destination file");
                    out.write(content.getBytes(StandardCharsets.UTF_8));
                    out.flush();
                    Toast.makeText(this, R.string.export_saved, Toast.LENGTH_SHORT).show();
                } catch (IOException | SecurityException e) {
                    new AlertDialog.Builder(this).setMessage(getString(R.string.error) + "\n" + e.getMessage())
                        .setPositiveButton(android.R.string.ok, null).show();
                }
            }
        }
    }

    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack(); else super.onBackPressed();
    }

    @Override protected void onPause() {
        if (web != null) web.onPause();
        super.onPause();
    }

    @Override protected void onResume() {
        super.onResume();
        if (web != null) web.onResume();
    }

    private void releaseWebView() {
        if (pendingFiles != null) {
            pendingFiles.onReceiveValue(null);
            pendingFiles = null;
        }
        pendingExportText = null;
        if (web != null) {
            web.stopLoading();
            web.removeJavascriptInterface("h16Station");
            web.setWebChromeClient(null);
            web.setWebViewClient(null);
            ViewParent parent = web.getParent();
            if (parent instanceof ViewGroup) ((ViewGroup) parent).removeView(web);
            web.destroy();
            web = null;
        }
    }

    @Override protected void onDestroy() {
        releaseWebView();
        super.onDestroy();
    }
}
