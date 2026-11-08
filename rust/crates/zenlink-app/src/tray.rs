//! Notification-area icon ("Close to the tray"), "Start with Windows" and
//! one window per user.

use std::sync::atomic::AtomicBool;

pub const BACKGROUND_ARG: &str = "--background";

/// What the tray asks the window to do.
#[allow(dead_code)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Event {
    /// Left click: show the window, or hide it when it is shown.
    Toggle,
    /// Menu "Open", or a second ZenLink.exe was started.
    Show,
    Quit,
}

/// True while the window is hidden in the tray (no work for it then).
pub static HIDDEN: AtomicBool = AtomicBool::new(false);

#[cfg(windows)]
mod win {
    use std::cell::{Cell, RefCell};
    use std::rc::Rc;
    use std::sync::atomic::Ordering::Relaxed;

    use windows::core::{w, PCWSTR};
    use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, POINT, WPARAM};
    use windows::Win32::System::LibraryLoader::GetModuleHandleW;
    use windows::Win32::System::Registry::{
        RegDeleteKeyValueW, RegGetValueW, RegSetKeyValueW, HKEY_CURRENT_USER, REG_SZ, RRF_RT_REG_SZ,
    };
    use windows::Win32::UI::Shell::{
        Shell_NotifyIconW, NIF_ICON, NIF_MESSAGE, NIF_TIP, NIM_ADD, NIM_DELETE, NOTIFYICONDATAW,
    };
    use windows::Win32::UI::WindowsAndMessaging::{
        AppendMenuW, CreatePopupMenu, CreateWindowExW, DefWindowProcW, DestroyMenu, FindWindowW,
        GetCursorPos, GetSystemMetrics, LoadIconW, LoadImageW, PostMessageW, RegisterClassW,
        RegisterWindowMessageW, SetForegroundWindow, TrackPopupMenu, HICON, IDI_APPLICATION,
        IMAGE_ICON, LR_DEFAULTCOLOR, MF_SEPARATOR, MF_STRING, SM_CXSMICON, SM_CYSMICON,
        TPM_BOTTOMALIGN, TPM_RETURNCMD, TPM_RIGHTBUTTON, WINDOW_EX_STYLE, WM_APP, WM_CONTEXTMENU,
        WM_LBUTTONUP, WM_NULL, WM_RBUTTONUP, WNDCLASSW, WS_OVERLAPPED,
    };

    use super::{Event, BACKGROUND_ARG};

    const CLASS: PCWSTR = w!("ZenLinkTrayV25");
    const RUN_KEY: PCWSTR = w!("Software\\Microsoft\\Windows\\CurrentVersion\\Run");
    const RUN_VALUE: PCWSTR = w!("ZenLink");
    const WM_TRAY: u32 = WM_APP + 0x51;
    const WM_SHOW_OTHER: u32 = WM_APP + 0x52;
    const ID_OPEN: usize = 1;
    const ID_QUIT: usize = 2;

    type Handler = Rc<dyn Fn(Event)>;

    thread_local! {
        static HWND_TRAY: Cell<Option<isize>> = const { Cell::new(None) };
        static HANDLER: RefCell<Option<Handler>> = const { RefCell::new(None) };
        static LABELS: RefCell<(String, String)> = RefCell::new(("Open ZenLink".into(), "Quit".into()));
        static ICON_ON: Cell<bool> = const { Cell::new(false) };
        static TASKBAR_CREATED: Cell<u32> = const { Cell::new(0) };
    }

    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    pub fn show_running_instance() -> bool {
        match unsafe { FindWindowW(CLASS, PCWSTR::null()) } {
            Ok(h) if !h.is_invalid() => {
                let _ = unsafe { PostMessageW(Some(h), WM_SHOW_OTHER, WPARAM(0), LPARAM(0)) };
                true
            }
            _ => false,
        }
    }

    pub fn install(handler: impl Fn(Event) + 'static) {
        HANDLER.with_borrow_mut(|h| *h = Some(Rc::new(handler)));
        unsafe {
            let Ok(module) = GetModuleHandleW(None) else {
                return;
            };
            let wc = WNDCLASSW {
                lpfnWndProc: Some(wndproc),
                hInstance: module.into(),
                lpszClassName: CLASS,
                ..Default::default()
            };
            let _ = RegisterClassW(&wc);
            let msg = RegisterWindowMessageW(w!("TaskbarCreated"));
            TASKBAR_CREATED.with(|c| c.set(msg));
            if let Ok(h) = CreateWindowExW(
                WINDOW_EX_STYLE(0),
                CLASS,
                CLASS,
                WS_OVERLAPPED,
                0,
                0,
                0,
                0,
                None,
                None,
                Some(module.into()),
                None,
            ) {
                HWND_TRAY.with(|c| c.set(Some(h.0 as isize)));
            }
        }
    }

    pub fn set_icon(on: bool, open: &str, quit: &str) {
        LABELS.with_borrow_mut(|l| *l = (open.into(), quit.into()));
        ICON_ON.with(|c| c.set(on));
        let Some(h) = HWND_TRAY.with(|c| c.get()) else {
            return;
        };
        if on {
            notify(NIM_ADD);
        } else {
            notify(NIM_DELETE);
        }
    }

    fn notify(op: windows::Win32::UI::Shell::NOTIFY_ICON_MESSAGE) -> bool {
        let Some(h) = HWND_TRAY.with(|c| c.get()) else {
            return false;
        };
        let icon = load_app_icon();
        let mut nid = NOTIFYICONDATAW {
            cbSize: std::mem::size_of::<NOTIFYICONDATAW>() as u32,
            hWnd: HWND(h as _),
            uID: 1,
            uFlags: NIF_MESSAGE | NIF_ICON | NIF_TIP,
            uCallbackMessage: WM_TRAY,
            hIcon: icon,
            ..Default::default()
        };
        let tip = wide("ZenLink");
        let n = tip.len().min(nid.szTip.len());
        nid.szTip[..n].copy_from_slice(&tip[..n]);
        unsafe { Shell_NotifyIconW(op, &nid).as_bool() }
    }

    fn load_app_icon() -> HICON {
        unsafe {
            if let Ok(module) = GetModuleHandleW(None) {
                let sm_cx = GetSystemMetrics(SM_CXSMICON);
                let sm_cy = GetSystemMetrics(SM_CYSMICON);
                if let Ok(img) = LoadImageW(
                    Some(module.into()),
                    PCWSTR(1 as _),
                    IMAGE_ICON,
                    sm_cx,
                    sm_cy,
                    LR_DEFAULTCOLOR,
                ) {
                    if !img.is_invalid() {
                        return HICON(img.0);
                    }
                }
            }
            LoadIconW(None, IDI_APPLICATION).unwrap_or(HICON::default())
        }
    }

    pub fn run_command(exe: &std::path::Path) -> String {
        format!("\"{}\" {}", exe.display(), BACKGROUND_ARG)
    }

    pub fn set_start_with_windows(on: bool, user_action: bool) {
        let Ok(exe) = std::env::current_exe() else {
            return;
        };
        let cmd = wide(&run_command(&exe));
        let val = wide("ZenLink");
        unsafe {
            if on {
                let _ = RegSetKeyValueW(
                    HKEY_CURRENT_USER,
                    RUN_KEY,
                    PCWSTR(val.as_ptr()),
                    REG_SZ.0,
                    Some(cmd.as_ptr() as _),
                    (cmd.len() * 2) as u32,
                );
            } else if user_action {
                let _ = RegDeleteKeyValueW(HKEY_CURRENT_USER, RUN_KEY, PCWSTR(val.as_ptr()));
            }
        }
    }

    unsafe extern "system" fn wndproc(h: HWND, msg: u32, wp: WPARAM, lp: LPARAM) -> LRESULT {
        let taskbar = TASKBAR_CREATED.with(|c| c.get());
        if taskbar != 0 && msg == taskbar {
            if ICON_ON.with(|c| c.get()) {
                notify(NIM_ADD);
            }
            return LRESULT(0);
        }
        match msg {
            WM_SHOW_OTHER => {
                dispatch(Event::Show);
                LRESULT(0)
            }
            WM_TRAY => {
                let event = (lp.0 as u32) & 0xffff;
                match event {
                    WM_LBUTTONUP => {
                        dispatch(Event::Toggle);
                    }
                    WM_RBUTTONUP | WM_CONTEXTMENU => {
                        show_menu(h);
                    }
                    _ => {}
                }
                LRESULT(0)
            }
            _ => DefWindowProcW(h, msg, wp, lp),
        }
    }

    fn dispatch(event: Event) {
        if let Some(cb) = HANDLER.with_borrow(|h| h.clone()) {
            cb(event);
        }
    }

    fn show_menu(h: HWND) {
        unsafe {
            let Ok(menu) = CreatePopupMenu() else { return };
            let (open, quit) = LABELS.with_borrow(|l| l.clone());
            let open_w = wide(&open);
            let quit_w = wide(&quit);
            let _ = AppendMenuW(menu, MF_STRING, ID_OPEN, PCWSTR(open_w.as_ptr()));
            let _ = AppendMenuW(menu, MF_SEPARATOR, 0, PCWSTR::null());
            let _ = AppendMenuW(menu, MF_STRING, ID_QUIT, PCWSTR(quit_w.as_ptr()));
            let mut pt = POINT::default();
            let _ = GetCursorPos(&mut pt);
            let _ = SetForegroundWindow(h);
            let cmd = TrackPopupMenu(
                menu,
                TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_RETURNCMD,
                pt.x,
                pt.y,
                0,
                h,
                None,
            );
            let _ = PostMessageW(Some(h), WM_NULL, WPARAM(0), LPARAM(0));
            let _ = DestroyMenu(menu);
            match cmd.0 as usize {
                ID_OPEN => dispatch(Event::Show),
                ID_QUIT => dispatch(Event::Quit),
                _ => {}
            }
        }
    }
}

#[cfg(windows)]
pub use win::*;

#[cfg(not(windows))]
pub fn show_running_instance() -> bool {
    false
}

#[cfg(not(windows))]
pub fn install(_handler: impl Fn(Event) + 'static) {}

#[cfg(not(windows))]
pub fn set_icon(_on: bool, _open: &str, _quit: &str) {}

#[cfg(not(windows))]
#[allow(dead_code)]
pub fn run_command(exe: &std::path::Path) -> String {
    format!("{} {}", exe.display(), BACKGROUND_ARG)
}

#[cfg(not(windows))]
pub fn set_start_with_windows(_on: bool, _user_action: bool) {}
