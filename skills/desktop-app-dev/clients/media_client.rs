use serde_json::{json, Value};

pub struct MediaClient {
    base_url: String,
    client: reqwest::Client,
    token: Option<String>,
}

impl MediaClient {
    pub fn new(base_url: impl Into<String>, token: Option<String>) -> Self {
        Self {
            base_url: base_url.into(),
            client: reqwest::Client::new(),
            token,
        }
    }

    pub async fn enqueue(
        &self,
        kind: &str,
        payload: Value,
        dedupe_key: Option<&str>,
    ) -> Result<Value, reqwest::Error> {
        let body = json!({"kind": kind, "payload": payload, "dedupe_key": dedupe_key});
        let mut request = self
            .client
            .post(format!("{}/tasks", self.base_url))
            .json(&body);
        if let Some(token) = &self.token {
            request = request.bearer_auth(token);
        }
        request
            .send()
            .await?
            .json()
            .await
    }

    pub async fn task(&self, id: i64) -> Result<Value, reqwest::Error> {
        let mut request = self.client.get(format!("{}/tasks/{}", self.base_url, id));
        if let Some(token) = &self.token {
            request = request.bearer_auth(token);
        }
        request
            .send()
            .await?
            .json()
            .await
    }

    pub async fn deps_progress(&self) -> Result<Value, reqwest::Error> {
        let mut request = self
            .client
            .get(format!("{}/deps/progress", self.base_url));
        if let Some(token) = &self.token {
            request = request.bearer_auth(token);
        }
        request
            .send()
            .await?
            .json()
            .await
    }

    pub async fn deps_status(&self) -> Result<Value, reqwest::Error> {
        let mut request = self
            .client
            .get(format!("{}/deps/status", self.base_url));
        if let Some(token) = &self.token {
            request = request.bearer_auth(token);
        }
        request
            .send()
            .await?
            .json()
            .await
    }

    pub async fn install_deps(&self) -> Result<Value, reqwest::Error> {
        let mut request = self
            .client
            .post(format!("{}/deps/install", self.base_url));
        if let Some(token) = &self.token {
            request = request.bearer_auth(token);
        }
        request
            .send()
            .await?
            .json()
            .await
    }
}
