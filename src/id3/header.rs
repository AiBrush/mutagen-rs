use crate::common::error::{MutagenError, Result};

/// Syncsafe integer encoding used in ID3v2 tags.
/// Each byte uses only 7 bits (MSB is always 0).
pub struct BitPaddedInt;

impl BitPaddedInt {
    /// Decode a syncsafe integer from bytes.
    /// `bits` is the number of significant bits per byte (7 for syncsafe, 8 for normal).
    pub fn decode(data: &[u8], bits: u8) -> u32 {
        let mut result: u32 = 0;
        let mask = (1u32 << bits) - 1;
        for &b in data {
            result = (result << bits) | (b as u32 & mask);
        }
        result
    }

    /// Decode standard syncsafe (7 bits per byte).
    pub fn syncsafe(data: &[u8]) -> u32 {
        Self::decode(data, 7)
    }

    /// Decode as normal integer (8 bits per byte).
    pub fn normal(data: &[u8]) -> u32 {
        Self::decode(data, 8)
    }

    /// Encode an integer as syncsafe bytes.
    pub fn encode(value: u32, width: usize, bits: u8) -> Vec<u8> {
        let mut result = vec![0u8; width];
        let mask = (1u32 << bits) - 1;
        let mut val = value;
        for i in (0..width).rev() {
            result[i] = (val & mask) as u8;
            val >>= bits;
        }
        result
    }

    /// Check if data could be a valid syncsafe integer (no high bits set).
    pub fn has_valid_padding(data: &[u8]) -> bool {
        data.iter().all(|&b| b & 0x80 == 0)
    }
}

/// ID3v2 header flags.
#[derive(Debug, Clone, Copy, Default)]
pub struct ID3Flags {
    pub unsynchronisation: bool,
    pub extended: bool,
    pub experimental: bool,
    pub footer: bool,
}

/// Parsed ID3v2 header (10 bytes).
#[derive(Debug, Clone)]
pub struct ID3Header {
    pub version: (u8, u8), // (major, revision) e.g. (4, 0) for ID3v2.4
    pub flags: ID3Flags,
    pub size: u32,         // Tag size excluding header (10 bytes)
    pub offset: u64,       // Offset of the ID3 header in the file
}

impl ID3Header {
    /// Parse an ID3v2 header from the first 10 bytes.
    pub fn parse(data: &[u8], offset: u64) -> Result<Self> {
        if data.len() < 10 {
            return Err(MutagenError::ID3NoHeader);
        }

        // Check magic "ID3"
        if &data[0..3] != b"ID3" {
            return Err(MutagenError::ID3NoHeader);
        }

        let major = data[3];
        let revision = data[4];

        // We support versions 2.2, 2.3, 2.4
        if !(2..=4).contains(&major) {
            return Err(MutagenError::ID3UnsupportedVersion(
                format!("ID3v2.{}.{}", major, revision),
            ));
        }

        let flag_byte = data[5];

        let flags = ID3Flags {
            unsynchronisation: flag_byte & 0x80 != 0,
            extended: flag_byte & 0x40 != 0,
            experimental: flag_byte & 0x20 != 0,
            footer: major == 4 && (flag_byte & 0x10 != 0),
        };

        // Size is always syncsafe in the header
        let size = BitPaddedInt::syncsafe(&data[6..10]);

        Ok(ID3Header {
            version: (major, revision),
            flags,
            size,
            offset,
        })
    }

    /// Full tag size including 10-byte header (and optional 10-byte footer).
    pub fn full_size(&self) -> u32 {
        let mut s = self.size + 10;
        if self.flags.footer {
            s += 10;
        }
        s
    }
}

/// Determine BPI (Bytes Per Integer) for frame sizes in ID3v2.4.
/// Some encoders (notably iTunes) incorrectly use normal integers instead of syncsafe.
/// This function heuristically determines which encoding is used.
pub fn determine_bpi(data: &[u8], frames_end: usize) -> u8 {
    // Matches mutagen's determine_bpi: try both interpretations, count known frames,
    // track overshoot. Handles zero-size frames and non-ASCII IDs gracefully.
    let end = frames_end.min(data.len());
    let empty10 = [0u8; 10];

    // Pass 1: syncsafe (BPI) interpretation
    let mut o = 0usize;
    let mut asbpi = 0u32;
    let bpioff;
    loop {
        if o + 10 > end { bpioff = o as i64 - end as i64; break; }
        if data[o..o + 10] == empty10 {
            bpioff = -(((end - o) % 10) as i64);
            break;
        }
        let size = BitPaddedInt::syncsafe(&data[o + 4..o + 8]) as usize;
        o += 10 + size;
        let id = &data[o - 10 - size..o - 10 - size + 4];
        if id.iter().all(|&b| b.is_ascii_uppercase() || b.is_ascii_digit()) {
            asbpi += 1;
        }
    }

    // Pass 2: normal (int) interpretation
    let mut o = 0usize;
    let mut asint = 0u32;
    let intoff;
    loop {
        if o + 10 > end { intoff = o as i64 - end as i64; break; }
        if data[o..o + 10] == empty10 {
            intoff = -(((end - o) % 10) as i64);
            break;
        }
        let size = BitPaddedInt::normal(&data[o + 4..o + 8]) as usize;
        o += 10 + size;
        let id = &data[o - 10 - size..o - 10 - size + 4];
        if id.iter().all(|&b| b.is_ascii_uppercase() || b.is_ascii_digit()) {
            asint += 1;
        }
    }

    // Match mutagen: prefer int if more tags, or equal counts but bpi overshoots
    if asint > asbpi || (asint == asbpi && bpioff >= 1 && intoff <= 1) {
        8
    } else {
        7
    }
}

/// Search for an ID3v2 tag in the file data.
/// Returns the offset where the tag starts, or None.
pub fn find_id3v2_header(data: &[u8]) -> Option<u64> {
    if data.len() >= 10 && &data[0..3] == b"ID3" {
        Some(0)
    } else {
        None
    }
}
