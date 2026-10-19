//! kora-bench <film.cube> <linear.npy> <out.npy> [repeats]
//!
//! Applies the official LUT adapter to a linear sRGB float32 (H, W, 3) array
//! and prints the best wall time, for parity checks against the Python engine.
use kora_core::{lut::Lut3d, npy, official::apply_official};
use std::path::Path;
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 4 {
        eprintln!("usage: kora-bench <film.cube> <linear.npy> <out.npy> [repeats]");
        std::process::exit(2);
    }
    let repeats: usize = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(3).max(1);
    let started = Instant::now();
    let lut = Lut3d::load(Path::new(&args[1])).unwrap_or_else(|e| fail(&e.to_string()));
    let lut_seconds = started.elapsed().as_secs_f64();
    let input = npy::read_f32(Path::new(&args[2])).unwrap_or_else(|e| fail(&e.to_string()));
    if input.shape.len() != 3 || input.shape[2] != 3 {
        fail("expected an (H, W, 3) array");
    }
    let mut out = vec![0f32; input.data.len()];
    let mut best = f64::INFINITY;
    for _ in 0..repeats {
        let t = Instant::now();
        apply_official(&lut, &input.data, &mut out);
        best = best.min(t.elapsed().as_secs_f64());
    }
    npy::write_f32(Path::new(&args[3]), &input.shape, &out).unwrap_or_else(|e| fail(&e.to_string()));
    println!(
        "{{\"lut_load_seconds\": {lut_seconds:.4}, \"apply_seconds\": {best:.4}, \"threads\": {}}}",
        rayon::current_num_threads()
    );
}

fn fail(message: &str) -> ! {
    eprintln!("kora-bench: {message}");
    std::process::exit(1);
}
