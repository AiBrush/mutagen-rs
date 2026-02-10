use crate::common::error::{MutagenError, Result};
use crate::id3::specs::{self, Encoding, PictureType};

/// Represents the hash key for a frame, used for dictionary-like access.
/// Most frames use their 4-char ID, but some include extra info
/// (e.g., TXXX:description, COMM:description:language).
/// Uses inline storage for short keys (<=16 bytes) to avoid heap allocation.
#[derive(Debug, Clone)]
pub enum HashKey {
    /// Short key stored inline (most frame IDs: "TIT2", "TPE1", etc.)
    Short([u8; 16], u8),
    /// Long key on the heap (e.g., "TXXX:some long description")
    Long(String),
}

impl HashKey {
    #[inline]
    pub fn new(s: &str) -> Self {
        let bytes = s.as_bytes();
        if bytes.len() <= 16 {
            let mut buf = [0u8; 16];
            buf[..bytes.len()].copy_from_slice(bytes);
            HashKey::Short(buf, bytes.len() as u8)
        } else {
            HashKey::Long(s.to_string())
        }
    }

    #[inline]
    pub fn as_str(&self) -> &str {
        match self {
            HashKey::Short(buf, len) => {
                // SAFETY: we only store valid UTF-8 in the buffer
                unsafe { std::str::from_utf8_unchecked(&buf[..*len as usize]) }
            }
            HashKey::Long(s) => s.as_str(),
        }
    }

    /// Create from a format string (used for composite keys like "TXXX:desc")
    #[inline]
    pub fn from_string(s: String) -> Self {
        if s.len() <= 16 {
            let mut buf = [0u8; 16];
            buf[..s.len()].copy_from_slice(s.as_bytes());
            HashKey::Short(buf, s.len() as u8)
        } else {
            HashKey::Long(s)
        }
    }
}

impl PartialEq for HashKey {
    #[inline]
    fn eq(&self, other: &Self) -> bool {
        self.as_str() == other.as_str()
    }
}

impl Eq for HashKey {}

impl std::hash::Hash for HashKey {
    #[inline]
    fn hash<H: std::hash::Hasher>(&self, state: &mut H) {
        self.as_str().hash(state)
    }
}

/// A parsed ID3v2 frame.
#[derive(Debug, Clone)]
pub enum Frame {
    Text(TextFrame),
    UserText(UserTextFrame),
    Url(UrlFrame),
    UserUrl(UserUrlFrame),
    Comment(CommentFrame),
    Lyrics(LyricsFrame),
    Picture(PictureFrame),
    Popularimeter(PopularimeterFrame),
    Binary(BinaryFrame),
    PairedText(PairedTextFrame),
}

impl Frame {
    /// Get the frame ID (4-char string like "TIT2").
    pub fn frame_id(&self) -> &str {
        match self {
            Frame::Text(f) => &f.id,
            Frame::UserText(f) => &f.id,
            Frame::Url(f) => &f.id,
            Frame::UserUrl(f) => &f.id,
            Frame::Comment(f) => &f.id,
            Frame::Lyrics(f) => &f.id,
            Frame::Picture(f) => &f.id,
            Frame::Popularimeter(f) => &f.id,
            Frame::Binary(f) => &f.id,
            Frame::PairedText(f) => &f.id,
        }
    }

    /// Get the hash key for dictionary storage.
    pub fn hash_key(&self) -> HashKey {
        match self {
            Frame::Text(f) => HashKey::new(&f.id),
            Frame::UserText(f) => HashKey::from_string(format!("TXXX:{}", f.desc)),
            Frame::Url(f) => HashKey::new(&f.id),
            Frame::UserUrl(f) => HashKey::from_string(format!("WXXX:{}", f.desc)),
            Frame::Comment(f) => HashKey::from_string(format!("COMM:{}:{}", f.desc, f.lang)),
            Frame::Lyrics(f) => HashKey::from_string(format!("USLT:{}:{}", f.desc, f.lang)),
            Frame::Picture(f) => HashKey::from_string(format!("APIC:{}", f.desc)),
            Frame::Popularimeter(f) => HashKey::from_string(format!("POPM:{}", f.email)),
            Frame::Binary(f) => HashKey::new(&f.id),
            Frame::PairedText(f) => HashKey::new(&f.id),
        }
    }

    /// Get a human-readable representation.
    pub fn pprint(&self) -> String {
        match self {
            Frame::Text(f) => f.text.join("/"),
            Frame::UserText(f) => format!("{}={}", f.desc, f.text.join("/")),
            Frame::Url(f) => f.url.clone(),
            Frame::UserUrl(f) => format!("{}={}", f.desc, f.url),
            Frame::Comment(f) => f.text.clone(),
            Frame::Lyrics(f) => f.text.clone(),
            Frame::Picture(f) => format!("{} ({}, {} bytes)", f.desc, f.mime, f.data.len()),
            Frame::Popularimeter(f) => format!("{}={}/{}", f.email, f.rating, f.count),
            Frame::Binary(f) => format!("[{} bytes]", f.data.len()),
            Frame::PairedText(f) => {
                f.people
                    .iter()
                    .map(|(a, b)| format!("{}={}", a, b))
                    .collect::<Vec<_>>()
                    .join("/")
            }
        }
    }

    /// Get text value(s) for common attribute access.
    pub fn text_values(&self) -> Vec<String> {
        match self {
            Frame::Text(f) => f.text.clone(),
            Frame::UserText(f) => f.text.clone(),
            Frame::Comment(f) => vec![f.text.clone()],
            Frame::Lyrics(f) => vec![f.text.clone()],
            _ => vec![self.pprint()],
        }
    }

    /// Serialize frame data back to bytes (without frame header).
    pub fn write_data(&self, version: u8) -> Result<Vec<u8>> {
        match self {
            Frame::Text(f) => write_text_frame(f, version),
            Frame::UserText(f) => write_user_text_frame(f, version),
            Frame::Url(f) => write_url_frame(f),
            Frame::UserUrl(f) => write_user_url_frame(f, version),
            Frame::Comment(f) => write_comment_frame(f, version),
            Frame::Lyrics(f) => write_lyrics_frame(f, version),
            Frame::Picture(f) => write_picture_frame(f, version),
            Frame::Popularimeter(f) => write_popm_frame(f),
            Frame::Binary(f) => Ok(f.data.clone()),
            Frame::PairedText(f) => write_paired_text_frame(f, version),
        }
    }
}

/// Standard text frame (TIT2, TPE1, TALB, TRCK, TCON, TDRC, etc.)
#[derive(Debug, Clone)]
pub struct TextFrame {
    pub id: String,
    pub encoding: Encoding,
    pub text: Vec<String>,
}

/// User-defined text frame (TXXX).
#[derive(Debug, Clone)]
pub struct UserTextFrame {
    pub id: String,
    pub encoding: Encoding,
    pub desc: String,
    pub text: Vec<String>,
}

/// URL link frame (WOAR, WORS, etc.)
#[derive(Debug, Clone)]
pub struct UrlFrame {
    pub id: String,
    pub url: String,
}

/// User-defined URL frame (WXXX).
#[derive(Debug, Clone)]
pub struct UserUrlFrame {
    pub id: String,
    pub encoding: Encoding,
    pub desc: String,
    pub url: String,
}

/// Comment frame (COMM).
#[derive(Debug, Clone)]
pub struct CommentFrame {
    pub id: String,
    pub encoding: Encoding,
    pub lang: String,
    pub desc: String,
    pub text: String,
}

/// Unsynchronised lyrics frame (USLT).
#[derive(Debug, Clone)]
pub struct LyricsFrame {
    pub id: String,
    pub encoding: Encoding,
    pub lang: String,
    pub desc: String,
    pub text: String,
}

/// Picture frame (APIC).
#[derive(Debug, Clone)]
pub struct PictureFrame {
    pub id: String,
    pub encoding: Encoding,
    pub mime: String,
    pub pic_type: PictureType,
    pub desc: String,
    pub data: Vec<u8>,
}

/// Popularimeter frame (POPM).
#[derive(Debug, Clone)]
pub struct PopularimeterFrame {
    pub id: String,
    pub email: String,
    pub rating: u8,
    pub count: u64,
}

/// Generic binary frame for unknown/unsupported frame types.
#[derive(Debug, Clone)]
pub struct BinaryFrame {
    pub id: String,
    pub data: Vec<u8>,
}

/// Paired text frame (TIPL, TMCL, IPLS).
#[derive(Debug, Clone)]
pub struct PairedTextFrame {
    pub id: String,
    pub encoding: Encoding,
    pub people: Vec<(String, String)>,
}

// ---- Parsing functions ----

/// Parse a text frame from raw data.
pub fn parse_text_frame(id: &str, data: &[u8]) -> Result<Frame> {
    if data.is_empty() {
        return Ok(Frame::Text(TextFrame {
            id: id.to_string(),
            encoding: Encoding::Latin1,
            text: vec![],
        }));
    }

    let encoding = Encoding::from_byte(data[0])?;
    let text_data = &data[1..];
    let full_text = specs::decode_text(text_data, encoding)?;

    // Split by null characters for multiple values
    let text: Vec<String> = if full_text.contains('\0') {
        full_text
            .split('\0')
            .filter(|s| !s.is_empty())
            .map(|s| s.to_string())
            .collect()
    } else if full_text.is_empty() {
        vec![]
    } else {
        vec![full_text]
    };

    Ok(Frame::Text(TextFrame {
        id: id.to_string(),
        encoding,
        text,
    }))
}

/// Parse a TXXX (user text) frame.
pub fn parse_user_text_frame(id: &str, data: &[u8]) -> Result<Frame> {
    if data.is_empty() {
        return Err(MutagenError::ID3("Empty TXXX frame".into()));
    }

    let encoding = Encoding::from_byte(data[0])?;
    let rest = &data[1..];

    let (desc, consumed) = specs::read_encoded_text(rest, encoding)?;
    let text_data = &rest[consumed..];
    let full_text = specs::decode_text(text_data, encoding)?;

    let text: Vec<String> = if full_text.contains('\0') {
        full_text.split('\0').filter(|s| !s.is_empty()).map(|s| s.to_string()).collect()
    } else if full_text.is_empty() {
        vec![]
    } else {
        vec![full_text]
    };

    Ok(Frame::UserText(UserTextFrame {
        id: id.to_string(),
        encoding,
        desc,
        text,
    }))
}

/// Parse a URL frame (WXXX excluded).
pub fn parse_url_frame(id: &str, data: &[u8]) -> Result<Frame> {
    let url = specs::decode_text(data, Encoding::Latin1)?;
    let url = url.trim_end_matches('\0').to_string();
    Ok(Frame::Url(UrlFrame {
        id: id.to_string(),
        url,
    }))
}

/// Parse a WXXX (user URL) frame.
pub fn parse_user_url_frame(id: &str, data: &[u8]) -> Result<Frame> {
    if data.is_empty() {
        return Err(MutagenError::ID3("Empty WXXX frame".into()));
    }

    let encoding = Encoding::from_byte(data[0])?;
    let rest = &data[1..];

    let (desc, consumed) = specs::read_encoded_text(rest, encoding)?;
    let url_data = &rest[consumed..];
    let url = specs::decode_text(url_data, Encoding::Latin1)?;
    let url = url.trim_end_matches('\0').to_string();

    Ok(Frame::UserUrl(UserUrlFrame {
        id: id.to_string(),
        encoding,
        desc,
        url,
    }))
}

/// Parse a COMM (comment) frame.
pub fn parse_comment_frame(id: &str, data: &[u8]) -> Result<Frame> {
    if data.len() < 4 {
        return Err(MutagenError::ID3("COMM frame too short".into()));
    }

    let encoding = Encoding::from_byte(data[0])?;
    let lang = std::str::from_utf8(&data[1..4])
        .unwrap_or("XXX")
        .to_string();
    let rest = &data[4..];

    let (desc, consumed) = specs::read_encoded_text(rest, encoding)?;
    let text = specs::decode_text(&rest[consumed..], encoding)?;
    let text = text.trim_end_matches('\0').to_string();

    Ok(Frame::Comment(CommentFrame {
        id: id.to_string(),
        encoding,
        lang,
        desc,
        text,
    }))
}

/// Parse a USLT (lyrics) frame.
pub fn parse_lyrics_frame(id: &str, data: &[u8]) -> Result<Frame> {
    if data.len() < 4 {
        return Err(MutagenError::ID3("USLT frame too short".into()));
    }

    let encoding = Encoding::from_byte(data[0])?;
    let lang = std::str::from_utf8(&data[1..4])
        .unwrap_or("XXX")
        .to_string();
    let rest = &data[4..];

    let (desc, consumed) = specs::read_encoded_text(rest, encoding)?;
    let text = specs::decode_text(&rest[consumed..], encoding)?;
    let text = text.trim_end_matches('\0').to_string();

    Ok(Frame::Lyrics(LyricsFrame {
        id: id.to_string(),
        encoding,
        lang,
        desc,
        text,
    }))
}

/// Parse an APIC (picture) frame.
pub fn parse_picture_frame(id: &str, data: &[u8]) -> Result<Frame> {
    if data.is_empty() {
        return Err(MutagenError::ID3("Empty APIC frame".into()));
    }

    let encoding = Encoding::from_byte(data[0])?;
    let rest = &data[1..];

    // MIME type is always Latin1
    let (mime, consumed) = specs::read_latin1_text(rest)?;
    let rest = &rest[consumed..];

    if rest.is_empty() {
        return Err(MutagenError::ID3("APIC frame too short".into()));
    }

    let pic_type = PictureType::from_byte(rest[0]);
    let rest = &rest[1..];

    let (desc, consumed) = specs::read_encoded_text(rest, encoding)?;
    let pic_data = rest[consumed..].to_vec();

    Ok(Frame::Picture(PictureFrame {
        id: id.to_string(),
        encoding,
        mime,
        pic_type,
        desc,
        data: pic_data,
    }))
}

/// Parse a POPM (popularimeter) frame.
pub fn parse_popm_frame(id: &str, data: &[u8]) -> Result<Frame> {
    let (email, consumed) = specs::read_latin1_text(data)?;
    let rest = &data[consumed..];

    let rating = if !rest.is_empty() { rest[0] } else { 0 };

    let count = if rest.len() > 1 {
        let count_data = &rest[1..];
        let mut val: u64 = 0;
        for &b in count_data {
            val = (val << 8) | b as u64;
        }
        val
    } else {
        0
    };

    Ok(Frame::Popularimeter(PopularimeterFrame {
        id: id.to_string(),
        email,
        rating,
        count,
    }))
}

/// Parse a paired text frame (TIPL, TMCL, IPLS).
pub fn parse_paired_text_frame(id: &str, data: &[u8]) -> Result<Frame> {
    if data.is_empty() {
        return Ok(Frame::PairedText(PairedTextFrame {
            id: id.to_string(),
            encoding: Encoding::Latin1,
            people: vec![],
        }));
    }

    let encoding = Encoding::from_byte(data[0])?;
    let text = specs::decode_text(&data[1..], encoding)?;

    let parts: Vec<&str> = text.split('\0').collect();
    let mut people = Vec::new();

    let mut i = 0;
    while i + 1 < parts.len() {
        people.push((parts[i].to_string(), parts[i + 1].to_string()));
        i += 2;
    }

    Ok(Frame::PairedText(PairedTextFrame {
        id: id.to_string(),
        encoding,
        people,
    }))
}

/// Parse a frame from its ID and raw data.
pub fn parse_frame(id: &str, data: &[u8]) -> Result<Frame> {
    match id {
        // Text frames (T*** except TXXX)
        s if s.starts_with('T') && s != "TXXX" => parse_text_frame(id, data),
        "TXXX" => parse_user_text_frame(id, data),

        // URL frames (W*** except WXXX)
        s if s.starts_with('W') && s != "WXXX" => parse_url_frame(id, data),
        "WXXX" => parse_user_url_frame(id, data),

        // Comment and lyrics
        "COMM" => parse_comment_frame(id, data),
        "USLT" => parse_lyrics_frame(id, data),

        // Picture
        "APIC" => parse_picture_frame(id, data),

        // Popularimeter
        "POPM" => parse_popm_frame(id, data),

        // Paired text
        "TIPL" | "TMCL" | "IPLS" => parse_paired_text_frame(id, data),

        // Everything else → binary
        _ => Ok(Frame::Binary(BinaryFrame {
            id: id.to_string(),
            data: data.to_vec(),
        })),
    }
}

// ---- v2.2 to v2.3/v2.4 frame ID mapping ----

/// Convert a v2.2 3-char frame ID to v2.3+ 4-char equivalent.
pub fn convert_v22_frame_id(id: &str) -> Option<&'static str> {
    match id {
        "BUF" => Some("RBUF"),
        "CNT" => Some("PCNT"),
        "COM" => Some("COMM"),
        "CRA" => Some("AENC"),
        "ETC" => Some("ETCO"),
        "GEO" => Some("GEOB"),
        "IPL" => Some("IPLS"),
        "LNK" => Some("LINK"),
        "MCI" => Some("MCDI"),
        "MLL" => Some("MLLT"),
        "PIC" => Some("APIC"),
        "POP" => Some("POPM"),
        "REV" => Some("RVRB"),
        "SLT" => Some("SYLT"),
        "STC" => Some("SYTC"),
        "TAL" => Some("TALB"),
        "TBP" => Some("TBPM"),
        "TCM" => Some("TCOM"),
        "TCO" => Some("TCON"),
        "TCR" => Some("TCOP"),
        "TDA" => Some("TDAT"),
        "TDY" => Some("TDLY"),
        "TEN" => Some("TENC"),
        "TFT" => Some("TFLT"),
        "TIM" => Some("TIME"),
        "TKE" => Some("TKEY"),
        "TLA" => Some("TLAN"),
        "TLE" => Some("TLEN"),
        "TMT" => Some("TMED"),
        "TOA" => Some("TOPE"),
        "TOF" => Some("TOFN"),
        "TOL" => Some("TOLY"),
        "TOR" => Some("TORY"),
        "TOT" => Some("TOAL"),
        "TP1" => Some("TPE1"),
        "TP2" => Some("TPE2"),
        "TP3" => Some("TPE3"),
        "TP4" => Some("TPE4"),
        "TPA" => Some("TPOS"),
        "TPB" => Some("TPUB"),
        "TRC" => Some("TSRC"),
        "TRD" => Some("TRDA"),
        "TRK" => Some("TRCK"),
        "TSI" => Some("TSIZ"),
        "TSS" => Some("TSSE"),
        "TT1" => Some("TIT1"),
        "TT2" => Some("TIT2"),
        "TT3" => Some("TIT3"),
        "TXT" => Some("TEXT"),
        "TXX" => Some("TXXX"),
        "TYE" => Some("TYER"),
        "UFI" => Some("UFID"),
        "ULT" => Some("USLT"),
        "WAF" => Some("WOAF"),
        "WAR" => Some("WOAR"),
        "WAS" => Some("WOAS"),
        "WCM" => Some("WCOM"),
        "WCP" => Some("WCOP"),
        "WPB" => Some("WPUB"),
        "WXX" => Some("WXXX"),
        _ => None,
    }
}

/// Parse a v2.2 PIC frame (different format than APIC).
pub fn parse_v22_picture_frame(data: &[u8]) -> Result<Frame> {
    if data.len() < 5 {
        return Err(MutagenError::ID3("PIC frame too short".into()));
    }

    let encoding = Encoding::from_byte(data[0])?;

    // v2.2 uses 3-char image format instead of MIME
    let img_format = std::str::from_utf8(&data[1..4]).unwrap_or("JPG");
    let mime = match img_format.to_uppercase().as_str() {
        "JPG" => "image/jpeg".to_string(),
        "PNG" => "image/png".to_string(),
        _ => format!("image/{}", img_format.to_lowercase()),
    };

    let pic_type = PictureType::from_byte(data[4]);
    let rest = &data[5..];

    let (desc, consumed) = specs::read_encoded_text(rest, encoding)?;
    let pic_data = rest[consumed..].to_vec();

    Ok(Frame::Picture(PictureFrame {
        id: "APIC".to_string(),
        encoding,
        mime,
        pic_type,
        desc,
        data: pic_data,
    }))
}

// ---- Write functions ----

fn write_text_frame(f: &TextFrame, version: u8) -> Result<Vec<u8>> {
    let encoding = if version >= 4 {
        f.encoding
    } else if f.encoding == Encoding::Utf8 {
        Encoding::Utf16
    } else {
        f.encoding
    };

    let mut data = vec![encoding as u8];
    let joined = f.text.join("\0");
    data.extend_from_slice(&specs::encode_text(&joined, encoding));
    Ok(data)
}

fn write_user_text_frame(f: &UserTextFrame, version: u8) -> Result<Vec<u8>> {
    let encoding = if version >= 4 {
        f.encoding
    } else if f.encoding == Encoding::Utf8 {
        Encoding::Utf16
    } else {
        f.encoding
    };

    let mut data = vec![encoding as u8];
    data.extend_from_slice(&specs::encode_text(&f.desc, encoding));
    let term = specs::null_terminator_size(encoding);
    data.extend_from_slice(&vec![0u8; term]);
    let joined = f.text.join("\0");
    data.extend_from_slice(&specs::encode_text(&joined, encoding));
    Ok(data)
}

fn write_url_frame(f: &UrlFrame) -> Result<Vec<u8>> {
    Ok(f.url.as_bytes().to_vec())
}

fn write_user_url_frame(f: &UserUrlFrame, version: u8) -> Result<Vec<u8>> {
    let encoding = if version >= 4 {
        f.encoding
    } else if f.encoding == Encoding::Utf8 {
        Encoding::Utf16
    } else {
        f.encoding
    };

    let mut data = vec![encoding as u8];
    data.extend_from_slice(&specs::encode_text(&f.desc, encoding));
    let term = specs::null_terminator_size(encoding);
    data.extend_from_slice(&vec![0u8; term]);
    data.extend_from_slice(f.url.as_bytes());
    Ok(data)
}

fn write_comment_frame(f: &CommentFrame, version: u8) -> Result<Vec<u8>> {
    let encoding = if version >= 4 {
        f.encoding
    } else if f.encoding == Encoding::Utf8 {
        Encoding::Utf16
    } else {
        f.encoding
    };

    let mut data = vec![encoding as u8];
    let lang_bytes = f.lang.as_bytes();
    let lang = if lang_bytes.len() >= 3 {
        &lang_bytes[..3]
    } else {
        b"XXX"
    };
    data.extend_from_slice(lang);
    data.extend_from_slice(&specs::encode_text(&f.desc, encoding));
    let term = specs::null_terminator_size(encoding);
    data.extend_from_slice(&vec![0u8; term]);
    data.extend_from_slice(&specs::encode_text(&f.text, encoding));
    Ok(data)
}

fn write_lyrics_frame(f: &LyricsFrame, version: u8) -> Result<Vec<u8>> {
    let encoding = if version >= 4 {
        f.encoding
    } else if f.encoding == Encoding::Utf8 {
        Encoding::Utf16
    } else {
        f.encoding
    };

    let mut data = vec![encoding as u8];
    let lang_bytes = f.lang.as_bytes();
    let lang = if lang_bytes.len() >= 3 {
        &lang_bytes[..3]
    } else {
        b"XXX"
    };
    data.extend_from_slice(lang);
    data.extend_from_slice(&specs::encode_text(&f.desc, encoding));
    let term = specs::null_terminator_size(encoding);
    data.extend_from_slice(&vec![0u8; term]);
    data.extend_from_slice(&specs::encode_text(&f.text, encoding));
    Ok(data)
}

fn write_picture_frame(f: &PictureFrame, version: u8) -> Result<Vec<u8>> {
    let encoding = if version >= 4 {
        f.encoding
    } else if f.encoding == Encoding::Utf8 {
        Encoding::Utf16
    } else {
        f.encoding
    };

    let mut data = vec![encoding as u8];
    data.extend_from_slice(f.mime.as_bytes());
    data.push(0); // null-terminate MIME
    data.push(f.pic_type as u8);
    data.extend_from_slice(&specs::encode_text(&f.desc, encoding));
    let term = specs::null_terminator_size(encoding);
    data.extend_from_slice(&vec![0u8; term]);
    data.extend_from_slice(&f.data);
    Ok(data)
}

fn write_popm_frame(f: &PopularimeterFrame) -> Result<Vec<u8>> {
    let mut data = Vec::new();
    data.extend_from_slice(f.email.as_bytes());
    data.push(0);
    data.push(f.rating);

    // Encode count
    if f.count > 0 {
        let mut count = f.count;
        let mut count_bytes = Vec::new();
        while count > 0 {
            count_bytes.push((count & 0xFF) as u8);
            count >>= 8;
        }
        count_bytes.reverse();
        data.extend_from_slice(&count_bytes);
    }

    Ok(data)
}

fn write_paired_text_frame(f: &PairedTextFrame, version: u8) -> Result<Vec<u8>> {
    let encoding = if version >= 4 {
        f.encoding
    } else if f.encoding == Encoding::Utf8 {
        Encoding::Utf16
    } else {
        f.encoding
    };

    let mut data = vec![encoding as u8];
    let parts: Vec<String> = f
        .people
        .iter()
        .flat_map(|(a, b)| vec![a.clone(), b.clone()])
        .collect();
    let joined = parts.join("\0");
    data.extend_from_slice(&specs::encode_text(&joined, encoding));
    Ok(data)
}
