use std::fs::{File, OpenOptions};
use std::io::{Read, Write, Seek, SeekFrom};
use crate::common::error::{MutagenError, Result};

/// Insert `count` bytes at `offset` in the file, shifting existing data forward.
pub fn insert_bytes(fobj: &mut File, size: u64, offset: u64) -> Result<()> {
    if size == 0 {
        return Ok(());
    }

    let file_len = fobj.metadata()?.len();
    if offset > file_len {
        return Err(MutagenError::ValueError("offset beyond end of file".into()));
    }

    // Read all data from offset to end
    fobj.seek(SeekFrom::Start(offset))?;
    let mut trailing = Vec::new();
    fobj.read_to_end(&mut trailing)?;

    // Extend the file
    fobj.set_len(file_len + size)?;

    // Write padding (zeros) at offset
    fobj.seek(SeekFrom::Start(offset))?;
    let zeros = vec![0u8; size as usize];
    fobj.write_all(&zeros)?;

    // Write trailing data after the inserted space
    fobj.write_all(&trailing)?;
    fobj.flush()?;

    Ok(())
}

/// Delete `size` bytes at `offset` in the file, shifting data backward.
pub fn delete_bytes(fobj: &mut File, size: u64, offset: u64) -> Result<()> {
    if size == 0 {
        return Ok(());
    }

    let file_len = fobj.metadata()?.len();
    if offset + size > file_len {
        return Err(MutagenError::ValueError("delete beyond end of file".into()));
    }

    // Read all data after the deleted region
    fobj.seek(SeekFrom::Start(offset + size))?;
    let mut trailing = Vec::new();
    fobj.read_to_end(&mut trailing)?;

    // Write trailing data at offset
    fobj.seek(SeekFrom::Start(offset))?;
    fobj.write_all(&trailing)?;
    fobj.flush()?;

    // Truncate file
    fobj.set_len(file_len - size)?;

    Ok(())
}

/// Open a file for read/write access.
pub fn open_rw(path: &str) -> Result<File> {
    Ok(OpenOptions::new()
        .read(true)
        .write(true)
        .open(path)?)
}

/// Open a file for read-only access.
pub fn open_ro(path: &str) -> Result<File> {
    Ok(File::open(path)?)
}
