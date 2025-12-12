let client = null;
let map = null;
const deviceMarkers = {};

function initMap() {
  if (map) return;

  // Initialize Leaflet map
  map = L.map("map").setView([-18.91854, -48.25949], 20);

  // Add a tile layer (OpenStreetMap)
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);

  map.invalidateSize();
  setupInfoToggle();

  // Initial state: ensure topic input is enabled on load
  document.getElementById("mqtt-topic").disabled = false;
}

// Ensure initMap runs only after the DOM (and thus Leaflet) is loaded
document.addEventListener("DOMContentLoaded", function () {
  if (typeof L !== "undefined") {
    initMap();
  } else {
    console.error(
      "Leaflet (L) is not defined. Check script loading order in index.html.",
    );
  }
});

// --- Info Box Toggle Setup ---
function setupInfoToggle() {
  const toggle = document.getElementById("show-info-toggle");
  const mapContainer = document.getElementById("map-container");

  toggle.addEventListener("change", function () {
    if (this.checked) {
      mapContainer.classList.add("show-all-info");
    } else {
      mapContainer.classList.remove("show-all-info");
    }
  });

  if (toggle.checked) {
    mapContainer.classList.add("show-all-info");
  }
}

// --- Utility and MQTT Connection Functions ---

function updateStatus(message) {
  document.getElementById("status-message").innerText = `Status: ${message}`;
}

window.connectToBroker = function () {
  const host = document.getElementById("broker-url").value;
  const port = parseInt(document.getElementById("broker-port").value);
  const topic = document.getElementById("mqtt-topic").value; // READ TOPIC HERE

  // Generate a UNIQUE Client ID for every connection attempt
  const clientId = `web_client_${Math.random().toString(16).substr(2, 8)}`;

  // Disconnect the old client if it exists and is connected
  if (client && client.isConnected()) {
    client.disconnect();
  }

  // ALWAYS create a NEW Paho client instance
  client = new Paho.MQTT.Client(host, port, "/mqtt", clientId);

  // Set callback handlers
  client.onConnectionLost = onConnectionLost;
  client.onMessageArrived = onMessageArrived;

  const options = {
    timeout: 3,
    onSuccess: onConnectSuccess,
    onFailure: onConnectFailure,
    // The topic subscription happens in onConnectSuccess
  };

  updateStatus("Connecting...");
  try {
    client.connect(options);
    // Temporarily disable the topic input field during connection attempt
    document.getElementById("mqtt-topic").disabled = true;
  } catch (error) {
    console.error("Connection attempt failed:", error);
    updateStatus(`Connection Error: ${error.message}`);
    // Re-enable on immediate failure
    document.getElementById("mqtt-topic").disabled = false;
  }
};

window.disconnectFromBroker = function () {
  if (client && client.isConnected()) {
    client.disconnect();
    updateStatus("Disconnected");
    document.getElementById("connect-btn").disabled = false;
    document.getElementById("disconnect-btn").disabled = true;
    document.getElementById("mqtt-topic").disabled = false; // RE-ENABLE TOPIC
  }
};

function onConnectSuccess(context) {
  const topic = document.getElementById("mqtt-topic").value;
  updateStatus("Connected!");
  document.getElementById("connect-btn").disabled = true;
  document.getElementById("disconnect-btn").disabled = false;
  document.getElementById("mqtt-topic").disabled = true; // KEEP TOPIC DISABLED

  client.subscribe(topic); // SUBSCRIBE USING THE INPUT FIELD VALUE
  console.log(`Subscribed to topic: ${topic}`);
}

function onConnectFailure(responseObject) {
  if (responseObject.errorMessage !== "") {
    updateStatus(`Connection Failed: ${responseObject.errorMessage}`);
    document.getElementById("connect-btn").disabled = false;
    document.getElementById("disconnect-btn").disabled = true;
    document.getElementById("mqtt-topic").disabled = false; // RE-ENABLE TOPIC
  }
}

function onConnectionLost(responseObject) {
  if (responseObject.errorCode !== 0) {
    updateStatus(`Connection Lost: ${responseObject.errorMessage}`);
    document.getElementById("connect-btn").disabled = false;
    document.getElementById("disconnect-btn").disabled = true;
    document.getElementById("mqtt-topic").disabled = false; // RE-ENABLE TOPIC
  }
}

function onMessageArrived(message) {
  try {
    const payload = JSON.parse(message.payloadString);
    processDeviceData(payload);
  } catch (e) {
    console.error("Error processing MQTT message:", e);
  }
}

// --- Map Repositioning Logic ---

function fitMapToBounds() {
  const uuids = Object.keys(deviceMarkers);
  if (uuids.length === 0) {
    return;
  }

  const bounds = L.latLngBounds(
    uuids.map((uuid) => deviceMarkers[uuid].getLatLng()),
  );
  map.fitBounds(bounds, { padding: [50, 50] });
}

// --- Device Rendering Logic ---

function processDeviceData(data) {
  const uuid = data.uuid;
  const lat = data.coordinate.latitude;
  const lon = data.coordinate.longitude;

  const battery = Math.min(100, Math.max(0, data.battery)).toFixed(0);
  const temperature = data.temperature.toFixed(1);

  // --- STATUS AND BLINKING LOGIC (3 tiers) ---
  let displayStatusClass = "Normal";
  let shouldBlink = false;

  if (data.status.startsWith("ERROR")) {
    // Red: Error Status (Highest Priority)
    displayStatusClass = "Error";
    shouldBlink = true;
  } else if (battery < 10) {
    // Yellow: Warning (Low Battery)
    displayStatusClass = "Warning";
    shouldBlink = true;
  }

  const blinkClass = shouldBlink ? "blinking" : "";
  // ---------------------------------------------

  // Battery Sizing Logic
  const BASE_FONT_SIZE = 16;
  const MAX_FONT_INCREASE = 14;

  const iconSize = BASE_FONT_SIZE + MAX_FONT_INCREASE * (battery / 100);

  // 1. Create/Update the Marker's appearance using custom HTML
  const markerContent = `
        <div class="device-marker status-${displayStatusClass} ${blinkClass}" style="font-size: ${iconSize}px;">
            <div class="device-icon">●</div>
            <div class="device-info">
                UUID: ${uuid.substring(0, 8)}...<br>
                Temp: ${temperature}°C, Batt: ${battery}%
            </div>
        </div>
    `;

  const customIcon = L.divIcon({
    className: "",
    html: markerContent,
    iconSize: [100, 40],
  });

  let marker = deviceMarkers[uuid];

  if (marker) {
    // Update existing marker
    marker.setLatLng([lat, lon]);
    marker.setIcon(customIcon);
  } else {
    // Create new marker
    marker = L.marker([lat, lon], { icon: customIcon }).addTo(map);
    marker.bindPopup(`
            <b>Device ID:</b> ${uuid}<br>
            <b>Status:</b> ${status}<br>
            <b>Lat/Lon:</b> ${lat}, ${lon}
        `);
    deviceMarkers[uuid] = marker;
  }

  // Conditional Auto-Centering
  const isAutoCenterEnabled =
    document.getElementById("auto-center-toggle").checked;

  if (isAutoCenterEnabled) {
    fitMapToBounds();
  }
}
