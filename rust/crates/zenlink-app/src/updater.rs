//! In-app update (v2.5.1).
//! Windows: HTTPS through WinHTTP, SHA-256 through BCrypt.
//! Linux: Package manager / source checkout.

use std::path::{Path, PathBuf};

use zenlink_core::update::{Asset, Channel, Offer, Release, Version};

#[allow(dead_code)]
pub const REPLACE_ARG: &str = "--replace-old=";

#[allow(dead_code)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Installed,
    Portable,
    Source,
    Store,
}

#[allow(dead_code)]
pub const STORE_PRODUCT_ID: &str = "9N67KCFZSB1T";

#[cfg(windows)]
mod win {
    use std::ffi::c_void;
    use std::io::Write;
    use std::path::{Path, PathBuf};
    use std::time::{Duration, Instant};

    use windows::core::{HSTRING, PCWSTR};
    use windows::Win32::Networking::WinHttp::*;
    use windows::Win32::Security::Cryptography::*;
    use zenlink_core::update::{self, Asset, Channel, Offer, Release, Version};

    use super::{Kind, STORE_PRODUCT_ID, REPLACE_ARG};

    pub fn is_store() -> bool {
        use std::sync::OnceLock;
        static STORE: OnceLock<bool> = OnceLock::new();
        *STORE.get_or_init(|| {
            let mut len = 0u32;
            let r = unsafe {
                windows::Win32::Storage::Packaging::Appx::GetCurrentPackageFullName(&mut len, None)
            };
            r.0 == 122
        })
    }

    pub fn open_store_page() {
        let _ = std::process::Command::new("explorer.exe")
            .arg(format!("ms-windows-store://pdp/?productid={STORE_PRODUCT_ID}"))
            .spawn();
    }

    pub fn visible_log_dir() -> PathBuf {
        let dir = zenlink_core::log_dir();
        if !is_store() || dir.exists() {
            return dir;
        }
        let (Some(local), Some(pfn)) = (std::env::var_os("LOCALAPPDATA"), package_family_name()) else {
            return dir;
        };
        let local = PathBuf::from(local);
        match dir.strip_prefix(&local) {
            Ok(rest) => local
                .join("Packages")
                .join(pfn)
                .join("LocalCache")
                .join("Local")
                .join(rest),
            Err(_) => dir,
        }
    }

    fn package_family_name() -> Option<String> {
        use windows::Win32::Storage::Packaging::Appx::GetCurrentPackageFamilyName;
        let mut len = 0u32;
        unsafe {
            let _ = GetCurrentPackageFamilyName(&mut len, None);
            if len == 0 {
                return None;
            }
            let mut buf = vec![0u16; len as usize];
            if GetCurrentPackageFamilyName(&mut len, Some(windows::core::PWSTR(buf.as_mut_ptr()))).0 != 0 {
                return None;
            }
            Some(String::from_utf16_lossy(&buf[..len.saturating_sub(1) as usize]))
        }
    }

    struct Handle(*mut c_void);
    impl Drop for Handle {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe {
                    let _ = WinHttpCloseHandle(self.0);
                }
            }
        }
    }

    fn last_error(what: &str) -> String {
        format!("{what}: {}", windows::core::Error::from_thread())
    }

    struct Response {
        _session: Handle,
        _connect: Handle,
        request: Handle,
        pub length: Option<u64>,
    }

    impl Response {
        fn read(&mut self, buf: &mut [u8]) -> Result<usize, String> {
            let mut n = 0u32;
            unsafe {
                WinHttpReadData(
                    self.request.0,
                    buf.as_mut_ptr().cast(),
                    buf.len() as u32,
                    &mut n,
                )
            }
            .map_err(|e| format!("read: {e}"))?;
            Ok(n as usize)
        }
    }

    fn split_url(url: &str) -> Option<(&str, &str)> {
        let rest = url.strip_prefix("https://")?;
        let (host, path) = match rest.find('/') {
            Some(i) => (&rest[..i], &rest[i..]),
            None => (rest, "/"),
        };
        (!host.is_empty() && !host.contains(['@', ':', ' ', '?', '#'])).then_some((host, path))
    }

    fn get(url: &str, accept: &str) -> Result<Response, String> {
        let (host, path) = split_url(url).ok_or("not an https URL")?;
        let agent = HSTRING::from(format!("ZenLink-Updater/{}", env!("CARGO_PKG_VERSION")));
        unsafe {
            let session = Handle(WinHttpOpen(
                &agent,
                WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
                PCWSTR::null(),
                PCWSTR::null(),
                0,
            ));
            if session.0.is_null() {
                return Err(last_error("WinHttpOpen"));
            }
            let protocols = (WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2 | WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_3).to_le_bytes();
            let _ = WinHttpSetOption(Some(session.0), WINHTTP_OPTION_SECURE_PROTOCOLS, Some(&protocols));
            let _ = WinHttpSetTimeouts(session.0, 15_000, 15_000, 15_000, 30_000);
            let connect = Handle(WinHttpConnect(session.0, &HSTRING::from(host), INTERNET_DEFAULT_HTTPS_PORT, 0));
            if connect.0.is_null() {
                return Err(last_error("WinHttpConnect"));
            }
            let request = Handle(WinHttpOpenRequest(
                connect.0,
                &HSTRING::from("GET"),
                &HSTRING::from(path),
                PCWSTR::null(),
                PCWSTR::null(),
                std::ptr::null(),
                WINHTTP_FLAG_SECURE,
            ));
            if request.0.is_null() {
                return Err(last_error("WinHttpOpenRequest"));
            }
            let headers: Vec<u16> = format!("Accept: {accept}\r\n").encode_utf16().collect();
            WinHttpSendRequest(request.0, Some(&headers), None, 0, 0, 0).map_err(|e| format!("send: {e}"))?;
            WinHttpReceiveResponse(request.0, std::ptr::null_mut()).map_err(|e| format!("receive: {e}"))?;
            let number = |info: u32| -> Option<u64> {
                let mut v = 0u32;
                let mut len = 4u32;
                WinHttpQueryHeaders(
                    request.0,
                    info | WINHTTP_QUERY_FLAG_NUMBER,
                    PCWSTR::null(),
                    Some((&mut v as *mut u32).cast()),
                    &mut len,
                    std::ptr::null_mut(),
                )
                .ok()
                .map(|_| v as u64)
            };
            let status = number(WINHTTP_QUERY_STATUS_CODE).unwrap_or(0);
            if !(200..300).contains(&status) {
                return Err(format!("HTTP {status}"));
            }
            let length = number(WINHTTP_QUERY_CONTENT_LENGTH);
            Ok(Response {
                _session: session,
                _connect: connect,
                request,
                length,
            })
        }
    }

    fn feed() -> Result<serde_json::Value, String> {
        let src = std::env::var("ZL_UPDATE_FEED").unwrap_or_else(|_| update::RELEASES_URL.to_string());
        let bytes = if src.starts_with("https://") {
            let mut r = get(&src, "application/vnd.github+json")?;
            let mut out = Vec::new();
            let mut buf = vec![0u8; 64 * 1024];
            loop {
                let n = r.read(&mut buf)?;
                if n == 0 {
                    break;
                }
                out.extend_from_slice(&buf[..n]);
                if out.len() > 8 << 20 {
                    return Err("feed too large".into());
                }
            }
            out
        } else {
            std::fs::read(&src).map_err(|e| format!("{src}: {e}"))?
        };
        serde_json::from_slice(&bytes).map_err(|e| format!("feed: {e}"))
    }

    pub fn check(channel: Channel) -> Result<Offer, String> {
        Ok(update::pick(&feed()?, &super::current_version(), channel))
    }

    struct Sha256(BCRYPT_HASH_HANDLE);
    impl Sha256 {
        fn new() -> Result<Self, String> {
            let mut h = BCRYPT_HASH_HANDLE::default();
            let st = unsafe { BCryptCreateHash(BCRYPT_SHA256_ALG_HANDLE, &mut h, None, None, 0) };
            st.ok().map_err(|e| format!("sha256: {e}"))?;
            Ok(Self(h))
        }
        fn update(&mut self, data: &[u8]) -> Result<(), String> {
            unsafe { BCryptHashData(self.0, data, 0) }.ok().map_err(|e| format!("sha256: {e}"))
        }
        fn hex(self) -> Result<String, String> {
            let mut out = [0u8; 32];
            unsafe { BCryptFinishHash(self.0, &mut out, 0) }.ok().map_err(|e| format!("sha256: {e}"))?;
            Ok(out.iter().map(|b| format!("{b:02x}")).collect())
        }
    }
    impl Drop for Sha256 {
        fn drop(&mut self) {
            unsafe {
                let _ = BCryptDestroyHash(self.0);
            }
        }
    }

    pub fn sha256_hex(data: &[u8]) -> Result<String, String> {
        let mut h = Sha256::new()?;
        h.update(data)?;
        h.hex()
    }

    pub fn download(a: &Asset, dest: &Path, progress: &dyn Fn(u64, u64)) -> Result<(), String> {
        let part = dest.with_extension("part");
        let result = (|| {
            let mut r = get(&a.url, "application/octet-stream")?;
            if r.length.is_some_and(|l| l != a.size) {
                return Err(format!("size {} instead of {}", r.length.unwrap_or(0), a.size));
            }
            let mut f = std::fs::File::create(&part).map_err(|e| format!("{}: {e}", part.display()))?;
            let mut hash = Sha256::new()?;
            let mut buf = vec![0u8; 256 * 1024];
            let mut done = 0u64;
            let mut last = Instant::now();
            loop {
                let n = r.read(&mut buf)?;
                if n == 0 {
                    break;
                }
                done += n as u64;
                if done > a.size {
                    return Err("larger than announced".into());
                }
                hash.update(&buf[..n])?;
                f.write_all(&buf[..n]).map_err(|e| format!("write: {e}"))?;
                if last.elapsed() >= Duration::from_millis(100) {
                    progress(done, a.size);
                    last = Instant::now();
                }
            }
            f.sync_all().map_err(|e| format!("write: {e}"))?;
            drop(f);
            progress(done, a.size);
            if done != a.size {
                return Err(format!("got {done} of {} bytes", a.size));
            }
            let got = hash.hex()?;
            if got != a.sha256 {
                return Err(format!("SHA-256 mismatch ({got})"));
            }
            let _ = std::fs::remove_file(dest);
            std::fs::rename(&part, dest).map_err(|e| format!("{}: {e}", dest.display()))
        })();
        if result.is_err() {
            let _ = std::fs::remove_file(&part);
        }
        result
    }

    pub fn launch(kind: Kind, file: &Path, replace: bool) -> Result<(), String> {
        use std::process::Command;
        let mut c = Command::new(file);
        match kind {
            _ if !replace => {}
            Kind::Installed => {
                c.args(["/SILENT", "/SP-", "/SUPPRESSMSGBOXES", "/NORESTART", "/MERGETASKS=!firewall", "/ZLRELAUNCH=1"]);
            }
            Kind::Portable => {
                let exe = std::env::current_exe().map_err(|e| e.to_string())?;
                if exe == file {
                    return Err("already this file".into());
                }
                c.arg(format!("{REPLACE_ARG}{}", exe.display()));
            }
            Kind::Source => return Err("source checkout".into()),
            Kind::Store => return Err("the Microsoft Store installs updates".into()),
        }
        c.spawn().map(|_| ()).map_err(|e| format!("{}: {e}", file.display()))
    }
}

#[cfg(windows)]
pub use win::*;

#[cfg(not(windows))]
pub fn is_store() -> bool {
    false
}

#[cfg(not(windows))]
pub fn open_store_page() {
    let _ = std::process::Command::new("xdg-open")
        .arg("https://github.com/zenvyzenshiro/zenlink")
        .spawn();
}

#[cfg(not(windows))]
pub fn visible_log_dir() -> PathBuf {
    zenlink_core::log_dir()
}

pub fn kind() -> Kind {
    Kind::Source
}

pub fn current_version() -> Version {
    Version::parse(env!("CARGO_PKG_VERSION")).expect("Cargo version")
}

#[cfg(not(windows))]
pub fn check(_channel: Channel) -> Result<Offer, String> {
    Ok(Offer::UpToDate)
}

pub fn asset_for(kind: Kind, r: &Release) -> Option<&Asset> {
    match kind {
        Kind::Installed => r.setup.as_ref(),
        Kind::Portable => r.portable.as_ref(),
        Kind::Source | Kind::Store => None,
    }
}

#[cfg(not(windows))]
#[allow(dead_code)]
pub fn sha256_hex(_data: &[u8]) -> Result<String, String> {
    Ok(String::new())
}

#[cfg(not(windows))]
pub fn download(_a: &Asset, _dest: &Path, _progress: &dyn Fn(u64, u64)) -> Result<(), String> {
    Err("updates on Linux are managed via git or system packages".into())
}

pub fn download_path(_kind: Kind, a: &Asset) -> Result<PathBuf, String> {
    let dir = std::env::temp_dir().join(format!("{}-update", zenlink_core::DATA_DIR_NAME));
    std::fs::create_dir_all(&dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    Ok(dir.join(&a.name))
}

#[cfg(not(windows))]
pub fn launch(_kind: Kind, file: &Path, _replace: bool) -> Result<(), String> {
    std::process::Command::new(file)
        .spawn()
        .map(|_| ())
        .map_err(|e| format!("{}: {e}", file.display()))
}

pub fn finish_portable_update() {}
