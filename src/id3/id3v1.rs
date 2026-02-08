use crate::common::error::Result;
use crate::id3::frames::{Frame, TextFrame, CommentFrame};
use crate::id3::specs::{self, Encoding, GENRES};

/// Check if file data ends with an ID3v1 tag.
/// Returns the offset of the TAG if found.
pub fn find_id3v1(data: &[u8]) -> Option<usize> {
    if data.len() < 128 {
        return None;
    }
    let tag_offset = data.len() - 128;
    if &data[tag_offset..tag_offset + 3] == b"TAG" {
        Some(tag_offset)
    } else {
        None
    }
}

/// Parse an ID3v1 tag into ID3v2-compatible frames.
pub fn parse_id3v1(data: &[u8]) -> Result<Vec<Frame>> {
    if data.len() < 128 {
        return Ok(vec![]);
    }

    let tag_data = if data.len() == 128 {
        data
    } else {
        &data[data.len() - 128..]
    };

    if &tag_data[0..3] != b"TAG" {
        return Ok(vec![]);
    }

    let mut frames = Vec::new();

    // Title: bytes 3-32
    let title = decode_v1_string(&tag_data[3..33]);
    if !title.is_empty() {
        frames.push(Frame::Text(TextFrame {
            id: "TIT2".to_string(),
            encoding: Encoding::Latin1,
            text: vec![title],
        }));
    }

    // Artist: bytes 33-62
    let artist = decode_v1_string(&tag_data[33..63]);
    if !artist.is_empty() {
        frames.push(Frame::Text(TextFrame {
            id: "TPE1".to_string(),
            encoding: Encoding::Latin1,
            text: vec![artist],
        }));
    }

    // Album: bytes 63-92
    let album = decode_v1_string(&tag_data[63..93]);
    if !album.is_empty() {
        frames.push(Frame::Text(TextFrame {
            id: "TALB".to_string(),
            encoding: Encoding::Latin1,
            text: vec![album],
        }));
    }

    // Year: bytes 93-96
    let year = decode_v1_string(&tag_data[93..97]);
    if !year.is_empty() {
        frames.push(Frame::Text(TextFrame {
            id: "TDRC".to_string(),
            encoding: Encoding::Latin1,
            text: vec![year],
        }));
    }

    // Comment: bytes 97-126 (or 97-124 for v1.1)
    // Check for v1.1: if byte 125 is 0 and byte 126 is non-zero, it's track number
    if tag_data[125] == 0 && tag_data[126] != 0 {
        // ID3v1.1 - has track number
        let comment = decode_v1_string(&tag_data[97..125]);
        if !comment.is_empty() {
            frames.push(Frame::Comment(CommentFrame {
                id: "COMM".to_string(),
                encoding: Encoding::Latin1,
                lang: "eng".to_string(),
                desc: "ID3v1 Comment".to_string(),
                text: comment,
            }));
        }

        let track = tag_data[126];
        frames.push(Frame::Text(TextFrame {
            id: "TRCK".to_string(),
            encoding: Encoding::Latin1,
            text: vec![track.to_string()],
        }));
    } else {
        let comment = decode_v1_string(&tag_data[97..127]);
        if !comment.is_empty() {
            frames.push(Frame::Comment(CommentFrame {
                id: "COMM".to_string(),
                encoding: Encoding::Latin1,
                lang: "eng".to_string(),
                desc: "ID3v1 Comment".to_string(),
                text: comment,
            }));
        }
    }

    // Genre: byte 127
    let genre_id = tag_data[127] as usize;
    if genre_id < GENRES.len() {
        frames.push(Frame::Text(TextFrame {
            id: "TCON".to_string(),
            encoding: Encoding::Latin1,
            text: vec![GENRES[genre_id].to_string()],
        }));
    }

    Ok(frames)
}

/// Decode an ID3v1 fixed-length string, trimming nulls and trailing spaces.
fn decode_v1_string(data: &[u8]) -> String {
    // Find end (first null or end of data)
    let end = data.iter().position(|&b| b == 0).unwrap_or(data.len());
    let s = specs::decode_text(&data[..end], Encoding::Latin1).unwrap_or_default();
    s.trim_end().to_string()
}

/// Create an ID3v1 tag from frames.
pub fn make_id3v1(frames: &[Frame]) -> Vec<u8> {
    let mut tag = vec![0u8; 128];
    tag[0] = b'T';
    tag[1] = b'A';
    tag[2] = b'G';

    for frame in frames {
        match frame {
            Frame::Text(f) => {
                let text = f.text.first().map(|s| s.as_str()).unwrap_or("");
                match f.id.as_str() {
                    "TIT2" => write_v1_string(&mut tag[3..33], text),
                    "TPE1" => write_v1_string(&mut tag[33..63], text),
                    "TALB" => write_v1_string(&mut tag[63..93], text),
                    "TDRC" | "TYER" => write_v1_string(&mut tag[93..97], text),
                    "TRCK" => {
                        if let Ok(n) = text.split('/').next().unwrap_or("").parse::<u8>() {
                            tag[125] = 0;
                            tag[126] = n;
                        }
                    }
                    "TCON" => {
                        let genres = specs::parse_genre(text);
                        if let Some(genre_name) = genres.first() {
                            if let Some(idx) = GENRES.iter().position(|&g| g == genre_name.as_str())
                            {
                                tag[127] = idx as u8;
                            } else {
                                tag[127] = 255; // Unknown
                            }
                        }
                    }
                    _ => {}
                }
            }
            _ => {}
        }
    }

    tag
}

fn write_v1_string(dest: &mut [u8], text: &str) {
    let bytes = text.as_bytes();
    let len = bytes.len().min(dest.len());
    dest[..len].copy_from_slice(&bytes[..len]);
}
