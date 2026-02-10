use crate::common::error::Result;
use crate::id3::header::BitPaddedInt;
use crate::id3::tags::ID3Tags;

/// Build a complete ID3v2 tag from frames, ready to write to file.
/// Returns the full tag data including header.
pub fn render_tag(tags: &ID3Tags, version: u8) -> Result<Vec<u8>> {
    let frame_data = tags.render(version)?;

    // Add padding (1024 bytes default, like mutagen)
    let padding = 1024usize;
    let total_size = frame_data.len() + padding;

    let mut tag = Vec::with_capacity(10 + total_size);

    // ID3v2 header
    tag.extend_from_slice(b"ID3");
    tag.push(version); // major version
    tag.push(0);       // revision

    // Flags (none set)
    tag.push(0);

    // Size (syncsafe)
    tag.extend_from_slice(&BitPaddedInt::encode(total_size as u32, 4, 7));

    // Frame data
    tag.extend_from_slice(&frame_data);

    // Padding
    tag.extend(std::iter::repeat_n(0u8, padding));

    Ok(tag)
}
