//! Minimal little-endian float32 C-order `.npy` I/O for parity checks.
use std::io::{Error, ErrorKind, Result};
use std::path::Path;

pub struct Array {
    pub shape: Vec<usize>,
    pub data: Vec<f32>,
}

pub fn read_f32(path: &Path) -> Result<Array> {
    let bytes = std::fs::read(path)?;
    let invalid = |m: &str| Error::new(ErrorKind::InvalidData, m.to_string());
    if bytes.len() < 10 || &bytes[..6] != b"\x93NUMPY" {
        return Err(invalid("not an .npy file"));
    }
    let (header_len, start) = match bytes[6] {
        1 => (u16::from_le_bytes([bytes[8], bytes[9]]) as usize, 10),
        2 | 3 => (u32::from_le_bytes(bytes[8..12].try_into().unwrap()) as usize, 12),
        _ => return Err(invalid("unsupported .npy version")),
    };
    let header = std::str::from_utf8(&bytes[start..start + header_len]).map_err(|_| invalid("bad header"))?;
    if !header.contains("'descr': '<f4'") || !header.contains("'fortran_order': False") {
        return Err(invalid("expected little-endian float32 in C order"));
    }
    let shape_text = header
        .split("'shape': (")
        .nth(1)
        .and_then(|rest| rest.split(')').next())
        .ok_or_else(|| invalid("missing shape"))?;
    let shape: Vec<usize> = shape_text
        .split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(|s| s.parse().map_err(|_| invalid("bad shape")))
        .collect::<Result<_>>()?;
    let body = &bytes[start + header_len..];
    let count: usize = shape.iter().product();
    if body.len() != count * 4 {
        return Err(invalid("size does not match shape"));
    }
    let data = body.chunks_exact(4).map(|c| f32::from_le_bytes(c.try_into().unwrap())).collect();
    Ok(Array { shape, data })
}

pub fn write_f32(path: &Path, shape: &[usize], data: &[f32]) -> Result<()> {
    let dims: Vec<String> = shape.iter().map(|d| d.to_string()).collect();
    let shape_text = if dims.len() == 1 { format!("{},", dims[0]) } else { dims.join(", ") };
    let mut header = format!("{{'descr': '<f4', 'fortran_order': False, 'shape': ({shape_text}), }}");
    // Pad so the data starts on a 64-byte boundary, terminated by a newline.
    while (10 + header.len() + 1) % 64 != 0 {
        header.push(' ');
    }
    header.push('\n');
    let mut bytes = Vec::with_capacity(10 + header.len() + data.len() * 4);
    bytes.extend_from_slice(b"\x93NUMPY\x01\x00");
    bytes.extend_from_slice(&(header.len() as u16).to_le_bytes());
    bytes.extend_from_slice(header.as_bytes());
    for v in data {
        bytes.extend_from_slice(&v.to_le_bytes());
    }
    std::fs::write(path, bytes)
}
