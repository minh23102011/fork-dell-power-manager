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
            let path = entry.path();
            if path.is_dir() {
                directories.push(path);
            }
        }
        directories.sort();
        Ok(directories)
    }
}

#[cfg(test)]
mod tests {
    use std::os::unix::fs::symlink;
    use std::time::{SystemTime, UNIX_EPOCH};

    use super::*;

    #[test]
    fn list_dirs_follows_symlinked_directories() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock before Unix epoch")
            .as_nanos();
        let base =
            std::env::temp_dir().join(format!("powerdeck-sysfs-{}-{unique}", std::process::id()));
        let class_root = base.join("class");
        let device_root = base.join("device");
        let class_link = class_root.join("BAT0");

        fs::create_dir_all(&class_root).expect("create class root");
        fs::create_dir_all(&device_root).expect("create device root");
        symlink(&device_root, &class_link).expect("create sysfs-style symlink");

        let directories = StdSysfsIo
            .list_dirs(&class_root)
            .expect("enumerate class root");

        assert_eq!(directories, vec![class_link]);

        fs::remove_dir_all(&base).expect("remove test tree");
    }
}
