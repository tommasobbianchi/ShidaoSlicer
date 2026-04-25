// orcabelt-fluidd-host — isolated WebKitGTK host for the Device tab.
//
// Why this binary exists: embedding Fluidd's Vue SPA inside Orca's main
// process exposes libjavascriptcoregtk's JSC runtime to whatever the
// Plater main thread does (OpenGL, TBB slicing, heavy malloc). Reliably
// segfaults on first WebView load after a slice (libjavascriptcoregtk
// +0x191f9fc).
//
// Architecture (overlay, not XEmbed): the WebView lives in a borderless
// undecorated toplevel GTK window. Orca tracks the screen geometry of
// the Device-tab panel and sends GEOM commands so the host window aligns
// over that area. Hidden/shown via stdin. Avoids GtkPlug/GtkSocket
// XEmbed which doesn't work reliably when the socket lives inside a
// wxGTK wxPizza container.
//
// Protocol (stdin, one command per line):
//   URL <url>             navigate
//   BLANK                 about:blank (pause)
//   RELOAD                reload
//   APIKEY <k>            update injected X-API-Key
//   GEOM <x> <y> <w> <h>  position window over (screen-coords px)
//   SHOW                  map window
//   HIDE                  unmap window
//   QUIT                  exit cleanly

#include <gtk/gtk.h>
#include <webkit2/webkit2.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <unistd.h>
#include <execinfo.h>
#include <signal.h>

namespace {

GtkWidget*     g_window  = nullptr;
WebKitWebView* g_webview = nullptr;
std::string    g_apikey;

std::string escape_js_string(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 4);
    for (char c : s) {
        switch (c) {
            case '\\': out += "\\\\"; break;
            case '\'': out += "\\'"; break;
            case '"':  out += "\\\""; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    char buf[8];
                    snprintf(buf, sizeof(buf), "\\x%02x", (unsigned char)c);
                    out += buf;
                } else {
                    out += c;
                }
        }
    }
    return out;
}

void refresh_apikey_script() {
    if (!g_webview) return;
    WebKitUserContentManager* ucm = webkit_web_view_get_user_content_manager(g_webview);
    webkit_user_content_manager_remove_all_scripts(ucm);
    if (g_apikey.empty()) return;
    const std::string k = escape_js_string(g_apikey);
    const std::string script =
        "if (window.fetch) {"
        "  const __orig = window.fetch;"
        "  window.fetch = function(input, init = {}) {"
        "    init.headers = init.headers || {};"
        "    init.headers['X-API-Key'] = '" + k + "';"
        "    return __orig(input, init);"
        "  };"
        "}";
    WebKitUserScript* us = webkit_user_script_new(
        script.c_str(),
        WEBKIT_USER_CONTENT_INJECT_ALL_FRAMES,
        WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START,
        nullptr, nullptr);
    webkit_user_content_manager_add_script(ucm, us);
    webkit_user_script_unref(us);
}

void do_load(const char* uri) {
    if (!g_webview || !uri || !*uri) return;
    refresh_apikey_script();
    webkit_web_view_load_uri(g_webview, uri);
}

void do_geom(int x, int y, int w, int h) {
    if (!g_window) return;
    if (w < 1) w = 1; if (h < 1) h = 1;
    gtk_window_move(GTK_WINDOW(g_window), x, y);
    gtk_window_resize(GTK_WINDOW(g_window), w, h);
}

gboolean on_stdin(GIOChannel* ch, GIOCondition cond, gpointer /*data*/) {
    if (cond & (G_IO_HUP | G_IO_ERR)) {
        gtk_main_quit();
        return FALSE;
    }
    gchar* line = nullptr;
    gsize  len  = 0;
    GError* err = nullptr;
    GIOStatus st = g_io_channel_read_line(ch, &line, &len, nullptr, &err);
    if (st != G_IO_STATUS_NORMAL || !line) {
        if (err) g_error_free(err);
        if (st == G_IO_STATUS_EOF) {
            gtk_main_quit();
            return FALSE;
        }
        return TRUE;
    }
    while (len > 0 && (line[len-1] == '\n' || line[len-1] == '\r')) {
        line[--len] = '\0';
    }
    fprintf(stderr, "[host] cmd: %s\n", line); fflush(stderr);
    if (strncmp(line, "URL ", 4) == 0) {
        do_load(line + 4);
    } else if (strncmp(line, "APIKEY ", 7) == 0) {
        g_apikey = line + 7;
    } else if (strcmp(line, "BLANK") == 0) {
        do_load("about:blank");
    } else if (strcmp(line, "RELOAD") == 0) {
        if (g_webview) webkit_web_view_reload(g_webview);
    } else if (strncmp(line, "GEOM ", 5) == 0) {
        int x = 0, y = 0, w = 0, h = 0;
        if (sscanf(line + 5, "%d %d %d %d", &x, &y, &w, &h) == 4) do_geom(x, y, w, h);
    } else if (strcmp(line, "SHOW") == 0) {
        if (g_window) gtk_widget_show(g_window);
    } else if (strcmp(line, "HIDE") == 0) {
        if (g_window) gtk_widget_hide(g_window);
    } else if (strcmp(line, "QUIT") == 0) {
        g_free(line);
        gtk_main_quit();
        return FALSE;
    }
    g_free(line);
    return TRUE;
}

void on_load_changed(WebKitWebView* /*w*/, WebKitLoadEvent ev, gpointer /*ud*/) {
    const char* names[] = {"STARTED", "REDIRECTED", "COMMITTED", "FINISHED"};
    fprintf(stderr, "[host] load_changed: %s\n",
        (ev >= 0 && ev < 4) ? names[ev] : "?");
    fflush(stderr);
}

gboolean on_load_failed(WebKitWebView* /*w*/, WebKitLoadEvent /*ev*/,
                        const char* uri, GError* error, gpointer /*ud*/) {
    fprintf(stderr, "[host] load_failed: uri=%s error=%s\n",
            uri ? uri : "(null)", error ? error->message : "(null)");
    fflush(stderr);
    return FALSE;
}

void on_web_process_terminated(WebKitWebView* /*w*/,
                               WebKitWebProcessTerminationReason reason,
                               gpointer /*ud*/) {
    const char* names[] = {"CRASHED", "EXCEEDED_MEMORY_LIMIT", "TERMINATED_BY_API"};
    fprintf(stderr, "[host] web_process_terminated: %s\n",
        (reason >= 0 && reason <= 2) ? names[reason] : "?");
    fflush(stderr);
}

void on_window_destroy(GtkWidget* /*w*/, gpointer /*ud*/) {
    fprintf(stderr, "[host] window destroy\n"); fflush(stderr);
    gtk_main_quit();
}

} // anonymous namespace

static void crash_handler(int sig) {
    fprintf(stderr, "[host] *** signal %d caught, backtrace:\n", sig);
    void* frames[64];
    int n = backtrace(frames, 64);
    backtrace_symbols_fd(frames, n, STDERR_FILENO);
    fflush(stderr);
    signal(sig, SIG_DFL);
    raise(sig);
}

static void install_crash_handlers() {
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = crash_handler;
    sa.sa_flags   = SA_RESTART;
    sigaction(SIGSEGV, &sa, nullptr);
    sigaction(SIGABRT, &sa, nullptr);
    sigaction(SIGBUS,  &sa, nullptr);
    sigaction(SIGFPE,  &sa, nullptr);
}

int main(int argc, char** argv) {
    install_crash_handlers();
    fprintf(stderr, "[host] starting argc=%d\n", argc);
    for (int i = 0; i < argc; ++i) fprintf(stderr, "[host]   argv[%d]=%s\n", i, argv[i]);
    fflush(stderr);

    gtk_init(&argc, &argv);
    fprintf(stderr, "[host] gtk_init OK display=%s\n",
            gdk_display_get_name(gdk_display_get_default()));
    const char* keys[] = {"JSC_useJIT", "JSC_useDFGJIT", "JSC_useFTLJIT",
                          "JSC_useBaselineJIT", "JSC_useLLInt",
                          "WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS",
                          "WEBKIT_DISABLE_DMABUF_RENDERER", nullptr};
    for (int i = 0; keys[i]; ++i) {
        const char* v = getenv(keys[i]);
        fprintf(stderr, "[host] env %s=%s\n", keys[i], v ? v : "(unset)");
    }
    fflush(stderr);

    const char* initial_url = "about:blank";
    int init_x = 0, init_y = 0, init_w = 800, init_h = 600;
    bool start_hidden = false;
    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--url") == 0 && i + 1 < argc)         initial_url = argv[++i];
        else if (strcmp(argv[i], "--api-key") == 0 && i + 1 < argc) g_apikey   = argv[++i];
        else if (strcmp(argv[i], "--x") == 0 && i + 1 < argc)       init_x = atoi(argv[++i]);
        else if (strcmp(argv[i], "--y") == 0 && i + 1 < argc)       init_y = atoi(argv[++i]);
        else if (strcmp(argv[i], "--w") == 0 && i + 1 < argc)       init_w = atoi(argv[++i]);
        else if (strcmp(argv[i], "--h") == 0 && i + 1 < argc)       init_h = atoi(argv[++i]);
        else if (strcmp(argv[i], "--hidden") == 0)                  start_hidden = true;
        // Legacy --xid (no-op now): we don't XEmbed anymore.
        else if (strcmp(argv[i], "--xid") == 0 && i + 1 < argc)     ++i;
    }

    g_window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_decorated(GTK_WINDOW(g_window), FALSE);
    gtk_window_set_skip_taskbar_hint(GTK_WINDOW(g_window), TRUE);
    gtk_window_set_skip_pager_hint(GTK_WINDOW(g_window), TRUE);
    gtk_window_set_type_hint(GTK_WINDOW(g_window), GDK_WINDOW_TYPE_HINT_UTILITY);
    gtk_window_set_default_size(GTK_WINDOW(g_window), init_w, init_h);
    gtk_window_move(GTK_WINDOW(g_window), init_x, init_y);
    gtk_widget_set_size_request(g_window, 1, 1);
    fprintf(stderr, "[host] window created %dx%d at (%d,%d)\n",
            init_w, init_h, init_x, init_y); fflush(stderr);

    GtkWidget* wv_widget = webkit_web_view_new();
    g_webview = WEBKIT_WEB_VIEW(wv_widget);
    g_signal_connect(g_webview, "load-changed", G_CALLBACK(on_load_changed), nullptr);
    g_signal_connect(g_webview, "load-failed",  G_CALLBACK(on_load_failed),  nullptr);
    g_signal_connect(g_webview, "web-process-terminated",
                     G_CALLBACK(on_web_process_terminated), nullptr);
    gtk_container_add(GTK_CONTAINER(g_window), wv_widget);
    fprintf(stderr, "[host] webview attached to window\n"); fflush(stderr);

    do_load(initial_url);

    g_signal_connect(g_window, "destroy", G_CALLBACK(on_window_destroy), nullptr);
    if (!start_hidden)
        gtk_widget_show_all(g_window);
    else
        gtk_widget_show(wv_widget);  // realize webview without mapping window

    GIOChannel* stdin_ch = g_io_channel_unix_new(STDIN_FILENO);
    g_io_channel_set_flags(stdin_ch, G_IO_FLAG_NONBLOCK, nullptr);
    g_io_add_watch(stdin_ch,
        static_cast<GIOCondition>(G_IO_IN | G_IO_HUP | G_IO_ERR),
        on_stdin, nullptr);
    g_io_channel_unref(stdin_ch);

    fprintf(stderr, "[host] entering gtk_main\n"); fflush(stderr);
    gtk_main();
    fprintf(stderr, "[host] gtk_main returned, exiting cleanly\n"); fflush(stderr);
    return 0;
}
