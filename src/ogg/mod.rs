use std::io::{Read, Write, Seek, SeekFrom};
use crate::common::error::{MutagenError, Result};
use crate::vorbis::VorbisComment;

/// A single OGG page.
#[derive(Debug, Clone)]
pub struct OggPage {
    pub version: u8,
    pub header_type: u8,
    pub granule_position: i64,
    pub serial_number: u32,
    pub page_sequence: u32,
    pub checksum: u32,
    pub segments: Vec<u8>,     // Segment table
    pub packets: Vec<Vec<u8>>, // Reassembled packets
    pub offset: usize,         // Offset in file
    pub size: usize,           // Total page size
}

impl OggPage {
    /// Parse an OGG page from data at the given offset.
    #[inline]
    pub fn parse(data: &[u8], offset: usize) -> Result<Self> {
        if offset + 27 > data.len() {
            return Err(MutagenError::Ogg("Page header too short".into()));
        }

        let d = &data[offset..];

        // Check OggS magic
        if &d[0..4] != b"OggS" {
            return Err(MutagenError::Ogg("Not an OGG page".into()));
        }

        let version = d[4];
        let header_type = d[5];
        let granule_position = i64::from_le_bytes([
            d[6], d[7], d[8], d[9], d[10], d[11], d[12], d[13],
        ]);
        let serial_number = u32::from_le_bytes([d[14], d[15], d[16], d[17]]);
        let page_sequence = u32::from_le_bytes([d[18], d[19], d[20], d[21]]);
        let checksum = u32::from_le_bytes([d[22], d[23], d[24], d[25]]);
        let num_segments = d[26] as usize;

        if offset + 27 + num_segments > data.len() {
            return Err(MutagenError::Ogg("Segment table extends past data".into()));
        }

        let segments = d[27..27 + num_segments].to_vec();
        let total_data_size: usize = segments.iter().map(|&s| s as usize).sum();
        let header_size = 27 + num_segments;

        if offset + header_size + total_data_size > data.len() {
            return Err(MutagenError::Ogg("Page data extends past file".into()));
        }

        // Reassemble packets from segments
        let page_data = &d[header_size..header_size + total_data_size];
        let mut packets = Vec::new();
        let mut current_packet = Vec::new();
        let mut data_pos = 0;

        for &seg_size in &segments {
            let seg_data = &page_data[data_pos..data_pos + seg_size as usize];
            current_packet.extend_from_slice(seg_data);
            data_pos += seg_size as usize;

            if seg_size < 255 {
                // End of packet
                packets.push(std::mem::take(&mut current_packet));
            }
        }

        if !current_packet.is_empty() {
            packets.push(current_packet);
        }

        Ok(OggPage {
            version,
            header_type,
            granule_position,
            serial_number,
            page_sequence,
            checksum,
            segments,
            packets,
            offset,
            size: header_size + total_data_size,
        })
    }

    /// Check if this is a first page (BOS = Beginning of Stream).
    pub fn is_first(&self) -> bool {
        self.header_type & 0x02 != 0
    }

    /// Check if this is a last page (EOS = End of Stream).
    pub fn is_last(&self) -> bool {
        self.header_type & 0x04 != 0
    }

    /// Check if this is a continuation page.
    pub fn is_continuation(&self) -> bool {
        self.header_type & 0x01 != 0
    }

    /// Find the last OGG page in the data (scanning backward).
    pub fn find_last(data: &[u8], serial: u32) -> Option<OggPage> {
        // Use find_last_granule for the common case, fall back to full parse only if needed
        if let Some(granule) = find_last_granule(data, serial) {
            // Build a minimal OggPage with just the granule position
            return Some(OggPage {
                version: 0,
                header_type: 0,
                granule_position: granule,
                serial_number: serial,
                page_sequence: 0,
                checksum: 0,
                segments: Vec::new(),
                packets: Vec::new(),
                offset: 0,
                size: 0,
            });
        }
        None
    }
}

/// Find the granule position of the last OGG page with the given serial number.
/// Zero-allocation: only reads the 27-byte page header, no packet reassembly.
#[inline]
pub fn find_last_granule(data: &[u8], serial: u32) -> Option<i64> {
    use memchr::memmem;

    // Tiered search: try small window first (covers most files), then expand.
    // Most OGG files have the last page within the last 8KB.
    for &window in &[8192usize, 65536] {
        let search_start = data.len().saturating_sub(window);
        let search_data = &data[search_start..];

        // Use SIMD-accelerated reverse search for "OggS" magic
        for pos in memmem::rfind_iter(search_data, b"OggS") {
            let abs_pos = search_start + pos;
            if abs_pos + 27 > data.len() {
                continue;
            }
            let d = &data[abs_pos..];
            let page_serial = u32::from_le_bytes([d[14], d[15], d[16], d[17]]);
            if page_serial == serial {
                let granule = i64::from_le_bytes([
                    d[6], d[7], d[8], d[9], d[10], d[11], d[12], d[13],
                ]);
                return Some(granule);
            }
        }
        // If file is smaller than the window, no point expanding
        if data.len() <= window { break; }
    }
    None
}

/// Parsed OGG Vorbis audio info.
#[derive(Debug, Clone)]
pub struct OggVorbisInfo {
    pub length: f64,
    pub channels: u8,
    pub sample_rate: u32,
    pub bitrate: u32,       // nominal bitrate
    pub bitrate_max: u32,
    pub bitrate_min: u32,
}

/// Complete OGG Vorbis file handler.
#[derive(Debug)]
pub struct OggVorbisFile {
    pub info: OggVorbisInfo,
    pub tags: VorbisComment,
    pub path: String,
    raw_comment_data: Vec<u8>,
    tags_parsed: bool,
    page1_size: usize,
    serial: u32,
}

/// Lightweight page header — no packet reassembly, zero allocations.
#[inline(always)]
fn ogg_page_header(data: &[u8], offset: usize) -> Option<(u32, usize)> {
    if offset + 27 > data.len() { return None; }
    let d = &data[offset..];
    if &d[0..4] != b"OggS" { return None; }
    let serial = u32::from_le_bytes([d[14], d[15], d[16], d[17]]);
    let num_seg = d[26] as usize;
    let header_size = 27 + num_seg;
    if offset + header_size > data.len() { return None; }
    let data_size: usize = d[27..27 + num_seg].iter().map(|&s| s as usize).sum();
    Some((serial, header_size + data_size))
}

/// Extract the first packet from an OGG page without allocating.
/// Returns a slice into the original data.
#[inline(always)]
fn ogg_first_packet(data: &[u8], offset: usize) -> Option<&[u8]> {
    if offset + 27 > data.len() { return None; }
    let d = &data[offset..];
    let num_seg = d[26] as usize;
    let header_size = 27 + num_seg;
    if offset + header_size > data.len() { return None; }
    let mut packet_size = 0usize;
    for &seg in &d[27..header_size] {
        packet_size += seg as usize;
        if seg < 255 { break; }
    }
    let pkt_start = offset + header_size;
    if pkt_start + packet_size > data.len() { return None; }
    Some(&data[pkt_start..pkt_start + packet_size])
}

/// Assemble the first packet from an OGG page, handling multi-page packets.
/// Returns the complete packet data across all continuation pages.
pub fn ogg_assemble_first_packet(data: &[u8], offset: usize) -> Option<Vec<u8>> {
    // Pre-scan to compute total size for single allocation
    let mut total_size = 0usize;
    let mut scan_offset = offset;
    loop {
        if scan_offset + 27 > data.len() { break; }
        let d = &data[scan_offset..];
        if &d[0..4] != b"OggS" { break; }
        let num_seg = d[26] as usize;
        let header_size = 27 + num_seg;
        if scan_offset + header_size > data.len() { break; }
        let mut page_done = false;
        for &seg in &d[27..27 + num_seg] {
            total_size += seg as usize;
            if seg < 255 { page_done = true; break; }
        }
        if page_done { break; }
        let total_data_size: usize = d[27..27 + num_seg].iter().map(|&s| s as usize).sum();
        scan_offset += header_size + total_data_size;
    }
    if total_size == 0 { return None; }

    let mut result = Vec::with_capacity(total_size);
    let mut page_offset = offset;

    loop {
        if page_offset + 27 > data.len() { break; }
        let d = &data[page_offset..];
        if &d[0..4] != b"OggS" { break; }

        let num_seg = d[26] as usize;
        let header_size = 27 + num_seg;
        if page_offset + header_size > data.len() { break; }

        let mut data_pos = page_offset + header_size;
        let mut packet_complete = false;

        for &seg in &d[27..27 + num_seg] {
            let seg_size = seg as usize;
            if data_pos + seg_size > data.len() {
                return if result.is_empty() { None } else { Some(result) };
            }
            result.extend_from_slice(&data[data_pos..data_pos + seg_size]);
            data_pos += seg_size;
            if seg < 255 {
                packet_complete = true;
                break;
            }
        }

        if packet_complete { break; }

        let total_data_size: usize = d[27..27 + num_seg].iter().map(|&s| s as usize).sum();
        page_offset += header_size + total_data_size;
    }

    if result.is_empty() { None } else { Some(result) }
}

impl OggVorbisFile {
    pub fn open(path: &str) -> Result<Self> {
        let data = std::fs::read(path)?;
        Self::parse(&data, path)
    }

    /// Parse using lightweight inline page headers — no OggPage allocation,
    /// no Vec<u8> segment tables, no Vec<Vec<u8>> packet reassembly.
    /// Only parses the identification header. Duration + comments are deferred.
    #[inline(always)]
    pub fn parse(data: &[u8], path: &str) -> Result<Self> {
        // Page 1: identification header (zero-alloc)
        let (serial, page1_size) = ogg_page_header(data, 0)
            .ok_or_else(|| MutagenError::Ogg("Cannot parse first OGG page".into()))?;

        let id_packet = ogg_first_packet(data, 0)
            .ok_or_else(|| MutagenError::Ogg("No packets in first page".into()))?;

        if id_packet.len() < 30 || &id_packet[0..7] != b"\x01vorbis" {
            return Err(MutagenError::Ogg("Not a Vorbis stream".into()));
        }

        let channels = id_packet[11];
        let sample_rate = u32::from_le_bytes([
            id_packet[12], id_packet[13], id_packet[14], id_packet[15],
        ]);
        let bitrate = u32::from_le_bytes([
            id_packet[20], id_packet[21], id_packet[22], id_packet[23],
        ]);

        Ok(OggVorbisFile {
            info: OggVorbisInfo {
                length: 0.0,
                channels,
                sample_rate,
                bitrate,
                bitrate_max: 0,
                bitrate_min: 0,
            },
            tags: VorbisComment::new(),
            path: path.to_string(),
            raw_comment_data: Vec::new(),
            tags_parsed: true,
            page1_size,
            serial,
        })
    }

    /// Complete parsing: duration, bitrate, and comment data from original file data.
    pub fn ensure_full_parse(&mut self, data: &[u8]) {
        // Parse bitrate_max/min from identification packet
        if let Some(id_packet) = ogg_first_packet(data, 0) {
            if id_packet.len() >= 28 {
                self.info.bitrate_max = u32::from_le_bytes([
                    id_packet[16], id_packet[17], id_packet[18], id_packet[19],
                ]);
                self.info.bitrate_min = u32::from_le_bytes([
                    id_packet[24], id_packet[25], id_packet[26], id_packet[27],
                ]);
            }
        }

        // Comment header (may span multiple pages)
        if let Some(comment_packet) = ogg_assemble_first_packet(data, self.page1_size) {
            if comment_packet.len() >= 7 && &comment_packet[0..7] == b"\x03vorbis" {
                self.raw_comment_data = comment_packet[7..].to_vec();
                self.tags_parsed = false;
            }
        }

        // Duration from last page
        if let Some(granule) = find_last_granule(data, self.serial) {
            if granule > 0 && self.info.sample_rate > 0 {
                self.info.length = granule as f64 / self.info.sample_rate as f64;
            }
        }

        // Compute actual bitrate
        if self.info.bitrate == 0 && self.info.length > 0.0 {
            self.info.bitrate = (data.len() as f64 * 8.0 / self.info.length) as u32;
        }
    }

    /// Ensure VorbisComment tags are parsed (lazy initialization).
    pub fn ensure_tags(&mut self) {
        if !self.tags_parsed {
            self.tags_parsed = true;
            if let Ok(vc) = VorbisComment::parse(&self.raw_comment_data, true) {
                self.tags = vc;
            }
            self.raw_comment_data = Vec::new(); // Free memory
        }
    }

    /// Save tags back to the OGG file.
    pub fn save(&self) -> Result<()> {
        // For now, read-only support. Writing OGG is complex (page rewriting).
        // A full implementation would rebuild the comment pages.
        let mut file = std::fs::OpenOptions::new().read(true).write(true).open(&self.path)?;
        let mut existing = Vec::new();
        file.read_to_end(&mut existing)?;

        // Parse original pages to find comment page boundaries
        let first_page = OggPage::parse(&existing, 0)?;
        let second_page = OggPage::parse(&existing, first_page.size)?;

        // Build new comment packet
        let mut comment_packet = Vec::new();
        comment_packet.extend_from_slice(b"\x03vorbis");
        comment_packet.extend_from_slice(&self.tags.render(true));

        // Build new comment page segments
        let mut segments = Vec::new();
        let mut remaining = comment_packet.len();
        while remaining >= 255 {
            segments.push(255u8);
            remaining -= 255;
        }
        segments.push(remaining as u8);

        // Build new second page
        let mut new_page = Vec::new();
        new_page.extend_from_slice(b"OggS");
        new_page.push(0); // version
        new_page.push(0); // header type (not continuation, not BOS, not EOS)
        new_page.extend_from_slice(&second_page.granule_position.to_le_bytes());
        new_page.extend_from_slice(&second_page.serial_number.to_le_bytes());
        new_page.extend_from_slice(&second_page.page_sequence.to_le_bytes());
        new_page.extend_from_slice(&0u32.to_le_bytes()); // checksum placeholder
        new_page.push(segments.len() as u8);
        new_page.extend_from_slice(&segments);
        new_page.extend_from_slice(&comment_packet);

        // Calculate CRC
        let crc = ogg_crc(&new_page);
        new_page[22..26].copy_from_slice(&crc.to_le_bytes());

        // Rebuild file
        let rest_start = first_page.size + second_page.size;
        file.seek(SeekFrom::Start(0))?;
        file.set_len(0)?;
        file.write_all(&existing[..first_page.size])?;
        file.write_all(&new_page)?;
        file.write_all(&existing[rest_start..])?;
        file.flush()?;

        Ok(())
    }

    pub fn score(path: &str, data: &[u8]) -> u32 {
        let mut score = 0u32;
        let ext = path.rsplit('.').next().unwrap_or("");
        if ext.eq_ignore_ascii_case("ogg") {
            score += 2;
        }
        if data.len() >= 4 && &data[0..4] == b"OggS" {
            score += 1;
            // Inline check for Vorbis identification without full page parse.
            // Page header: 27 bytes + segment_count segments.
            // First packet starts right after segment table.
            if data.len() >= 28 {
                let num_segments = data[26] as usize;
                let header_size = 27 + num_segments;
                if header_size + 7 <= data.len() {
                    if &data[header_size..header_size + 7] == b"\x01vorbis" {
                        score += 2;
                    }
                }
            }
        }
        score
    }
}

/// Calculate OGG-style CRC32.
fn ogg_crc(data: &[u8]) -> u32 {
    // OGG uses CRC32 with polynomial 0x04C11DB7
    let mut crc: u32 = 0;
    for &byte in data {
        crc = (crc << 8) ^ OGG_CRC_TABLE[((crc >> 24) as u8 ^ byte) as usize];
    }
    crc
}

const OGG_CRC_TABLE: [u32; 256] = {
    let mut table = [0u32; 256];
    let mut i = 0u32;
    while i < 256 {
        let mut r = i << 24;
        let mut j = 0;
        while j < 8 {
            if r & 0x80000000 != 0 {
                r = (r << 1) ^ 0x04C11DB7;
            } else {
                r <<= 1;
            }
            j += 1;
        }
        table[i as usize] = r;
        i += 1;
    }
    table
};
