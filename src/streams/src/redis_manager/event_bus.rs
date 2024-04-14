use rustis::{
    client::Client,
    commands::{StreamCommands, StreamEntry},
    Result as RustisResult,
};
use serde::Serialize;
use serde_json::Error as SerdeJsonError;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::Mutex;

pub struct EventBus {
    client: Arc<Mutex<Client>>,
}

impl EventBus {
    pub fn new(client: Arc<Mutex<Client>>) -> Self {
        EventBus { client }
    }

    pub async fn xadd<T: Serialize>(&self, stream: &str, values: T) -> RustisResult<String> {
        let client = self.client.lock().await;
        let serialized_values = serde_json::to_string(&values).map_err(convert_serde_error)?;

        let response = client
            .xadd(
                stream,
                "*",
                [("data", &serialized_values)],
                Default::default(),
            )
            .await?;
        Ok(response)
    }

    pub async fn xread(
        &self,
        stream: &str,
        start_id: &str,
        count: usize,
    ) -> RustisResult<Vec<(String, HashMap<String, String>)>> {
        let client = self.client.lock().await;
        let options = rustis::commands::XReadOptions::default()
            .count(count)
            .block(0);

        // Assuming xread returns Vec<(String, Vec<StreamEntry<V>>)> where V is a type compatible with String
        let entries: Vec<(String, Vec<StreamEntry<String>>)> =
            client.xread(options, vec![stream], vec![start_id]).await?;

        let mut result = Vec::new();
        for (stream_name, stream_entries) in entries {
            for stream_entry in stream_entries {
                let stream_id = stream_entry.stream_id;
                let mut fields_map: HashMap<String, String> = HashMap::new();
                for (field, value) in stream_entry.items.iter() {
                    fields_map.insert(field.clone(), value.clone());
                }
                result.push((stream_id, fields_map)); // Use stream_id if you need to associate each entry with its unique ID within the stream
            }
        }

        Ok(result)
    }

    pub async fn xlen(&self, stream: &str) -> RustisResult<usize> {
        let client = self.client.lock().await;
        let length = client.xlen(stream).await?;
        Ok(length)
    }

    pub async fn xreadgroup(
        &self,
        group: &str,
        consumer: &str,
        streams: &[(&str, &str)], // Each tuple contains a stream key and a last read ID
        count: usize,
        block: u64,
    ) -> RustisResult<Vec<(String, HashMap<String, String>)>> {
        let client = self.client.lock().await;

        // Split streams into separate vectors for keys and IDs
        let (keys, ids): (Vec<&str>, Vec<&str>) = streams.iter().cloned().unzip();

        // Prepare options for the XREADGROUP command
        let options = rustis::commands::XReadGroupOptions::default()
            .count(count)
            .block(block);

        // Execute the XREADGROUP command with separated keys and IDs
        let entries: Vec<(String, Vec<StreamEntry<String>>)> = client
            .xreadgroup(group, consumer, options, keys, ids)
            .await?;

        // Process the entries similarly to xread, converting them to a Vec<(String, HashMap<String, String>)>
        let mut result = Vec::new();
        for (_stream_name, stream_entries) in entries {
            for stream_entry in stream_entries {
                let stream_id = stream_entry.stream_id;
                let mut fields_map: HashMap<String, String> = HashMap::new();
                for (field, value) in stream_entry.items.iter() {
                    fields_map.insert(field.clone(), value.clone());
                }
                result.push((stream_id, fields_map));
            }
        }

        Ok(result)
    }

    pub async fn ensure_consumer_group(
        &self,
        stream_name: &str,
        group_name: &str,
    ) -> RustisResult<()> {
        let client = self.client.lock().await;

        let options = rustis::commands::XGroupCreateOptions::default().mk_stream();

        match client
            .xgroup_create(stream_name, group_name, "$", options)
            .await
        {
            Ok(_) => Ok(()),
            Err(e) => {
                if e.to_string().contains("BUSYGROUP") {
                    // Group already exists, which is fine
                    Ok(())
                } else {
                    Err(e)
                }
            }
        }
    }

    pub async fn listen_for_messages(
        &self,
        streams: &[&str],
        consumer_group: &str,
        consumer_name: &str,
    ) -> RustisResult<()> {
        let client = self.client.lock().await;
        let last_id = ">";

        loop {
            for &stream_key in streams {
                let options = rustis::commands::XReadGroupOptions::default()
                    .block(500)
                    .count(10);

                let entries: Vec<(String, Vec<StreamEntry<String>>)> = client
                    .xreadgroup(
                        consumer_group,
                        consumer_name,
                        options,
                        vec![stream_key],
                        vec![last_id],
                    )
                    .await?;

                for (_, stream_entries) in entries {
                    for stream_entry in stream_entries {
                        match stream_key {
                            "DataFeed" => {
                                // Process DataFeed specific data
                                let symbol = stream_entry.items.get("symbol");
                                let exchange = stream_entry.items.get("exchange");
                                let data_type = stream_entry.items.get("data_type");
                                let response = stream_entry.items.get("response");

                                println!(
                                    "DataFeed message: {:?}, {:?}, {:?}, {:?}",
                                    symbol, exchange, data_type, response
                                );
                            }
                            "ZeroMQ" => {
                                // Process ZeroMQ specific data
                                let event_type = stream_entry.items.get("event_type");
                                let name = stream_entry.items.get("name");
                                let port = stream_entry.items.get("port");

                                println!(
                                    "ZeroMQ message: {:?}, {:?}, {:?}",
                                    event_type, name, port
                                );
                            }
                            "APIManager" => {
                                // Process APIManager specific data
                                let event_type = stream_entry.items.get("event_type");
                                let adapter_id = stream_entry.items.get("adapter_id");
                                let status = stream_entry.items.get("status");

                                println!(
                                    "APIManager message: {:?}, {:?}, {:?}",
                                    event_type, adapter_id, status
                                );
                            }
                            _ => eprintln!("Unknown stream: {}", stream_key),
                        }

                        let message_id = &stream_entry.stream_id.as_str();
                        let message_ids: [&str; 1] = [message_id];

                        let ack_result = client
                            .xack(stream_key, consumer_group, &message_ids[..])
                            .await;
                        if let Err(e) = ack_result {
                            eprintln!("Failed to acknowledge message: {}", e);
                        }
                    }
                }
            }

            tokio::task::yield_now().await;
        }
    }
}

fn convert_serde_error(err: SerdeJsonError) -> rustis::Error {
    rustis::Error::Client(err.to_string()) // Adjust based on the actual variants available in rustis::Error
}
