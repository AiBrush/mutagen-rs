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

    /// Set a tag value, replacing existing or inserting new.
    pub fn set(&mut self, key: &str, value: MP4TagValue) {
        if let Some((_, v)) = self.items.iter_mut().find(|(k, _)| k == key) {
            *v = value;
        } else {
            self.items.push((key.to_string(), value));
        }
    }

    /// Remove a tag by key.
    pub fn delete(&mut self, key: &str) {
        self.items.retain(|(k, _)| k != key);
    }

    /// Render all tags as an ilst atom.
    pub fn render_ilst(&self) -> Vec<u8> {
        let mut ilst_data = Vec::new();
        for (key, value) in &self.items {
            let item_data = render_tag_item(key, value);
            ilst_data.extend_from_slice(&item_data);
        }
        make_atom(b"ilst", &ilst_data)
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

    /// Save tags back to the file.
    pub fn save(&self) -> Result<()> {
        save_mp4_tags(&self.path, &self.tags)
    }

    /// Delete all tags from the file.
    pub fn delete_tags(&self) -> Result<()> {
        let empty = MP4Tags::new();
        save_mp4_tags(&self.path, &empty)
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
        let item_start = item_atom.data_offset;
        let item_end = item_atom.data_offset + item_atom.data_size;

        // For freeform atoms (----), build key from mean+name sub-atoms
        let key = if item_atom.name == *b"----" {
            build_freeform_key(data, item_start, item_end)
        } else {
            atom_name_to_key(&item_atom.name)
        };

        // Iterate data atoms within each item
        for data_atom in AtomIter::new(data, item_start, item_end) {
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

/// Build a freeform atom key in the format "----:mean:name".
/// Freeform atoms contain 'mean' and 'name' sub-atoms that define the key.
pub fn build_freeform_key(data: &[u8], start: usize, end: usize) -> String {
    let mut mean_str = String::new();
    let mut name_str = String::new();

    for atom in AtomIter::new(data, start, end) {
        if atom.name == *b"mean" && atom.data_size > 4 {
            // Skip 4 bytes of version/flags
            let s = atom.data_offset + 4;
            let e = atom.data_offset + atom.data_size;
            if e <= data.len() {
                mean_str = String::from_utf8_lossy(&data[s..e]).into_owned();
            }
        } else if atom.name == *b"name" && atom.data_size > 4 {
            let s = atom.data_offset + 4;
            let e = atom.data_offset + atom.data_size;
            if e <= data.len() {
                name_str = String::from_utf8_lossy(&data[s..e]).into_owned();
            }
        }
    }

    if !mean_str.is_empty() && !name_str.is_empty() {
        format!("----:{}:{}", mean_str, name_str)
    } else if !mean_str.is_empty() {
        format!("----:{}", mean_str)
    } else {
        "----".to_string()
    }
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

// ────────────────────────────────────────────────────────
// MP4 Write Support
// ────────────────────────────────────────────────────────

/// Build a raw atom: [size(4)][name(4)][data].
fn make_atom(name: &[u8; 4], data: &[u8]) -> Vec<u8> {
    let size = (8 + data.len()) as u32;
    let mut buf = Vec::with_capacity(size as usize);
    buf.extend_from_slice(&size.to_be_bytes());
    buf.extend_from_slice(name);
    buf.extend_from_slice(data);
    buf
}

/// Build a data atom with type indicator and locale (0).
fn make_data_atom(type_indicator: u32, payload: &[u8]) -> Vec<u8> {
    // data atom: [size][name="data"][type(4)][locale(4)][payload]
    let data_size = (8 + 4 + 4 + payload.len()) as u32;
    let mut buf = Vec::with_capacity(data_size as usize);
    buf.extend_from_slice(&data_size.to_be_bytes());
    buf.extend_from_slice(b"data");
    buf.extend_from_slice(&type_indicator.to_be_bytes());
    buf.extend_from_slice(&[0u8; 4]); // locale
    buf.extend_from_slice(payload);
    buf
}

/// Convert a key string to a 4-byte atom name.
fn key_to_atom_name(key: &str) -> [u8; 4] {
    let bytes = key.as_bytes();
    // Handle \u{00a9}xxx keys (© symbol = 0xC2 0xA9 in UTF-8)
    if bytes.len() >= 3 && bytes[0] == 0xC2 && bytes[1] == 0xA9 {
        let rest = &key[2..]; // skip the © character
        let rb = rest.as_bytes();
        let mut name = [0xa9, 0, 0, 0];
        for (i, &b) in rb.iter().take(3).enumerate() {
            name[i + 1] = b;
        }
        return name;
    }
    // Standard 4-byte names
    let mut name = [0u8; 4];
    for (i, &b) in bytes.iter().take(4).enumerate() {
        name[i] = b;
    }
    name
}

/// Render a single tag item as an atom (item_atom wrapping data atoms).
fn render_tag_item(key: &str, value: &MP4TagValue) -> Vec<u8> {
    // Freeform (----) atoms have a special structure
    if key.starts_with("----:") {
        return render_freeform_item(key, value);
    }

    let atom_name = key_to_atom_name(key);
    let data_atoms = render_data_atoms(key, value);
    make_atom(&atom_name, &data_atoms)
}

/// Render data atoms for a tag value.
fn render_data_atoms(_key: &str, value: &MP4TagValue) -> Vec<u8> {
    let mut buf = Vec::new();
    match value {
        MP4TagValue::Text(texts) => {
            for text in texts {
                buf.extend_from_slice(&make_data_atom(1, text.as_bytes()));
            }
        }
        MP4TagValue::Integer(ints) => {
            for &val in ints {
                // Use the smallest representation that fits
                let payload = if val >= i8::MIN as i64 && val <= i8::MAX as i64 {
                    vec![val as u8]
                } else if val >= i16::MIN as i64 && val <= i16::MAX as i64 {
                    (val as i16).to_be_bytes().to_vec()
                } else if val >= i32::MIN as i64 && val <= i32::MAX as i64 {
                    (val as i32).to_be_bytes().to_vec()
                } else {
                    val.to_be_bytes().to_vec()
                };
                buf.extend_from_slice(&make_data_atom(21, &payload));
            }
        }
        MP4TagValue::IntPair(pairs) => {
            for &(a, b) in pairs {
                // trkn/disk format: 2 bytes padding + 2 bytes num + 2 bytes total + 2 bytes padding
                let mut payload = vec![0u8; 8];
                payload[2..4].copy_from_slice(&(a as i16).to_be_bytes());
                payload[4..6].copy_from_slice(&(b as i16).to_be_bytes());
                buf.extend_from_slice(&make_data_atom(0, &payload));
            }
        }
        MP4TagValue::Bool(val) => {
            buf.extend_from_slice(&make_data_atom(21, &[if *val { 1 } else { 0 }]));
        }
        MP4TagValue::Cover(covers) => {
            for cover in covers {
                let type_ind = cover.format as u32;
                buf.extend_from_slice(&make_data_atom(type_ind, &cover.data));
            }
        }
        MP4TagValue::FreeForm(forms) => {
            for form in forms {
                buf.extend_from_slice(&make_data_atom(form.dataformat, &form.data));
            }
        }
        MP4TagValue::Data(d) => {
            buf.extend_from_slice(&make_data_atom(0, d));
        }
    }
    buf
}

/// Render a freeform (----) atom with mean/name/data sub-atoms.
fn render_freeform_item(key: &str, value: &MP4TagValue) -> Vec<u8> {
    // Parse key: "----:com.apple.iTunes:NAME"
    let parts: Vec<&str> = key.splitn(3, ':').collect();
    let mean = if parts.len() > 1 { parts[1] } else { "com.apple.iTunes" };
    let name = if parts.len() > 2 { parts[2] } else { "" };

    let mut inner = Vec::new();

    // mean atom: [size][name="mean"][version(4)][mean_string]
    let mean_size = (8 + 4 + mean.len()) as u32;
    inner.extend_from_slice(&mean_size.to_be_bytes());
    inner.extend_from_slice(b"mean");
    inner.extend_from_slice(&[0u8; 4]); // version/flags
    inner.extend_from_slice(mean.as_bytes());

    // name atom: [size][name="name"][version(4)][name_string]
    let name_size = (8 + 4 + name.len()) as u32;
    inner.extend_from_slice(&name_size.to_be_bytes());
    inner.extend_from_slice(b"name");
    inner.extend_from_slice(&[0u8; 4]); // version/flags
    inner.extend_from_slice(name.as_bytes());

    // data atoms
    inner.extend_from_slice(&render_data_atoms(key, value));

    make_atom(b"----", &inner)
}

/// Save MP4 tags to a file.
///
/// Strategy:
/// 1. Read file, locate moov atom
/// 2. Build new ilst from tags
/// 3. Rebuild moov with new ilst (preserving non-tag atoms)
/// 4. If moov size changed and moov is before mdat, fix stco/co64 offsets
/// 5. Write output file
pub fn save_mp4_tags(path: &str, tags: &MP4Tags) -> Result<()> {
    let data = std::fs::read(path)?;

    // Find moov atom
    let moov = AtomIter::new(&data, 0, data.len())
        .find_name(b"moov")
        .ok_or_else(|| MutagenError::MP4("No moov atom found".into()))?;

    let moov_start = moov.offset; // includes header
    let moov_header_size = moov.header_size as usize;
    let moov_body_start = moov.data_offset;
    let moov_body_end = moov.data_offset + moov.data_size;

    // Render new ilst
    let new_ilst = tags.render_ilst();

    // Rebuild moov body: keep all atoms except udta, then append new udta/meta/ilst
    let mut new_moov_body = Vec::new();
    let mut had_udta = false;

    for atom in AtomIter::new(&data, moov_body_start, moov_body_end) {
        if atom.name == *b"udta" {
            had_udta = true;
            // Rebuild udta: keep non-meta atoms, replace meta with new meta/ilst
            let mut new_udta_body = Vec::new();
            let mut had_meta = false;

            for ua in AtomIter::new(&data, atom.data_offset, atom.data_offset + atom.data_size) {
                if ua.name == *b"meta" {
                    had_meta = true;
                    // Rebuild meta: keep non-ilst atoms, insert new ilst
                    let mut new_meta_body = Vec::with_capacity(4 + new_ilst.len());
                    // meta has 4 bytes version/flags
                    let meta_inner_start = ua.data_offset + 4;
                    let meta_inner_end = ua.data_offset + ua.data_size;
                    new_meta_body.extend_from_slice(&[0u8; 4]); // version/flags

                    if meta_inner_start < meta_inner_end {
                        // Copy non-ilst atoms from original meta
                        for ma in AtomIter::new(&data, meta_inner_start, meta_inner_end) {
                            if ma.name != *b"ilst" {
                                let orig = &data[ma.offset..ma.offset + ma.size];
                                new_meta_body.extend_from_slice(orig);
                            }
                        }
                    }

                    // Append new ilst (even if empty, to clear tags)
                    if !new_ilst.is_empty() {
                        new_meta_body.extend_from_slice(&new_ilst);
                    }

                    new_udta_body.extend_from_slice(&make_atom(b"meta", &new_meta_body));
                } else {
                    // Copy other udta children as-is
                    let orig = &data[ua.offset..ua.offset + ua.size];
                    new_udta_body.extend_from_slice(orig);
                }
            }

            if !had_meta && !new_ilst.is_empty() {
                // Create meta with version/flags + hdlr + ilst
                let mut meta_body = Vec::new();
                meta_body.extend_from_slice(&[0u8; 4]); // version/flags
                // hdlr atom for meta
                meta_body.extend_from_slice(&make_meta_hdlr());
                meta_body.extend_from_slice(&new_ilst);
                new_udta_body.extend_from_slice(&make_atom(b"meta", &meta_body));
            }

            new_moov_body.extend_from_slice(&make_atom(b"udta", &new_udta_body));
        } else {
            // Copy non-udta moov children as-is
            let orig = &data[atom.offset..atom.offset + atom.size];
            new_moov_body.extend_from_slice(orig);
        }
    }

    if !had_udta && !new_ilst.is_empty() {
        // Create udta/meta/ilst from scratch
        let mut meta_body = Vec::new();
        meta_body.extend_from_slice(&[0u8; 4]); // version/flags
        meta_body.extend_from_slice(&make_meta_hdlr());
        meta_body.extend_from_slice(&new_ilst);
        let meta_atom = make_atom(b"meta", &meta_body);
        new_moov_body.extend_from_slice(&make_atom(b"udta", &meta_atom));
    }

    // Build new moov atom
    let new_moov = make_atom(b"moov", &new_moov_body);

    // Calculate size delta for offset fixup
    let old_moov_size = moov_header_size + moov.data_size;
    let new_moov_size = new_moov.len();
    let delta = new_moov_size as i64 - old_moov_size as i64;

    // Apply stco/co64 fixup if moov is before mdat and size changed
    let mut new_moov_fixed = new_moov;
    if delta != 0 {
        // Check if moov is before any mdat
        let moov_before_mdat = AtomIter::new(&data, 0, data.len()).any(|a| {
            a.name == *b"mdat" && a.offset > moov_start
        });
        if moov_before_mdat {
            fix_chunk_offsets(&mut new_moov_fixed, delta);
        }
    }

    // Assemble output: [before moov][new moov][after moov]
    let moov_end = moov_start + old_moov_size;
    let mut output = Vec::with_capacity(data.len().saturating_add_signed(delta as isize));
    output.extend_from_slice(&data[..moov_start]);
    output.extend_from_slice(&new_moov_fixed);
    if moov_end < data.len() {
        output.extend_from_slice(&data[moov_end..]);
    }

    std::fs::write(path, &output)?;
    Ok(())
}

/// Create a minimal hdlr atom for the meta atom.
fn make_meta_hdlr() -> Vec<u8> {
    // hdlr: version/flags(4) + pre_defined(4) + handler_type(4) + reserved(12) + name(1)
    let mut body = Vec::with_capacity(25);
    body.extend_from_slice(&[0u8; 4]); // version/flags
    body.extend_from_slice(&[0u8; 4]); // pre_defined
    body.extend_from_slice(b"mdir");   // handler_type
    body.extend_from_slice(b"appl");   // reserved[0]
    body.extend_from_slice(&[0u8; 8]); // reserved[1..2]
    body.push(0); // name (empty string with null terminator)
    make_atom(b"hdlr", &body)
}

/// Fix stco and co64 chunk offsets within a moov atom buffer by delta.
fn fix_chunk_offsets(moov_buf: &mut [u8], delta: i64) {
    // moov_buf starts with the moov header (8 bytes), body follows
    if moov_buf.len() < 8 {
        return;
    }
    fix_chunk_offsets_in(moov_buf, 8, moov_buf.len(), delta);
}

/// Recursively scan for stco/co64 atoms and adjust offsets.
fn fix_chunk_offsets_in(buf: &mut [u8], start: usize, end: usize, delta: i64) {
    let mut pos = start;
    while pos + 8 <= end {
        let size = u32::from_be_bytes([buf[pos], buf[pos + 1], buf[pos + 2], buf[pos + 3]]) as usize;
        if size < 8 || pos + size > end {
            break;
        }
        let name: [u8; 4] = [buf[pos + 4], buf[pos + 5], buf[pos + 6], buf[pos + 7]];
        let data_start = pos + 8;
        let data_end = pos + size;

        match &name {
            b"stco" => {
                // stco: version(1) + flags(3) + entry_count(4) + entries(4 each)
                if data_end - data_start >= 8 {
                    let count = u32::from_be_bytes([
                        buf[data_start + 4], buf[data_start + 5],
                        buf[data_start + 6], buf[data_start + 7],
                    ]) as usize;
                    let entries_start = data_start + 8;
                    for i in 0..count {
                        let off = entries_start + i * 4;
                        if off + 4 > data_end { break; }
                        let old = u32::from_be_bytes([buf[off], buf[off + 1], buf[off + 2], buf[off + 3]]);
                        let new_val = (old as i64 + delta) as u32;
                        buf[off..off + 4].copy_from_slice(&new_val.to_be_bytes());
                    }
                }
            }
            b"co64" => {
                // co64: version(1) + flags(3) + entry_count(4) + entries(8 each)
                if data_end - data_start >= 8 {
                    let count = u32::from_be_bytes([
                        buf[data_start + 4], buf[data_start + 5],
                        buf[data_start + 6], buf[data_start + 7],
                    ]) as usize;
                    let entries_start = data_start + 8;
                    for i in 0..count {
                        let off = entries_start + i * 8;
                        if off + 8 > data_end { break; }
                        let old = u64::from_be_bytes([
                            buf[off], buf[off + 1], buf[off + 2], buf[off + 3],
                            buf[off + 4], buf[off + 5], buf[off + 6], buf[off + 7],
                        ]);
                        let new_val = (old as i64 + delta) as u64;
                        buf[off..off + 8].copy_from_slice(&new_val.to_be_bytes());
                    }
                }
            }
            // Container atoms: recurse into children
            b"trak" | b"mdia" | b"minf" | b"stbl" | b"edts" | b"dinf" | b"traf" | b"moof" => {
                fix_chunk_offsets_in(buf, data_start, data_end, delta);
            }
            _ => {}
        }

        pos += size;
        if pos <= start { break; } // prevent infinite loop
    }
}
