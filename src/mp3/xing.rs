use crate::mp3::header::{MPEGVersion, ChannelMode};

/// Bitrate mode for VBR detection.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum BitrateMode {
    Unknown,
    CBR,
    VBR,
    ABR,
}

/// Parsed Xing/Info VBR header.
#[derive(Debug, Clone)]
pub struct XingHeader {
    pub frames: Option<u32>,
    pub bytes: Option<u32>,
    pub toc: Option<Vec<u8>>,
    pub quality: Option<u32>,
    pub is_info: bool, // "Info" tag = CBR, "Xing" tag = VBR
    pub lame_header: Option<LAMEHeader>,
}

/// Parsed LAME header (extension of Xing).
#[derive(Debug, Clone)]
pub struct LAMEHeader {
    pub encoder_version: String,
    pub vbr_method: u8,
    pub lowpass_freq: u32,
    pub replay_gain_peak: f32,
    pub track_gain: Option<f32>,
    pub album_gain: Option<f32>,
    pub encoder_delay: u16,
    pub encoder_padding: u16,
}

/// Parsed VBRI header.
#[derive(Debug, Clone)]
pub struct VBRIHeader {
    pub frames: u32,
    pub bytes: u32,
    pub quality: u16,
}

impl XingHeader {
    /// Try to parse a Xing/Info header from the MPEG frame data.
    /// `data` should start at the beginning of the MPEG frame (after sync).
    pub fn parse(data: &[u8], version: MPEGVersion, channel_mode: ChannelMode) -> Option<Self> {
        // Xing header offset depends on MPEG version and channel mode
        let offset = match (version, channel_mode) {
            (MPEGVersion::V1, ChannelMode::Mono) => 21,
            (MPEGVersion::V1, _) => 36,
            (_, ChannelMode::Mono) => 13,
            (_, _) => 21,
        };

        // Add 4 bytes for the frame header itself
        let xing_offset = offset + 4;

        if data.len() < xing_offset + 4 {
            return None;
        }

        let tag = &data[xing_offset..xing_offset + 4];
        let is_info;
        if tag == b"Xing" {
            is_info = false;
        } else if tag == b"Info" {
            is_info = true;
        } else {
            return None;
        }

        let mut pos = xing_offset + 4;
        if pos + 4 > data.len() {
            return None;
        }

        let flags = u32::from_be_bytes([data[pos], data[pos + 1], data[pos + 2], data[pos + 3]]);
        pos += 4;

        let frames = if flags & 0x01 != 0 {
            if pos + 4 > data.len() {
                return None;
            }
            let f =
                u32::from_be_bytes([data[pos], data[pos + 1], data[pos + 2], data[pos + 3]]);
            pos += 4;
            Some(f)
        } else {
            None
        };

        let bytes = if flags & 0x02 != 0 {
            if pos + 4 > data.len() {
                return None;
            }
            let b =
                u32::from_be_bytes([data[pos], data[pos + 1], data[pos + 2], data[pos + 3]]);
            pos += 4;
            Some(b)
        } else {
            None
        };

        let toc = if flags & 0x04 != 0 {
            if pos + 100 > data.len() {
                return None;
            }
            // Skip TOC data without copying (saves allocation)
            pos += 100;
            None
        } else {
            None
        };

        let quality = if flags & 0x08 != 0 {
            if pos + 4 > data.len() {
                return None;
            }
            let q =
                u32::from_be_bytes([data[pos], data[pos + 1], data[pos + 2], data[pos + 3]]);
            pos += 4;
            Some(q)
        } else {
            None
        };

        // Try to parse LAME header
        let lame_header = if pos + 9 <= data.len() {
            parse_lame_header(data, pos)
        } else {
            None
        };

        Some(XingHeader {
            frames,
            bytes,
            toc,
            quality,
            is_info,
            lame_header,
        })
    }
}

/// Parse LAME encoder info from Xing header extension.
fn parse_lame_header(data: &[u8], offset: usize) -> Option<LAMEHeader> {
    if offset + 36 > data.len() {
        return None;
    }

    // First 9 bytes: encoder version string (e.g., "LAME3.100")
    let version_bytes = &data[offset..offset + 9];
    let encoder_version = String::from_utf8_lossy(version_bytes).trim().to_string();

    // Check if this is actually a LAME header
    if !encoder_version.starts_with("LAME") && !encoder_version.starts_with("L3.9") {
        return None;
    }

    let pos = offset + 9;

    // Byte at pos: info tag revision + VBR method
    let vbr_method = data[pos] & 0x0F;

    // Lowpass frequency
    let lowpass_freq = data[pos + 1] as u32 * 100;

    // Replay gain peak signal amplitude
    let peak_bytes = &data[pos + 2..pos + 6];
    let peak_raw = u32::from_be_bytes([peak_bytes[0], peak_bytes[1], peak_bytes[2], peak_bytes[3]]);
    let replay_gain_peak = f32::from_bits(peak_raw);

    // Track gain (2 bytes at pos+6..pos+8)
    let track_gain_raw = i16::from_be_bytes([data[pos + 6], data[pos + 7]]);
    let track_gain = if track_gain_raw != 0 {
        Some(track_gain_raw as f32 / 10.0)
    } else {
        None
    };

    // Album gain (2 bytes at pos+8..pos+10)
    let album_gain_raw = i16::from_be_bytes([data[pos + 8], data[pos + 9]]);
    let album_gain = if album_gain_raw != 0 {
        Some(album_gain_raw as f32 / 10.0)
    } else {
        None
    };

    // Encoder delay and padding at pos+21
    let delay_padding_pos = pos + 21;
    let (encoder_delay, encoder_padding) = if delay_padding_pos + 3 <= data.len() {
        let dp = u32::from_be_bytes([
            0,
            data[delay_padding_pos],
            data[delay_padding_pos + 1],
            data[delay_padding_pos + 2],
        ]);
        let delay = ((dp >> 12) & 0xFFF) as u16;
        let padding = (dp & 0xFFF) as u16;
        (delay, padding)
    } else {
        (0, 0)
    };

    Some(LAMEHeader {
        encoder_version,
        vbr_method,
        lowpass_freq,
        replay_gain_peak,
        track_gain,
        album_gain,
        encoder_delay,
        encoder_padding,
    })
}

impl VBRIHeader {
    /// Try to parse a VBRI header. VBRI always starts at offset 36 from frame start.
    pub fn parse(data: &[u8]) -> Option<Self> {
        let offset = 36; // VBRI header is at exactly byte 36 from frame start
        if data.len() < offset + 26 {
            return None;
        }

        if &data[offset..offset + 4] != b"VBRI" {
            return None;
        }

        let pos = offset + 4;
        // Skip version (2) and delay (2)
        let pos = pos + 4;
        // Quality (2 bytes)
        let quality = u16::from_be_bytes([data[pos], data[pos + 1]]);
        let pos = pos + 2;
        // Bytes (4 bytes)
        let bytes = u32::from_be_bytes([data[pos], data[pos + 1], data[pos + 2], data[pos + 3]]);
        let pos = pos + 4;
        // Frames (4 bytes)
        let frames =
            u32::from_be_bytes([data[pos], data[pos + 1], data[pos + 2], data[pos + 3]]);

        Some(VBRIHeader {
            frames,
            bytes,
            quality,
        })
    }
}
