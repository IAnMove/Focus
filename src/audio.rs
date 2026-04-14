use std::thread;
use std::time::Duration;

#[cfg(all(unix, not(target_os = "macos")))]
use std::io::{self, Write};
#[cfg(not(target_os = "windows"))]
use std::process::Command;

pub fn play_add() {
    spawn_pattern(&[(620, 45)]);
}

pub fn play_click() {
    spawn_pattern(&[(1050, 35)]);
}

pub fn play_complete() {
    spawn_pattern(&[(440, 80), (0, 20), (523, 90), (0, 20), (659, 140)]);
}

pub fn play_notification() {
    spawn_pattern(&[(880, 40), (0, 20), (1046, 60)]);
}

fn spawn_pattern(pattern: &'static [(u32, u64)]) {
    thread::spawn(move || play_pattern(pattern));
}

#[cfg(target_os = "windows")]
fn play_pattern(pattern: &[(u32, u64)]) {
    use windows_sys::Win32::System::Diagnostics::Debug::Beep;

    for (freq, duration_ms) in pattern {
        if *freq == 0 {
            thread::sleep(Duration::from_millis(*duration_ms));
            continue;
        }

        unsafe {
            let _ = Beep(*freq, *duration_ms as u32);
        }
    }
}

#[cfg(not(target_os = "windows"))]
fn play_pattern(pattern: &[(u32, u64)]) {
    for (freq, duration_ms) in pattern {
        if *freq == 0 {
            thread::sleep(Duration::from_millis(*duration_ms));
            continue;
        }

        play_pulse(*duration_ms);
    }
}

#[cfg(target_os = "macos")]
fn play_pulse(duration_ms: u64) {
    let _ = Command::new("osascript").args(["-e", "beep 1"]).status();
    thread::sleep(Duration::from_millis(duration_ms.min(90)));
}

#[cfg(all(unix, not(target_os = "macos")))]
fn play_pulse(duration_ms: u64) {
    if try_linux_sound("canberra-gtk-play", &["-i", "bell"])
        || try_linux_sound("canberra-gtk-play", &["-i", "message-new-instant"])
        || try_linux_sound("paplay", &["/usr/share/sounds/freedesktop/stereo/bell.oga"])
        || try_linux_sound("paplay", &["/usr/share/sounds/freedesktop/stereo/message.oga"])
        || try_linux_sound("aplay", &["/usr/share/sounds/alsa/Front_Center.wav"])
    {
        thread::sleep(Duration::from_millis(duration_ms.min(90)));
        return;
    }

    let mut stderr = io::stderr();
    let _ = stderr.write_all(b"\x07");
    let _ = stderr.flush();
    thread::sleep(Duration::from_millis(duration_ms.min(90)));
}

#[cfg(all(unix, not(target_os = "macos")))]
fn try_linux_sound(command: &str, args: &[&str]) -> bool {
    Command::new(command)
        .args(args)
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}
