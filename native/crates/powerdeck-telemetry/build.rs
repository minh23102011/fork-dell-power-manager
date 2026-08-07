fn main() {
    println!("cargo:rerun-if-changed=c/perf_helper.c");
    cc::Build::new()
        .file("c/perf_helper.c")
        .warnings(true)
        .extra_warnings(true)
        .compile("powerdeck_perf_helper");
}
