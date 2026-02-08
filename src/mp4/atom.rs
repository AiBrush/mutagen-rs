use crate::common::error::Result;

/// Container atom names that have children.
#[allow(dead_code)]
const CONTAINER_ATOMS: &[&[u8; 4]] = &[
    b"moov", b"udta", b"trak", b"mdia", b"minf", b"stbl",
    b"meta", b"ilst", b"moof", b"traf", b"edts", b"dinf",
];

/// An MP4 atom (box).
#[derive(Debug, Clone)]
pub struct Atom {
    pub name: [u8; 4],
    pub offset: usize,      // Position of atom start in file
    pub size: usize,         // Total atom size including header
    pub data_offset: usize,  // Start of data (after header)
    pub data_size: usize,    // Size of data
    pub header_size: u8,     // 8 or 16 (extended size)
}

impl Atom {
    pub fn name_str(&self) -> String {
        String::from_utf8_lossy(&self.name).to_string()
    }
}

/// Zero-allocation atom iterator over a byte slice region.
pub struct AtomIter<'a> {
    data: &'a [u8],
    pos: usize,
    end: usize,
}

impl<'a> AtomIter<'a> {
    /// Create a new atom iterator over a region of data.
    #[inline]
    pub fn new(data: &'a [u8], start: usize, end: usize) -> Self {
        AtomIter {
            data,
            pos: start,
            end: end.min(data.len()),
        }
    }

    /// Find the first atom with the given name.
    #[inline]
    pub fn find_name(mut self, name: &[u8; 4]) -> Option<Atom> {
        self.find(|a| &a.name == name)
    }
}

impl<'a> Iterator for AtomIter<'a> {
    type Item = Atom;

    #[inline]
    fn next(&mut self) -> Option<Atom> {
        if self.pos + 8 > self.end || self.pos + 8 > self.data.len() {
            return None;
        }

        let d = self.data;
        let pos = self.pos;

        let size = u32::from_be_bytes([d[pos], d[pos + 1], d[pos + 2], d[pos + 3]]) as usize;
        let name: [u8; 4] = [d[pos + 4], d[pos + 5], d[pos + 6], d[pos + 7]];

        let (atom_size, header_size) = if size == 1 {
            if pos + 16 > self.end || pos + 16 > d.len() {
                return None;
            }
            let ext_size = u64::from_be_bytes([
                d[pos + 8], d[pos + 9], d[pos + 10], d[pos + 11],
                d[pos + 12], d[pos + 13], d[pos + 14], d[pos + 15],
            ]) as usize;
            (ext_size, 16u8)
        } else if size == 0 {
            (self.end - pos, 8u8)
        } else {
            (size, 8u8)
        };

        if atom_size < header_size as usize {
            return None;
        }

        let data_offset = pos + header_size as usize;
        let data_size = (atom_size - header_size as usize)
            .min(self.end.saturating_sub(data_offset))
            .min(d.len().saturating_sub(data_offset));

        let atom = Atom {
            name,
            offset: pos,
            size: atom_size,
            data_offset,
            data_size,
            header_size,
        };

        self.pos += atom_size;
        if self.pos <= pos {
            self.pos = self.end; // Prevent infinite loop
        }

        Some(atom)
    }
}

/// Parse atoms from data within a range (legacy API, now backed by iterator).
pub fn parse_atoms(data: &[u8], start: usize, end: usize) -> Result<Vec<Atom>> {
    Ok(AtomIter::new(data, start, end).collect())
}

/// Find an atom by navigating a path like ["moov", "trak", "mdia"].
/// Uses iterators instead of collecting to Vec for intermediate levels.
pub fn find_atom_path(data: &[u8], path: &[&[u8; 4]]) -> Option<Atom> {
    find_atom_path_in(data, 0, data.len(), path)
}

/// Find an atom by path within a region, using iterators (no Vec allocation).
pub fn find_atom_path_in(data: &[u8], start: usize, end: usize, path: &[&[u8; 4]]) -> Option<Atom> {
    if path.is_empty() {
        return None;
    }

    let found = AtomIter::new(data, start, end).find_name(path[0])?;

    if path.len() == 1 {
        return Some(found);
    }

    find_atom_path_in(data, found.data_offset, found.data_offset + found.data_size, &path[1..])
}

// Keep the old signature for backward compatibility
#[allow(dead_code)]
pub fn find_atom_path_legacy<'a>(data: &[u8], atoms: &'a [Atom], path: &[&[u8; 4]]) -> Option<Atom> {
    if path.is_empty() {
        return None;
    }

    let target = path[0];
    let found = atoms.iter().find(|a| &a.name == target)?;

    if path.len() == 1 {
        return Some(found.clone());
    }

    let children = parse_atoms(data, found.data_offset, found.data_offset + found.data_size).ok()?;
    find_atom_path_legacy(data, &children, &path[1..])
}
