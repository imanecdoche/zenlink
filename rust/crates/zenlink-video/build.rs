fn main() {
    #[cfg(target_os = "linux")]
    {
        let codec = pkg_config::probe_library("libavcodec").expect("libavcodec-dev is required on Linux");
        let swscale = pkg_config::probe_library("libswscale").expect("libswscale-dev is required on Linux");
        let avutil = pkg_config::probe_library("libavutil").expect("libavutil-dev is required on Linux");

        let mut build = cc::Build::new();
        build.file("src/zlvideo.c");

        for inc in codec.include_paths.iter().chain(&swscale.include_paths).chain(&avutil.include_paths) {
            build.include(inc);
        }

        build.compile("zlvideo");
        println!("cargo:rerun-if-changed=src/zlvideo.c");
    }
}
