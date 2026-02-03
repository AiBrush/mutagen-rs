use std::fs::File;
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
        // Scan backward from end for OggS magic
        let mut pos = data.len().saturating_sub(65536); // Start max 64KB from end
        if pos < 4 {
            pos = 0;
        }

        let mut last_page = None;

        while pos + 4 < data.len() {
            if &data[pos..pos + 4] == b"OggS" {
                if let Ok(page) = OggPage::parse(data, pos) {
                    if page.serial_number == serial {
                        last_page = Some(page.clone());
                    }
                    pos += page.size;
                    continue;
                }
            }
            pos += 1;
        }

        last_page
    }
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
}

impl OggVorbisFile {
    pub fn open(path: &str) -> Result<Self> {
        let data = std::fs::read(path)?;
        Self::parse(&data, path)
    }

    pub fn parse(data: &[u8], path: &str) -> Result<Self> {
        // Parse first page (should contain identification header)
        let first_page = OggPage::parse(data, 0)?;

        if first_page.packets.is_empty() {
            return Err(MutagenError::Ogg("No packets in first page".into()));
        }

        let id_packet = &first_page.packets[0];

        // Verify Vorbis identification header
        if id_packet.len() < 30 || &id_packet[0..7] != b"\x01vorbis" {
            return Err(MutagenError::Ogg("Not a Vorbis stream".into()));
        }

        // Parse identification header
        let _vorbis_version = u32::from_le_bytes([
            id_packet[7], id_packet[8], id_packet[9], id_packet[10],
        ]);
        let channels = id_packet[11];
        let sample_rate = u32::from_le_bytes([
            id_packet[12], id_packet[13], id_packet[14], id_packet[15],
        ]);
        let bitrate_max = u32::from_le_bytes([
            id_packet[16], id_packet[17], id_packet[18], id_packet[19],
        ]);
        let bitrate = u32::from_le_bytes([
            id_packet[20], id_packet[21], id_packet[22], id_packet[23],
        ]);
        let bitrate_min = u32::from_le_bytes([
            id_packet[24], id_packet[25], id_packet[26], id_packet[27],
        ]);

        // Parse second page (comment header)
        let second_page = OggPage::parse(data, first_page.size)?;
        let mut comment_data = if !second_page.packets.is_empty() {
            second_page.packets[0].clone()
        } else {
            return Err(MutagenError::Ogg("No comment packet".into()));
        };

        // The comment packet starts with \x03vorbis
        if comment_data.len() < 7 || &comment_data[0..7] != b"\x03vorbis" {
            return Err(MutagenError::Ogg("Invalid comment header".into()));
        }

        let tags = VorbisComment::parse(&comment_data[7..], true)?;

        // Calculate duration from last page
        let length = if let Some(last_page) = OggPage::find_last(data, first_page.serial_number) {
            if last_page.granule_position > 0 && sample_rate > 0 {
                last_page.granule_position as f64 / sample_rate as f64
            } else {
                0.0
            }
        } else {
            0.0
        };

        // Calculate actual bitrate from file size if nominal is 0
        let actual_bitrate = if bitrate > 0 {
            bitrate
        } else if length > 0.0 {
            (data.len() as f64 * 8.0 / length) as u32
        } else {
            0
        };

        Ok(OggVorbisFile {
            info: OggVorbisInfo {
                length,
                channels,
                sample_rate,
                bitrate: actual_bitrate,
                bitrate_max,
                bitrate_min,
            },
            tags,
            path: path.to_string(),
        })
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
        let ext = path.rsplit('.').next().unwrap_or("").to_lowercase();
        if ext == "ogg" {
            score += 2;
        }
        if data.len() >= 4 && &data[0..4] == b"OggS" {
            score += 1;
        }
        // Check for vorbis identification
        if data.len() >= 35 && &data[0..4] == b"OggS" {
            if let Ok(page) = OggPage::parse(data, 0) {
                if !page.packets.is_empty() && page.packets[0].len() >= 7 {
                    if &page.packets[0][0..7] == b"\x01vorbis" {
                        score += 2;
                    }
                }
            }
        }
        score
    }
}

/// OGG CRC32 lookup table.
const CRC_LOOKUP: [u32; 256] = {
    let mut table = [0u32; 256];
    let mut i = 0;
    while i < 256 {
        let mut r = i as u32;
        let mut j = 0;
        while j < 8 {
            if r & 1 != 0 {
                r = (r >> 1) ^ 0xEDB88320;
            } else {
                r >>= 1;
            }
            j += 1;
        }
        // Actually OGG uses a different polynomial
        table[i] = r;
        i += 1;
    }
    table
};

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
