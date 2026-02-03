use std::fs::File;
use std::io::{Write, Seek, SeekFrom, Read};
use crate::common::error::{MutagenError, Result};
use crate::vorbis::VorbisComment;

/// FLAC metadata block types.
#[derive(Debug, Clone, Copy, PartialEq)]
#[repr(u8)]
pub enum BlockType {
    StreamInfo = 0,
    Padding = 1,
    Application = 2,
    SeekTable = 3,
    VorbisComment = 4,
    CueSheet = 5,
    Picture = 6,
    Unknown(u8),
}

impl BlockType {
    pub fn from_byte(b: u8) -> Self {
        match b {
            0 => BlockType::StreamInfo,
            1 => BlockType::Padding,
            2 => BlockType::Application,
            3 => BlockType::SeekTable,
            4 => BlockType::VorbisComment,
            5 => BlockType::CueSheet,
            6 => BlockType::Picture,
            n => BlockType::Unknown(n),
        }
    }

    pub fn to_byte(&self) -> u8 {
        match self {
            BlockType::StreamInfo => 0,
            BlockType::Padding => 1,
            BlockType::Application => 2,
            BlockType::SeekTable => 3,
            BlockType::VorbisComment => 4,
            BlockType::CueSheet => 5,
            BlockType::Picture => 6,
            BlockType::Unknown(n) => *n,
        }
    }
}

/// A raw FLAC metadata block.
#[derive(Debug, Clone)]
pub struct MetadataBlock {
    pub block_type: BlockType,
    pub is_last: bool,
    pub data: Vec<u8>,
}

/// Parsed FLAC StreamInfo block.
#[derive(Debug, Clone)]
pub struct StreamInfo {
    pub min_block_size: u16,
    pub max_block_size: u16,
    pub min_frame_size: u32,
    pub max_frame_size: u32,
    pub sample_rate: u32,
    pub channels: u8,
    pub bits_per_sample: u8,
    pub total_samples: u64,
    pub md5: [u8; 16],
    pub length: f64,
}

impl StreamInfo {
    pub fn parse(data: &[u8]) -> Result<Self> {
        if data.len() < 34 {
            return Err(MutagenError::FLAC("StreamInfo block too short".into()));
        }

        let min_block_size = u16::from_be_bytes([data[0], data[1]]);
        let max_block_size = u16::from_be_bytes([data[2], data[3]]);
        let min_frame_size = u32::from_be_bytes([0, data[4], data[5], data[6]]);
        let max_frame_size = u32::from_be_bytes([0, data[7], data[8], data[9]]);

        // Bits 10-12: sample rate (20 bits), channels (3 bits), bps (5 bits), total_samples (36 bits)
        let sr_hi = u32::from_be_bytes([0, data[10], data[11], data[12]]);
        let sample_rate = (sr_hi >> 4) & 0xFFFFF;

        let channels = (((data[12] >> 1) & 0x07) + 1) as u8;
        let bps_hi = ((data[12] & 0x01) as u8) << 4;
        let bps_lo = (data[13] >> 4) & 0x0F;
        let bits_per_sample = bps_hi | bps_lo + 1;

        let total_samples_hi = ((data[13] & 0x0F) as u64) << 32;
        let total_samples_lo = u32::from_be_bytes([data[14], data[15], data[16], data[17]]) as u64;
        let total_samples = total_samples_hi | total_samples_lo;

        let mut md5 = [0u8; 16];
        md5.copy_from_slice(&data[18..34]);

        let length = if sample_rate > 0 {
            total_samples as f64 / sample_rate as f64
        } else {
            0.0
        };

        Ok(StreamInfo {
            min_block_size,
            max_block_size,
            min_frame_size,
            max_frame_size,
            sample_rate,
            channels,
            bits_per_sample,
            total_samples,
            md5,
            length,
        })
    }
}

/// FLAC Picture block.
#[derive(Debug, Clone)]
pub struct FLACPicture {
    pub pic_type: u32,
    pub mime: String,
    pub desc: String,
    pub width: u32,
    pub height: u32,
    pub depth: u32,
    pub colors: u32,
    pub data: Vec<u8>,
}

impl FLACPicture {
    pub fn parse(block_data: &[u8]) -> Result<Self> {
        if block_data.len() < 32 {
            return Err(MutagenError::FLAC("Picture block too short".into()));
        }

        let mut pos = 0;
        let pic_type = u32::from_be_bytes([
            block_data[pos], block_data[pos + 1], block_data[pos + 2], block_data[pos + 3],
        ]);
        pos += 4;

        let mime_len = u32::from_be_bytes([
            block_data[pos], block_data[pos + 1], block_data[pos + 2], block_data[pos + 3],
        ]) as usize;
        pos += 4;

        if pos + mime_len > block_data.len() {
            return Err(MutagenError::FLAC("Picture MIME extends past data".into()));
        }
        let mime = String::from_utf8_lossy(&block_data[pos..pos + mime_len]).into_owned();
        pos += mime_len;

        if pos + 4 > block_data.len() {
            return Err(MutagenError::FLAC("Picture block too short for desc".into()));
        }
        let desc_len = u32::from_be_bytes([
            block_data[pos], block_data[pos + 1], block_data[pos + 2], block_data[pos + 3],
        ]) as usize;
        pos += 4;

        if pos + desc_len > block_data.len() {
            return Err(MutagenError::FLAC("Picture desc extends past data".into()));
        }
        let desc = String::from_utf8_lossy(&block_data[pos..pos + desc_len]).into_owned();
        pos += desc_len;

        if pos + 20 > block_data.len() {
            return Err(MutagenError::FLAC("Picture block too short for dimensions".into()));
        }

        let width = u32::from_be_bytes([
            block_data[pos], block_data[pos + 1], block_data[pos + 2], block_data[pos + 3],
        ]);
        pos += 4;
        let height = u32::from_be_bytes([
            block_data[pos], block_data[pos + 1], block_data[pos + 2], block_data[pos + 3],
        ]);
        pos += 4;
        let depth = u32::from_be_bytes([
            block_data[pos], block_data[pos + 1], block_data[pos + 2], block_data[pos + 3],
        ]);
        pos += 4;
        let colors = u32::from_be_bytes([
            block_data[pos], block_data[pos + 1], block_data[pos + 2], block_data[pos + 3],
        ]);
        pos += 4;

        let data_len = u32::from_be_bytes([
            block_data[pos], block_data[pos + 1], block_data[pos + 2], block_data[pos + 3],
        ]) as usize;
        pos += 4;

        let data = if pos + data_len <= block_data.len() {
            block_data[pos..pos + data_len].to_vec()
        } else {
            block_data[pos..].to_vec()
        };

        Ok(FLACPicture {
            pic_type,
            mime,
            desc,
            width,
            height,
            depth,
            colors,
            data,
        })
    }

    pub fn render(&self) -> Vec<u8> {
        let mut data = Vec::new();
        data.extend_from_slice(&self.pic_type.to_be_bytes());
        let mime_bytes = self.mime.as_bytes();
        data.extend_from_slice(&(mime_bytes.len() as u32).to_be_bytes());
        data.extend_from_slice(mime_bytes);
        let desc_bytes = self.desc.as_bytes();
        data.extend_from_slice(&(desc_bytes.len() as u32).to_be_bytes());
        data.extend_from_slice(desc_bytes);
        data.extend_from_slice(&self.width.to_be_bytes());
        data.extend_from_slice(&self.height.to_be_bytes());
        data.extend_from_slice(&self.depth.to_be_bytes());
        data.extend_from_slice(&self.colors.to_be_bytes());
        data.extend_from_slice(&(self.data.len() as u32).to_be_bytes());
        data.extend_from_slice(&self.data);
        data
    }
}

/// Complete FLAC file handler.
#[derive(Debug)]
pub struct FLACFile {
    pub info: StreamInfo,
    pub tags: Option<VorbisComment>,
    pub pictures: Vec<FLACPicture>,
    pub metadata_blocks: Vec<MetadataBlock>,
    pub path: String,
    pub metadata_length: usize, // total bytes of fLaC + metadata blocks
}

impl FLACFile {
    /// Open and parse a FLAC file.
    pub fn open(path: &str) -> Result<Self> {
        let data = std::fs::read(path)?;
        Self::parse(&data, path)
    }

    pub fn parse(data: &[u8], path: &str) -> Result<Self> {
        // Check for fLaC magic
        if data.len() < 4 || &data[0..4] != b"fLaC" {
            // Check if there's an ID3v2 header before fLaC
            let offset = if data.len() >= 3 && &data[0..3] == b"ID3" {
                // Parse ID3 header to find its size
                if data.len() >= 10 {
                    let size = crate::id3::header::BitPaddedInt::syncsafe(&data[6..10]) as usize;
                    10 + size
                } else {
                    return Err(MutagenError::FLACNoHeader);
                }
            } else {
                return Err(MutagenError::FLACNoHeader);
            };

            if offset + 4 > data.len() || &data[offset..offset + 4] != b"fLaC" {
                return Err(MutagenError::FLACNoHeader);
            }

            return Self::parse_from_offset(data, offset, path);
        }

        Self::parse_from_offset(data, 0, path)
    }

    fn parse_from_offset(data: &[u8], flac_offset: usize, path: &str) -> Result<Self> {
        let mut pos = flac_offset + 4; // Skip fLaC magic
        let mut blocks = Vec::new();
        let mut stream_info = None;
        let mut tags = None;
        let mut pictures = Vec::new();

        loop {
            if pos + 4 > data.len() {
                break;
            }

            let header_byte = data[pos];
            let is_last = header_byte & 0x80 != 0;
            let block_type = BlockType::from_byte(header_byte & 0x7F);
            let block_size = u32::from_be_bytes([0, data[pos + 1], data[pos + 2], data[pos + 3]]) as usize;
            pos += 4;

            if pos + block_size > data.len() {
                break;
            }

            let block_data = data[pos..pos + block_size].to_vec();
            pos += block_size;

            match block_type {
                BlockType::StreamInfo => {
                    stream_info = Some(StreamInfo::parse(&block_data)?);
                }
                BlockType::VorbisComment => {
                    tags = Some(VorbisComment::parse(&block_data, false)?);
                }
                BlockType::Picture => {
                    if let Ok(pic) = FLACPicture::parse(&block_data) {
                        pictures.push(pic);
                    }
                }
                _ => {}
            }

            blocks.push(MetadataBlock {
                block_type,
                is_last,
                data: block_data,
            });

            if is_last {
                break;
            }
        }

        let info = stream_info.ok_or_else(|| MutagenError::FLAC("No StreamInfo block found".into()))?;

        Ok(FLACFile {
            info,
            tags,
            pictures,
            metadata_blocks: blocks,
            path: path.to_string(),
            metadata_length: pos - flac_offset,
        })
    }

    /// Save metadata back to the FLAC file.
    pub fn save(&self) -> Result<()> {
        let mut file = std::fs::OpenOptions::new().read(true).write(true).open(&self.path)?;
        let mut existing = Vec::new();
        file.read_to_end(&mut existing)?;

        // Find the fLaC offset
        let flac_offset = if existing.len() >= 4 && &existing[0..4] == b"fLaC" {
            0
        } else if existing.len() >= 3 && &existing[0..3] == b"ID3" {
            if existing.len() >= 10 {
                let size = crate::id3::header::BitPaddedInt::syncsafe(&existing[6..10]) as usize;
                10 + size
            } else {
                return Err(MutagenError::FLAC("Cannot find fLaC header".into()));
            }
        } else {
            return Err(MutagenError::FLAC("Cannot find fLaC header".into()));
        };

        // Rebuild metadata blocks
        let mut new_metadata = Vec::new();

        // fLaC magic
        new_metadata.extend_from_slice(b"fLaC");

        // Collect blocks to write
        let mut blocks_to_write: Vec<(BlockType, Vec<u8>)> = Vec::new();

        // StreamInfo (always first)
        for block in &self.metadata_blocks {
            if block.block_type == BlockType::StreamInfo {
                blocks_to_write.push((BlockType::StreamInfo, block.data.clone()));
                break;
            }
        }

        // Vorbis comment
        if let Some(ref vc) = self.tags {
            blocks_to_write.push((BlockType::VorbisComment, vc.render(false)));
        }

        // Pictures
        for pic in &self.pictures {
            blocks_to_write.push((BlockType::Picture, pic.render()));
        }

        // Other blocks (skip StreamInfo, VorbisComment, Picture, Padding)
        for block in &self.metadata_blocks {
            match block.block_type {
                BlockType::StreamInfo | BlockType::VorbisComment | BlockType::Picture | BlockType::Padding => {}
                _ => {
                    blocks_to_write.push((block.block_type, block.data.clone()));
                }
            }
        }

        // Add padding
        let padding_size = 1024;
        blocks_to_write.push((BlockType::Padding, vec![0u8; padding_size]));

        // Write blocks with proper headers
        for (i, (block_type, block_data)) in blocks_to_write.iter().enumerate() {
            let is_last = i == blocks_to_write.len() - 1;
            let header_byte = if is_last {
                block_type.to_byte() | 0x80
            } else {
                block_type.to_byte()
            };

            new_metadata.push(header_byte);
            let size = block_data.len() as u32;
            new_metadata.push((size >> 16) as u8);
            new_metadata.push((size >> 8) as u8);
            new_metadata.push(size as u8);
            new_metadata.extend_from_slice(block_data);
        }

        // Audio data starts after original metadata
        let audio_start = flac_offset + self.metadata_length;
        let audio_data = &existing[audio_start..];

        // Write the file
        file.seek(SeekFrom::Start(flac_offset as u64))?;
        file.set_len(flac_offset as u64)?;
        file.write_all(&new_metadata)?;
        file.write_all(audio_data)?;
        file.flush()?;

        Ok(())
    }

    /// Score for auto-detection.
    pub fn score(path: &str, data: &[u8]) -> u32 {
        let mut score = 0u32;

        let ext = path.rsplit('.').next().unwrap_or("").to_lowercase();
        if ext == "flac" {
            score += 2;
        }

        if data.len() >= 4 && &data[0..4] == b"fLaC" {
            score += 3;
        }

        score
    }
}
