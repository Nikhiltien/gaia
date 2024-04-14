use serde::Deserialize;
use std::collections::HashMap;
use std::fs::File;
use std::io::Read;
use std::path::Path;
use zmq::{poll, Context, Result, Socket, DEALER, POLLIN, PUB, ROUTER, SUB};

const CONFIG_PATH: &str = "etc/zmq_config.yml";

#[derive(Deserialize)]
pub struct SocketConfig {
    pub port: String,
    pub name: String,
    pub socket_type: String,
    pub event_type: String,
    pub identity: Option<String>, // Optional identity for DEALER sockets
    pub topics: Option<Vec<String>>,
}

pub struct ZmqSocketManager {
    context: Context,
    config: Option<Vec<SocketConfig>>,
    subscribers: HashMap<String, Socket>,
}

impl ZmqSocketManager {
    pub fn new() -> Self {
        let mut manager = ZmqSocketManager {
            context: zmq::Context::new(),
            config: None,
            subscribers: HashMap::new(),
        };
        let configs = Self::load_socket_configs(CONFIG_PATH);
        manager.config = Some(configs);
        manager
    }

    fn load_socket_configs<P: AsRef<Path>>(path: P) -> Vec<SocketConfig> {
        let mut file = File::open(path).expect("Unable to open the file");
        let mut contents = String::new();
        file.read_to_string(&mut contents)
            .expect("Unable to read the file");

        serde_yaml::from_str(&contents).expect("Unable to deserialize the YAML")
    }

    pub fn start_subscribers(&mut self) {
        if let Some(configs) = &self.config {
            for config in configs {
                if config.socket_type == "SUB" {
                    let subscriber = self
                        .create_subscriber(config)
                        .expect("Failed to create subscriber");
                    self.subscribers.insert(config.name.clone(), subscriber);
                }
            }
        }
    }

    pub fn create_socket(&self, config: &SocketConfig) -> Result<Socket> {
        let socket = match config.socket_type.as_str() {
            "PUB" => self.context.socket(PUB)?,
            "SUB" => self.context.socket(SUB)?,
            "DEALER" => {
                let dealer = self.context.socket(DEALER)?;
                if let Some(identity) = &config.identity {
                    dealer.set_identity(identity.as_bytes())?;
                }
                dealer
            }
            "ROUTER" => self.context.socket(ROUTER)?,
            _ => return Err(zmq::Error::EINVAL),
        };

        match config.event_type.as_str() {
            "bind" => socket.bind(&format!("tcp://*:{}", config.port))?,
            "connect" => socket.connect(&format!("tcp://localhost:{}", config.port))?,
            _ => return Err(zmq::Error::EINVAL),
        };

        Ok(socket)
    }

    pub fn create_subscriber(&self, config: &SocketConfig) -> Result<Socket> {
        let subscriber = self.context.socket(SUB)?;

        match config.event_type.as_str() {
            "bind" => subscriber.bind(&format!("tcp://*:{}", config.port))?,
            "connect" => subscriber.connect(&format!("tcp://localhost:{}", config.port))?,
            _ => return Err(zmq::Error::EINVAL),
        };

        // Subscribe to specified topics or all if none are specified
        match &config.topics {
            Some(topics) => {
                for topic in topics {
                    subscriber.set_subscribe(topic.as_bytes())?;
                }
            }
            None => {
                subscriber.set_subscribe(b"")?;
            }
        }

        Ok(subscriber)
    }

    pub fn create_publisher(&self, config: &SocketConfig) -> Result<Socket> {
        let publisher = self.context.socket(PUB)?;
        match config.event_type.as_str() {
            "bind" => publisher.bind(&format!("tcp://*:{}", config.port))?,
            "connect" => return Err(zmq::Error::EPROTONOSUPPORT),
            _ => return Err(zmq::Error::EINVAL),
        };
        Ok(publisher)
    }

    pub fn poll_messages(&self) -> Vec<(String, String, Vec<u8>)> {
        let mut messages = Vec::new();
        let mut poll_items: Vec<_> = self
            .subscribers
            .iter()
            .map(|(_, sub)| sub.as_poll_item(POLLIN))
            .collect();

        poll(&mut poll_items, 0).expect("Poll failed"); // Non-blocking poll

        for (index, (name, subscriber)) in self.subscribers.iter().enumerate() {
            if poll_items[index].is_readable() {
                if let Ok(Ok(topic)) = subscriber.recv_string(0) {
                    if let Ok(message_bytes) = subscriber.recv_bytes(0) {
                        messages.push((name.clone(), topic, message_bytes));
                    }
                }
            }
        }

        messages
    }

    // Optionally, a method to listen from a specific subscriber
    pub fn receive_from_subscriber(&self, name: &str) -> Option<(String, Vec<u8>)> {
        if let Some(subscriber) = self.subscribers.get(name) {
            if let Ok(Ok(topic)) = subscriber.recv_string(0) {
                if let Ok(message_bytes) = subscriber.recv_bytes(0) {
                    return Some((topic, message_bytes));
                }
            }
        }
        None
    }
}

#[test]
fn test_socket_creation() {
    let manager = ZmqSocketManager::new();
    let config = SocketConfig {
        port: "5555".to_string(),
        name: "test_socket".to_string(),
        socket_type: "PUB".to_string(),
        event_type: "bind".to_string(),
        identity: None,
        topics: None,
    };

    assert!(manager.create_socket(&config).is_ok());
}

#[test]
fn test_invalid_socket_type() {
    let manager = ZmqSocketManager::new();
    let config = SocketConfig {
        port: "5556".to_string(),
        name: "invalid_socket".to_string(),
        socket_type: "INVALID".to_string(),
        event_type: "bind".to_string(),
        identity: None,
        topics: None,
    };

    assert!(manager.create_socket(&config).is_err());
}

#[test]
fn test_dealer_identity() {
    let manager = ZmqSocketManager::new();
    let config = SocketConfig {
        port: "5557".to_string(),
        name: "dealer_socket".to_string(),
        socket_type: "DEALER".to_string(),
        event_type: "bind".to_string(),
        identity: Some("unique_identity".to_string()),
        topics: None,
    };

    let socket = manager.create_socket(&config).unwrap();
    assert_eq!(socket.get_identity().unwrap(), b"unique_identity");
}

#[test]
fn test_publisher_bind_failure() {
    let manager = ZmqSocketManager::new();
    let config = SocketConfig {
        port: "5559".to_string(),
        name: "pub_socket".to_string(),
        socket_type: "PUB".to_string(),
        event_type: "connect".to_string(),
        identity: None,
        topics: None,
    };

    assert!(manager.create_publisher(&config).is_err());
}

#[test]
fn test_pub_sub_communication() {
    let context = zmq::Context::new();

    // Setup PUB socket
    let publisher = context.socket(zmq::PUB).unwrap();
    publisher.bind("tcp://*:5560").unwrap();

    // Setup SUB socket
    let subscriber = context.socket(zmq::SUB).unwrap();
    subscriber.connect("tcp://localhost:5560").unwrap();
    subscriber.set_subscribe(b"").unwrap(); // Subscribe to all messages

    // Allow some time for connections to establish
    std::thread::sleep(std::time::Duration::from_millis(100));

    // Send a message
    let message = "Hello, world!";
    publisher.send(message, 0).unwrap();

    // Receive the message
    let mut msg = zmq::Message::new();
    subscriber.recv(&mut msg, 0).unwrap();

    // Verify the message was received correctly
    assert_eq!(msg.as_str().unwrap(), message);
}

#[test]
fn test_dealer_router_communication() {
    let context = zmq::Context::new();

    // Setup ROUTER socket
    let router = context.socket(zmq::ROUTER).unwrap();
    router.bind("tcp://*:5561").unwrap();

    // Setup DEALER socket
    let dealer = context.socket(zmq::DEALER).unwrap();
    dealer.set_identity(b"dealer1").unwrap();
    dealer.connect("tcp://localhost:5561").unwrap();

    // Allow some time for connections to establish
    std::thread::sleep(std::time::Duration::from_millis(100));

    // Send a message from DEALER to ROUTER
    let message = "Hello from DEALER!";
    dealer.send(message, 0).unwrap();

    // Receive the message on the ROUTER
    let mut identity = zmq::Message::new();
    let mut msg = zmq::Message::new();
    router.recv(&mut identity, 0).unwrap();
    router.recv(&mut msg, 0).unwrap();

    // Verify the message was received correctly and identity is correct
    assert_eq!(msg.as_str().unwrap(), message);
    assert_eq!(identity.as_str().unwrap(), "dealer1");
}
