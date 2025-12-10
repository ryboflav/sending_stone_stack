#include "audio_stream.h"

#include "esp_log.h"
#include "protocol.h"

static const char *TAG = "audio_stream";

void audio_stream_task(void *pvParameters) {
    (void)pvParameters;

    // TODO: replace with WebSocket client that streams audio and receives TTS.
    while (1) {
        ESP_LOGI(TAG, "Sending fake audio chunk (%s)", MSG_TYPE_AUDIO_CHUNK);
        // Placeholder: send a dummy buffer to edge service.

        ESP_LOGI(TAG, "Pretend receiving TTS data (%s)", MSG_TYPE_TTS_CHUNK);
        // Placeholder: handle playback buffer.

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

