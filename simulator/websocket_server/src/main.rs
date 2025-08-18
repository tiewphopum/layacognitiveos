use tokio::net::{TcpListener, TcpStream};
use tokio_tungstenite::accept_async;
use futures_util::{stream::StreamExt, sink::SinkExt};
use tokio::time::{interval, Duration};

async fn handle_connection(stream: TcpStream) {
    let ws_stream = accept_async(stream).await.expect("Failed to accept");
    let (mut write, mut read) = ws_stream.split();

    println!("Client connected");

    // สร้าง interval สำหรับส่งข้อมูลแบบ stream
    let mut interval = interval(Duration::from_secs(1));
    let mut counter = 0;

    // สร้าง future สำหรับรับข้อความจาก client
    let receive_task = async {
        while let Some(msg) = read.next().await {
            let msg = msg.expect("Failed to read message");
            if msg.is_text() {
                println!("Received: {}", msg.to_text().unwrap());
            }
        }
    };

    // สร้าง future สำหรับส่งข้อความแบบ stream ไปหา client
    let send_task = async {
        loop {
            interval.tick().await;
            counter += 1;
            let message = format!("Stream message #{}", counter);
            if let Err(e) = write.send(message.into()).await {
                eprintln!("Error sending message: {}", e);
                break;
            }
        }
    };

    // รันทั้งสอง task พร้อมกัน
    tokio::select! {
        _ = receive_task => println!("Receive task finished"),
        _ = send_task => println!("Send task finished"),
    }

    println!("Client disconnected");
}

#[tokio::main]
async fn main() {
    let listener = TcpListener::bind("127.0.0.1:8080").await.expect("Failed to bind");
    println!("WebSocket server is running on ws://localhost:8080");

    while let Ok((stream, _)) = listener.accept().await {
        tokio::spawn(handle_connection(stream));
    }
}