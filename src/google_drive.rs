use std::fmt;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use reqwest::StatusCode;
use reqwest::blocking::Client;
use serde::Deserialize;

use crate::model::SyncFile;

const AUTH_URL: &str = "https://accounts.google.com/o/oauth2/v2/auth";
const TOKEN_URL: &str = "https://oauth2.googleapis.com/token";
const DRIVE_DOWNLOAD_URL: &str = "https://www.googleapis.com/drive/v3/files";
const DRIVE_UPLOAD_URL: &str = "https://www.googleapis.com/upload/drive/v3/files";
const DRIVE_SCOPE: &str = "https://www.googleapis.com/auth/drive";

#[derive(Debug, Clone)]
pub struct GoogleDriveConfig {
    pub client_id: String,
    pub file_id: String,
    pub refresh_token: String,
}

#[derive(Debug, Clone)]
pub struct GoogleDriveSession {
    pub refresh_token: String,
    pub access_token: String,
}

#[derive(Debug)]
pub enum GoogleDriveError {
    Config(&'static str),
    AuthRequired,
    BrowserLaunch(String),
    CallbackTimeout,
    Callback(String),
    Http(String),
    AccessDenied,
    NotFound(String),
    InvalidPayload(String),
}

impl fmt::Display for GoogleDriveError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Config(message) => write!(f, "{message}"),
            Self::AuthRequired => write!(
                f,
                "Google Drive needs a one-time browser authorization. Run Sync now to sign in."
            ),
            Self::BrowserLaunch(message) => write!(f, "{message}"),
            Self::CallbackTimeout => write!(f, "Timed out waiting for the Google OAuth callback."),
            Self::Callback(message) => write!(f, "{message}"),
            Self::Http(message) => write!(f, "{message}"),
            Self::AccessDenied => write!(f, "Google authorization was denied or cancelled."),
            Self::NotFound(message) => write!(f, "{message}"),
            Self::InvalidPayload(message) => write!(f, "{message}"),
        }
    }
}

#[derive(Debug, Deserialize)]
struct TokenResponse {
    access_token: String,
    #[serde(default)]
    refresh_token: Option<String>,
}

pub fn authorize(config: &GoogleDriveConfig, interactive: bool) -> Result<GoogleDriveSession, GoogleDriveError> {
    if config.client_id.trim().is_empty() {
        return Err(GoogleDriveError::Config(
            "Google Drive sync needs a desktop client_id.",
        ));
    }
    if config.file_id.trim().is_empty() {
        return Err(GoogleDriveError::Config(
            "Google Drive sync needs a shared file_id.",
        ));
    }

    let client = http_client()?;
    let refresh_token = if config.refresh_token.trim().is_empty() {
        if !interactive {
            return Err(GoogleDriveError::AuthRequired);
        }
        interactive_authorization(&client, &config.client_id)?
    } else {
        config.refresh_token.trim().to_string()
    };

    let access_token = refresh_access_token(&client, &config.client_id, &refresh_token)?;
    Ok(GoogleDriveSession {
        refresh_token,
        access_token,
    })
}

pub fn download_sync_file(config: &GoogleDriveConfig, access_token: &str) -> Result<SyncFile, GoogleDriveError> {
    let client = http_client()?;
    let url = format!("{}/{}?alt=media", DRIVE_DOWNLOAD_URL, urlencoding::encode(config.file_id.trim()));
    let response = client
        .get(url)
        .bearer_auth(access_token)
        .send()
        .map_err(|error| GoogleDriveError::Http(format!("Google Drive download failed: {error}")))?;

    if response.status() == StatusCode::NOT_FOUND {
        return Err(GoogleDriveError::NotFound(format!(
            "Google Drive file_id {} was not found. Create or upload focus-sync.json first, then reuse that file_id.",
            config.file_id.trim()
        )));
    }

    if response.status() == StatusCode::UNAUTHORIZED || response.status() == StatusCode::FORBIDDEN {
        return Err(GoogleDriveError::Http(
            "Google Drive rejected the token. Re-run Sync now to authorize the desktop app again.".to_string(),
        ));
    }

    let response = response
        .error_for_status()
        .map_err(|error| GoogleDriveError::Http(format!("Google Drive download failed: {error}")))?;

    let body = response
        .text()
        .map_err(|error| GoogleDriveError::Http(format!("Google Drive download failed: {error}")))?;

    serde_json::from_str::<SyncFile>(&body)
        .map(|file| file.normalized())
        .map_err(|error| GoogleDriveError::InvalidPayload(format!(
            "Google Drive returned an invalid focus-sync.json: {error}"
        )))
}

pub fn upload_sync_file(config: &GoogleDriveConfig, access_token: &str, sync_file: &SyncFile) -> Result<(), GoogleDriveError> {
    let client = http_client()?;
    let url = format!(
        "{}/{}?uploadType=media",
        DRIVE_UPLOAD_URL,
        urlencoding::encode(config.file_id.trim())
    );
    let payload = serde_json::to_string_pretty(&sync_file.clone().normalized())
        .map_err(|error| GoogleDriveError::InvalidPayload(format!("Could not serialize sync payload: {error}")))?;

    let response = client
        .patch(url)
        .bearer_auth(access_token)
        .header("Content-Type", "application/json; charset=utf-8")
        .body(payload)
        .send()
        .map_err(|error| GoogleDriveError::Http(format!("Google Drive upload failed: {error}")))?;

    if response.status() == StatusCode::NOT_FOUND {
        return Err(GoogleDriveError::NotFound(format!(
            "Google Drive file_id {} was not found. Create or upload focus-sync.json first, then reuse that file_id.",
            config.file_id.trim()
        )));
    }

    response
        .error_for_status()
        .map_err(|error| GoogleDriveError::Http(format!("Google Drive upload failed: {error}")))?;

    Ok(())
}

fn interactive_authorization(client: &Client, client_id: &str) -> Result<String, GoogleDriveError> {
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|error| GoogleDriveError::Callback(format!("Could not start OAuth callback listener: {error}")))?;
    listener
        .set_nonblocking(false)
        .map_err(|error| GoogleDriveError::Callback(format!("Could not configure OAuth callback listener: {error}")))?;
    listener
        .set_ttl(64)
        .map_err(|error| GoogleDriveError::Callback(format!("Could not configure OAuth callback listener: {error}")))?;
    let port = listener
        .local_addr()
        .map_err(|error| GoogleDriveError::Callback(format!("Could not read OAuth callback port: {error}")))?
        .port();
    let redirect_uri = format!("http://127.0.0.1:{port}/oauth/google/callback");
    let state = oauth_state();
    let auth_url = build_auth_url(client_id, &redirect_uri, &state);

    open_system_browser(&auth_url)?;
    listener
        .set_nonblocking(true)
        .map_err(|error| GoogleDriveError::Callback(format!("Could not configure OAuth callback listener: {error}")))?;

    let code = wait_for_callback(&listener, &state)?;
    let token = exchange_authorization_code(client, client_id, &redirect_uri, &code)?;
    token.refresh_token.ok_or_else(|| {
        GoogleDriveError::Callback(
            "Google OAuth completed but no refresh_token was returned. Remove this app from your Google account permissions and try again."
                .to_string(),
        )
    })
}

fn build_auth_url(client_id: &str, redirect_uri: &str, state: &str) -> String {
    format!(
        "{AUTH_URL}?response_type=code&client_id={}&redirect_uri={}&scope={}&access_type=offline&prompt=consent&state={}",
        urlencoding::encode(client_id),
        urlencoding::encode(redirect_uri),
        urlencoding::encode(DRIVE_SCOPE),
        urlencoding::encode(state),
    )
}

fn refresh_access_token(client: &Client, client_id: &str, refresh_token: &str) -> Result<String, GoogleDriveError> {
    let token: TokenResponse = client
        .post(TOKEN_URL)
        .form(&[
            ("client_id", client_id),
            ("grant_type", "refresh_token"),
            ("refresh_token", refresh_token),
        ])
        .send()
        .map_err(|error| GoogleDriveError::Http(format!("Google OAuth token refresh failed: {error}")))?
        .error_for_status()
        .map_err(|error| GoogleDriveError::Http(format!("Google OAuth token refresh failed: {error}")))?
        .json()
        .map_err(|error| GoogleDriveError::Http(format!("Google OAuth token refresh failed: {error}")))?;

    Ok(token.access_token)
}

fn exchange_authorization_code(
    client: &Client,
    client_id: &str,
    redirect_uri: &str,
    code: &str,
) -> Result<TokenResponse, GoogleDriveError> {
    client
        .post(TOKEN_URL)
        .form(&[
            ("client_id", client_id),
            ("grant_type", "authorization_code"),
            ("code", code),
            ("redirect_uri", redirect_uri),
        ])
        .send()
        .map_err(|error| GoogleDriveError::Http(format!("Google OAuth code exchange failed: {error}")))?
        .error_for_status()
        .map_err(|error| GoogleDriveError::Http(format!("Google OAuth code exchange failed: {error}")))?
        .json()
        .map_err(|error| GoogleDriveError::Http(format!("Google OAuth code exchange failed: {error}")))
}

fn wait_for_callback(listener: &TcpListener, expected_state: &str) -> Result<String, GoogleDriveError> {
    let started = std::time::Instant::now();
    while started.elapsed() < Duration::from_secs(180) {
        match listener.accept() {
            Ok((mut stream, _addr)) => {
                let mut request = [0_u8; 4096];
                let size = stream
                    .read(&mut request)
                    .map_err(|error| GoogleDriveError::Callback(format!("Could not read OAuth callback: {error}")))?;
                let request = String::from_utf8_lossy(&request[..size]);
                let first_line = request.lines().next().unwrap_or_default();
                let path = first_line
                    .split_whitespace()
                    .nth(1)
                    .ok_or_else(|| GoogleDriveError::Callback("OAuth callback request was malformed.".to_string()))?;
                let (code, state, oauth_error) = parse_callback_query(path);
                let response_body = if oauth_error.is_some() {
                    "Google authorization was cancelled. You can close this tab and return to focus."
                } else {
                    "Google authorization finished. You can close this tab and return to focus."
                };
                let _ = write!(
                    stream,
                    "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n<html><body><p>{response_body}</p></body></html>"
                );

                if oauth_error.is_some() {
                    return Err(GoogleDriveError::AccessDenied);
                }

                let Some(state) = state else {
                    return Err(GoogleDriveError::Callback(
                        "Google OAuth callback did not include state.".to_string(),
                    ));
                };
                if state != expected_state {
                    return Err(GoogleDriveError::Callback(
                        "Google OAuth callback state did not match the request.".to_string(),
                    ));
                }
                let Some(code) = code else {
                    return Err(GoogleDriveError::Callback(
                        "Google OAuth callback did not include an authorization code.".to_string(),
                    ));
                };
                return Ok(code);
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(150));
            }
            Err(error) => {
                return Err(GoogleDriveError::Callback(format!(
                    "Could not receive OAuth callback: {error}"
                )));
            }
        }
    }

    Err(GoogleDriveError::CallbackTimeout)
}

fn parse_callback_query(path: &str) -> (Option<String>, Option<String>, Option<String>) {
    let query = path.split_once('?').map(|(_, query)| query).unwrap_or("");
    let mut code = None;
    let mut state = None;
    let mut error = None;

    for part in query.split('&').filter(|part| !part.is_empty()) {
        let (key, value) = part.split_once('=').unwrap_or((part, ""));
        let value = urlencoding::decode(value)
            .map(|decoded| decoded.into_owned())
            .unwrap_or_else(|_| value.to_string());
        match key {
            "code" => code = Some(value),
            "state" => state = Some(value),
            "error" => error = Some(value),
            _ => {}
        }
    }

    (code, state, error)
}

fn open_system_browser(url: &str) -> Result<(), GoogleDriveError> {
    #[cfg(target_os = "windows")]
    let status = std::process::Command::new("rundll32.exe")
        .arg("url.dll,FileProtocolHandler")
        .arg(url)
        .status();

    #[cfg(target_os = "macos")]
    let status = std::process::Command::new("open").arg(url).status();

    #[cfg(all(unix, not(target_os = "macos")))]
    let status = std::process::Command::new("xdg-open").arg(url).status();

    status
        .map_err(|error| {
            GoogleDriveError::BrowserLaunch(format!(
                "Could not open the browser for Google OAuth: {error}. Open this URL manually: {url}"
            ))
        })
        .and_then(|status| {
            if status.success() {
                Ok(())
            } else {
                Err(GoogleDriveError::BrowserLaunch(format!(
                    "Could not open the browser for Google OAuth. Open this URL manually: {url}"
                )))
            }
        })
}

fn oauth_state() -> String {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    format!("focus-{}-{nonce}", std::process::id())
}

fn http_client() -> Result<Client, GoogleDriveError> {
    Client::builder()
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|error| GoogleDriveError::Http(format!("Could not create HTTP client: {error}")))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_auth_url_contains_expected_desktop_flow_fields() {
        let url = build_auth_url(
            "desktop.apps.googleusercontent.com",
            "http://127.0.0.1:8123/oauth/google/callback",
            "state-1",
        );

        assert!(url.contains("response_type=code"));
        assert!(url.contains("access_type=offline"));
        assert!(url.contains("prompt=consent"));
        assert!(url.contains("desktop.apps.googleusercontent.com"));
    }

    #[test]
    fn parse_callback_query_handles_code_and_errors() {
        let (code, state, error) =
            parse_callback_query("/oauth/google/callback?code=abc123&state=s1");
        assert_eq!(code.as_deref(), Some("abc123"));
        assert_eq!(state.as_deref(), Some("s1"));
        assert!(error.is_none());

        let (code, state, error) =
            parse_callback_query("/oauth/google/callback?error=access_denied&state=s2");
        assert!(code.is_none());
        assert_eq!(state.as_deref(), Some("s2"));
        assert_eq!(error.as_deref(), Some("access_denied"));
    }
}
