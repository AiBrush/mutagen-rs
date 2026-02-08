use crate::common::error::{MutagenError, Result};
use crate::id3::header::{ID3Header, BitPaddedInt, determine_bpi};
use crate::id3::frames::{self, Frame, HashKey, convert_v22_frame_id, parse_v22_picture_frame};
use crate::id3::specs;
use crate::id3::unsynch;

/// A lazy frame that stores raw data and decodes on first access.
#[derive(Debug, Clone)]
pub enum LazyFrame {
    /// Already decoded frame.
    Decoded(Frame),
    /// Raw frame data that hasn't been decoded yet.
    Raw { id: String, data: Vec<u8> },
    /// Zero-allocation frame: stores offset into parent ID3Tags.raw_buf.
    Slice { id: [u8; 4], offset: u32, len: u32 },
}

impl LazyFrame {
    /// Get the hash key without full decoding.
    pub fn hash_key(&self) -> HashKey {
        match self {
            LazyFrame::Decoded(f) => f.hash_key(),
            LazyFrame::Raw { id, data } => quick_hash_key(id, data),
            LazyFrame::Slice { id, .. } => {
                let s = std::str::from_utf8(id).unwrap_or("XXXX");
                HashKey::new(s)
            }
        }
    }

    /// Get the frame ID.
    pub fn frame_id(&self) -> &str {
        match self {
            LazyFrame::Decoded(f) => f.frame_id(),
            LazyFrame::Raw { id, .. } => id,
            LazyFrame::Slice { id, .. } => std::str::from_utf8(id).unwrap_or("XXXX"),
        }
    }

    /// Force decode the frame, returning a reference to the decoded frame.
    /// For Slice frames, use decode_with_buf instead.
    pub fn decode(&mut self) -> Result<&Frame> {
        self.decode_with_buf(&[])
    }

    /// Decode the frame using a buffer (needed for Slice variant).
    pub fn decode_with_buf(&mut self, buf: &[u8]) -> Result<&Frame> {
        match self {
            LazyFrame::Decoded(_) => {}
            LazyFrame::Raw { id, data } => {
                let frame = frames::parse_frame(id, data)?;
                *self = LazyFrame::Decoded(frame);
            }
            LazyFrame::Slice { id, offset, len } => {
                let id_str = std::str::from_utf8(&id[..]).unwrap_or("XXXX");
                let data = &buf[*offset as usize..(*offset as usize + *len as usize)];
                let frame = frames::parse_frame(id_str, data)?;
                *self = LazyFrame::Decoded(frame);
            }
        }
        match self {
            LazyFrame::Decoded(f) => Ok(f),
            _ => unreachable!(),
        }
    }

    /// Get the decoded frame, decoding if necessary.
    pub fn get_decoded(&self) -> Option<&Frame> {
        match self {
            LazyFrame::Decoded(f) => Some(f),
            _ => None,
        }
    }

    /// Force decode and return the frame (consuming self).
    pub fn into_decoded(self) -> Result<Frame> {
        match self {
            LazyFrame::Decoded(f) => Ok(f),
            LazyFrame::Raw { id, data } => frames::parse_frame(&id, &data),
            LazyFrame::Slice { .. } => {
                Err(MutagenError::ID3("Cannot decode Slice without buffer".into()))
            }
        }
    }
}

/// Container for ID3v2 frames, providing dict-like access.
/// Uses Vec instead of HashMap for better cache locality and lower allocation overhead
/// (typical MP3 files have <20 unique frame types).
#[derive(Debug, Clone)]
pub struct ID3Tags {
    pub frames: Vec<(HashKey, Vec<LazyFrame>)>,
    pub version: (u8, u8),
    pub unknown_frames: Vec<(String, Vec<u8>)>,
    pub(crate) raw_buf: Vec<u8>,
}

impl ID3Tags {
    pub fn new() -> Self {
        ID3Tags {
            frames: Vec::with_capacity(16),
            version: (4, 0),
            unknown_frames: Vec::new(),
            raw_buf: Vec::new(),
        }
    }

    /// Add a decoded frame.
    pub fn add(&mut self, frame: Frame) {
        let key = frame.hash_key();
        if let Some((_, frames)) = self.frames.iter_mut().find(|(k, _)| k == &key) {
            frames.push(LazyFrame::Decoded(frame));
        } else {
            self.frames.push((key, vec![LazyFrame::Decoded(frame)]));
        }
    }

    /// Add a raw (lazy) frame.
    pub fn add_raw(&mut self, id: String, data: Vec<u8>) {
        let key = quick_hash_key(&id, &data);
        let lazy = LazyFrame::Raw { id, data };
        if let Some((_, frames)) = self.frames.iter_mut().find(|(k, _)| k == &key) {
            frames.push(lazy);
        } else {
            self.frames.push((key, vec![lazy]));
        }
    }

    /// Get all frames with the given key (forces decode).
    pub fn getall(&self, key: &str) -> Vec<&Frame> {
        let hash_key = HashKey::new(key);
        match self.frames.iter().find(|(k, _)| k == &hash_key) {
            Some((_, frames)) => {
                frames.iter().filter_map(|lf| lf.get_decoded()).collect()
            }
            None => vec![],
        }
    }

    /// Get all frames with given key, decoding if needed (mutable version).
    pub fn getall_mut(&mut self, key: &str) -> Vec<&Frame> {
        let hash_key = HashKey::new(key);
        if let Some((_, frames)) = self.frames.iter_mut().find(|(k, _)| k == &hash_key) {
            for lf in frames.iter_mut() {
                let _ = lf.decode_with_buf(&self.raw_buf);
            }
        }
        self.getall(key)
    }

    /// Get the first frame with the given key (forces decode).
    pub fn get(&self, key: &str) -> Option<&Frame> {
        self.getall(key).into_iter().next()
    }

    /// Get first frame, decoding if needed.
    pub fn get_mut(&mut self, key: &str) -> Option<&Frame> {
        let hash_key = HashKey::new(key);
        if let Some((_, frames)) = self.frames.iter_mut().find(|(k, _)| k == &hash_key) {
            if let Some(lf) = frames.first_mut() {
                let _ = lf.decode_with_buf(&self.raw_buf);
            }
        }
        self.get(key)
    }

    /// Set all frames for a given key (replaces existing).
    pub fn setall(&mut self, key: &str, frames_list: Vec<Frame>) {
        let hash_key = HashKey::new(key);
        let new_frames: Vec<LazyFrame> = frames_list.into_iter().map(LazyFrame::Decoded).collect();
        if let Some((_, frames)) = self.frames.iter_mut().find(|(k, _)| k == &hash_key) {
            *frames = new_frames;
        } else {
            self.frames.push((hash_key, new_frames));
        }
    }

    /// Delete all frames with the given key.
    pub fn delall(&mut self, key: &str) {
        let hash_key = HashKey::new(key);
        self.frames.retain(|(k, _)| k != &hash_key);
    }

    /// Get all keys.
    pub fn keys(&self) -> Vec<String> {
        self.frames.iter().map(|(k, _)| k.as_str().to_string()).collect()
    }

    /// Get all decoded frames as a flat list.
    pub fn values(&self) -> Vec<&Frame> {
        self.frames.iter().flat_map(|(_, v)| {
            v.iter().filter_map(|lf| lf.get_decoded())
        }).collect()
    }

    /// Decode all frames and return as flat list.
    pub fn values_decoded(&mut self) -> Vec<&Frame> {
        for (_, frames) in self.frames.iter_mut() {
            for lf in frames.iter_mut() {
                let _ = lf.decode_with_buf(&self.raw_buf);
            }
        }
        self.values()
    }

    /// Number of unique keys.
    pub fn len(&self) -> usize {
        self.frames.len()
    }

    pub fn is_empty(&self) -> bool {
        self.frames.is_empty()
    }

    /// Check if a key exists (Vec-based linear scan).
    pub fn contains_key(&self, key: &HashKey) -> bool {
        self.frames.iter().any(|(k, _)| k == key)
    }

    /// Parse frames from raw tag data.
    pub fn read_frames(&mut self, data: &[u8], header: &ID3Header) -> Result<()> {
        let version = header.version.0;
        let mut offset = 0usize;

        // Handle extended header
        if header.flags.extended && version >= 3 {
            if data.len() < 4 {
                return Ok(());
            }
            let ext_size = if version == 4 {
                BitPaddedInt::syncsafe(&data[0..4]) as usize
            } else {
                u32::from_be_bytes([data[0], data[1], data[2], data[3]]) as usize
            };
            offset = if version == 4 {
                ext_size
            } else {
                ext_size + 4
            };
            if offset >= data.len() {
                return Ok(());
            }
        }

        // Determine BPI for v2.4
        let bpi = if version == 4 {
            determine_bpi(&data[offset..], data.len())
        } else {
            8
        };

        self.version = header.version;

        // Store raw tag data for Slice-based zero-alloc frame storage
        self.raw_buf = data.to_vec();

        if version == 2 {
            self.read_v22_frames(data, offset)?;
        } else {
            self.read_v23_v24_frames(data, offset, version, bpi)?;
        }

        Ok(())
    }

    /// Read v2.2 frames (6-byte headers).
    fn read_v22_frames(&mut self, data: &[u8], mut offset: usize) -> Result<()> {
        while offset + 6 <= data.len() {
            if data[offset] == 0 {
                break;
            }

            let id_bytes = &data[offset..offset + 3];
            if !id_bytes.iter().all(|&b| b.is_ascii_uppercase() || b.is_ascii_digit()) {
                break;
            }

            let size = ((data[offset + 3] as usize) << 16)
                | ((data[offset + 4] as usize) << 8)
                | (data[offset + 5] as usize);

            offset += 6;

            if size == 0 || offset + size > data.len() {
                break;
            }

            let frame_data = &data[offset..offset + size];
            offset += size;

            // Check for PIC frame directly on bytes (avoid String allocation)
            if id_bytes == b"PIC" {
                match parse_v22_picture_frame(frame_data) {
                    Ok(frame) => self.add(frame),
                    Err(_) => {}
                }
                continue;
            }

            let id_str = std::str::from_utf8(id_bytes).unwrap_or("XXX");

            let v24_id = match convert_v22_frame_id(id_str) {
                Some(new_id) => new_id.to_string(),
                None => {
                    self.unknown_frames.push((id_str.to_string(), frame_data.to_vec()));
                    continue;
                }
            };

            // Store as lazy (raw) frame
            self.add_raw(v24_id, frame_data.to_vec());
        }

        Ok(())
    }

    /// Read v2.3/v2.4 frames (10-byte headers).
    fn read_v23_v24_frames(
        &mut self,
        data: &[u8],
        mut offset: usize,
        version: u8,
        bpi: u8,
    ) -> Result<()> {
        while offset + 10 <= data.len() {
            if data[offset] == 0 {
                break;
            }

            let id_bytes = &data[offset..offset + 4];
            if !id_bytes
                .iter()
                .all(|&b| b.is_ascii_uppercase() || b.is_ascii_digit())
            {
                break;
            }

            let size = BitPaddedInt::decode(&data[offset + 4..offset + 8], bpi) as usize;
            let flags = u16::from_be_bytes([data[offset + 8], data[offset + 9]]);

            offset += 10;

            if size == 0 || offset + size > data.len() {
                break;
            }

            // Handle frame-level flags
            let (compressed, encrypted, unsynchronised, has_data_length) = if version == 4 {
                (
                    flags & 0x0008 != 0,
                    flags & 0x0004 != 0,
                    flags & 0x0002 != 0,
                    flags & 0x0001 != 0,
                )
            } else {
                (
                    flags & 0x0080 != 0,
                    flags & 0x0040 != 0,
                    false,
                    flags & 0x0080 != 0,
                )
            };

            // Defer String allocation until we know we need it
            let id_str = std::str::from_utf8(id_bytes).unwrap_or("XXXX");

            // Fast path: no flags that require data mutation (common case)
            // Use Slice frames: zero allocation (no String for ID, no Vec for data)
            if !encrypted && !compressed && !unsynchronised && !has_data_length {
                let id_arr: [u8; 4] = [id_bytes[0], id_bytes[1], id_bytes[2], id_bytes[3]];
                let frame_offset = offset as u32;
                let frame_len = size as u32;
                // Compute hash key directly from raw data (no full parse)
                let key = quick_hash_key(id_str, &data[offset..offset + size]);
                let lazy = LazyFrame::Slice { id: id_arr, offset: frame_offset, len: frame_len };
                if let Some((_, frames)) = self.frames.iter_mut().find(|(k, _)| k == &key) {
                    frames.push(lazy);
                } else {
                    self.frames.push((key, vec![lazy]));
                }
                offset += size;
                continue;
            }

            let id = id_str.to_string();
            let mut frame_data = data[offset..offset + size].to_vec();
            offset += size;

            if encrypted {
                self.unknown_frames.push((id, frame_data));
                continue;
            }

            if has_data_length && frame_data.len() >= 4 {
                frame_data = frame_data[4..].to_vec();
            }

            if unsynchronised {
                frame_data = unsynch::decode(&frame_data)?;
            }

            if compressed {
                match decompress_zlib(&frame_data) {
                    Ok(decompressed) => frame_data = decompressed,
                    Err(_) => {
                        self.unknown_frames.push((id, frame_data));
                        continue;
                    }
                }
            }

            // Store as lazy (raw) frame - don't decode until accessed
            self.add_raw(id, frame_data);
        }

        Ok(())
    }

    /// Serialize all frames to bytes for writing.
    pub fn render(&self, version: u8) -> Result<Vec<u8>> {
        let mut data = Vec::with_capacity(4096);

        for (_, frames_list) in self.frames.iter() {
            for lf in frames_list {
                let (id, frame_data) = match lf {
                    LazyFrame::Decoded(frame) => {
                        (frame.frame_id().to_string(), frame.write_data(version)?)
                    }
                    LazyFrame::Raw { id, data } => {
                        // Re-serialize raw data as-is
                        (id.clone(), data.clone())
                    }
                    LazyFrame::Slice { id, offset, len } => {
                        let id_str = std::str::from_utf8(&id[..]).unwrap_or("XXXX").to_string();
                        let slice_data = self.raw_buf[*offset as usize..(*offset as usize + *len as usize)].to_vec();
                        (id_str, slice_data)
                    }
                };

                if version == 4 {
                    data.extend_from_slice(id.as_bytes());
                    data.extend_from_slice(&BitPaddedInt::encode(
                        frame_data.len() as u32,
                        4,
                        7,
                    ));
                    data.extend_from_slice(&[0u8; 2]);
                    data.extend_from_slice(&frame_data);
                } else {
                    data.extend_from_slice(id.as_bytes());
                    data.extend_from_slice(&(frame_data.len() as u32).to_be_bytes());
                    data.extend_from_slice(&[0u8; 2]);
                    data.extend_from_slice(&frame_data);
                }
            }
        }

        Ok(data)
    }
}

/// Extract hash key from raw frame bytes without full frame parsing.
/// For special frames (TXXX, WXXX, COMM, USLT, APIC, POPM), reads only
/// the description/email header bytes to build the key. Avoids copying
/// large frame data (critical for APIC picture frames which can be 200KB+).
#[inline]
fn quick_hash_key(id: &str, data: &[u8]) -> HashKey {
    match id {
        "TXXX" | "WXXX" => {
            if data.is_empty() { return HashKey::new(id); }
            if let Ok(enc) = specs::Encoding::from_byte(data[0]) {
                if let Ok((desc, _)) = specs::read_encoded_text(&data[1..], enc) {
                    return HashKey::from_string(format!("{}:{}", id, desc));
                }
            }
            HashKey::new(id)
        }
        "COMM" | "USLT" => {
            if data.len() < 4 { return HashKey::new(id); }
            if let Ok(enc) = specs::Encoding::from_byte(data[0]) {
                let lang = std::str::from_utf8(&data[1..4]).unwrap_or("XXX");
                if let Ok((desc, _)) = specs::read_encoded_text(&data[4..], enc) {
                    return HashKey::from_string(format!("{}:{}:{}", id, desc, lang));
                }
            }
            HashKey::new(id)
        }
        "APIC" => {
            if data.is_empty() { return HashKey::new("APIC"); }
            if let Ok(enc) = specs::Encoding::from_byte(data[0]) {
                // Skip MIME (null-term Latin1)
                if let Ok((_, mime_consumed)) = specs::read_latin1_text(&data[1..]) {
                    let after_mime = 1 + mime_consumed;
                    // Skip pic_type (1 byte)
                    let after_type = after_mime + 1;
                    if after_type < data.len() {
                        if let Ok((desc, _)) = specs::read_encoded_text(&data[after_type..], enc) {
                            return HashKey::from_string(format!("APIC:{}", desc));
                        }
                    }
                }
            }
            HashKey::new("APIC")
        }
        "POPM" => {
            if let Ok((email, _)) = specs::read_latin1_text(data) {
                return HashKey::from_string(format!("POPM:{}", email));
            }
            HashKey::new("POPM")
        }
        _ => HashKey::new(id),
    }
}

/// Quick hash key extraction for Slice variant using raw_buf data.
#[inline]
#[allow(dead_code)]
fn quick_hash_key_from_buf(id: &[u8; 4], buf: &[u8], offset: u32, len: u32) -> HashKey {
    let id_str = std::str::from_utf8(id).unwrap_or("XXXX");
    let data = &buf[offset as usize..(offset as usize + len as usize)];
    quick_hash_key(id_str, data)
}

fn decompress_zlib(data: &[u8]) -> Result<Vec<u8>> {
    use flate2::read::ZlibDecoder;
    use std::io::Read;

    let mut decoder = ZlibDecoder::new(data);
    let mut result = Vec::new();
    decoder
        .read_to_end(&mut result)
        .map_err(|_| MutagenError::ID3BadCompressedData)?;
    Ok(result)
}
