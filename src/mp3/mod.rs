pub mod header;
pub mod xing;

use crate::common::error::{MutagenError, Result};
use crate::id3;
use crate::id3::header::ID3Header;
use crate::id3::tags::ID3Tags;
use crate::mp3::header::{find_sync, ChannelMode};
use crate::mp3::xing::{XingHeader, VBRIHeader, BitrateMode};

/// Parsed MP3 file information.
#[derive(Debug, Clone)]
pub struct MPEGInfo {
    pub length: f64,
    pub channels: u32,
    pub bitrate: u32,
    pub sample_rate: u32,
    pub version: f64,
    pub layer: u8,
    pub mode: u32,
    pub protected: bool,
    pub bitrate_mode: BitrateMode,
    pub encoder_info: String,
    pub encoder_settings: String,
    pub track_gain: Option<f32>,
    pub track_peak: Option<f32>,
    pub album_gain: Option<f32>,
}

impl MPEGInfo {
    /// Parse MPEG audio info from data starting at offset.
    pub fn parse(data: &[u8], offset: usize, file_size: u64) -> Result<Self> {
        let (sync_offset, first_frame) = find_sync(data, offset)
            .ok_or_else(|| MutagenError::HeaderNotFoundError(
                "can't sync to MPEG frame".into(),
            ))?;

        let version = first_frame.version;
        let layer = first_frame.layer;
        let sample_rate = first_frame.sample_rate;
        let channels = first_frame.channels;
        let channel_mode = first_frame.channel_mode;
        let protected = first_frame.protected;
        let mode = match channel_mode {
            ChannelMode::Stereo => 0,
            ChannelMode::JointStereo => 1,
            ChannelMode::DualChannel => 2,
            ChannelMode::Mono => 3,
        };

        let frame_data = &data[sync_offset..];

        let mut bitrate_mode = BitrateMode::Unknown;
        let mut length = 0.0f64;
        let mut bitrate = first_frame.bitrate * 1000;
        let mut encoder_info = String::new();
        let encoder_settings = String::new();
        let mut track_gain = None;
        let mut track_peak = None;
        let mut album_gain = None;

        if let Some(xing) = XingHeader::parse(frame_data, version, channel_mode) {
            bitrate_mode = if xing.is_info { BitrateMode::CBR } else { BitrateMode::VBR };

            if let (Some(frames), Some(bytes)) = (xing.frames, xing.bytes) {
                let spf = first_frame.samples_per_frame as f64;
                length = (frames as f64 * spf) / sample_rate as f64;
                if length > 0.0 {
                    bitrate = (bytes as f64 * 8.0 / length) as u32;
                }
            }

            if let Some(ref lame) = xing.lame_header {
                encoder_info = lame.encoder_version.clone();
                track_gain = lame.track_gain;
                track_peak = if lame.replay_gain_peak > 0.0 { Some(lame.replay_gain_peak) } else { None };
                album_gain = lame.album_gain;
                bitrate_mode = match lame.vbr_method {
                    1 | 8 => BitrateMode::CBR,
                    2 | 9 => BitrateMode::ABR,
                    3..=7 => BitrateMode::VBR,
                    _ => bitrate_mode,
                };
            }
        } else if let Some(vbri) = VBRIHeader::parse(frame_data) {
            bitrate_mode = BitrateMode::VBR;
            if vbri.frames > 0 {
                let spf = first_frame.samples_per_frame as f64;
                length = (vbri.frames as f64 * spf) / sample_rate as f64;
                if length > 0.0 {
                    bitrate = (vbri.bytes as f64 * 8.0 / length) as u32;
                }
            }
        }

        if length == 0.0 {
            bitrate_mode = BitrateMode::CBR;
            let audio_size = file_size as usize - sync_offset;
            if bitrate > 0 {
                length = audio_size as f64 * 8.0 / bitrate as f64;
            }
        }

        Ok(MPEGInfo {
            length, channels, bitrate, sample_rate,
            version: version.as_f64(), layer: layer.as_u8(),
            mode, protected, bitrate_mode,
            encoder_info, encoder_settings,
            track_gain, track_peak, album_gain,
        })
    }
}

/// Complete MP3 file: tags + audio info.
#[derive(Debug)]
pub struct MP3File {
    pub tags: ID3Tags,
    pub info: MPEGInfo,
    pub path: String,
    pub id3_header: Option<ID3Header>,
}

impl MP3File {
    /// Open and parse an MP3 file using cached file reads.
    pub fn open(path: &str) -> Result<Self> {
        let data = std::fs::read(path)?;
        let mut f = Self::parse(&data, path)?;
        f.ensure_tags_parsed(&data);
        Ok(f)
    }

    /// Parse an MP3 file: validates format + parses MPEG info.
    /// ID3 frame parsing is deferred to ensure_tags_parsed().
    pub fn parse(data: &[u8], path: &str) -> Result<Self> {
        let file_size = data.len() as u64;

        // Parse ID3v2 header (but NOT frames)
        let (id3_header, audio_start) = if data.len() >= 10 {
            match ID3Header::parse(&data[0..10], 0) {
                Ok(h) => {
                    let tag_size = h.size as usize;
                    if 10 + tag_size <= data.len() {
                        let audio_start = h.full_size() as usize;
                        (Some(h), audio_start)
                    } else {
                        (None, 0)
                    }
                }
                Err(_) => (None, 0),
            }
        } else {
            (None, 0)
        };

        // Parse MPEG audio info from audio data
        let audio_end = data.len().min(audio_start + 8192);
        let audio_data = if audio_start < data.len() {
            &data[audio_start..audio_end]
        } else {
            &[]
        };

        let info = MPEGInfo::parse(audio_data, 0, file_size.saturating_sub(audio_start as u64))?;

        Ok(MP3File {
            tags: ID3Tags::new(),
            info,
            path: path.to_string(),
            id3_header,
        })
    }

    /// Parse ID3 frames from the original file data.
    /// Call this after parse() when you need tag access.
    pub fn ensure_tags_parsed(&mut self, data: &[u8]) {
        if let Some(ref h) = self.id3_header {
            let tag_size = h.size as usize;
            if 10 + tag_size <= data.len() {
                let mut tags = ID3Tags::new();
                if h.flags.unsynchronisation && h.version.0 < 4 {
                    if let Ok(tag_data) = id3::unsynch::decode(&data[10..10 + tag_size]) {
                        let _ = tags.read_frames(&tag_data, h);
                    }
                } else {
                    let _ = tags.read_frames(&data[10..10 + tag_size], h);
                }
                self.tags = tags;
            }
        }

        // Check for ID3v1 at file end
        if data.len() >= 128 {
            let v1_data = &data[data.len() - 128..];
            if v1_data.len() >= 3 && &v1_data[0..3] == b"TAG" {
                if let Ok(v1_frames) = id3::id3v1::parse_id3v1(v1_data) {
                    for frame in v1_frames {
                        let key = frame.hash_key();
                        if !self.tags.contains_key(&key) {
                            self.tags.add(frame);
                        }
                    }
                }
            }
        }
    }

    pub fn save(&self) -> Result<()> {
        id3::save_id3(&self.path, &self.tags, self.tags.version.0.max(3))
    }

    pub fn score(path: &str, data: &[u8]) -> u32 {
        let mut score = 0u32;
        let ext = path.rsplit('.').next().unwrap_or("");
        if ext.eq_ignore_ascii_case("mp3") { score += 2; }
        if data.len() >= 3 && &data[0..3] == b"ID3" { score += 2; }
        // Limit sync scan to first 512 bytes for scoring performance
        let scan_len = data.len().min(512);
        if find_sync(&data[..scan_len], 0).is_some() { score += 1; }
        score
    }
}
