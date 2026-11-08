//! Detection of USB phones plugged in without ADB enabled.

#[cfg(windows)]
use windows::core::GUID;
#[cfg(windows)]
use windows::Win32::Devices::DeviceAndDriverInstallation::{
    SetupDiDestroyDeviceInfoList, SetupDiEnumDeviceInfo, SetupDiGetClassDevsW,
    SetupDiGetDeviceInstanceIdW, DIGCF_PRESENT, SP_DEVINFO_DATA,
};

#[cfg(windows)]
const WPD_CLASS: GUID = GUID::from_u128(0xeec5ad98_8080_425f_922a_dabf3de3f69a);

#[cfg(windows)]
pub fn phone_without_adb() -> bool {
    instance_ids().iter().any(|id| is_android_candidate(id))
}

#[cfg(not(windows))]
pub fn phone_without_adb() -> bool {
    false
}

#[cfg(windows)]
fn instance_ids() -> Vec<String> {
    let mut out = Vec::new();
    unsafe {
        let Ok(set) = SetupDiGetClassDevsW(Some(&WPD_CLASS), None, None, DIGCF_PRESENT) else {
            return out;
        };
        let mut i = 0;
        loop {
            let mut info = SP_DEVINFO_DATA {
                cbSize: std::mem::size_of::<SP_DEVINFO_DATA>() as u32,
                ..Default::default()
            };
            if SetupDiEnumDeviceInfo(set, i, &mut info).is_err() {
                break;
            }
            let mut buf = [0u16; 512];
            if SetupDiGetDeviceInstanceIdW(set, &info, Some(&mut buf), None).is_ok() {
                let n = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
                out.push(String::from_utf16_lossy(&buf[..n]));
            }
            i += 1;
        }
        let _ = SetupDiDestroyDeviceInfoList(set);
    }
    out
}

#[allow(dead_code)]
pub fn is_android_candidate(instance_id: &str) -> bool {
    let id = instance_id.to_ascii_uppercase();
    (id.starts_with("USB\\") || id.starts_with("USB/")) && !id.contains("VID_05AC")
}

#[cfg(test)]
mod tests {
    use super::is_android_candidate;

    #[test]
    fn picks_usb_portable_devices_but_not_apple() {
        assert!(is_android_candidate(r"USB\VID_0E8D&PID_2008\0123456789"));
        assert!(is_android_candidate(r"usb\vid_04e8&pid_6860\R58N"));
        assert!(!is_android_candidate(r"USB\VID_05AC&PID_12A8\00008110"));
        assert!(!is_android_candidate(r"SWD\WPDBUSENUM\{1234}"));
    }
}
