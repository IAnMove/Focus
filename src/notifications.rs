use std::fs::File;
use std::io::BufReader;
use std::path::Path;
use std::process::Command;
use std::thread;
use std::time::Duration;

use rodio::{Decoder, OutputStream, Sink};

use crate::audio;

pub fn send_task_reminder(title: &str, body: &str, sound_enabled: bool, sound_path: &str) {
    send_notification("Task reminder", title, body, sound_enabled, sound_path);
}

pub fn send_due_warning(title: &str, body: &str, sound_enabled: bool, sound_path: &str) {
    send_notification("Due soon", title, body, sound_enabled, sound_path);
}

fn send_notification(kind: &str, title: &str, body: &str, sound_enabled: bool, sound_path: &str) {
    let kind = kind.to_string();
    let title = title.to_string();
    let body = body.to_string();
    let sound_path = sound_path.trim().to_string();
    thread::spawn(move || {
        let _ = dispatch_notification(&kind, &title, &body);
        if sound_enabled {
            if !play_custom_sound(&sound_path) {
                audio::play_notification();
            }
        }
    });
}

#[cfg(target_os = "windows")]
fn dispatch_notification(kind: &str, title: &str, body: &str) -> std::io::Result<()> {
    let title = escape_ps(&(kind.to_string() + " - " + title));
    let body = escape_ps(body);
    let script = format!(
        "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; \
         $n = New-Object System.Windows.Forms.NotifyIcon; \
         $n.Icon = [System.Drawing.SystemIcons]::Information; \
         $n.BalloonTipTitle = '{title}'; \
         $n.BalloonTipText = '{body}'; \
         $n.Visible = $true; \
         $n.ShowBalloonTip(5000); \
         Start-Sleep -Seconds 6; \
         $n.Dispose();"
    );
    Command::new("powershell")
        .args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", &script])
        .spawn()?;
    Ok(())
}

#[cfg(target_os = "macos")]
fn dispatch_notification(kind: &str, title: &str, body: &str) -> std::io::Result<()> {
    let summary = format!("{kind} - {title}");
    Command::new("osascript")
        .args([
            "-e",
            &format!(
                "display notification \"{}\" with title \"focus\" subtitle \"{}\"",
                escape_osascript(body),
                escape_osascript(&summary)
            ),
        ])
        .spawn()?;
    Ok(())
}

#[cfg(all(unix, not(target_os = "macos")))]
fn dispatch_notification(kind: &str, title: &str, body: &str) -> std::io::Result<()> {
    Command::new("notify-send")
        .args([&format!("{kind} - {title}"), body])
        .spawn()?;
    Ok(())
}

fn play_custom_sound(path: &str) -> bool {
    let path = path.trim();
    if path.is_empty() || !Path::new(path).exists() {
        return false;
    }

    let Ok((_stream, handle)) = OutputStream::try_default() else {
        return false;
    };
    let Ok(file) = File::open(path) else {
        return false;
    };
    let Ok(source) = Decoder::new(BufReader::new(file)) else {
        return false;
    };
    let Ok(sink) = Sink::try_new(&handle) else {
        return false;
    };
    sink.append(source);
    sink.sleep_until_end();
    thread::sleep(Duration::from_millis(30));
    true
}

#[cfg(target_os = "windows")]
fn escape_ps(value: &str) -> String {
    value.replace('\'', "''")
}

#[cfg(target_os = "macos")]
fn escape_osascript(value: &str) -> String {
    value.replace('\\', "\\\\").replace('\"', "\\\"")
}
