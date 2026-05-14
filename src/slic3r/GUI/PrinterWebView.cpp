#include "PrinterWebView.hpp"

#include "I18N.hpp"
#include "slic3r/GUI/wxExtensions.hpp"
#include "slic3r/GUI/GUI_App.hpp"
#include "slic3r/GUI/MainFrame.hpp"
#include "libslic3r_version.h"

#include <wx/sizer.h>
#include <wx/string.h>
#include <wx/timer.h>
#include <wx/stattext.h>
#include <wx/button.h>
#include <wx/utils.h>
#include <chrono>

#include <boost/filesystem.hpp>
#include <boost/log/trivial.hpp>

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <csignal>
#include <string>
#include <vector>

// The WebKit-isolator subprocess fix (commit 3a116ffdec) targets the
// libjavascriptcoregtk SIGSEGV that's specific to wxWebView's GTK back-end
// (webkit2gtk-4.1). Windows wxWebView uses Edge WebView2 and macOS uses
// WKWebView; neither suffers from the JSC/TBB/GL clash. On those platforms
// we ship a no-op stub class so the GUI links — embedding the native widget
// would be a separate piece of work, not a CI blocker.
#if defined(__linux__)
#define ORCABELT_USE_WEBKIT_SUBPROCESS 1
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <unistd.h>
#include <fcntl.h>
#endif

namespace Slic3r {
namespace GUI {

namespace {

#if defined(ORCABELT_USE_WEBKIT_SUBPROCESS)
// Locate the orcabelt-fluidd-host binary. Precedence:
//   1. $ORCABELT_FLUIDD_HOST (absolute path override)
//   2. Sibling of /proc/self/exe (same bin/ as orca-slicer)
//   3. $PATH lookup at exec-time (returned as bare name "orcabelt-fluidd-host")
std::string locate_host_binary()
{
    if (const char* env = std::getenv("ORCABELT_FLUIDD_HOST"); env && *env) {
        return std::string(env);
    }
    char self[4096] = {0};
    ssize_t n = readlink("/proc/self/exe", self, sizeof(self) - 1);
    if (n > 0) {
        self[n] = '\0';
        boost::filesystem::path p(self);
        boost::filesystem::path candidate = p.parent_path() / "orcabelt-fluidd-host";
        boost::system::error_code ec;
        if (boost::filesystem::exists(candidate, ec))
            return candidate.string();
    }
    return "orcabelt-fluidd-host";
}
#endif // ORCABELT_USE_WEBKIT_SUBPROCESS

constexpr int GEOM_POLL_MS = 100;

// If the subprocess dies within this many ms of spawn, treat it as the
// "webkit JSC bug" failure mode and switch the placeholder to xdg-open
// fallback UI. A subprocess that survives past this threshold is
// considered viable, and a later death is treated as transient (we just
// respawn on next activation).
constexpr long long FALLBACK_THRESHOLD_MS = 5000;

long long now_ms() {
    using namespace std::chrono;
    return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

} // anonymous namespace

PrinterWebView::PrinterWebView(wxWindow* parent)
    : wxPanel(parent, wxID_ANY, wxDefaultPosition, wxDefaultSize)
{
    // Plain panel — no GtkSocket. The subprocess overlays its own toplevel
    // window over our screen rectangle. We track that rectangle via a
    // periodic timer (window can be moved by the user, layouts reflow,
    // etc.) and send GEOM commands.
    m_overlay_sizer = new wxBoxSizer(wxVERTICAL);
    SetSizer(m_overlay_sizer);

    // Two stacked UI states share the same area:
    //   - loading state: just "Loading printer view…" while the
    //     subprocess is being spawned / overlaying.
    //   - fallback state: a short explanation + "Open in browser" button.
    //     Activated when the subprocess crashes within 5 s of spawn
    //     (= the webkit2gtk-4.1 JSC bug — see feedback memory).
    m_placeholder = new wxStaticText(this, wxID_ANY,
        _L("Loading printer view…"),
        wxDefaultPosition, wxDefaultSize, wxALIGN_CENTRE_HORIZONTAL);

    m_fallback_msg = new wxStaticText(this, wxID_ANY,
        _L("The embedded Klipper view crashed (known WebKit2GTK / JSC bug).\n"
           "Use the system browser instead — same UI, full stability."),
        wxDefaultPosition, wxDefaultSize, wxALIGN_CENTRE_HORIZONTAL);
    m_fallback_url = new wxStaticText(this, wxID_ANY, "",
        wxDefaultPosition, wxDefaultSize, wxALIGN_CENTRE_HORIZONTAL);
    m_fallback_btn = new wxButton(this, wxID_ANY, _L("Open in browser"));
    m_retry_btn    = new wxButton(this, wxID_ANY, _L("Retry embed"));
    m_fallback_btn->Bind(wxEVT_BUTTON, &PrinterWebView::on_open_in_browser, this);
    m_retry_btn   ->Bind(wxEVT_BUTTON, &PrinterWebView::on_retry_embed,    this);

    m_overlay_sizer->AddStretchSpacer();
    m_overlay_sizer->Add(m_placeholder,  0, wxALIGN_CENTRE_HORIZONTAL | wxALL, 16);
    m_overlay_sizer->Add(m_fallback_msg, 0, wxALIGN_CENTRE_HORIZONTAL | wxALL, 8);
    m_overlay_sizer->Add(m_fallback_url, 0, wxALIGN_CENTRE_HORIZONTAL | wxALL, 4);
    m_overlay_sizer->Add(m_fallback_btn, 0, wxALIGN_CENTRE_HORIZONTAL | wxALL, 8);
    m_overlay_sizer->Add(m_retry_btn,    0, wxALIGN_CENTRE_HORIZONTAL | wxALL, 4);
    m_overlay_sizer->AddStretchSpacer();

    // Start in loading state.
    m_fallback_msg->Hide();
    m_fallback_url->Hide();
    m_fallback_btn->Hide();
    m_retry_btn   ->Hide();

    m_geom_timer = new wxTimer(this);
    Bind(wxEVT_TIMER, &PrinterWebView::on_geom_timer, this, m_geom_timer->GetId());

    Bind(wxEVT_CLOSE_WINDOW, &PrinterWebView::OnClose, this);
}

PrinterWebView::~PrinterWebView()
{
    BOOST_LOG_TRIVIAL(info) << "PrinterWebView dtor: stopping subprocess";
    SetEvtHandlerEnabled(false);
    if (m_geom_timer) { m_geom_timer->Stop(); delete m_geom_timer; m_geom_timer = nullptr; }
    stop_subprocess();
}

void PrinterWebView::load_url(wxString& url, wxString apikey)
{
    m_apikey     = apikey;
    m_active_url = url;
    BOOST_LOG_TRIVIAL(info) << "PrinterWebView::load_url url=" << url;

    if (m_paused) return;  // Resume() will navigate when tab returns

    reap_if_dead();
    if (m_child_pid <= 0) {
        ensure_started();
        return;  // spawned with URL via argv
    }

    if (!m_apikey.IsEmpty()) {
        std::string cmd = "APIKEY " + std::string(m_apikey.utf8_str()) + "\n";
        send_command(cmd.c_str());
    }
    std::string cmd = "URL " + std::string(m_active_url.utf8_str()) + "\n";
    send_command(cmd.c_str());
}

void PrinterWebView::Pause()
{
    if (m_paused) return;
    m_paused = true;
    if (m_geom_timer) m_geom_timer->Stop();
    if (m_child_pid > 0) {
        send_command("HIDE\n");
        send_command("BLANK\n");
    }
}

void PrinterWebView::Resume()
{
    m_paused = false;
    reap_if_dead();
    if (m_child_pid <= 0) {
        ensure_started();
    } else {
        push_geom(/*force=*/true);
        send_command("SHOW\n");
        if (!m_active_url.IsEmpty()) {
            std::string cmd = "URL " + std::string(m_active_url.utf8_str()) + "\n";
            send_command(cmd.c_str());
        }
    }
    if (m_geom_timer && IsShown())
        m_geom_timer->Start(GEOM_POLL_MS);
}

bool PrinterWebView::Show(bool show)
{
    bool ret = wxPanel::Show(show);
    if (show) {
        reap_if_dead();
        if (m_child_pid <= 0 && !m_paused)
            ensure_started();
        else if (m_child_pid > 0 && !m_paused) {
            push_geom(/*force=*/true);
            send_command("SHOW\n");
        }
        if (m_geom_timer && !m_paused)
            m_geom_timer->Start(GEOM_POLL_MS);
    } else {
        if (m_geom_timer) m_geom_timer->Stop();
        if (m_child_pid > 0)
            send_command("HIDE\n");
    }
    return ret;
}

void PrinterWebView::reload()
{
    reap_if_dead();
    if (m_child_pid > 0)
        send_command("RELOAD\n");
    else
        ensure_started();
}

void PrinterWebView::update_mode() { /* DevTools toggle not forwarded */ }
void PrinterWebView::UpdateState() { /* legacy no-op */ }
void PrinterWebView::OnClose(wxCloseEvent& /*evt*/) { this->Hide(); }

void PrinterWebView::on_geom_timer(wxTimerEvent& /*evt*/)
{
    reap_if_dead();
    if (m_child_pid <= 0) {
        if (m_geom_timer) m_geom_timer->Stop();
        return;
    }
    push_geom(/*force=*/false);
}

bool PrinterWebView::compute_screen_rect(int& x, int& y, int& w, int& h) const
{
    wxSize sz = GetSize();
    if (sz.GetWidth() <= 0 || sz.GetHeight() <= 0) return false;
    wxPoint origin = ClientToScreen(wxPoint(0, 0));
    x = origin.x; y = origin.y;
    w = sz.GetWidth(); h = sz.GetHeight();
    return true;
}

void PrinterWebView::push_geom(bool force)
{
    int x = 0, y = 0, w = 0, h = 0;
    if (!compute_screen_rect(x, y, w, h)) return;
    if (!force && x == m_last_x && y == m_last_y && w == m_last_w && h == m_last_h)
        return;
    m_last_x = x; m_last_y = y; m_last_w = w; m_last_h = h;
    char buf[64];
    int n = snprintf(buf, sizeof(buf), "GEOM %d %d %d %d\n", x, y, w, h);
    if (n > 0 && n < (int)sizeof(buf))
        send_command(buf);
}

void PrinterWebView::ensure_started()
{
#if !defined(ORCABELT_USE_WEBKIT_SUBPROCESS)
    // No-op stub for Windows/macOS — wxWebView uses native back-ends there
    // (Edge WebView2 / WKWebView) which don't suffer from the webkit2gtk
    // JSC SIGSEGV. The embedded Klipper UI path on those platforms is a
    // separate piece of work; for now the panel stays at the loading
    // placeholder.
    return;
#else
    if (m_fallback_mode) {
        // Already given up on the embed for this URL — user must hit
        // "Retry embed" to re-attempt. Avoids a crash → respawn → crash
        // tight loop when the webkit JSC bug fires every spawn.
        return;
    }
    if (m_child_pid > 0) return;
    if (m_active_url.IsEmpty()) {
        BOOST_LOG_TRIVIAL(info) << "PrinterWebView::ensure_started: no URL yet, deferring";
        return;
    }
    if (!IsShownOnScreen()) {
        BOOST_LOG_TRIVIAL(info) << "PrinterWebView::ensure_started: not shown on screen, deferring";
        return;
    }

    int x = 0, y = 0, w = 800, h = 600;
    compute_screen_rect(x, y, w, h);

    int pipefd[2] = {-1, -1};
    if (pipe(pipefd) != 0) {
        BOOST_LOG_TRIVIAL(error) << "PrinterWebView: pipe() failed: " << strerror(errno);
        return;
    }

    const char* child_log_path = "/tmp/orcabelt-fluidd-host.log";
    int child_log_fd = open(child_log_path,
                            O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);

    std::string host_bin   = locate_host_binary();
    std::string url_str    = std::string(m_active_url.utf8_str());
    std::string apikey_str = std::string(m_apikey.utf8_str());
    char xs[16], ys[16], ws[16], hs[16];
    snprintf(xs, sizeof(xs), "%d", x);
    snprintf(ys, sizeof(ys), "%d", y);
    snprintf(ws, sizeof(ws), "%d", w);
    snprintf(hs, sizeof(hs), "%d", h);

    pid_t pid = fork();
    if (pid < 0) {
        BOOST_LOG_TRIVIAL(error) << "PrinterWebView: fork() failed: " << strerror(errno);
        close(pipefd[0]); close(pipefd[1]);
        if (child_log_fd >= 0) close(child_log_fd);
        return;
    }
    if (pid == 0) {
        if (pipefd[0] != STDIN_FILENO) {
            dup2(pipefd[0], STDIN_FILENO);
            close(pipefd[0]);
        }
        close(pipefd[1]);
        if (child_log_fd >= 0) {
            dup2(child_log_fd, STDOUT_FILENO);
            dup2(child_log_fd, STDERR_FILENO);
        }
        // Detach from Orca's process group / session.
        setsid();
        // Reset signal mask — Orca may have signals masked; inherited
        // through exec. JSC GC sometimes uses SIGSEGV-on-mprotect for
        // soft heap probes, and a masked SIGSEGV would manifest as a
        // hard crash.
        sigset_t empty_mask;
        sigemptyset(&empty_mask);
        sigprocmask(SIG_SETMASK, &empty_mask, nullptr);
        // Reset stack rlimit to a sane default (Orca bumps it; large
        // stacks make JSC's conservative GC scan more memory and
        // statistically hit more spurious pointer-like values that
        // trigger the +0x191f9fc SIGSEGV).
        struct rlimit rl_stack{8 * 1024 * 1024, RLIM_INFINITY};
        setrlimit(RLIMIT_STACK, &rl_stack);
        // Close every other inherited FD (X connection, dbus, tmp files,
        // etc.) — they can poison WebKit's WebProcess sandbox setup.
        for (int fd = 3; fd < 4096; ++fd) close(fd);
        // Disable WebKit sandbox in child (bwrap fails silently in nested
        // forks); also avoid DMA-BUF compositor races with parent's GL.
        setenv("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS", "1", 1);
        setenv("WEBKIT_DISABLE_DMABUF_RENDERER", "1", 0);
        // Disable every JSC JIT tier — webkit2gtk-4.1 2.50.4 on Ubuntu
        // 24.04 deterministically SIGSEGVs in JSC ~2s after Fluidd loads
        // (libjavascriptcoregtk +0x191f9fc in conservative GC stack walk).
        // Forcing LLInt-only interpreter mode eliminates the bug entirely;
        // Fluidd is a dashboard SPA so the interpreter is fast enough.
        // JSC reads "true"/"false", NOT "1"/"0", for boolean options.
        setenv("JSC_useJIT",          "false", 1);
        setenv("JSC_useDFGJIT",       "false", 1);
        setenv("JSC_useFTLJIT",       "false", 1);
        setenv("JSC_useBaselineJIT",  "false", 1);
        setenv("JSC_useLLInt",        "true",  1);

        std::vector<const char*> argv;
        argv.push_back(host_bin.c_str());
        argv.push_back("--x"); argv.push_back(xs);
        argv.push_back("--y"); argv.push_back(ys);
        argv.push_back("--w"); argv.push_back(ws);
        argv.push_back("--h"); argv.push_back(hs);
        argv.push_back("--url"); argv.push_back(url_str.c_str());
        if (!apikey_str.empty()) {
            argv.push_back("--api-key"); argv.push_back(apikey_str.c_str());
        }
        argv.push_back(nullptr);
        execvp(host_bin.c_str(), const_cast<char* const*>(argv.data()));
        fprintf(stderr, "orcabelt: execvp(%s) failed: %s\n",
                host_bin.c_str(), strerror(errno));
        _exit(127);
    }
    close(pipefd[0]);
    if (child_log_fd >= 0) close(child_log_fd);
    int flags = fcntl(pipefd[1], F_GETFL, 0);
    if (flags >= 0) fcntl(pipefd[1], F_SETFL, flags | O_NONBLOCK);

    m_child_pid      = pid;
    m_child_stdin_fd = pipefd[1];
    m_spawn_time_ms  = now_ms();
    m_last_x = x; m_last_y = y; m_last_w = w; m_last_h = h;
    BOOST_LOG_TRIVIAL(warning)
        << "PrinterWebView: spawned orcabelt-fluidd-host pid=" << pid
        << " geom=" << x << "," << y << " " << w << "x" << h
        << " url=" << url_str
        << " bin=" << host_bin
        << " (stderr→" << child_log_path << ")";

    if (m_geom_timer && IsShown())
        m_geom_timer->Start(GEOM_POLL_MS);
#endif // ORCABELT_USE_WEBKIT_SUBPROCESS
}

bool PrinterWebView::send_command(const char* cmd)
{
#if !defined(ORCABELT_USE_WEBKIT_SUBPROCESS)
    (void)cmd;
    return false;
#else
    if (m_child_pid <= 0 || m_child_stdin_fd < 0) return false;
    size_t len = strlen(cmd);
    ssize_t w = write(m_child_stdin_fd, cmd, len);
    if (w < 0) {
        if (errno == EPIPE) {
            BOOST_LOG_TRIVIAL(warning) << "PrinterWebView: subprocess pipe broken, marking dead";
            close(m_child_stdin_fd); m_child_stdin_fd = -1;
            m_child_pid = 0;
            reap_if_dead();
        } else if (errno == EAGAIN || errno == EWOULDBLOCK) {
            BOOST_LOG_TRIVIAL(warning) << "PrinterWebView: pipe full, dropping command";
        } else {
            BOOST_LOG_TRIVIAL(warning) << "PrinterWebView: write failed: " << strerror(errno);
        }
        return false;
    }
    return true;
#endif // ORCABELT_USE_WEBKIT_SUBPROCESS
}

void PrinterWebView::reap_if_dead()
{
#if !defined(ORCABELT_USE_WEBKIT_SUBPROCESS)
    return;
#else
    if (m_child_pid <= 0) return;
    int status = 0;
    pid_t r = waitpid(m_child_pid, &status, WNOHANG);
    if (r == m_child_pid) {
        long long alive_ms = now_ms() - m_spawn_time_ms;
        BOOST_LOG_TRIVIAL(warning)
            << "PrinterWebView: subprocess exited, status=" << status
            << " (alive " << alive_ms << " ms)";
        m_child_pid = 0;
        if (m_child_stdin_fd >= 0) { close(m_child_stdin_fd); m_child_stdin_fd = -1; }
        // If the subprocess died within FALLBACK_THRESHOLD_MS of spawn
        // we treat it as the deterministic webkit2gtk JSC bug and switch
        // to the xdg-open fallback UI. Beyond the threshold we assume
        // it's a transient issue (user closed it, network blip, etc.)
        // and just leave the placeholder loading state — next Resume()
        // or Show() will respawn.
        if (!m_fallback_mode && m_spawn_time_ms > 0
            && alive_ms < FALLBACK_THRESHOLD_MS) {
            BOOST_LOG_TRIVIAL(warning)
                << "PrinterWebView: subprocess died too fast — switching to xdg-open fallback";
            enter_fallback_mode();
        }
    }
#endif // ORCABELT_USE_WEBKIT_SUBPROCESS
}

void PrinterWebView::enter_fallback_mode()
{
    if (m_fallback_mode) return;
    m_fallback_mode = true;
    if (m_geom_timer) m_geom_timer->Stop();
    if (m_fallback_url && !m_active_url.IsEmpty())
        m_fallback_url->SetLabel(m_active_url);
    if (m_placeholder)  m_placeholder->Hide();
    if (m_fallback_msg) m_fallback_msg->Show();
    if (m_fallback_url) m_fallback_url->Show();
    if (m_fallback_btn) m_fallback_btn->Show();
    if (m_retry_btn)    m_retry_btn->Show();
    if (m_overlay_sizer) m_overlay_sizer->Layout();
}

void PrinterWebView::exit_fallback_mode()
{
    if (!m_fallback_mode) return;
    m_fallback_mode = false;
    if (m_placeholder)  m_placeholder->Show();
    if (m_fallback_msg) m_fallback_msg->Hide();
    if (m_fallback_url) m_fallback_url->Hide();
    if (m_fallback_btn) m_fallback_btn->Hide();
    if (m_retry_btn)    m_retry_btn->Hide();
    if (m_overlay_sizer) m_overlay_sizer->Layout();
}

void PrinterWebView::on_open_in_browser(wxCommandEvent& /*evt*/)
{
    if (m_active_url.IsEmpty()) return;
    BOOST_LOG_TRIVIAL(info) << "PrinterWebView: launching system browser at " << m_active_url;
    wxLaunchDefaultBrowser(m_active_url);
}

void PrinterWebView::on_retry_embed(wxCommandEvent& /*evt*/)
{
    BOOST_LOG_TRIVIAL(info) << "PrinterWebView: user requested retry embed";
    exit_fallback_mode();
    m_spawn_time_ms = 0;  // reset so next death is freshly evaluated
    if (!m_paused && IsShownOnScreen())
        ensure_started();
}

void PrinterWebView::stop_subprocess()
{
#if !defined(ORCABELT_USE_WEBKIT_SUBPROCESS)
    return;
#else
    if (m_child_pid <= 0) {
        if (m_child_stdin_fd >= 0) { close(m_child_stdin_fd); m_child_stdin_fd = -1; }
        return;
    }
    if (m_child_stdin_fd >= 0) {
        write(m_child_stdin_fd, "QUIT\n", 5);
        close(m_child_stdin_fd);
        m_child_stdin_fd = -1;
    }
    for (int i = 0; i < 20; ++i) {
        int status = 0;
        pid_t r = waitpid(m_child_pid, &status, WNOHANG);
        if (r == m_child_pid) { m_child_pid = 0; return; }
        usleep(10 * 1000);
    }
    kill(m_child_pid, SIGTERM);
    for (int i = 0; i < 20; ++i) {
        int status = 0;
        pid_t r = waitpid(m_child_pid, &status, WNOHANG);
        if (r == m_child_pid) { m_child_pid = 0; return; }
        usleep(10 * 1000);
    }
    kill(m_child_pid, SIGKILL);
    int status = 0;
    waitpid(m_child_pid, &status, 0);
    m_child_pid = 0;
#endif // ORCABELT_USE_WEBKIT_SUBPROCESS
}

} // namespace GUI
} // namespace Slic3r
