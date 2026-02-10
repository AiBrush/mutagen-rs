use crate::common::error::{MutagenError, Result};
use std::collections::HashMap;

/// A Vorbis comment: list of key=value pairs with a vendor string.
#[derive(Debug, Clone)]
pub struct VorbisComment {
    pub vendor: String,
    pub comments: Vec<(String, String)>,
}

impl Default for VorbisComment {
    fn default() -> Self {
        Self::new()
    }
}

impl VorbisComment {
    pub fn new() -> Self {
        VorbisComment {
            vendor: String::new(),
            comments: Vec::new(),
        }
    }

    /// Parse a Vorbis comment block from bytes.
    /// `framing` controls whether to expect a framing bit at the end (true for OGG, false for FLAC).
    pub fn parse(data: &[u8], _framing: bool) -> Result<Self> {
        if data.len() < 4 {
            return Err(MutagenError::InvalidData("Vorbis comment too short".into()));
        }

        let mut pos = 0;

        // Vendor string length (LE32)
        let vendor_len = u32::from_le_bytes([
            data[pos], data[pos + 1], data[pos + 2], data[pos + 3],
        ]) as usize;
        pos += 4;

        if pos + vendor_len > data.len() {
            return Err(MutagenError::InvalidData("Vendor string extends past data".into()));
        }

        let vendor = match std::str::from_utf8(&data[pos..pos + vendor_len]) {
            Ok(s) => s.to_string(),
            Err(_) => String::from_utf8_lossy(&data[pos..pos + vendor_len]).into_owned(),
        };
        pos += vendor_len;

        if pos + 4 > data.len() {
            return Err(MutagenError::InvalidData("No comment count".into()));
        }

        // Comment count (LE32)
        let count = u32::from_le_bytes([
            data[pos], data[pos + 1], data[pos + 2], data[pos + 3],
        ]) as usize;
        pos += 4;

        let mut comments = Vec::with_capacity(count.min(64));

        for _ in 0..count {
            if pos + 4 > data.len() {
                break;
            }

            let comment_len = u32::from_le_bytes([
                data[pos], data[pos + 1], data[pos + 2], data[pos + 3],
            ]) as usize;
            pos += 4;

            if pos + comment_len > data.len() {
                break;
            }

            let raw = &data[pos..pos + comment_len];
            pos += comment_len;

            // Use SIMD-accelerated memchr to find '=' on raw bytes (avoid UTF-8 decode overhead)
            let eq_pos = match memchr::memchr(b'=', raw) {
                Some(p) => p,
                None => continue,
            };

            let key_bytes = &raw[..eq_pos];
            let value_bytes = &raw[eq_pos + 1..];

            // Key: fast ASCII lowercase (matches mutagen behavior)
            let key = if key_bytes.iter().all(|&b| !b.is_ascii_uppercase()) {
                // Already lowercase (common case) - zero-copy if valid UTF-8
                match std::str::from_utf8(key_bytes) {
                    Ok(s) => s.to_string(),
                    Err(_) => continue,
                }
            } else {
                // Fast ASCII lowercase without full Unicode overhead
                let mut k = String::with_capacity(key_bytes.len());
                for &b in key_bytes {
                    k.push(if b.is_ascii_uppercase() { (b + 32) as char } else { b as char });
                }
                k
            };

            // Value: zero-copy if valid UTF-8
            let value = match std::str::from_utf8(value_bytes) {
                Ok(s) => s.to_string(),
                Err(_) => String::from_utf8_lossy(value_bytes).into_owned(),
            };

            comments.push((key, value));
        }

        Ok(VorbisComment { vendor, comments })
    }

    /// Serialize to bytes.
    pub fn render(&self, framing: bool) -> Vec<u8> {
        let mut data = Vec::new();

        // Vendor string
        let vendor_bytes = self.vendor.as_bytes();
        data.extend_from_slice(&(vendor_bytes.len() as u32).to_le_bytes());
        data.extend_from_slice(vendor_bytes);

        // Comment count
        data.extend_from_slice(&(self.comments.len() as u32).to_le_bytes());

        // Comments
        for (key, value) in &self.comments {
            let comment = format!("{}={}", key, value);
            let comment_bytes = comment.as_bytes();
            data.extend_from_slice(&(comment_bytes.len() as u32).to_le_bytes());
            data.extend_from_slice(comment_bytes);
        }

        if framing {
            data.push(1); // framing bit
        }

        data
    }

    /// Get as a case-insensitive dict (keys are lowercase, matching mutagen).
    pub fn as_dict(&self) -> HashMap<String, Vec<String>> {
        let mut dict: HashMap<String, Vec<String>> = HashMap::new();
        for (key, value) in &self.comments {
            dict.entry(key.to_lowercase())
                .or_default()
                .push(value.clone());
        }
        dict
    }

    /// Get all values for a key (case-insensitive).
    #[inline(always)]
    pub fn get(&self, key: &str) -> Vec<&str> {
        self.comments
            .iter()
            .filter(|(k, _)| k.eq_ignore_ascii_case(key))
            .map(|(_, v)| v.as_str())
            .collect()
    }

    /// Set all values for a key (replaces existing).
    pub fn set(&mut self, key: &str, values: Vec<String>) {
        let lower = key.to_lowercase();
        self.comments.retain(|(k, _)| k != &lower);
        for v in values {
            self.comments.push((lower.clone(), v));
        }
    }

    /// Delete all entries for a key.
    pub fn delete(&mut self, key: &str) {
        let lower = key.to_lowercase();
        self.comments.retain(|(k, _)| k != &lower);
    }

    /// Get all unique keys. Uses linear scan instead of HashSet for
    /// typical small key counts (5-15 unique keys).
    #[inline(always)]
    pub fn keys(&self) -> Vec<String> {
        let mut keys = Vec::with_capacity(8);
        for (k, _) in &self.comments {
            if !keys.iter().any(|existing: &String| existing == k) {
                keys.push(k.clone());
            }
        }
        keys
    }
}
