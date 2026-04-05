use std::thread;
use std::time::Duration;

pub fn play_add() {
    spawn_pattern(&[(620, 45)]);
}

pub fn play_click() {
    spawn_pattern(&[(1050, 35)]);
}

pub fn play_complete() {
    spawn_pattern(&[(440, 80), (0, 20), (523, 90), (0, 20), (659, 140)]);
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
fn play_pattern(_pattern: &[(u32, u64)]) {}
