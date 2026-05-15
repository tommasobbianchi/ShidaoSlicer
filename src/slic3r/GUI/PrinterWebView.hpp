#ifndef slic3r_PrinterWebView_hpp_
#define slic3r_PrinterWebView_hpp_

#include <wx/panel.h>
#include <wx/string.h>
#include <wx/timer.h>

// The WebKit-subprocess isolator in PrinterWebView.cpp only runs on Linux
// (Windows uses Edge WebView2 directly, macOS uses WKWebView), so the
// m_child_pid member is never read or written outside the Linux branch.
// On Linux we use the real pid_t (signed int per POSIX); elsewhere we
// just declare it as int. Avoid a custom `typedef int pid_t;` on Windows
// because MSVC headers (and boost) may already declare it and the second
// declaration trips C2632 "'int' followed by 'int' is illegal".
#if defined(__linux__) || defined(__APPLE__) || defined(__unix__)
#include <sys/types.h>  // pid_t
#endif

class wxStaticText;
class wxButton;
class wxBoxSizer;

namespace Slic3r {
namespace GUI {

// PrinterWebView — process-isolated Fluidd/Mainsail host (overlay model).
//
// Why this exists: embedding Fluidd's Vue SPA inside Orca's main process
// exposes libjavascriptcoregtk's JSC runtime to Plater/TBB/OpenGL state
// and reliably SIGSEGVs on the first WebView load after a slice.
//
// Design: the actual WebKit widget runs in an external process
// (orcabelt-fluidd-host) as a borderless undecorated toplevel window.
// PrinterWebView is just a placeholder wxPanel that tracks its own
// screen geometry and tells the subprocess where to position itself
// (GEOM x y w h commands over the child's stdin). On Pause/HIDE the
// subprocess unmaps; on Resume/SHOW it re-maps and re-navigates. If the
// subprocess crashes, Orca stays alive — we re-spawn on next activation.
class PrinterWebView : public wxPanel {
public:
    PrinterWebView(wxWindow* parent);
    ~PrinterWebView() override;

    void load_url(wxString& url, wxString apikey = "");
    void reload();
    void update_mode();

    void Pause();
    void Resume();

    bool Show(bool show = true) override;

    void UpdateState();
    void OnClose(wxCloseEvent& evt);

private:
    void ensure_started();
    void stop_subprocess();
    bool send_command(const char* cmd);
    void reap_if_dead();
    void on_geom_timer(wxTimerEvent& evt);
    void push_geom(bool force);
    bool compute_screen_rect(int& x, int& y, int& w, int& h) const;
    void enter_fallback_mode();
    void exit_fallback_mode();
    void on_open_in_browser(wxCommandEvent& evt);
    void on_retry_embed(wxCommandEvent& evt);

    wxBoxSizer*   m_overlay_sizer = nullptr;
    wxStaticText* m_placeholder    = nullptr;
    wxStaticText* m_fallback_msg   = nullptr;
    wxStaticText* m_fallback_url   = nullptr;
    wxButton*     m_fallback_btn   = nullptr;
    wxButton*     m_retry_btn      = nullptr;
    wxTimer*      m_geom_timer     = nullptr;

#if defined(__linux__) || defined(__APPLE__) || defined(__unix__)
    pid_t m_child_pid = 0;
#else
    int   m_child_pid = 0;   // Windows: subprocess isolator unused, placeholder
#endif
    int   m_child_stdin_fd = -1;
    long long m_spawn_time_ms = 0;  // monotonic ms when subprocess started
    bool      m_fallback_mode = false;

    wxString m_active_url;
    wxString m_apikey;
    bool     m_paused = false;

    int m_last_x = INT32_MIN, m_last_y = INT32_MIN;
    int m_last_w = -1, m_last_h = -1;
};

} // namespace GUI
} // namespace Slic3r

#endif /* slic3r_PrinterWebView_hpp_ */
