use rustis::{
    client::{Client, IntoConfig},
    Result as RustisResult,
};
use std::sync::Arc;
use tokio::sync::Mutex;

#[derive(Clone)]
pub struct RedisConfig {
    pub host: String,
    pub port: u16,
    pub password: Option<String>,
    pub db: Option<i64>,
    pub use_ssl: bool,
}

impl RedisConfig {
    pub fn to_redis_url(&self) -> String {
        let credentials = self
            .password
            .as_ref()
            .map(|p| format!(":{}@", p))
            .unwrap_or_default();
        let mut url = format!(
            "redis{}://{}{}:{}",
            if self.use_ssl { "s" } else { "" },
            credentials,
            self.host,
            self.port
        );
        if let Some(ref db) = self.db {
            url.push_str(&format!("/{}", db));
        }
        url
    }
}

pub struct RedisConnectionManager {
    regular_client: Arc<Mutex<Client>>,
    pub_sub_client: Arc<Mutex<Client>>,
}

impl RedisConnectionManager {
    // Initializes two separate multiplexed clients based on RedisConfig
    pub async fn new(config: RedisConfig) -> RustisResult<Self> {
        let redis_url = config.to_redis_url();
        let client_config = redis_url.into_config()?;

        if let Some(password) = config.password {}

        let regular_client = Client::connect(client_config.clone()).await?;
        let pub_sub_client = Client::connect(client_config).await?;

        Ok(RedisConnectionManager {
            regular_client: Arc::new(Mutex::new(regular_client)),
            pub_sub_client: Arc::new(Mutex::new(pub_sub_client)),
        })
    }

    // Provide access to the regular client
    pub fn get_regular_client(&self) -> Arc<Mutex<Client>> {
        self.regular_client.clone()
    }

    // Provide access to the pub/sub client
    pub fn get_pub_sub_client(&self) -> Arc<Mutex<Client>> {
        self.pub_sub_client.clone()
    }
}
