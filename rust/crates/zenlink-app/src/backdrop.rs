//! Real Windows translucency behind the window (not a painted imitation).
//! On Linux, this is a no-op as compositor handles transparency/blur.

#[cfg(windows)]
use windows::core::BOOL;
#[cfg(windows)]
use windows::Win32::Foundation::HWND;
#[cfg(windows)]
use windows::Win32::Graphics::Dwm::{
    DwmExtendFrameIntoClientArea, DwmSetWindowAttribute, DWMSBT_NONE, DWMWA_SYSTEMBACKDROP_TYPE,
    DWMWA_USE_IMMERSIVE_DARK_MODE, DWM_SYSTEMBACKDROP_TYPE,
};
#[cfg(windows)]
use windows::Win32::UI::Controls::MARGINS;

use crate::PlatformHwnd;

pub type WindowHandle = PlatformHwnd;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Backdrop {
    /// No translucency: solid background (glass intensity 0%).
    None,
    /// Blur-behind that stays on while inactive.
    Accent,
}

#[cfg(windows)]
#[repr(C)]
struct AccentPolicy {
    state: u32,
    flags: u32,
    gradient: u32, // AABBGGRR tint
    animation: u32,
}

#[cfg(windows)]
#[repr(C)]
struct CompositionData {
    attribute: u32,
    data: *mut core::ffi::c_void,
    size: usize,
}

#[cfg(windows)]
type SetWca = unsafe extern "system" fn(HWND, *mut CompositionData) -> BOOL;

#[cfg(windows)]
fn set_accent(hwnd: HWND, state: u32, tint: u32) -> bool {
    use windows::core::s;
    use windows::Win32::System::LibraryLoader::{GetModuleHandleA, GetProcAddress};
    unsafe {
        let Ok(user32) = GetModuleHandleA(s!("user32.dll")) else {
            return false;
        };
        let Some(proc_) = GetProcAddress(user32, s!("SetWindowCompositionAttribute")) else {
            return false;
        };
        let f: SetWca = core::mem::transmute(proc_);
        let mut policy = AccentPolicy {
            state,
            flags: 2,
            gradient: tint,
            animation: 0,
        };
        let mut data = CompositionData {
            attribute: 19, // WCA_ACCENT_POLICY
            data: &mut policy as *mut _ as *mut _,
            size: core::mem::size_of::<AccentPolicy>(),
        };
        f(hwnd, &mut data).as_bool()
    }
}

#[cfg(windows)]
pub fn dark_title_bar(hwnd: WindowHandle, dark: bool) {
    let d = BOOL::from(dark);
    unsafe {
        let _ = DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, &d as *const _ as _, 4);
    }
}

#[cfg(windows)]
pub fn apply(hwnd: WindowHandle, mode: Backdrop, dark: bool, thick: f32, round: bool) -> bool {
    unsafe {
        let d = BOOL::from(dark);
        let _ = DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, &d as *const _ as _, 4);
        let corner: u32 = if round { 2 } else { 1 };
        let _ = DwmSetWindowAttribute(
            hwnd,
            windows::Win32::Graphics::Dwm::DWMWA_WINDOW_CORNER_PREFERENCE,
            &corner as *const _ as _,
            4,
        );
        let margins = MARGINS::default();
        let _ = DwmExtendFrameIntoClientArea(hwnd, &margins);
        let set_backdrop = |t: DWM_SYSTEMBACKDROP_TYPE| {
            DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, &t as *const _ as _, 4).is_ok()
        };
        match mode {
            Backdrop::None => {
                set_accent(hwnd, 0, 0);
                set_backdrop(DWMSBT_NONE)
            }
            Backdrop::Accent if thick < 0.03 => {
                set_backdrop(DWMSBT_NONE);
                set_accent(hwnd, 0, 0)
            }
            Backdrop::Accent => {
                set_backdrop(DWMSBT_NONE);
                let glass = 1.0 - thick;
                let a = (((1.0 - glass.clamp(0.0, 1.0)) * 0xB0 as f32) as u32).max(1);
                let g = glass.clamp(0.0, 1.0);
                let mix = |c: u32, n: u32| -> u32 {
                    let ch = |sh: u32| {
                        let (a, b) = (((c >> sh) & 0xff) as f32, ((n >> sh) & 0xff) as f32);
                        ((a + (b - a) * g) as u32) << sh
                    };
                    ch(0) | ch(8) | ch(16)
                };
                let rgb = mix(
                    if dark { 0x1e_1c_1c } else { 0xf7_f2_f2 },
                    if dark { 0x2c_2c_2c } else { 0xa8_a8_a8 },
                );
                set_accent(hwnd, 4, (a << 24) | rgb)
            }
        }
    }
}

#[cfg(not(windows))]
pub fn dark_title_bar(_hwnd: WindowHandle, _dark: bool) {}

#[cfg(not(windows))]
pub fn apply(_hwnd: WindowHandle, _mode: Backdrop, _dark: bool, _thick: f32, _round: bool) -> bool {
    false
}
