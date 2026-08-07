use std::fs;
use std::io;
use std::path::{Path, PathBuf};

pub trait SysfsIo: Send + Sync {
    fn read_text(&self, path: &Path) -> io::Result<Option<String>>;
    fn write_text(&self, path: &Path, value: &str) -> io::Result<()>;
    fn exists(&self, path: &Path) -> bool;
    fn list_dirs(&self, root: &Path) -> io::Result<Vec<PathBuf>>;
}

#[derive(Debug, Default, Clone, Copy)]
pub struct StdSysfsIo;

impl SysfsIo for StdSysfsIo {
    fn read_text(&self, path: &Path) -> io::Result<Option<String>> {
        match fs::read_to_string(path) {
            Ok(value) => {
                let trimmed = value.trim();
                if trimmed.is_empty() {
                    Ok(None)
                } else {
                    Ok(Some(trimmed.to_owned()))
                }
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
            Err(error) => Err(error),
        }
    }

    fn write_text(&self, path: &Path, value: &str) -> io::Result<()> {
        fs::write(path, value)
    }

    fn exists(&self, path: &Path) -> bool {
        path.exists()
    }

    fn list_dirs(&self, root: &Path) -> io::Result<Vec<PathBuf>> {
        let mut directories = Vec::new();
        for entry in fs::read_dir(root)? {
            let entry = entry?;
            if entry.file_type()?.is_dir() {
                directories.push(entry.path());
            }
        }
        directories.sort();
        Ok(directories)
    }
}
