pub mod atom;

use crate::common::error::{MutagenError, Result};
use crate::mp4::atom::AtomIter;

/// MP4 audio information.
#[derive(Debug, Clone)]
pub struct MP4Info {
    pub length: f64,
    pub channels: u32,
    pub sample_rate: u32,
    pub bitrate: u32,
    pub bits_per_sample: u32,
    pub codec: String,
    pub codec_description: String,
}

impl Default for MP4Info {
    fn default() -> Self {
        MP4Info {
            length: 0.0,
            channels: 2,
            sample_rate: 44100,
            bitrate: 0,
            bits_per_sample: 16,
            codec: String::new(),
            codec_description: String::new(),
        }
    }
}

/// MP4 cover art format.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum MP4CoverFormat {
    JPEG = 13,
    PNG = 14,
}

/// MP4 cover art.
#[derive(Debug, Clone)]
pub struct MP4Cover {
    pub data: Vec<u8>,
    pub format: MP4CoverFormat,
}

/// MP4 freeform data.
#[derive(Debug, Clone)]
pub struct MP4FreeForm {
    pub data: Vec<u8>,
    pub dataformat: u32,
}

/// Tag value types in MP4.
#[derive(Debug, Clone)]
pub enum MP4TagValue {
    Text(Vec<String>),
    Integer(Vec<i64>),
    IntPair(Vec<(i32, i32)>),
    Bool(bool),
    Cover(Vec<MP4Cover>),
    FreeForm(Vec<MP4FreeForm>),
    Data(Vec<u8>),
}

/// Complete MP4 tag container (Vec-based for cache locality and low allocation).
#[derive(Debug, Clone)]
pub struct MP4Tags {
    pub items: Vec<(String, MP4TagValue)>,
}

impl MP4Tags {
    #[inline]
    pub fn new() -> Self {
        MP4Tags {
            items: Vec::new(),
        }
    }

    #[inline]
    pub fn keys(&self) -> Vec<String> {
        self.items.iter().map(|(k, _)| k.clone()).collect()
    }

    #[inline]
    pub fn get(&self, key: &str) -> Option<&MP4TagValue> {
        self.items.iter().find(|(k, _)| k == key).map(|(_, v)| v)
    }

    #[inline]
    pub fn get_mut(&mut self, key: &str) -> Option<&mut MP4TagValue> {
        self.items.iter_mut().find(|(k, _)| k == key).map(|(_, v)| v)
    }

    #[inline]
    pub fn contains_key(&self, key: &str) -> bool {
        self.items.iter().any(|(k, _)| k == key)
    }
}

/// Complete MP4 file handler.
#[derive(Debug)]
pub struct MP4File {
    pub info: MP4Info,
    pub tags: MP4Tags,
    pub path: String,
    moov_offset: usize,
    moov_size: usize,
    file_size: usize,
    parsed: bool,
}

impl MP4File {
    pub fn open(path: &str) -> Result<Self> {
        let data = std::fs::read(path)?;
        let mut f = Self::parse(&data, path)?;
        f.ensure_parsed_with_data(&data);
        Ok(f)
    }

    /// Parse: only find moov atom position (zero-copy, no data allocation).
    pub fn parse(data: &[u8], path: &str) -> Result<Self> {
        // Find moov atom using iterator (no Vec allocation for top-level)
        let moov = AtomIter::new(data, 0, data.len())
            .find_name(b"moov")
            .ok_or_else(|| MutagenError::MP4("No moov atom".into()))?;

        Ok(MP4File {
            info: MP4Info::default(),
            tags: MP4Tags::new(),
            path: path.to_string(),
            moov_offset: moov.data_offset,
            moov_size: moov.data_size,
            file_size: data.len(),
            parsed: false,
        })
    }

    /// Parse tags and info directly from the original file data (no copy).
    pub fn ensure_parsed_with_data(&mut self, data: &[u8]) {
        if self.parsed {
            return;
        }
        self.parsed = true;
        let moov_end = self.moov_offset + self.moov_size;
        if let Ok(mut info) = parse_mp4_info_iter(data, self.moov_offset, moov_end) {
            if info.length > 0.0 {
                info.bitrate = (self.file_size as f64 * 8.0 / info.length) as u32;
            }
            self.info = info;
        }
        if let Ok(tags) = parse_mp4_tags_iter(data, self.moov_offset, moov_end) {
            self.tags = tags;
        }
    }

    pub fn save(&self) -> Result<()> {
        Err(MutagenError::MP4("MP4 write not yet implemented".into()))
    }

    pub fn score(path: &str, data: &[u8]) -> u32 {
        let mut score = 0u32;
        let ext = path.rsplit('.').next().unwrap_or("");
        if ext.eq_ignore_ascii_case("m4a") || ext.eq_ignore_ascii_case("m4b")
            || ext.eq_ignore_ascii_case("mp4") || ext.eq_ignore_ascii_case("m4v") {
            score += 2;
        }

        if data.len() >= 8 {
            let name = &data[4..8];
            if name == b"ftyp" {
                score += 3;
            }
        }

        score
    }
}

/// Parse MP4 audio info using iterators (no intermediate Vec allocations).
fn parse_mp4_info_iter(data: &[u8], moov_start: usize, moov_end: usize) -> Result<MP4Info> {
    let mut duration = 0u64;
    let mut timescale = 1000u32;

    // Find mvhd
    if let Some(mvhd) = AtomIter::new(data, moov_start, moov_end).find_name(b"mvhd") {
        let mvhd_data = &data[mvhd.data_offset..mvhd.data_offset + mvhd.data_size];
        if !mvhd_data.is_empty() {
            let version = mvhd_data[0];
            if version == 0 && mvhd_data.len() >= 20 {
                timescale = u32::from_be_bytes([mvhd_data[12], mvhd_data[13], mvhd_data[14], mvhd_data[15]]);
                duration = u32::from_be_bytes([mvhd_data[16], mvhd_data[17], mvhd_data[18], mvhd_data[19]]) as u64;
            } else if version == 1 && mvhd_data.len() >= 28 {
                timescale = u32::from_be_bytes([mvhd_data[20], mvhd_data[21], mvhd_data[22], mvhd_data[23]]);
                duration = u64::from_be_bytes([
                    mvhd_data[24], mvhd_data[25], mvhd_data[26], mvhd_data[27],
                    mvhd_data[28], mvhd_data[29], mvhd_data[30], mvhd_data[31],
                ]);
            }
        }
    }

    let length = if timescale > 0 {
        duration as f64 / timescale as f64
    } else {
        0.0
    };

    let mut channels = 2u32;
    let mut sample_rate = 44100u32;
    let mut bits_per_sample = 16u32;
    let mut codec = String::from("mp4a");
    let codec_description = String::new();
    let mut bitrate = 0u32;

    // Walk trak atoms using iterator
    for trak in AtomIter::new(data, moov_start, moov_end) {
        if trak.name != *b"trak" { continue; }
        let trak_s = trak.data_offset;
        let trak_e = trak.data_offset + trak.data_size;

        let mdia = match AtomIter::new(data, trak_s, trak_e).find_name(b"mdia") {
            Some(a) => a,
            None => continue,
        };
        let mdia_s = mdia.data_offset;
        let mdia_e = mdia.data_offset + mdia.data_size;

        // Check hdlr for sound track
        let is_audio = AtomIter::new(data, mdia_s, mdia_e).any(|a| {
            if a.name == *b"hdlr" {
                let d = &data[a.data_offset..a.data_offset + a.data_size.min(12)];
                d.len() >= 12 && &d[8..12] == b"soun"
            } else {
                false
            }
        });

        if !is_audio { continue; }

        let minf = match AtomIter::new(data, mdia_s, mdia_e).find_name(b"minf") {
            Some(a) => a,
            None => continue,
        };
        let stbl = match AtomIter::new(data, minf.data_offset, minf.data_offset + minf.data_size).find_name(b"stbl") {
            Some(a) => a,
            None => continue,
        };
        let stsd = match AtomIter::new(data, stbl.data_offset, stbl.data_offset + stbl.data_size).find_name(b"stsd") {
            Some(a) => a,
            None => continue,
        };

        let stsd_data = &data[stsd.data_offset..stsd.data_offset + stsd.data_size];
        if stsd_data.len() >= 16 {
            let entry_data = &stsd_data[8..];
            if entry_data.len() >= 28 + 8 {
                let fmt = &entry_data[4..8];
                codec = String::from_utf8_lossy(fmt).to_string();

                let audio_entry = &entry_data[8..];
                if audio_entry.len() >= 20 {
                    channels = u16::from_be_bytes([audio_entry[16], audio_entry[17]]) as u32;
                    bits_per_sample = u16::from_be_bytes([audio_entry[18], audio_entry[19]]) as u32;
                    if audio_entry.len() >= 28 {
                        sample_rate = u16::from_be_bytes([audio_entry[24], audio_entry[25]]) as u32;
                    }
                }
            }
        }
    }

    if length > 0.0 {
        bitrate = (data.len() as f64 * 8.0 / length) as u32;
    }

    Ok(MP4Info {
        length,
        channels,
        sample_rate,
        bitrate,
        bits_per_sample,
        codec,
        codec_description,
    })
}

/// Parse MP4 tags using iterators (no intermediate Vec allocations).
fn parse_mp4_tags_iter(data: &[u8], moov_start: usize, moov_end: usize) -> Result<MP4Tags> {
    let mut tags = MP4Tags::new();

    // Navigate: udta/meta/ilst within moov using iterators
    let udta = match AtomIter::new(data, moov_start, moov_end).find_name(b"udta") {
        Some(a) => a,
        None => return Ok(tags),
    };

    let meta = match AtomIter::new(data, udta.data_offset, udta.data_offset + udta.data_size).find_name(b"meta") {
        Some(a) => a,
        None => return Ok(tags),
    };

    // meta atom has 4 bytes of version/flags before children
    let meta_offset = meta.data_offset + 4;
    let meta_end = meta.data_offset + meta.data_size;

    if meta_offset >= meta_end {
        return Ok(tags);
    }

    let ilst = match AtomIter::new(data, meta_offset, meta_end).find_name(b"ilst") {
        Some(a) => a,
        None => return Ok(tags),
    };

    // Iterate ilst children
    for item_atom in AtomIter::new(data, ilst.data_offset, ilst.data_offset + ilst.data_size) {
        let key = atom_name_to_key(&item_atom.name);

        // Iterate data atoms within each item
        for data_atom in AtomIter::new(data, item_atom.data_offset, item_atom.data_offset + item_atom.data_size) {
            if data_atom.name == *b"data" {
                let atom_data = &data[data_atom.data_offset..data_atom.data_offset + data_atom.data_size];
                if atom_data.len() < 8 {
                    continue;
                }

                let type_indicator = u32::from_be_bytes([atom_data[0], atom_data[1], atom_data[2], atom_data[3]]);
                let value_data = &atom_data[8..];

                let value = parse_mp4_data_value(&key, type_indicator, value_data);
                if let Some(v) = value {
                    match tags.get_mut(&key) {
                        Some(existing) => merge_mp4_values(existing, v),
                        None => { tags.items.push((key.clone(), v)); }
                    }
                }
            }
        }
    }

    Ok(tags)
}

fn atom_name_to_key(name: &[u8; 4]) -> String {
    if name[0] == 0xa9 {
        format!("\u{00a9}{}", String::from_utf8_lossy(&name[1..]))
    } else {
        String::from_utf8_lossy(name).to_string()
    }
}

fn parse_mp4_data_value(key: &str, type_indicator: u32, data: &[u8]) -> Option<MP4TagValue> {
    match type_indicator {
        1 => {
            let text = String::from_utf8_lossy(data).to_string();
            Some(MP4TagValue::Text(vec![text]))
        }
        2 => {
            let (result, _, _) = encoding_rs::UTF_16BE.decode(data);
            Some(MP4TagValue::Text(vec![result.into_owned()]))
        }
        13 => {
            Some(MP4TagValue::Cover(vec![MP4Cover {
                data: data.to_vec(),
                format: MP4CoverFormat::JPEG,
            }]))
        }
        14 => {
            Some(MP4TagValue::Cover(vec![MP4Cover {
                data: data.to_vec(),
                format: MP4CoverFormat::PNG,
            }]))
        }
        21 => {
            let val = match data.len() {
                1 => data[0] as i8 as i64,
                2 => i16::from_be_bytes([data[0], data[1]]) as i64,
                3 => {
                    let sign = if data[0] & 0x80 != 0 { 0xFF } else { 0x00 };
                    i32::from_be_bytes([sign, data[0], data[1], data[2]]) as i64
                }
                4 => i32::from_be_bytes([data[0], data[1], data[2], data[3]]) as i64,
                8 => i64::from_be_bytes([
                    data[0], data[1], data[2], data[3],
                    data[4], data[5], data[6], data[7],
                ]),
                _ => return None,
            };
            Some(MP4TagValue::Integer(vec![val]))
        }
        0 => {
            match key {
                "trkn" | "disk" => {
                    if data.len() >= 6 {
                        let a = i16::from_be_bytes([data[2], data[3]]) as i32;
                        let b = i16::from_be_bytes([data[4], data[5]]) as i32;
                        Some(MP4TagValue::IntPair(vec![(a, b)]))
                    } else if data.len() >= 4 {
                        let a = i16::from_be_bytes([data[2], data[3]]) as i32;
                        Some(MP4TagValue::IntPair(vec![(a, 0)]))
                    } else {
                        None
                    }
                }
                "gnre" => {
                    if data.len() >= 2 {
                        let genre_id = u16::from_be_bytes([data[0], data[1]]) as usize;
                        if genre_id > 0 && genre_id <= crate::id3::specs::GENRES.len() {
                            Some(MP4TagValue::Text(vec![
                                crate::id3::specs::GENRES[genre_id - 1].to_string()
                            ]))
                        } else {
                            Some(MP4TagValue::Integer(vec![genre_id as i64]))
                        }
                    } else {
                        None
                    }
                }
                _ => {
                    Some(MP4TagValue::Data(data.to_vec()))
                }
            }
        }
        _ => {
            Some(MP4TagValue::Data(data.to_vec()))
        }
    }
}

fn merge_mp4_values(existing: &mut MP4TagValue, new: MP4TagValue) {
    match (existing, new) {
        (MP4TagValue::Text(ref mut v), MP4TagValue::Text(new_v)) => v.extend(new_v),
        (MP4TagValue::Integer(ref mut v), MP4TagValue::Integer(new_v)) => v.extend(new_v),
        (MP4TagValue::Cover(ref mut v), MP4TagValue::Cover(new_v)) => v.extend(new_v),
        (MP4TagValue::FreeForm(ref mut v), MP4TagValue::FreeForm(new_v)) => v.extend(new_v),
        (MP4TagValue::IntPair(ref mut v), MP4TagValue::IntPair(new_v)) => v.extend(new_v),
        _ => {}
    }
}
