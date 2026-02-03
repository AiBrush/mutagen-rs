pub mod atom;

use std::collections::HashMap;
use crate::common::error::{MutagenError, Result};
use crate::mp4::atom::{Atom, parse_atoms, find_atom_path};

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

/// Complete MP4 tag container.
#[derive(Debug, Clone)]
pub struct MP4Tags {
    pub items: HashMap<String, MP4TagValue>,
}

impl MP4Tags {
    pub fn new() -> Self {
        MP4Tags {
            items: HashMap::new(),
        }
    }

    pub fn keys(&self) -> Vec<String> {
        self.items.keys().cloned().collect()
    }

    pub fn get(&self, key: &str) -> Option<&MP4TagValue> {
        self.items.get(key)
    }
}

/// Complete MP4 file handler.
#[derive(Debug)]
pub struct MP4File {
    pub info: MP4Info,
    pub tags: MP4Tags,
    pub path: String,
}

impl MP4File {
    pub fn open(path: &str) -> Result<Self> {
        let data = std::fs::read(path)?;
        Self::parse(&data, path)
    }

    pub fn parse(data: &[u8], path: &str) -> Result<Self> {
        let atoms = parse_atoms(data, 0, data.len())?;

        // Parse audio info from moov/trak/mdia/minf/stbl/stsd
        let info = parse_mp4_info(data, &atoms)?;

        // Parse tags from moov/udta/meta/ilst
        let tags = parse_mp4_tags(data, &atoms)?;

        Ok(MP4File {
            info,
            tags,
            path: path.to_string(),
        })
    }

    pub fn save(&self) -> Result<()> {
        // MP4 writing is complex. For now, basic support.
        Err(MutagenError::MP4("MP4 write not yet implemented".into()))
    }

    pub fn score(path: &str, data: &[u8]) -> u32 {
        let mut score = 0u32;
        let ext = path.rsplit('.').next().unwrap_or("").to_lowercase();
        if ext == "m4a" || ext == "m4b" || ext == "mp4" || ext == "m4v" {
            score += 2;
        }

        // Check for ftyp atom
        if data.len() >= 8 {
            let name = &data[4..8];
            if name == b"ftyp" {
                score += 3;
            }
        }

        score
    }
}

/// Parse MP4 audio info from the atom tree.
fn parse_mp4_info(data: &[u8], atoms: &[Atom]) -> Result<MP4Info> {
    // Find moov atom
    let moov = atoms.iter().find(|a| a.name == *b"moov")
        .ok_or_else(|| MutagenError::MP4("No moov atom".into()))?;

    let moov_children = parse_atoms(data, moov.data_offset, moov.data_offset + moov.data_size)?;

    // Find mvhd for duration info
    let mut duration = 0u64;
    let mut timescale = 1000u32;

    if let Some(mvhd) = moov_children.iter().find(|a| a.name == *b"mvhd") {
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

    // Find audio track info
    let mut channels = 2u32;
    let mut sample_rate = 44100u32;
    let mut bits_per_sample = 16u32;
    let mut codec = String::from("mp4a");
    let mut codec_description = String::new();
    let mut bitrate = 0u32;

    // Walk trak/mdia/minf/stbl/stsd
    for trak in moov_children.iter().filter(|a| a.name == *b"trak") {
        let trak_children = parse_atoms(data, trak.data_offset, trak.data_offset + trak.data_size)?;

        if let Some(mdia) = trak_children.iter().find(|a| a.name == *b"mdia") {
            let mdia_children = parse_atoms(data, mdia.data_offset, mdia.data_offset + mdia.data_size)?;

            // Check hdlr to confirm this is a sound track
            let is_audio = mdia_children.iter().any(|a| {
                if a.name == *b"hdlr" {
                    let d = &data[a.data_offset..a.data_offset + a.data_size.min(12)];
                    d.len() >= 12 && &d[8..12] == b"soun"
                } else {
                    false
                }
            });

            if !is_audio {
                continue;
            }

            if let Some(minf) = mdia_children.iter().find(|a| a.name == *b"minf") {
                let minf_children = parse_atoms(data, minf.data_offset, minf.data_offset + minf.data_size)?;
                if let Some(stbl) = minf_children.iter().find(|a| a.name == *b"stbl") {
                    let stbl_children = parse_atoms(data, stbl.data_offset, stbl.data_offset + stbl.data_size)?;
                    if let Some(stsd) = stbl_children.iter().find(|a| a.name == *b"stsd") {
                        let stsd_data = &data[stsd.data_offset..stsd.data_offset + stsd.data_size];
                        if stsd_data.len() >= 16 {
                            // Skip version(4) + entry_count(4)
                            let entry_data = &stsd_data[8..];
                            if entry_data.len() >= 28 + 8 {
                                // AudioSampleEntry: skip size(4) + format(4) + reserved(6) + data_ref_index(2)
                                // + reserved(8) = 24 bytes, then channels(2), sample_size(2), ...
                                let fmt = &entry_data[4..8];
                                codec = String::from_utf8_lossy(fmt).to_string();

                                let audio_entry = &entry_data[8..]; // after size+format
                                if audio_entry.len() >= 20 {
                                    // reserved(6) + data_ref_index(2) + reserved(8)
                                    channels = u16::from_be_bytes([audio_entry[16], audio_entry[17]]) as u32;
                                    bits_per_sample = u16::from_be_bytes([audio_entry[18], audio_entry[19]]) as u32;
                                    // sample_rate at offset 24 (16.16 fixed point)
                                    if audio_entry.len() >= 28 {
                                        sample_rate = u16::from_be_bytes([audio_entry[24], audio_entry[25]]) as u32;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Estimate bitrate
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

/// Parse MP4 tags from ilst atom.
fn parse_mp4_tags(data: &[u8], atoms: &[Atom]) -> Result<MP4Tags> {
    let mut tags = MP4Tags::new();

    // Navigate: moov/udta/meta/ilst
    let moov = match atoms.iter().find(|a| a.name == *b"moov") {
        Some(a) => a,
        None => return Ok(tags),
    };

    let moov_children = parse_atoms(data, moov.data_offset, moov.data_offset + moov.data_size)?;
    let udta = match moov_children.iter().find(|a| a.name == *b"udta") {
        Some(a) => a,
        None => return Ok(tags),
    };

    let udta_children = parse_atoms(data, udta.data_offset, udta.data_offset + udta.data_size)?;
    let meta = match udta_children.iter().find(|a| a.name == *b"meta") {
        Some(a) => a,
        None => return Ok(tags),
    };

    // meta atom has 4 bytes of version/flags before children
    let meta_offset = meta.data_offset + 4;
    let meta_end = meta.data_offset + meta.data_size;

    if meta_offset >= meta_end {
        return Ok(tags);
    }

    let meta_children = parse_atoms(data, meta_offset, meta_end)?;
    let ilst = match meta_children.iter().find(|a| a.name == *b"ilst") {
        Some(a) => a,
        None => return Ok(tags),
    };

    let ilst_children = parse_atoms(data, ilst.data_offset, ilst.data_offset + ilst.data_size)?;

    for item_atom in &ilst_children {
        let key = atom_name_to_key(&item_atom.name);
        let item_children = parse_atoms(data, item_atom.data_offset, item_atom.data_offset + item_atom.data_size)?;

        // Look for 'data' atom within each item
        for data_atom in &item_children {
            if data_atom.name == *b"data" {
                let atom_data = &data[data_atom.data_offset..data_atom.data_offset + data_atom.data_size];
                if atom_data.len() < 8 {
                    continue;
                }

                // data atom: type_indicator(4) + locale(4) + value
                let type_indicator = u32::from_be_bytes([atom_data[0], atom_data[1], atom_data[2], atom_data[3]]);
                let value_data = &atom_data[8..];

                let value = parse_mp4_data_value(&key, type_indicator, value_data);
                if let Some(v) = value {
                    // Merge with existing value if present
                    match tags.items.get_mut(&key) {
                        Some(existing) => merge_mp4_values(existing, v),
                        None => { tags.items.insert(key.clone(), v); }
                    }
                }
            }
        }
    }

    Ok(tags)
}

fn atom_name_to_key(name: &[u8; 4]) -> String {
    // Some atoms use special characters like \xa9
    if name[0] == 0xa9 {
        format!("\u{00a9}{}", String::from_utf8_lossy(&name[1..]))
    } else {
        String::from_utf8_lossy(name).to_string()
    }
}

fn parse_mp4_data_value(key: &str, type_indicator: u32, data: &[u8]) -> Option<MP4TagValue> {
    match type_indicator {
        1 => {
            // UTF-8 text
            let text = String::from_utf8_lossy(data).to_string();
            Some(MP4TagValue::Text(vec![text]))
        }
        2 => {
            // UTF-16 text
            let (result, _, _) = encoding_rs::UTF_16BE.decode(data);
            Some(MP4TagValue::Text(vec![result.into_owned()]))
        }
        13 => {
            // JPEG image
            Some(MP4TagValue::Cover(vec![MP4Cover {
                data: data.to_vec(),
                format: MP4CoverFormat::JPEG,
            }]))
        }
        14 => {
            // PNG image
            Some(MP4TagValue::Cover(vec![MP4Cover {
                data: data.to_vec(),
                format: MP4CoverFormat::PNG,
            }]))
        }
        21 => {
            // Signed integer (1/2/3/4/8 bytes)
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
            // Implicit type - guess based on key
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
            // Store as raw data
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
        _ => {} // Don't merge incompatible types
    }
}
